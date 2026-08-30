# Startup & Test API Reference

---

## 1. First Time Setup

```bash
cd /Users/rahularagi/PycharmProjects/voicebot/langgraph_starter

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
pip install fastapi uvicorn

# Install Playwright browser
playwright install chromium

# Create .env from example
cp .env.example .env
# Open .env and set: GOOGLE_API_KEY=your-actual-key-here
```

---

## 2. Start Server

```bash
cd /Users/rahularagi/PycharmProjects/voicebot/langgraph_starter
source .venv/bin/activate
uvicorn langgraph_starter.run_qa:app --reload --port 8000
```

Server is ready when you see:
```
Application startup complete.
```

---

## 3. Available Agents

| Agent | Behavior |
|---|---|
| `QA_agent_1` | Exhaustive — all cases, negative first, happy path last |
| `QA_agent_2` | Edge cases only — long inputs, special chars, SQL injection |
| `QA_agent_3` | Negative only — wrong credentials, empty fields, unauthorized access |
| `QA_agent_4` | Positive only — happy path, valid inputs, expected flows |
| `QA_agent_5` | Security — SQL injection, XSS, unprotected routes, exposed data |

---

## 4. Test Scenarios

### Scenario 1 — Single Page: Test Login Only

Tests only the login page. No other pages crawled.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_1",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["test login"]
  }'
```

---

### Scenario 2 — Single Page: Negative Tests Only on Login

Only wrong credentials, empty fields, invalid inputs.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_3",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["test login with invalid credentials"]
  }'
```

---

### Scenario 3 — Single Page: Security Test on Login

SQL injection, XSS payloads, brute force patterns.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_5",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["test login security vulnerabilities"]
  }'
```

---

### Scenario 4 — Single Page: Edge Cases on Login

Extremely long inputs, special characters, whitespace-only values.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_2",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["test login edge cases"]
  }'
```

---

### Scenario 5 — Feature: Login then test Secure Area

Logs in first, then tests the secure area page.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_1",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["after login test the secure area page"]
  }'
```

---

### Scenario 6 — Feature: Login then Logout flow

Tests the full login → secure area → logout flow.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_4",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["login and then logout"]
  }'
```

---

### Scenario 7 — Multiple Scenarios Together

Runs all three scopes sequentially in one API call.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_1",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": [
      "test login",
      "after login test the secure area page",
      "test the complete app"
    ]
  }'
```

---

### Scenario 8 — Full Crawl: Test Entire App

Crawls all pages discovered from base URL and tests everything.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_1",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["test the complete app including all pages"]
  }'
```

---

### Scenario 9 — Full Crawl: Security Audit of Entire App

Security scan across all discovered pages.

```bash
curl -X POST http://localhost:8000/qa/run \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "QA_agent_5",
    "base_url": "https://the-internet.herokuapp.com/login",
    "credentials": {"email": "tomsmith", "password": "SuperSecretPassword!"},
    "scenarios": ["security audit the entire app"]
  }'
```

---

## 5. Check Screenshots

Screenshots are saved after every step:

```bash
ls -la /Users/rahularagi/PycharmProjects/voicebot/langgraph_starter/screenshots/
open /Users/rahularagi/PycharmProjects/voicebot/langgraph_starter/screenshots/
```

---

## 6. Health Check

```bash
curl http://localhost:8000/docs
```

Opens the FastAPI auto-generated docs in browser with all available endpoints.

---

## 7. Understanding the Response

```json
{
  "agent": "QA_agent_1",
  "total_scenarios": 13,
  "reports": [
    {
      "test_intent": "Go to /login, enter empty username...",
      "total_steps": 5,
      "passed": 5,
      "failed": 0,
      "healed": 0,
      "overall": "PASS",
      "page": "https://the-internet.herokuapp.com/login",
      "scenario": "test login",
      "scope": "single_page",
      "healing_events": [],
      "design_issues": [
        {"type": "low_contrast", "description": "...", "severity": "high"}
      ],
      "step_details": [...]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `total_scenarios` | Total test intents executed |
| `overall` | `PASS` or `FAIL` for that intent |
| `healed` | Steps that failed but self-healed |
| `design_issues` | Visual UI issues found via screenshot analysis |
| `scope` | `single_page` / `feature` / `full_crawl` — auto-detected |
