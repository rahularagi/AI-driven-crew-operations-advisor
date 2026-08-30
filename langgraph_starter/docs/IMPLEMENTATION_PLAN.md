# Implementation Plan — Autonomous QA Agent

Build in this exact order.

---

## Step 0 — Dependencies

```bash
pip install --prefer-binary -e .
pip install pyyaml
playwright install chromium
```

---

## Step 1 — Input config

**File:** `test_config.yaml` (project root, next to `langgraph_starter/`)

```yaml
base_url: https://yourapp.com
scenarios:
  - "test that login works with valid credentials"
  - "test that login fails with wrong password and shows error"
  - "test that forgot password form submits successfully"
```

This is the only file you edit to change what gets tested.

---

## Step 2 — State

**File:** `langgraph_starter/state.py`

Added fields vs original:
- `base_url`, `scenarios` — from yaml
- `discovered_routes` — crawler output
- `test_intents`, `current_intent_index` — intent generator output
- `all_reports` — aggregated across all scenarios
- `scenario_queue`, `active_scenario`, `scope`, `relevant_pages` — scenario routing

---

## Step 3 — Browser tools

**File:** `langgraph_starter/tools/browser_tools.py`

`get_page()` must be exported — crawler uses it directly for login and post-navigation URL detection.

---

## Step 4 — Scenario Router node

**File:** `langgraph_starter/nodes/scenario_router.py`

- Runs once at the start before any browser interaction
- Sends all plain English scenarios to LLM → classifies each automatically:
  - `single_page` — test one specific page only (e.g. "test login")
  - `feature` — test a feature spanning a few pages (e.g. "send and read email")
  - `full_crawl` — test entire app (e.g. "test the complete app")
- For `feature` scope: asks LLM which URL paths are relevant → sets `relevant_pages`
- Pops first scenario as `active_scenario`, puts rest in `scenario_queue`
- User writes plain English — no scope flags needed

---

## Step 5 — Crawler node

**File:** `langgraph_starter/nodes/crawler.py`

- Navigates to `base_url`
- Login behavior depends on scope:
  - `single_page` — skips login entirely (page itself is being tested)
  - `feature` / `full_crawl` — logs in using credentials before crawling
- Reads DOM, sends to LLM to extract routes, forms, links
- Link filtering based on scope:
  - `single_page` — no links added to queue
  - `feature` — only links in `relevant_pages` added
  - `full_crawl` — all internal links added
- Output: `discovered_routes[]`, updated `pages_to_visit`

---

## Step 6 — Intent generator node

**File:** `langgraph_starter/nodes/intent_generator.py`

- Sends page structure + `active_scenario` to LLM
- Prompt strictness depends on scope:
  - `single_page` / `feature` → strict: "generate ONLY for this scenario"
  - `full_crawl` → free: agent role drives expansion
- Output: `test_intents[]` for current page

---

## Step 7 — Orchestrator nodes

**File:** `langgraph_starter/nodes/orchestrator.py`

Three functions:
- `load_next_intent` — picks `test_intents[current_intent_index]`, resets per-scenario state
- `collect_report` — appends completed report to `all_reports`, increments index, tags report with `page`, `scenario`, `scope`
- `load_next_scenario` — pops next scenario from `scenario_queue`, resets all page + intent state

---

## Step 8 — Planner, Executor, Verifier, Healer, Reporter

Unchanged from original implementation.

---

## Step 9 — Graph

**File:** `langgraph_starter/graph.py`

Full edge map:
```
scenario_router → crawler → intent_generator
intent_generator → load_next_intent (has intents) or load_next_page or load_next_scenario or END
load_next_intent → planner → executor
executor → verifier (success) or healer (locator_failed)
verifier → executor (more steps) or reporter (done)
healer → verifier (healed) or reporter (failed)
reporter → collect_report
collect_report → load_next_intent (more intents)
              → load_next_page (more pages)
              → load_next_scenario (more scenarios)
              → END
load_next_page → crawler
load_next_scenario → crawler
```

---

## Step 10 — Entry point (Streaming)

**File:** `langgraph_starter/run_qa.py`

- FastAPI `POST /qa/run` endpoint
- Uses `StreamingResponse` with `text/event-stream` media type
- Uses `graph.stream(stream_mode="updates")` instead of `graph.invoke()`
- Streams each report as an SSE event the moment it completes — no waiting for all intents
- Final event sends `{"type": "done", "total_scenarios": N}`
- Browser closed in `finally` block after stream ends

**Stream output format:**
```
data: {"type": "report", "index": 1, "report": {"overall": "PASS", ...}}

data: {"type": "report", "index": 2, "report": {"overall": "FAIL", ...}}

data: {"type": "done", "total_scenarios": 13}
```

**curl to consume stream:**
```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  --no-buffer \
  -d '{"agent": "QA_agent_1", "base_url": "...", "scenarios": ["test login"]}'
```

---

## Build Order Summary

| Step | File | What it enables |
|------|------|-----------------|
| 0 | — | Dependencies installed |
| 1 | test_config.yaml | Human-readable test input |
| 2 | state.py | Extended shared data contract + scope fields |
| 3 | tools/browser_tools.py | Browser automation primitives |
| 4 | nodes/scenario_router.py | LLM auto-classifies scope from plain English |
| 5 | nodes/crawler.py | Scope-aware crawl + conditional login |
| 6 | nodes/intent_generator.py | Strict vs free intent generation by scope |
| 7 | nodes/orchestrator.py | Multi-scenario + multi-page loop control |
| 8 | nodes/planner.py | Intent → ordered browser steps |
| 9 | nodes/executor.py | Steps → Playwright browser actions |
| 10 | nodes/verifier.py | Screenshot → pass/fail + design issues |
| 11 | nodes/healer.py | Broken locator → self-healed |
| 12 | nodes/reporter.py | Per-intent report builder |
| 13 | graph.py | Full graph wired with scope-aware routing |
| 14 | run_qa.py | Streaming SSE endpoint |
