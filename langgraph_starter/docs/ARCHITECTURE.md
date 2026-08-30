# Architecture — Autonomous QA Agent with Discovery, Design Intelligence & Self-Healing

## What This System Does

A multi-stage LangGraph agent that:
1. Receives an API request — `agent`, `base_url`, `scenarios[]`
2. Loads agent prompt from `agents.yaml` based on the agent name
3. Crawls the site — navigates to `base_url`, extracts all routes, forms, and links from the DOM
4. Generates concrete test intents — maps each scenario to real URLs and form fields discovered by the crawler
5. Executes each intent — drives a real Chromium browser via Playwright, guided by the agent's prompt
6. Visually verifies each step — Gemini vision checks screenshots against expected outcomes
7. Self-heals broken locators — when a selector fails, LLM re-resolves it from the live DOM
8. Returns a structured report per scenario + aggregated summary

---

## Input

### API Request
```
POST /qa/run
{
  "agent": "QA_agent_1",
  "base_url": "https://yourapp.com",
  "scenarios": [
    "test that login works with valid credentials",
    "test that login fails with wrong password and shows error"
  ]
}
```

### agents.yaml
```yaml
QA_agent_1:
  prompt: >
    You are a thorough QA engineer. Focus on functional correctness —
    verify that every form submission, button click, and page navigation
    produces the expected outcome.

QA_agent_2:
  prompt: >
    You are a security-focused QA engineer. Look for exposed sensitive data,
    missing auth redirects, and inputs that accept unexpected values.
```

- `agent` name is validated against `agents.yaml` on every request
- `agent_prompt` is injected into the planner — different agents plan steps differently
- To add a new agent: add an entry to `agents.yaml`, no code changes needed

---

## System Diagram

```
POST /qa/run
  { agent, base_url, scenarios[] }
         │
         ▼
┌─────────────────────┐
│  agents.yaml lookup │  agent name → agent_prompt
│                     │  Unknown agent → 400 error
└──────────┬──────────┘
           │  agent_prompt injected into state
           ▼
┌─────────────────┐
│  CRAWLER node   │  Navigates base_url
│                 │  Reads DOM → LLM extracts routes, forms, links
│  browser_tools  │  Also pulls <a href> links via Playwright directly
└────────┬────────┘
         │  discovered_routes[]
         ▼
┌──────────────────────┐
│ INTENT_GENERATOR node│  For each scenario:
│                      │  scenario + discovered_routes → LLM
│                      │  Output: concrete test_intent per scenario
└──────────┬───────────┘
           │  test_intents[]
           ▼
┌──────────────────────┐
│  LOAD_NEXT_INTENT    │◀─────────────────────────────────────┐
│  (orchestrator)      │  Picks next test_intent              │
│                      │  Resets per-scenario state           │
└──────────┬───────────┘                                      │
           │                                                  │
           ▼                                                  │
┌──────────────────────┐                                      │
│   PLANNER node       │  agent_prompt + test_intent → LLM   │
│                      │  Output: ordered steps[]             │
│  ← agent_prompt      │  Prompt behavior varies by agent     │
│    shapes how steps  │                                      │
│    are planned       │                                      │
└──────────┬───────────┘                                      │
           │                                                  │
           ▼                                                  │
┌─────────────────┐                                           │
│  EXECUTOR node  │◀──────────────────────────────────┐      │
│                 │  DOM → LLM → CSS selector → action │      │
│  browser_tools  │  navigate / click / fill           │      │
└────────┬────────┘                                    │      │
         │                                             │      │
    success?                                           │      │
    ┌─────┴──────┐                                     │      │
   YES     NO (locator_failed)                         │      │
    │             │                                    │      │
    ▼             ▼                                    │      │
┌────────┐  ┌──────────────┐                          │      │
│VERIFIER│  │ HEALER node  │  DOM + failed selector   │      │
│  node  │  │              │  → LLM → new selector    │      │
│        │  │  healed?     │  → retry action           │      │
│ Gemini │  │  ┌───┴───┐   │                          │      │
│ vision │  │ YES      NO  │                          │      │
└───┬────┘  └──┼───────┼───┘                          │      │
    │          │       │                               │      │
    │          └───────┼───────────────────────────────┘      │
    │                  │ (mark step FAILED)                    │
    ▼                                                         │
more steps?       ┌──────────────┐                            │
 ┌────┴────┐      │ REPORTER node│                            │
YES        NO ──► │              │                            │
 │               │ per-scenario │                            │
 └──────────────► │ report       │                            │
                  └──────┬───────┘                            │
                         ▼                                    │
                ┌─────────────────────┐                       │
                │  COLLECT_REPORT     │                       │
                │  (orchestrator)     │                       │
                │  Saves to           │                       │
                │  all_reports[]      │                       │
                └──────────┬──────────┘                       │
                           │                                  │
                    more intents?                             │
                    ┌───────┴───────┐                         │
                   YES              NO                        │
                    └───────────────┘─────────────────────────┘
                                    │
                                   END
                    { agent, total_scenarios, reports[] }
```

---

## Node Responsibilities

| Node | Input | Output | Does NOT do |
|------|-------|--------|-------------|
| agents.yaml lookup | agent name | agent_prompt | run tests |
| Crawler | base_url | discovered_routes[] | generate test steps |
| Intent Generator | scenarios[] + discovered_routes[] | test_intents[] | execute anything |
| Load Next Intent | test_intents[], current_intent_index | test_intent + reset state | plan or execute |
| Planner | agent_prompt + test_intent | steps[] | execute anything |
| Executor | one step + DOM | screenshot, dom_snapshot, result | reason about results |
| Verifier | screenshot + expected_outcome | pass/fail + design_issues | fix anything |
| Healer | failed step + DOM | new_locator or failure | execute the retry |
| Reporter | step_results[] | per-scenario report | aggregate across scenarios |
| Collect Report | report + all_reports[] | updated all_reports[], incremented index | run tests |

---

## State Schema

```python
class QAState(TypedDict):
    # Input (from API request + agents.yaml)
    agent: str
    agent_prompt: str           # loaded from agents.yaml by agent name
    base_url: str
    scenarios: list[str]

    # Crawler output
    discovered_routes: list[dict]   # [{url, description, forms, links}]

    # Intent generator output
    test_intents: list[str]         # one concrete intent per scenario
    current_intent_index: int

    # Per-scenario execution (reset each intent)
    test_intent: str
    steps: list
    current_step_index: int
    screenshots: list[str]
    dom_snapshots: list[str]
    step_results: list
    heal_attempts: int
    _current_result: dict

    # Aggregated output
    all_reports: list[dict]
    report: dict

    messages: list
```

---

## LangGraph Edge Map

```
START
  └─► crawler
        └─► intent_generator
              └─► load_next_intent ◀──────────────────────────┐
                    └─► planner  (uses agent_prompt)          │
                          └─► executor                        │
                                ├─► (success) verifier        │
                                │     ├─► (more steps) executor   ← loop
                                │     └─► (done) reporter     │
                                └─► (locator_failed) healer   │
                                      ├─► (healed) verifier   │
                                      └─► (failed) reporter   │
                                                  │           │
                                            collect_report    │
                                                  ├─► (more intents) ──┘
                                                  └─► END
```

---

## File Map

```
langgraph_starter/
├── agents.yaml                    agent registry — name → prompt (add agents here)
├── test_config.yaml               reference example only (not used at runtime)
├── langgraph_starter/
│   ├── connection.py              get_llm(), ask_with_image()
│   ├── state.py                   QAState TypedDict
│   ├── run_qa.py                  FastAPI app — POST /qa/run
│   ├── graph.py                   all nodes + edges wired together
│   ├── tools/
│   │   ├── browser_tools.py       navigate, click, fill, screenshot, get_dom, get_page
│   │   └── visual_tools.py        check_visual_design(screenshot) → issues[]
│   └── nodes/
│       ├── crawler.py             navigate base_url → discovered_routes[]
│       ├── intent_generator.py    scenarios + routes → test_intents[]
│       ├── orchestrator.py        load_next_intent + collect_report (loop control)
│       ├── planner.py             agent_prompt + test_intent → steps[]
│       ├── executor.py            step → browser action (DOM → LLM → selector)
│       ├── verifier.py            screenshot → pass/fail + design issues
│       ├── healer.py              failed selector → healed selector
│       └── reporter.py            step_results → per-scenario report
└── docs/
    ├── ARCHITECTURE.md            (this file)
    ├── IMPLEMENTATION_PLAN.md     step-by-step build order
    └── DEMO_SCRIPT.md             what to show judges
```

---

## Adding a New Agent

Only `agents.yaml` needs to change:

```yaml
QA_agent_3:
  prompt: >
    You are a performance-focused QA engineer. Check that pages load
    within acceptable time and flag any slow or unresponsive elements.
```

Then call it immediately:
```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{"agent": "QA_agent_3", "base_url": "https://yourapp.com", "scenarios": [...]}'
```

---

## Better Approach Notes

| Concern | Current | Better |
|---------|---------|--------|
| Site discovery | Single-page DOM + 10 internal links | BFS crawl with `max_depth` config, or parse `/sitemap.xml` |
| Auth-gated routes | Not handled | Crawler logs in first using credentials from request, then crawls |
| Agent config | Prompt only | Add `max_heal_attempts`, `crawl_depth`, `llm_model` per agent in yaml |
| Concurrency | Sequential scenarios | Run scenarios in parallel with `asyncio.gather` |
