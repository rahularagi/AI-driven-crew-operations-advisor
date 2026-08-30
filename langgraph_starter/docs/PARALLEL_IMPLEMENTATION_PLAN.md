# Implementation Plan — Parallel Request Support

Enable multiple `/qa/run` requests to execute concurrently without interfering with each other.

---

## Problem Summary

| Issue | Root Cause |
|---|---|
| Single shared browser | `browser_tools.py` uses module-level globals `_pw`, `_browser`, `_page` |
| Blocking graph execution | `graph.invoke()` is synchronous — blocks the FastAPI thread |
| Sync Playwright | `sync_playwright` cannot run concurrently in async context |
| Sync LLM calls | `invoke_with_system` and `ask_with_image` are blocking |

---

## Target Architecture

Each request gets its own isolated browser session. All I/O (browser + LLM) is async. FastAPI handles requests concurrently via `async def` endpoints.

```
Request 1 ──▶ async graph.ainvoke ──▶ Browser Session A (isolated)
Request 2 ──▶ async graph.ainvoke ──▶ Browser Session B (isolated)
Request 3 ──▶ async graph.ainvoke ──▶ Browser Session C (isolated)
```

---

## Step 1 — `tools/browser_tools.py`

**What changes:** Replace module-level globals with a `BrowserSession` class. Each request creates and owns its own instance.

- Replace `sync_playwright` → `async_playwright`
- All functions (`navigate`, `click`, `fill`, `get_dom`, `take_screenshot`, `close_browser`) become `async def` methods on `BrowserSession`
- No more global `_page` — session is passed through state

**New interface:**
```python
class BrowserSession:
    async def start(self)
    async def close(self)
    async def navigate(self, url) -> dict
    async def click(self, selector) -> dict
    async def fill(self, selector, value) -> dict
    async def get_dom(self) -> str
    async def take_screenshot(self, step_index) -> str
```

---

## Step 2 — `state.py`

**What changes:** Add `browser_session` field to `QAState` so every node can access the request-scoped browser.

```python
browser_session: Any   # BrowserSession instance, injected at request start
```

---

## Step 3 — `connection.py`

**What changes:** Replace sync LangChain calls with async equivalents.

- `invoke_with_system` → `async def ainvoke_with_system`
- `ask_with_image` → `async def aask_with_image`
- Use `llm.ainvoke(messages)` instead of `llm.invoke(messages)`

---

## Step 4 — All nodes → `async def`

Every node function must become `async def` and `await` all I/O calls.

| File | Change |
|---|---|
| `nodes/scenario_router.py` | `async def route_scenarios`, `await ainvoke_with_system` |
| `nodes/crawler.py` | `async def crawl`, `await session.navigate`, `await session.get_dom` |
| `nodes/intent_generator.py` | `async def generate_intents`, `await ainvoke_with_system` |
| `nodes/planner.py` | `async def plan_steps`, `await ainvoke_with_system` |
| `nodes/executor.py` | `async def execute_step`, `await session.click/fill/navigate` |
| `nodes/verifier.py` | `async def verify_step`, `await aask_with_image` |
| `nodes/healer.py` | `async def heal_locator`, `await ainvoke_with_system` |
| `nodes/reporter.py` | `async def build_report` |
| `nodes/orchestrator.py` | `async def` for all three functions (no I/O, trivial change) |

---

## Step 5 — `graph.py`

**What changes:** None to the graph structure. LangGraph automatically handles async nodes when using `ainvoke`.

---

## Step 6 — `run_qa.py`

**What changes:**
- `run_qa` endpoint becomes `async def`
- Create `BrowserSession`, inject into `initial_state`
- Use `await graph.ainvoke(...)` instead of `graph.invoke(...)`
- `await session.close()` in a `finally` block to guarantee cleanup

```python
@app.post("/qa/run")
async def run_qa(request: QARequest):
    session = BrowserSession()
    await session.start()
    try:
        result = await graph.ainvoke(initial_state(..., browser_session=session))
    finally:
        await session.close()
    return {...}
```

---

## Step 7 — `initial_state` in `state.py`

**What changes:** Accept and store `browser_session` in initial state.

---

## Build Order

| Step | File | What it enables |
|---|---|---|
| 1 | `tools/browser_tools.py` | Async, session-scoped browser |
| 2 | `state.py` | `browser_session` field in state |
| 3 | `connection.py` | Async LLM calls |
| 4 | `nodes/scenario_router.py` | Async scenario classification |
| 5 | `nodes/crawler.py` | Async crawl + login |
| 6 | `nodes/intent_generator.py` | Async intent generation |
| 7 | `nodes/planner.py` | Async step planning |
| 8 | `nodes/executor.py` | Async browser actions |
| 9 | `nodes/verifier.py` | Async screenshot verification |
| 10 | `nodes/healer.py` | Async locator healing |
| 11 | `nodes/reporter.py` | Async report building |
| 12 | `nodes/orchestrator.py` | Async orchestration |
| 13 | `run_qa.py` | Async endpoint + session lifecycle |

---

## What Does NOT Change

| Component | Reason |
|---|---|
| `graph.py` | LangGraph handles async nodes automatically |
| `agents.yaml` | No change — static config |
| `state.py` fields (except new `browser_session`) | All existing fields stay |
| Node logic | Only the `def` → `async def` and `await` additions |
| Prompts | All LLM prompts stay identical |

---

## Testing Parallel Execution

After implementation, fire two requests simultaneously:

```bash
# Terminal 1
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{"agent": "QA_agent_1", "base_url": "https://the-internet.herokuapp.com/login", "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"}, "scenarios": ["test login"]}' &

# Terminal 2
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{"agent": "QA_agent_2", "base_url": "https://the-internet.herokuapp.com/login", "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"}, "scenarios": ["test login edge cases"]}' &

wait
```

Both should complete independently with separate reports and no interference.
