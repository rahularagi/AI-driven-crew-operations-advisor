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

## One-Time Setup (do this before the demo)

### Terminal 1 — Backend

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops

# 1. Start PostgreSQL
docker-compose up -d

# 2. Wait ~5s, verify healthy
docker-compose ps
# Should show: crew_ops_postgres  healthy

# 3. Seed all mock data
uv run python -m crew_ops.data.pipeline.run_all
# Expected: "All mock data loaded successfully."

# 4. Start API server
uv run uvicorn crew_ops.api.main:app --reload --port 8000
```

### Terminal 2 — Frontend

```bash
cd /Users/rahularagi/Desktop/setup/crew_ops_dashboard
npm run dev
# Starts on http://localhost:3000
```

### Verify everything is up

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
  "scheduled_jobs": ["observer_poll", "roster_build", "daily_validation",
                     "ftl_alert_scan", "ftl_midnight_recalc", "expire_proposals",
                     "auto_resolve_low", "push_proposals"]
}
```

Open `http://localhost:3000` — dashboard should load with flight data.

---

## Demo Script — 4 Flows (12 min)

---

### Flow 1 — Sick Call → AI Proposal → Confirm (3 min)

**What this shows:** Crew disruption → automated candidate ranking → one-click resolution.

**Step 1** — Trigger the sick call via API (paste in browser or curl):

```bash
curl -X POST http://localhost:8000/crew/C-003/unavailable \
  -H "Content-Type: application/json" \
  -d '{"reason": "SICK_CALL", "affected_leg_id": "AI305-BOM-CCU-20240205", "days_until_departure": 0}'
```

**What happens in the backend (invisible to audience):**
- `CrewDisruptedEvent` published on event bus
- `DisruptionHandler.handle_crew_disrupted()` runs
- Legality check against all 25 crew
- Top candidate ranked by: location at VABB (40pts) + fatigue score + home base bonus
- `PENDING` proposal written to `disruption_proposals` table with `severity=CRITICAL`

**Step 2** — Switch to dashboard. Within 10 seconds the Disruption Inbox shows:

```
🔴 CRITICAL  •  AI305 BOM→CCU  •  departs Xm
Capt Ravi Singh called sick. (SICK_CALL)
● Capt Vikram Joshi  C-007  Score: 87
[✓ Confirm]  [✗ Reject]  14:32
```

**Step 3** — Click **Confirm**. Show the audience:
- Card animates out with green flash
- Toast: "✓ Proposal accepted"
- Roster panel updates on next poll: AI305 shows new crew

**Talking point:** *"The system ran legality checks — FTL limits, license type ratings, leave records — against all 25 crew in under a second. The ops controller just clicks confirm. No spreadsheet, no phone calls."*

---

### Flow 2 — Flight Delay → FTL Breach → Auto Proposal (3 min)

**What this shows:** Observer detects delay → checks if delay causes FTL breach → creates proposal automatically.

**Step 1** — Trigger the observer poll manually (simulates the 5-min scheduler):

```bash
curl -X POST http://localhost:8000/ftl/scan
```

Then trigger the observer by calling the flight status endpoint directly. The mock sequences advance automatically each time the scheduler polls. To force it during demo, call:

```bash
# Manually advance the mock poll for AI202 by hitting the observer endpoint
curl http://localhost:8000/observer/legs/today
```

**Better for demo** — just wait. The observer polls every 5 min automatically. Or reduce the interval for demo by restarting with:

```bash
# In crew_ops/.env, add:
# (no env var needed — just explain the scheduler is running)
```

**Step 2** — Show the Flight Monitor panel. Point out AI202 DEL→BOM:
- First poll: SCHEDULED, no delay
- After scheduler runs: shows ⏱ DELAYED +150min (MEDIUM)

**Step 3** — If any assigned crew on AI202 breach FTL due to the delay, a proposal appears automatically in the Disruption Inbox.

**Talking point:** *"The observer doesn't just log the delay. It re-runs legality for every crew member on that flight against the new departure time. If anyone breaches their flight time limits, a replacement proposal is created before the controller even notices the delay."*

---

### Flow 3 — AI Chat Simulate → Apply (3 min)

**What this shows:** Natural language query → simulation → action → disruption pipeline.

> Requires LLM key in `.env`. If no key available, show this flow from the existing `dashboard_preview/index.html` instead.

**Step 1** — Open the Chat panel. Type:

```
If Capt Ravi is not available for AI305, who can cover?
```

**Expected response** (mode=SIMULATE):
```
Simulating removal of C-003 from AI305-BOM-CCU-20240205...

Top candidates:
1. Capt Vikram Joshi (C-007) — at VABB ✓  Score: 87  FTL: 0h/13h
2. Capt Arun Iyer (C-009)    — at VOBL    Score: 62  FTL: 2h/13h
3. Capt Mohan Das (C-024)    — at VABB ✓  Score: 58  FTL: 4h/13h

Want me to raise this as a disruption? [YES / NO]
```

**Step 2** — Type: `Apply it`

Response (mode=ACTION, requires_confirmation=true):
```
Capt Ravi Singh (C-003) will be marked unavailable for AI305.
DisruptionHandler will find the best replacement and create a
PENDING proposal. Approve from your Disruption Inbox.

[✓ CONFIRM]  [✗ CANCEL]
```

**Step 3** — Click **CONFIRM**. Show the Disruption Inbox — new card appears within 10 seconds.

**Talking point:** *"The AI doesn't directly assign crew. It goes through the same disruption pipeline as everything else — so there's always a human confirmation step before any roster change is committed."*

---

### Flow 4 — Weekly Roster Build → Approve (2 min)

**What this shows:** Automated roster planning → controller approval workflow.

**Step 1** — Go to Admin page. Click **Run Now** next to Roster Build.

Or via curl:
```bash
curl -X POST http://localhost:8000/planner/build \
  -H "Content-Type: application/json" \
  -d '"admin"'
```

**Step 2** — Switch to Dashboard → Roster panel. DRAFT rows appear with amber badges.

**Step 3** — Switch to List view. Click **Approve** on each leg. Badge flips to green PUBLISHED.

**Talking point:** *"The planner runs a 3-pass algorithm — first assigns by seniority and base, then fills gaps with reserve crew, then validates FTL across the whole week. Everything starts as DRAFT. Nothing goes live until a controller approves it."*

---

## Bonus — Show the Admin Panel (1 min)

Navigate to Admin (⚙ icon):

- **API Health** — green dots for DB, FastAPI, APScheduler
- **Mock Flags** — show all 6 flags as MOCK. Explain: *"Flip any flag to REAL and it calls the live Aviationstack or HRMS API. We can go live with one config change."*
- **Scheduled Jobs** — show all 8 jobs running. Point out observer every 5 min, FTL scan every 15 min.
- **API Explorer** — show all 16 endpoints. Click ↗ on `/health` to open in browser.

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

---

## Quick Reset Between Demo Runs

If you need to reset proposals and roster between runs:

```bash
# Reset just proposals
docker exec crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "DELETE FROM disruption_proposals;"

# Reset roster assignments
docker exec crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "DELETE FROM roster_crew_assignment; DELETE FROM roster_leg;"

# Full reset — nuke and reseed
docker-compose down -v
docker-compose up -d
sleep 5
uv run python -m crew_ops.data.pipeline.run_all
```

---

## If the LLM Key Is Not Available

Skip Flow 3 entirely. The other 3 flows are fully offline and demonstrate the core value:
- Automated disruption detection and candidate ranking
- Real legality checking
- Human-in-the-loop approval workflow

The chat panel will show "Error: could not reach AI backend" — just skip past it.

Alternatively, open `crew_ops/dashboard_preview/index.html` directly in a browser for a fully scripted chat demo with no backend required.
