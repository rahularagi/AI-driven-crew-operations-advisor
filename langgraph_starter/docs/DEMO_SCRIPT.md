# Demo Script — What to Show Judges

Total time: 6–7 minutes. Five acts.

---

## Act 1 — The Problem (30 seconds, no code)

Say this:
> "Traditional automated tests have two problems. First, they break when a developer renames a button — the selector drifts and someone has to manually fix it. Second, writing them requires knowing the app upfront — every URL, every form field, every selector. This agent solves both."

Show: a screenshot of a red CI pipeline with failing tests after a UI refactor.

---

## Act 2 — The Input: API Request + Agent Config (45 seconds)

**Show `agents.yaml`:**
```yaml
QA_agent_1:
  prompt: >
    You are a thorough QA engineer. Focus on functional correctness —
    verify that every form submission, button click, and page navigation
    produces the expected outcome. Flag any error messages, broken flows,
    or missing UI elements as failures.
```

Say:
> "An agent is just a named prompt. You define its behavior here — functional QA, security QA, performance QA — whatever you need. No code changes to add a new agent."

**Show the API request:**
```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_1",
    "base_url": "https://the-internet.herokuapp.com",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": [
      "test login",
      "after login send email and read email",
      "test the complete app"
    ]
  }'
```

Say:
> "This is the entire input. A URL, credentials, and plain-English scenarios written exactly how a human would think about them. No selectors. No scope flags. No page knowledge. The agent figures out the rest."

---

## Act 3 — Scenario Router + Crawler + Intent Generation (90 seconds)

**Start the server and fire the request:**
```bash
uvicorn langgraph_starter.run_qa:app
# in another terminal:
curl -X POST http://localhost:8000/qa/run ...
```

**First thing that runs is the scenario router. Narrate:**
> "Before touching the browser, the agent reads all three scenarios and classifies them automatically."

**Show the scenario router output in logs:**
```json
[
  {"description": "test login", "scope": "single_page", "target": "login"},
  {"description": "after login send email and read email", "scope": "feature", "target": "email", "relevant_pages": ["/inbox", "/compose", "/sent"]},
  {"description": "test the complete app", "scope": "full_crawl", "target": null}
]
```

Say:
> "Nobody told it these scopes. It inferred them from plain English. 'test login' means one page. 'send and read email' means a feature — it even figured out which pages that feature lives on. 'test the complete app' means crawl everything."

**Now the crawler runs for the first scenario. Narrate:**
> "Playwright opens a real Chromium browser, navigates to the URL, and logs in using the credentials. Then the crawler reads the DOM and extracts the page structure."

Say:
> "Important distinction — Playwright is just the hands. It opens pages and clicks buttons. The crawler is the brain — it decides where to go, reads what's there, and decides what to do next based on the scope."

**Show the crawler output in logs — `discovered_routes`:**
```json
[
  {
    "url": "https://the-internet.herokuapp.com/login",
    "description": "Login page",
    "forms": [{"id": "login", "fields": ["username", "password"]}],
    "links": ["/secure", "/forgot-password"]
  }
]
```

Say:
> "Scope is single_page — so even though it found links to /secure and /forgot-password, it ignores them. It only tests this one page."

**Show the generated intent:**
```
"Navigate to https://the-internet.herokuapp.com/login,
 fill the username field with 'tomsmith',
 fill the password field with 'SuperSecretPassword!',
 click the Login button,
 verify the secure area heading appears."
```

Say:
> "The agent wrote that test intent itself — from a one-line scenario and a DOM crawl. When the login scenario finishes, it automatically moves to the email scenario, then the full crawl — all from one API call."

---

## Act 4 — Execution + Normal Pass (60 seconds)

**While executor runs, narrate:**
> "For each step, the executor reads the live DOM, asks the LLM for a CSS selector, and drives the browser with Playwright. A screenshot is taken after every action."

**Show the report for scenario 1:**
```
============================================================
QA REPORT — PASS  [QA_agent_1]
============================================================
Scenario: test that login works with valid credentials
Steps: 4  Passed: 4  Failed: 0  Healed: 0
============================================================
```

**Show one screenshot** from `screenshots/` — point out it's a real Chromium browser.

**Show the report for scenario 2 (wrong password):**
```
============================================================
QA REPORT — PASS  [QA_agent_1]
============================================================
Scenario: test that login fails with wrong password and shows error
Steps: 3  Passed: 3  Failed: 0  Healed: 0
============================================================
```

Say:
> "Two scenarios, two independent test runs, one API call."

---

## Act 5 — Self-Healing (90 seconds — the money shot)

**Setup before demo — simulate selector drift in `executor.py`:**
```python
# DEMO BREAK: simulate a renamed element
if "login" in description.lower() or "submit" in description.lower():
    return "#this-selector-does-not-exist"
```

**Fire the same request again.**

**Narrate while it runs:**
> "I've simulated what happens when a developer renames an element. The selector the agent resolved is now wrong."
> "Watch — executor fails to find the element..."
> "...healer fires. It sends the current DOM and the failed selector to Gemini: 'where did this go?'"
> "Gemini reads the visible structure and finds it."

**Show the healed report:**
```
============================================================
QA REPORT — PASS  [QA_agent_1]
============================================================
Steps: 4  Passed: 4  Failed: 0  Healed: 1

Healing Events:
  Step 2: #this-selector-does-not-exist → button[type=submit]
============================================================
```

Say:
> "The test passed. The report tells you exactly what drifted and what it was healed to — your team knows what changed in the UI without touching git blame."

---

## Act 6 — Design Intelligence (45 seconds)

Say:
> "Every step also runs a visual check. Gemini looks at the screenshot — not the DOM — and flags issues a selector-based test would never catch."

**Show a screenshot with a known visual issue, then:**
```python
from langgraph_starter.tools.visual_tools import check_visual_design
print(check_visual_design("screenshots/step_02.png"))
```

**Output:**
```json
[
  {"type": "low_contrast", "description": "Submit button text is white on white — unreadable", "severity": "high"},
  {"type": "clipped_text", "description": "Error message cut off at right edge", "severity": "medium"}
]
```

Say:
> "The DOM still has the button. The selector still resolves. The click still works. But a real user can't see it. Gemini catches it because it sees what the user sees."

---

## Full Flow Summary (show this slide or draw it)

```
POST /qa/run  { agent, base_url, credentials, scenarios[] }
      ↓
agents.yaml      →  agent_prompt loaded
      ↓
Scenario Router  →  classifies each scenario → single_page / feature / full_crawl
      ↓                (LLM infers scope from plain English, no user input needed)
Crawler          →  Playwright opens browser, logs in, reads DOM
                     single_page → no links followed
                     feature     → only relevant_pages followed
                     full_crawl  → all internal links followed
      ↓
Intent Gen       →  scenario + page structure → concrete test intents
                     single_page/feature → strict (only what user asked)
                     full_crawl          → free expansion by agent role
      ↓
Planner          →  agent_prompt + intent → ordered browser steps
      ↓
Executor         →  DOM → LLM → CSS selector → Playwright action
      ↓ (locator fails?)
Healer           →  DOM + failed selector → LLM → new selector → retry
      ↓
Verifier         →  screenshot → Gemini vision → pass/fail + design issues
      ↓
Reporter         →  per-scenario report
      ↓
(repeat for each scenario in queue)
      ↓
Response         →  { agent, total_scenarios, reports[] }
```

### Playwright vs Crawler — one slide

```
Playwright  =  the hands
               opens pages, clicks buttons, fills forms, takes screenshots
               has no intelligence — just executes commands

Crawler     =  the brain
               decides where to go, reads what's on the page,
               decides which links to follow based on scope
               uses Playwright as its tool
```

---

## Closing Line

> "You give it a URL, a list of what to test, and an agent name. It discovers the app, writes the test intents, executes them in a real browser, fixes its own broken selectors, and checks the UI visually. That's the difference between a test suite that needs constant maintenance and one that maintains itself."

---

## Backup if something fails live

- Show `screenshots/` — real browser screenshots prove it ran
- Show `agents.yaml` — explain the agent prompt concept without running code
- Show `discovered_routes` JSON from logs — proves the crawler worked
- Run visual check standalone: `check_visual_design("screenshots/step_00.png")` — always works independently
