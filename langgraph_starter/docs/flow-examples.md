# LangGraph QA Agent — How It Works

---

## The Core Idea

This system is a robot that tests websites automatically. It has two parts working together:

- **The browser** — actually clicks buttons, fills forms, takes screenshots. This is pure code (Playwright). No LLM involved.
- **The brain (LLM)** — reads HTML and screenshots and makes decisions a human QA engineer would make.

**LangGraph** is the workflow manager. It decides which node runs next based on what happened in the previous node.

---

## Node Responsibilities

### 1. `scenario_router` — Understand what to test

You give it plain English. LLM converts it into a technical plan.

```
YOU SAY:    "test the checkout flow"
LLM SAYS:   This is a "feature" test. Relevant pages: /cart, /checkout, /payment
CODE DOES:  Stores those pages so crawler knows where to go next.
```

Without LLM here, the system can't convert human intent into actionable URLs.

---

### 2. `crawler` — Explore a page

Two LLM calls happen here.

**Call A — Login** (only if credentials are provided and scope isn't single_page):
```
PROBLEM:   The system needs to log in but doesn't know the CSS selectors.
LLM READS: Login page HTML.
LLM SAYS:  Fill input#email, fill input#password, click button[type=submit].
CODE DOES: Executes those exact browser actions.
```

**Call B — Extract page structure**:
```
CODE DOES: Gets the full raw HTML of the current page.
LLM READS: HTML
LLM SAYS:  This page has a login form with fields: username, password.
           Internal links: /dashboard, /profile.
CODE DOES: Stores this summary. Intent generator uses it next.
```

---

### 3. `intent_generator` — Decide what to test

LLM acts like a QA engineer thinking through what could go wrong on this page.

```
LLM KNOWS:  Page has a login form. Credentials available. Scenario: "test login".
LLM THINKS: What test cases make sense?
LLM OUTPUT: [
  "Fill empty username and password, expect error about username",
  "Fill valid username and wrong password, expect error about password",
  "Fill valid credentials, expect redirect to dashboard"
]
CODE DOES:  Stores the list. Nothing else.
```

---

### 4. `planner` — Convert one test case into browser steps

LLM takes one test case sentence and breaks it into exact executable actions.

```
TEST CASE:   "Fill empty username and password, expect error about username"
LLM OUTPUT:  [
  {action: navigate, target: /login},
  {action: fill,     target: "username field",  value: ""},
  {action: fill,     target: "password field",  value: ""},
  {action: click,    target: "login button"},
  {action: assert,   target: "error message",   expected: "error indicating username invalid"}
]
CODE DOES:  Stores these steps. Nothing else.
```

---

### 5. `executor` — Run one browser step

The steps say things like `"username field"` — not a CSS selector. The browser needs something like `input#username`. LLM translates.

```
LLM INPUT:  "username field" + current page HTML
LLM OUTPUT: "input#username"
CODE DOES:  Uses that selector to click/fill/navigate via Playwright.
            Takes a screenshot after the action.
```

If the selector fails (element not found):
```
CODE SETS: status = "locator_failed"
LANGGRAPH:  Routes to healer node
```

---

### 6. `verifier` — Did the step work?

Code cannot look at a screenshot and judge whether something passed. That requires visual understanding. LLM does it.

```
LLM SEES:   Screenshot of the current page state.
LLM KNOWS:  Expected outcome was "error indicating username invalid".
LLM LOOKS:  Is there any error message about username visible on screen?
LLM SAYS:   PASS or FAIL
CODE DOES:  Records the result and advances to the next step.
```

---

### 7. `healer` — Fix a broken selector

When executor fails because an element wasn't found, healer tries to recover.

```
LLM KNOWS:  We were looking for "login button". Selector ".login-btn" failed.
LLM READS:  Current page HTML.
LLM OUTPUT: "button[type='submit'].btn-primary"  ← new guess
CODE DOES:  Retries the action with the new selector.

If it works  → goes to verifier (step marked as healed)
If it fails  → after 2 attempts, goes to reporter as error
```

---

### 8. `reporter` and `collect_report` — Pure code, no LLM

`reporter` assembles the test results: step statuses, screenshots, healed selectors, design issues.

`collect_report` decides what to do next:
- More test cases on this page → pick next test case → planner
- More pages to visit → crawler
- More scenarios → crawler with new scenario
- Nothing left → done

---

## How LangGraph Controls the Flow

LangGraph uses routing functions after certain nodes. These are just Python if/else that inspect the state:

```python
# After executor:
if step failed due to locator and heal_attempts < 2:
    → healer
else:
    → verifier

# After verifier:
if all steps done:
    → reporter
else:
    → executor (next step)

# After healer:
if healed successfully:
    → verifier
else:
    → reporter (mark as error)

# After collect_report:
if more test cases on this page  → load_next_intent → planner
if more pages to crawl           → load_next_page → crawler
if more scenarios queued         → load_next_scenario → crawler
else                             → END
```

The **state** (`QAState`) is shared memory. Every node reads from it and writes back. Nodes don't call each other — they communicate through state.

---

## One-Line Summary Per Node

| Node | LLM task | Code task |
|---|---|---|
| `scenario_router` | Classify scope, list relevant URLs | Store plan in state |
| `crawler` | Read DOM → login steps + page structure | Open browser, execute login, store summary |
| `intent_generator` | Generate test cases from page structure | Store test case list |
| `planner` | Convert one test case → step sequence | Store step list |
| `executor` | Translate element description → CSS selector | Run click/fill/navigate, take screenshot |
| `verifier` | Look at screenshot → PASS or FAIL | Record result, advance step counter |
| `healer` | Find new CSS selector when old one broke | Retry browser action with new selector |
| `reporter` | None | Build structured test report |
| `collect_report` | None | Decide loop direction |

---

## Flow Diagram

```
scenario_router ──→ crawler ──→ intent_generator
                        ↑              │
                        │              ▼
              load_next_page    load_next_intent
              load_next_scenario      │
                        │             ▼
                        │           planner
                        │             │
                        │             ▼
                        │    ┌──── executor ────┐
                        │    │                  │
                        │    ▼ (locator failed) │
                        │  healer               │
                        │    │ (healed)         │ (step done)
                        │    └────→ verifier ←──┘
                        │               │
                        │               ▼ (all steps done)
                        │           reporter
                        │               │
                        └── collect_report ──→ END
```

---

## Flow Example 1 — Single Page Login Test

**Input:** `scenarios = ["test the login page"]`

```
scenario_router
  LLM: scope = single_page, no extra pages needed

crawler (/login)
  No login (scope=single_page — we want to test the login form itself)
  LLM reads HTML → page has username field, password field, login button

intent_generator
  LLM generates 3 test cases:
    1. Empty username → expect error about username
    2. Wrong password → expect error about password
    3. Valid credentials → expect redirect to dashboard

──── LOOP FOR EACH TEST CASE ────

planner (test case 1)
  LLM breaks it into 5 steps: navigate, fill empty, fill empty, click, assert error

executor (step 1: navigate)
  Code: browser navigates to /login ✓

executor (step 2: fill username)
  LLM: "username field" → "input#username"
  Code: fills with "" ✓

executor (step 3: fill password) → executor (step 4: click login) → executor (step 5: assert)
  LLM: "error message" → ".flash.error"
  Code: asserts element visible ✓
  Screenshot taken

verifier
  LLM looks at screenshot → sees "Your username is invalid!" → PASS

reporter → PASS

collect_report → more test cases → load_next_intent

[test case 2: wrong password → PASS]
[test case 3: valid credentials → PASS]

collect_report → no more intents, no more pages → END
```

**Result:** 3 test cases all PASS.

---

## Flow Example 2 — Self-Healing on Broken Selector

**Input:** `scenarios = ["test the checkout flow"]`

```
scenario_router
  LLM: scope = feature, pages = [/cart, /checkout, /payment]

crawler (/cart) → login first (feature scope, credentials present)
  LLM reads login HTML → generates login steps → code executes → logged in

intent_generator (/cart)
  LLM generates: ["Change quantity to 0, expect cart updates", "Click checkout, expect /checkout"]

planner (test case 1)
  LLM generates steps including "click quantity decrement button"

executor (click quantity decrement)
  LLM: "quantity decrement button" → ".qty-minus"
  Code: click(".qty-minus") → FAILS — element not found

  LangGraph routes to healer (heal_attempts=0 < 2)

healer
  LLM reads current DOM → finds: "button[data-action='decrement']"
  Code: click("button[data-action='decrement']") → SUCCESS
  result.healed = True

verifier
  LLM looks at screenshot → quantity changed → PASS

reporter → PASS (healed)

collect_report → more pages → crawler (/checkout) → ...

END
```

**Result:** 1 healed step, all tests pass.

---

## Flow Example 3 — Full Crawl with a Genuine Failure

**Input:** `scenarios = ["test everything"]`

```
scenario_router
  LLM: scope = full_crawl — follow all internal links

crawler (/) → login → on /dashboard
  LLM extracts links: [/users, /reports, /settings]
  pages_to_visit = [/users, /reports, /settings]

intent_generator (/dashboard)
  LLM: ["Verify stats load", "Click Reports link, expect /reports"]

[both test cases PASS]

collect_report → more pages → crawler (/users)

intent_generator (/users)
  LLM: ["Verify user list loads", "Click Create User button"]

planner (test case 2: click Create User)
  LLM step: click "Create User button"

executor
  LLM: "Create User button" → ".btn-create-user"
  Code: click(".btn-create-user") → FAILS

healer (attempt 1)
  LLM: new guess → "#new-user-btn"
  Code: click("#new-user-btn") → FAILS

healer (attempt 2)
  LLM: new guess → "a[href='/users/new']"
  Code: click("a[href='/users/new']") → FAILS

  heal_attempts = 2 → LangGraph routes to reporter (no more healing)

reporter → FAIL

collect_report → remaining pages → crawler (/reports) → PASS, crawler (/settings) → PASS

END
```

**Final result:**
```
/dashboard  → 2 tests → PASS
/users      → 2 tests → 1 FAIL (Create User button unreachable after 2 heal attempts)
/reports    → 3 tests → PASS
/settings   → 2 tests → PASS
```
