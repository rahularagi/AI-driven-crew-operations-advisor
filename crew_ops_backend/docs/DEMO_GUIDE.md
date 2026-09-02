# CrewOps — Hackathon Demo Guide

> End-to-end walkthrough. No internet required after first-time setup.
> Estimated demo time: **12–15 minutes**.

---

## Reality Check — What's Real vs Mock

| Layer | Status | Notes |
|-------|--------|-------|
| PostgreSQL | ✅ Real DB | Docker, runs locally |
| Flight schedule | ✅ Real DB | 15 seeded legs with crew assigned |
| Crew profiles | ✅ Real DB | 25 crew members |
| FTL state | ✅ Real DB | All 25 crew with realistic counters |
| Flight status polling | ✅ Mock sequences | `mock_observer.py` — scripted poll-by-poll responses |
| Disruption pipeline | ✅ Fully real | Event bus → handler → DB → proposals |
| Roster planner | ✅ Fully real | 3-pass algorithm, legality checks |
| AI chat | ✅ Real LangGraph | Needs LLM key (OpenAI / Anthropic / Bedrock) |
| External flight API | ❌ Not needed | `MOCK_FLIGHT_STATUS=True` uses scripted sequences |

**You do NOT need Aviationstack or any external API for the demo.**
The mock observer sequences in `mock_observer.py` simulate exactly:
- AI202 DEL→BOM: delay grows 0 → 45 → 150 min (MEDIUM disruption)
- AI410 BOM→DEL: delay grows to 240 min (HIGH disruption)
- AI101 DEL→LHR: cancellation (CRITICAL disruption)
- AI305 BOM→CCU: normal flight (disruption is crew-side via sick call)

---

## Step-by-Step Setup & Test

### Step 1 — Start the database

Open Terminal 1:

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_backend
docker-compose up -d
```

Wait 5 seconds, then verify:

```bash
docker-compose ps
```

Expected: `crew_ops_postgres` shows state `running` and health `healthy`

---

### Step 2 — Seed all mock data

In the same terminal:

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_backend
uv run python -m crew_ops.data.pipeline.run_all
```

Expected: no errors, data loaded messages printed for crew, licenses, FTL, legs, leave, reserve.

---

### Step 3 — Start the backend

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_backend
uv run uvicorn crew_ops.api.main:app --reload --port 8000
```

Leave this terminal running. You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

---

### Step 4 — Verify backend health

Open Terminal 2:

```bash
curl http://localhost:8000/health
```

Expected:
```json
{
  "status": "ok",
  "database": "connected",
  "mock_flags": {
    "crew_profile": true,
    "license": true,
    "flight_schedule": true,
    "flight_status": true,
    "ftl_state": true,
    "reserve_schedule": true
  },
  "scheduled_jobs": [
    "observer_poll", "roster_build", "daily_validation",
    "ftl_alert_scan", "ftl_midnight_recalc", "expire_proposals",
    "auto_resolve_low", "push_proposals"
  ]
}
```

---

### Step 5 — Run all backend tests

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_backend
uv run pytest tests/ -v
```

Expected: **275 passed**, 0 failed.

---

### Step 6 — Start the frontend

Open Terminal 3:

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_dashboard
npm run dev
```

Expected:
```
▲ Next.js 16.x
- Local: http://localhost:3000
```

Open `http://localhost:3000` in your browser. The dashboard should load with the dark theme and 5 nav items.

---

### Step 7 — Check today's flights load

In the browser, confirm the Flight Monitor panel shows flights. Or verify via curl:

```bash
curl http://localhost:8000/observer/legs/today
```

Expected: a JSON array of flight legs with assigned crew.

---

### Step 8 — Test the sick call flow

This is the main demo flow. Trigger Capt Ravi Singh (C-003) sick call for AI305:

```bash
curl -X POST http://localhost:8000/crew/C-003/unavailable \
  -H "Content-Type: application/json" \
  -d '{"reason": "SICK_CALL", "affected_leg_id": "AI305-BOM-CCU-20240205", "days_until_departure": 0}'
```

Expected response:
```json
{
  "status": "disruption event published",
  "crew_id": "C-003",
  "leg_id": "AI305-BOM-CCU-20240205",
  "severity": "CRITICAL",
  "reason": "SICK_CALL"
}
```

---

### Step 9 — Verify proposal was created

```bash
curl http://localhost:8000/disruptions/proposals
```

Expected: a PENDING CRITICAL proposal for AI305 with a `proposed_crew_id` (best replacement candidate).

In the browser, the Disruption Inbox panel should show the CRITICAL card within 10 seconds (polls every 10s).

---

### Step 10 — Accept the proposal

Copy the `proposal_id` from Step 9 output (format: `PROP-AI305-BOM-CCU-20240205-YYYYMMDDHHMMSS`), then:

```bash
curl -X POST http://localhost:8000/disruptions/proposals/<proposal_id>/accept \
  -H "Content-Type: application/json" \
  -d '"ops_controller_01"'
```

Replace `<proposal_id>` with the actual value.

Expected:
```json
{
  "status": "accepted",
  "leg_id": "AI305-BOM-CCU-20240205",
  "removed": "C-003",
  "added": "C-007"
}
```

In the browser, the card animates out and a success toast appears.

---

### Step 11 — Test roster build

```bash
curl -X POST http://localhost:8000/planner/build \
  -H "Content-Type: application/json" \
  -d '"admin"'
```

Then check the roster was created:

```bash
curl "http://localhost:8000/planner/roster?start=2024-02-05&end=2024-02-11"
```

Expected: array of roster rows with `status: "DRAFT"`.

In the browser, the Roster panel shows amber DRAFT badges.

---

### Step 12 — Approve a roster leg

Pick any `leg_id` from Step 11 output, then:

```bash
curl -X POST http://localhost:8000/planner/roster/<leg_id>/approve \
  -H "Content-Type: application/json" \
  -d '"ops_controller_01"'
```

Expected:
```json
{"status": "approved", "leg_id": "...", "approved_by": "ops_controller_01"}
```

In the browser, the roster row badge flips from amber DRAFT to green PUBLISHED.

---

### Step 13 — Test FTL scan

```bash
curl -X POST http://localhost:8000/ftl/scan
```

Expected: `{"status": "alert scan completed"}`

Check a specific crew member's FTL state:

```bash
curl http://localhost:8000/crew/C-007/ftl
```

Expected: full FTL state object with `status`, `flight_hours_28_day`, `consecutive_duty_days`, etc.

---

### Step 14 — Test the AI chat (requires LLM key in .env)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-session-01", "message": "Who can replace Capt Ravi on AI305?", "user_id": "ops_controller_01"}'
```

Expected: response with `mode: "SIMULATE"` and a list of ranked candidates.

If no LLM key is set, you will get an error — skip this step and use the chat panel in `dashboard_preview/index.html` for a scripted demo instead.

---

### Step 15 — Reset between demo runs

If you need a clean slate:

```bash
# Reset proposals only
docker exec crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "DELETE FROM disruption_proposals;"

# Reset roster only
docker exec crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "DELETE FROM roster_crew_assignment; DELETE FROM roster_leg;"

# Full reset — nuke DB and reseed everything
cd /Users/rahularagi/Desktop/setup/crew_ops_backend
docker-compose down -v
docker-compose up -d
sleep 5
uv run python -m crew_ops.data.pipeline.run_all
```

---

## Demo Script — 4 Flows (12 min)

---

### Flow 1 — Sick Call → Proposal → Confirm (3 min)

**What this shows:** Crew disruption → automated candidate ranking → one-click resolution.

1. Run Step 8 curl command
2. Switch to browser — Disruption Inbox shows CRITICAL card within 10s
3. Click **Confirm** — card animates out, toast appears, roster updates

**Talking point:** *"The system ran legality checks — FTL limits, license type ratings, leave records — against all 25 crew in under a second. The ops controller just clicks confirm. No spreadsheet, no phone calls."*

---

### Flow 2 — Flight Delay → FTL Breach → Auto Proposal (3 min)

**What this shows:** Observer detects delay → re-checks legality → creates proposal automatically.

1. The observer scheduler runs every 5 min automatically — just wait, or explain it while pointing at the Flight Monitor
2. Show Flight Monitor panel — AI202 DEL→BOM shows ⏱ DELAYED after the scheduler advances the mock poll sequence
3. If any crew on AI202 breach FTL due to the delay, a proposal appears in the Disruption Inbox automatically

**Talking point:** *"The observer doesn't just log the delay. It re-runs legality for every crew member on that flight against the new departure time. If anyone breaches their flight time limits, a replacement proposal is created before the controller even notices the delay."*

---

### Flow 3 — AI Chat Simulate → Apply (3 min)

> Requires LLM key in `.env`. If unavailable, open `crew_ops_backend/dashboard_preview/index.html` directly in a browser for a fully scripted offline demo.

1. Open Chat panel. Type: `If Capt Ravi is not available for AI305, who can cover?`
2. Agent responds with `mode=SIMULATE` — lists top 3 candidates with scores
3. Type: `Apply it`
4. Agent responds with `requires_confirmation=true` — CONFIRM/CANCEL buttons appear
5. Click **CONFIRM** — disruption pipeline runs, new proposal appears in inbox within 10s

**Talking point:** *"The AI doesn't directly assign crew. It goes through the same disruption pipeline as everything else — there's always a human confirmation step before any roster change is committed."*

---

### Flow 4 — Weekly Roster Build → Approve (2 min)

1. Go to Admin page (⚙ icon) → click **Run Now** next to Roster Build
2. Switch to Dashboard → Roster panel — DRAFT rows appear with amber badges
3. Switch to List view → click **Approve** on a leg — badge flips to green PUBLISHED

**Talking point:** *"The planner runs a 3-pass algorithm — assigns by seniority and base, fills gaps with reserve crew, validates FTL across the whole week. Everything starts as DRAFT. Nothing goes live until a controller approves it."*

---

## Talking Points for Judges

**"Why not just use a spreadsheet?"**
> Spreadsheets don't know FTL law. This system checks 11 legality gates — license type ratings, rest periods, 28-day hour caps, consecutive duty days, leave records — in real time, for every candidate, every time.

**"What happens when the real Aviationstack API is connected?"**
> Set `MOCK_FLIGHT_STATUS=False` in `.env` and add the API key. The observer client already has the integration point stubbed. Everything else stays identical.

**"How does the AI know about crew legality?"**
> The LangGraph agent calls the same `check_legality()` function the disruption handler uses. It's not a prompt — it's a real function call with real DB data.

**"What if the controller rejects the proposal?"**
> The system excludes the rejected candidate and re-runs `_find_and_rank_candidates()` with the next best option. It keeps proposing until candidates are exhausted, then flags for manual handling.

**"Is this production-ready?"**
> The architecture is. Event-driven, no circular dependencies, every service subscribes to events not other services. Swap any client from mock to real independently. 275 tests passing.
