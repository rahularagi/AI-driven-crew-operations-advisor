# CrewOps — System Design & Architecture

> 4 loosely coupled services communicating only through events.
> Nothing is tightly wired. Each service can be built, tested, and replaced independently.

---

## The 4 Services

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. WEEKLY PLANNER                                                   │
│                                                                      │
│  Job A — PLAN (runs Sunday night, weekly)                            │
│    Builds crew roster for next 6–7 weeks                             │
│    Emits: RosterPublished                                            │
│                                                                      │
│  Job B — DAILY VALIDATOR (runs every morning 3AM)                    │
│    Re-checks all future planned weeks against current reality        │
│    Detects: leave added, license expired, FTL state drifted          │
│    Emits: PlanDisrupted                                              │
└──────────────┬───────────────────────────────────────────────────────┘
               │ RosterPublished
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. OBSERVER                                                         │
│    Watches TODAY's active legs only via live flight API              │
│    Detects: delay, cancellation, diversion happening right now       │
│    Emits: FlightDisrupted, LegCompleted                              │
└──────────────┬───────────────────────────────────────────────────────┘
               │ FlightDisrupted
               │                    ┌─── PlanDisrupted (from Planner Job B)
               │                    │
               │                    │    ┌─── CrewDisrupted (from Ops Desk / API)
               ▼                    ▼    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. DISRUPTION HANDLER                                               │
│    Receives FlightDisrupted OR PlanDisrupted OR CrewDisrupted        │
│    Checks FTL impact → finds replacement → updates roster            │
│    Emits: RosterModified, CrewNotified                               │
└──────────────┬───────────────────────────────────────────────────────┘
               │ RosterModified, LegCompleted
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. FTL SERVICE (background, always running)                         │
│    Closes duty windows on landing                                    │
│    Runs proactive alert scan every 15 min                            │
│    Recalculates rolling counters every midnight                      │
│    Emits: FTLAlert                                                   │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Service 1 — Weekly Planner

### Job A — PLAN (weekly, Sunday night)

Builds a crew roster for the next 6–7 weeks.

**Why 6–7 weeks, not just 1:**
- The 28-day block hour counter means what happens today affects legality 4 weeks from now
- Weekly rest blocks (36hr continuous) must be guaranteed across the full horizon
- Reserve slots must be pre-filled so the disruption handler always has a standby pool

**Inputs:**

| Input | Source | What it contains |
|-------|--------|-----------------|
| `legs[]` | Flight schedule API | All legs 6–7 weeks ahead |
| `crew_profiles[]` | HRMS (nightly sync) | Name, role, base, licenses, seniority |
| `crew_ftl_state[]` | FTL ledger | Carry-over: 28-day hours, 7-day hours, consecutive days |
| `crew_leave[]` | AIMS / HR | Approved leave — these crew excluded |
| `crew_reserve_schedule[]` | Scheduling system | Existing standby slots — planner fills gaps |
| `fdp_rules` | Static config | Report time × sector count → max FDP |

**Algorithm — 3 passes:**

```
Pass 1 — Assign operating crew to legs (earliest departure first)
  For each leg:
    find_candidates: role match, base match, not on leave, FTL available
    legality_check: against simulated FTL state (future mode)
    rank: seniority + fatigue + location + hours remaining
    assign top N, advance their simulated FTL state forward

Pass 2 — Fill reserve/standby slots
  For each date × base airport:
    fill gaps from crew not on operating duties that day

Pass 3 — Full horizon validation
  Replay every crew member's full 6–7 week plan through legality checker
  Flag: FDP breach, rest violation, 7-day cap, 28-day cap, no weekly rest block
  Return validation report — do not publish until clean
```

**Output:**
- `roster_leg` rows → roster display table (status = DRAFT)
- `roster_crew_assignment` rows → crew alignment per leg
- `crew_reserve_schedule` rows → standby slots (separate from roster view)
- On controller approval → status = PUBLISHED, emit `RosterPublished`

---

### Job B — DAILY VALIDATOR (every morning, 3AM)

Re-checks all future planned weeks against current reality.
Answers the question: **"Is everything I planned last week still valid today?"**

**What can break a future plan that the Observer cannot see:**

| What broke | How it's detected | Example |
|-----------|------------------|---------|
| Crew added sick leave | `crew_leave` table has new entry for a future date | Capt Ravi adds leave for Mar 04 — was assigned to AI305 that day |
| License expired | `crew.license_expiry` date is before the planned leg date | FO Priya's A320 rating expires Mar 01, leg planned Mar 05 |
| Medical expired | `crew.medical_expiry` before planned leg date | Capt Mehta's medical expires Mar 10, leg planned Mar 12 |
| FTL state drifted | Actual duty hours higher than planner assumed | C-002 now at 94hrs by Week 3 — Week 4 assignment will breach 100hr cap |
| Flight schedule changed | Leg rescheduled, aircraft swapped, route cancelled | AI305 moved from B737 to A320 — assigned crew not A320 rated |

**How it runs:**

```
Every morning at 3AM:

  For each future roster entry (status = PLANNED or CONFIRMED):
    load current crew_ftl_state  (not simulated — actual live state)
    load current crew_leave      (any new leave added since last plan?)
    load current crew.license_expiry + medical_expiry
    load current leg.aircraft_type (did aircraft change?)

    re-run legality_check(crew_id, leg, current_ftl_state)

    if FAIL:
      emit PlanDisrupted {
        leg_id, affected_crew_id, reason, days_until_departure, severity
      }
```

**Severity based on days until departure:**

| days_until_departure | Severity | What happens |
|---------------------|----------|-------------|
| > 14 days | LOW | Planner quietly re-assigns in next planning cycle |
| 7 – 14 days | MEDIUM | Controller notified, re-plan this week |
| 2 – 7 days | HIGH | Disruption Handler runs full replacement pipeline |
| < 2 days | CRITICAL | Same urgency as a live FlightDisrupted event |

---

### PlanDisrupted event shape

```json
{
  "event": "PlanDisrupted",
  "source": "WEEKLY_PLANNER_VALIDATOR",
  "leg_id": "AI305-BOM-CCU-20240304",
  "flight_number": "AI305",
  "origin": "BOM",
  "destination": "CCU",
  "disruption_type": "CREW_UNAVAILABLE",
  "affected_crew_id": "C-003",
  "reason": "SICK_LEAVE",
  "leg_date": "2024-03-04",
  "days_until_departure": 28,
  "severity": "LOW",
  "detected_at": "2024-02-05T03:00:00+05:30"
}
```

**disruption_type values for PlanDisrupted:**

| type | Cause |
|------|-------|
| `CREW_UNAVAILABLE` | Sick leave, annual leave, training leave added |
| `LICENSE_EXPIRED` | Type rating expired before leg date |
| `MEDICAL_EXPIRED` | Medical certificate expired before leg date |
| `FTL_BREACH_PROJECTED` | Accumulated hours will breach cap by that week |
| `AIRCRAFT_TYPE_CHANGED` | Leg now requires different type rating |

---

### Planner re-validates after RosterModified

When Disruption Handler fixes a live disruption and emits `RosterModified`, the Planner re-checks future weeks for the affected crew:

```
RosterModified: Capt Mohan assigned to AI305 on Feb 05 (extra duty)

Planner validator next morning:
  Capt Mohan's flight_hours_28_day is now higher than planned
  Re-run legality check for all Capt Mohan's future legs
  If any future leg now breaches → emit PlanDisrupted for that leg
```

This closes the loop — today's fix cannot silently break a future week.

---

## Service 2 — Observer

**Scope: today's active legs only.**

Watches every leg that has crew assigned and is departing today. Polls the live flight status API. Detects when reality deviates from plan. Emits an event. Does nothing else.

**What triggers it:** `RosterPublished` → extracts today's leg_ids → starts polling.

**Polling frequency:**

| Leg status | Frequency | Why |
|-----------|-----------|-----|
| SCHEDULED, departure > 2hrs away | every 15 min | nothing happening yet |
| BOARDING / DELAYED_AT_GATE | every 5 min | departure imminent |
| ACTIVE (airborne) | every 60 sec | `estimated_arrival` updating |
| LANDED | stop polling | emit LegCompleted |
| CANCELLED / DIVERTED | stop polling | emit FlightDisrupted CRITICAL |

**Severity thresholds:**

| delay_minutes | Severity | Event |
|--------------|----------|-------|
| 0 – 29 | — | none |
| 30 – 119 | LOW | FlightDisrupted |
| 120 – 239 | MEDIUM | FlightDisrupted |
| 240+ | HIGH | FlightDisrupted |
| status = cancelled | CRITICAL | FlightDisrupted |
| status = diverted | CRITICAL | FlightDisrupted |
| status = landed | — | LegCompleted |

**What Observer does NOT know about:**
- FTL rules
- Crew availability
- Whether the delay actually causes a problem
- Future weeks

---

## Service 3 — Disruption Handler

Receives `FlightDisrupted` (from Observer), `PlanDisrupted` (from Planner validator), or `CrewDisrupted` (from Ops Desk via API).
Same pipeline handles all three — it does not care where the event came from.

**Processing pipeline:**

```
Step 1 — Classify
  FlightDisrupted → live disruption, urgency based on severity field
  PlanDisrupted   → future disruption, urgency based on days_until_departure
  CrewDisrupted   → find all roster_crew_assignment rows for this crew
                    between affected_from and affected_until
                    urgency based on days_until_departure of earliest affected leg

Step 2 — FTL impact check
  For each crew member on the affected leg:
    Recalculate projected_fdp_end
    Check if FDP will be breached
    Check if rest before next duty will be sufficient
  If no impact → log and close

Step 3 — Cascade check
  Find all other legs the affected crew member is assigned to
  Flag ripple effects

Step 4 — Find candidates (pure Python, no LLM)
  Check crew_reserve_schedule: who is on standby at this airport?
  Check crew_roster: who is AVAILABLE and not on another leg?
  Filter: role match, ACTIVE status, not on leave
  Run legality checker on each (hard gates only)

Step 5 — Score and rank (pure Python, no LLM)
  legal(40) + same_airport(30) + low_fatigue(20) + low_cost(10)
  Always append "delay the flight" as final fallback

Step 6 — LLM narration
  Takes ranked list (structured facts) → writes human-readable explanation
  Cannot change rankings or invent data

Step 7 — Human decision point
  CRITICAL / HIGH → present to controller immediately
  MEDIUM          → present to controller, 4hr window to respond
  LOW             → auto-resolve if clean replacement found, notify controller

Step 8 — Closed loop (on approval)
  Update roster_crew_assignment: remove old crew entry, add new crew entry
  Refresh roster_leg status if flight is now fully crewed
  Update crew_ftl_state: for both removed and replacement crew
  Emit RosterModified → Planner re-validates future weeks
  Emit CrewNotified → notification service sends messages
```

---

## Service 4 — FTL Service (Background)

Always running. Never called directly — only reacts to events.

```
On LegCompleted:
  for each crew on the leg:
    flight_time_current_duty += leg.duration_hours
    sectors_current_duty += 1
    current_airport = leg.destination
    at_home_base = (destination == crew.home_base)
    rest_start_time = actual_arrival + 30min debrief
    status = RESTING
    min_rest = max(12, duty_hours) if at_home_base else 10
    earliest_available = rest_start + min_rest
    if not at_home_base → trigger hotel notification

On RosterModified:
  for removed crew: status = SICK / OFF_DUTY (duty counters unchanged)
  for added crew:   duty_start_time set, projected_fdp_end calculated

Every 15 min — proactive alert scan:
  FDP approaching (< 2hrs remaining on active duty)
  Rest violation risk (next duty too soon)
  Weekly rest overdue (no 36hr block in 6 days)
  Cumulative cap approaching (28-day hours > 90)
  WOCL duty tomorrow (report time 0000–0600)
  License expiring within 30 days
  Medical expiring within 30 days

Every midnight — rolling counter recalculation:
  duty_hours_7_day    = sum of last 7 rolling days
  flight_hours_28_day = sum of last 28 rolling days
  consecutive_duty_days recalculated
  emit FTLAlert for any crew crossing warning thresholds
```

---

## Complete Event List

| Event | Emitted by | Consumed by |
|-------|-----------|-------------|
| `RosterPublished` | Weekly Planner (Job A) | Observer (starts watching today's legs) |
| `PlanDisrupted` | Weekly Planner (Job B) | Disruption Handler |
| `FlightDisrupted` | Observer | Disruption Handler |
| `CrewDisrupted` | Ops Desk via API (human in loop) | Disruption Handler |
| `LegCompleted` | Observer | FTL Service |
| `RosterModified` | Disruption Handler | Weekly Planner (re-validate future), FTL Service |
| `CrewNotified` | Disruption Handler | Notification Service |
| `FTLAlert` | FTL Service | Disruption Handler (auto-creates PlanDisrupted if needed) |

---

## Full Timeline of a Flight

```
6–7 weeks before departure
  Planner Job A runs
  Assigns crew to leg
  Writes roster_leg + roster_crew_assignment (status = DRAFT)
  On controller approval → status = PUBLISHED, emits RosterPublished
        │
        ▼
Every morning (3AM) until departure
  Planner Job B runs
  Re-checks this leg against current reality
  If crew leave added / license expired / FTL drifted:
    Emits PlanDisrupted → Disruption Handler fixes it
        │
        ▼
Day before departure
  Planner Job B confirms: all crew still valid
  crew_roster entry updated to CONFIRMED
  Hotel bookings triggered for layover crew
        │
        ▼
Day of departure — Observer takes over
  Observer polls this leg (today only)
  Departure > 2hrs: every 15 min
  Boarding: every 5 min
  Airborne: every 60 sec
        │
        ├── delay detected → FlightDisrupted → Disruption Handler
        ├── cancelled → FlightDisrupted CRITICAL → Disruption Handler
        ├── crew goes sick → Ops Desk calls POST /v1/crew/{id}/unavailable
        │                  → CrewDisrupted → Disruption Handler
        │
        ▼
Flight lands
  Observer detects status = landed
  Emits LegCompleted
  Stops polling this leg
        │
        ▼
FTL Service receives LegCompleted
  Closes duty window for all crew
  Starts rest clock
  Updates current_airport
  Triggers hotel notification if away from base
  Updates rolling counters
```

---

## Crew-Side Disruption — Human in Loop

Crew-side disruptions are entered manually by the Ops Desk. The system handles everything after that.

**Trigger:** Controller calls `POST /v1/crew/{crew_id}/unavailable`

**CrewDisrupted event shape:**

```json
{
  "event": "CrewDisrupted",
  "source": "OPS_DESK",
  "crew_id": "C-003",
  "crew_name": "Capt Ravi Singh",
  "disruption_type": "SICK_CALL",
  "affected_from": "2024-02-05",
  "affected_until": "2024-02-05",
  "entered_by": "controller_id",
  "entered_at": "2024-02-05T05:30:00+05:30"
}
```

**disruption_type values:**

| type | Cause |
|------|-------|
| `SICK_CALL` | Crew calls in sick |
| `EMERGENCY_LEAVE` | Family emergency, bereavement |
| `MEDICAL_GROUNDING` | Doctor grounds crew immediately |
| `NO_SHOW` | Crew did not report at check-in |
| `URGENT_TRAINING` | Regulator mandates emergency simulator check |

**Severity based on days_until_departure of earliest affected leg:**

| days_until_departure | Severity | Action |
|---------------------|----------|--------|
| < 1 day | CRITICAL | Immediate — activate nearest reserve |
| 1 – 2 days | HIGH | Disruption Handler runs now |
| 2 – 7 days | HIGH | Full replacement pipeline |
| 7 – 14 days | MEDIUM | Controller notified, fix this week |
| > 14 days | LOW | Planner re-assigns in next cycle |

**API endpoint:**

```
POST /v1/crew/{crew_id}/unavailable
  body: { disruption_type, affected_from, affected_until }
  → emits CrewDisrupted
  → returns list of all affected legs immediately so controller sees full impact
```

---

## What Each Service Owns

| | Planner Job A | Planner Job B | Observer | Disruption Handler | FTL Service |
|--|:---:|:---:|:---:|:---:|:---:|
| Reads flight schedule API | ✅ | ❌ | ✅ (today only) | ❌ | ❌ |
| Reads crew FTL state | ✅ (simulated) | ✅ (live) | ❌ | ✅ (live) | ✅ (live) |
| Runs legality checker | ✅ (future) | ✅ (future) | ❌ | ✅ (live) | ❌ |
| Writes `roster_leg` + `roster_crew_assignment` | ✅ DRAFT→PUBLISHED | ❌ | ❌ | ❌ | ❌ |
| Modifies `roster_crew_assignment` | ❌ | ❌ | ❌ | ✅ | ❌ |
| Writes crew_ftl_state | ❌ | ❌ | ❌ | ✅ | ✅ |
| Notifies crew | ❌ | ❌ | ❌ | ✅ | ✅ (alerts) |
| Needs LLM | ❌ | ❌ | ❌ | ✅ (narration only) | ❌ |

---

## Service 5 — Conversation Layer (Human-in-Loop)

The only entry point for human interaction. Translates free-text requests into structured intents, routes to the right service, and returns human-readable responses.

All 4 services stay completely unaware of the human. The Conversation Layer is the only new component.

```
Human (chat / UI)
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│  CONVERSATION LAYER  (LangGraph agent)                      │
│                                                             │
│  Intent Classifier → Router → Tool Executor                 │
│  Response Formatter ← Results ←──────────────────           │
│                                                             │
│  Holds: session context, pending confirmations              │
└──────┬──────────┬──────────┬──────────┬────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
   Roster     Disruption  Planner    FTL
   Service    Handler     Service    Service
  (read only) (write)    (simulate)  (read only)
```

### 3 Interaction Modes

**Mode 1 — QUERY (read only, no confirmation)**
```
"What is the status of AI305?"
"Who is assigned to AI101 tomorrow?"
"Show me Capt Mehta's schedule this week"
"How many hours does FO Sharma have left this month?"

Flow: Intent = QUERY → read-only tools → respond. No state change.
```

**Mode 2 — SIMULATE (what-if, no confirmation)**
```
"If Capt Ravi is not available tomorrow, who can replace him?"
"What happens if AI305 gets cancelled?"
"If I swap Capt Mehta and FO Sharma on AI202, is that legal?"
"If I move FO Nair from AI410 to AI305, what breaks?"

Flow: Intent = SIMULATE → run in memory → legality check → cascade check
      → rank options → LLM narrates → respond with outcome
      → "Want me to apply it?"   No state change yet.
```

**Mode 3 — ACTION (writes to system, requires confirmation)**
```
"Mark Capt Ravi as sick for today"
"Assign FO Deepa to AI305 instead of FO Sharma"
"Swap Capt Mehta and Capt Nisha on tomorrow's flights"
"Activate reserve C-007 for the BOM-DEL leg"

Flow: Intent = ACTION → legality check → cascade check
      → build confirmation package → present to human
      → human confirms → service call → event emitted → pipeline runs
      → respond with what changed
```

### System-Initiated Decisions (push to human)

Disruption Handler reaches Step 7 and pushes to human when severity is HIGH or CRITICAL:

```
"AI305 BOM→CCU departs in 90min. Capt Ravi called sick.
 Best replacement: Capt Vikram (reserve at BOM, FTL legal).
 Second option: FO Nair (deadhead from DEL, adds 45min to FDP).
 Confirm Capt Vikram? [YES / NO / SHOW MORE OPTIONS]"
```

| Severity | Behaviour |
|----------|----------|
| CRITICAL | Push to human immediately. Auto-escalate after 15min if no response |
| HIGH | Push to human immediately. 1hr window |
| MEDIUM | Push to human. 4hr window to respond |
| LOW | Auto-resolve if clean replacement found. Notify human only |

### Confirmation Package Shape

What the human sees before approving any action:

```json
{
  "action": "ASSIGN_REPLACEMENT",
  "summary": "Replace Capt Ravi Singh on AI305 BOM→CCU (10:00 departure)",
  "proposed_change": {
    "remove": { "crew_id": "C-003", "name": "Capt Ravi Singh", "reason": "SICK_CALL" },
    "add":    { "crew_id": "C-007", "name": "Capt Vikram Joshi", "type": "RESERVE" }
  },
  "legality": "LEGAL",
  "ftl_warnings": [],
  "cascade_impact": ["Capt Vikram reserve slot at BOM released for today"],
  "future_impact": "None — Capt Vikram has no future legs this week",
  "confidence": "HIGH",
  "expires_at": "2024-02-05T08:30:00+05:30",
  "options": [
    { "rank": 1, "crew": "Capt Vikram Joshi", "reason": "Reserve at BOM, FTL legal, low fatigue" },
    { "rank": 2, "crew": "FO Anita Nair",      "reason": "Deadhead from DEL, adds 45min FDP" },
    { "rank": 3, "crew": "Delay the flight",   "reason": "No other legal crew at BOM" }
  ]
}
```

### What Needs Confirmation vs What Doesn't

| Action | Confirmation | Why |
|--------|:---:|-----|
| Query current status | ❌ | Read only |
| Simulate what-if | ❌ | No state change |
| Mark crew unavailable | ✅ | Triggers pipeline |
| Assign replacement | ✅ | Modifies roster |
| Swap two crew | ✅ | Modifies roster for both |
| Approve weekly roster | ✅ | Publishes to all crew |
| Cancel a flight | ✅ | Cascades to all assigned crew |
| Activate reserve | ✅ | Changes crew assignment |
| Auto-resolve LOW severity | ❌ | System handles, just notifies |

### Edge Cases

| Edge Case | How handled |
|-----------|-------------|
| Human doesn't respond to CRITICAL in time | Auto-escalate after 15min → activate best reserve, notify human |
| Legality changes between ask and confirm | Re-run legality check at confirm time. If now illegal → reject, re-present |
| Two controllers act on same disruption | Lock disruption record when opened. Second controller sees "being handled by [name]" |
| Approved change breaks a future week | Show cascade impact before confirm. After apply → Planner Job B re-validates immediately |
| Ambiguous request ("swap these two") | Ask clarifying question before routing |
| Crew member not found | "I don't have a crew member by that name. Did you mean...?" |
| Session timeout mid-confirmation | Pending confirmation saved to queue. Nothing applied until confirmed |
| Option 1 auto-applied before human confirms option 2 | Detect conflict at confirm time → tell human what already happened |

### Intent Classification

```
QUERY     → read tools only → respond
SIMULATE  → simulate tools → show outcome → ask "apply?"
ACTION    → legality check → confirmation package → wait → apply
AMBIGUOUS → ask clarifying question → re-classify
UNKNOWN   → "I can help with crew scheduling. Try asking..."
```

### What LLM Does vs Pure Python

| Task | Who |
|------|-----|
| Classify intent from free text | LLM |
| Legality check | Pure Python (hard gates) |
| Cascade impact check | Pure Python |
| Rank replacement options | Pure Python |
| Write confirmation package narrative | LLM |
| Detect ambiguity | LLM |
| Format final response | LLM |
| Apply the actual change | Pure Python (service call) |

---

## Package Structure

```
crew_ops/
├── docs/
│   ├── SYSTEM_DESIGN.md              ← this file
│   ├── DATA_SOURCES_AND_APIS.md
│   ├── MOCK_API_RESPONSES.md
│   ├── CREWOPS_ADVISOR.md
│   ├── APPROACH_ANALYSIS.md
│   └── CREW_HANDLING_IMPLEMENTATION.md
│
├── models/
│   ├── leg.py                        Leg, Aircraft
│   ├── crew.py                       CrewMember (static profile)
│   ├── crew_ftl_state.py             CrewFTLState (live ledger)
│   ├── roster.py                     Roster (week header)
│   ├── roster_leg.py                 RosterLeg (one row per leg)
│   ├── roster_crew_assignment.py     RosterCrewAssignment (one row per crew per leg)
│   ├── crew_leave.py                 CrewLeave
│   ├── crew_reserve.py               CrewReserveSchedule
│   ├── disruption.py                 DisruptionEvent
│   └── events.py                     all event shapes
│
├── rules/
│   ├── legality.py                   CrewLegalityChecker — hard gates, no LLM
│   └── fdp_table.py                  FDP bracket table
│
├── data/
│   ├── seed_crew.py                  25 crew members
│   ├── seed_legs.py                  15 legs across DEL/BOM/BLR
│   ├── seed_ftl.py                   initial FTL states with deliberate variety
│   └── seed_roster.py                roster entries + leave + reserves
│
├── roster/                           ← Service 1: Weekly Planner
│   ├── planner.py                    Job A — RosterPlanner (Pass 1, 2, 3)
│   ├── validator.py                  Job B — DailyValidator (re-checks future weeks)
│   └── roster_service.py             CRUD for crew_roster + change log
│
├── observer/                         ← Service 2: Observer
│   ├── observer.py                   FlightObserver — polls today's legs
│   └── flight_client.py              thin wrapper around flight status API
│
├── disruption/                       ← Service 3: Disruption Handler
│   ├── handler.py                    main pipeline (handles FlightDisrupted, PlanDisrupted, CrewDisrupted)
│   ├── candidate_finder.py           find + filter candidates (pure Python)
│   └── ranker.py                     score + rank candidates (pure Python)
│
├── ftl/                              ← Service 4: FTL Service
│   └── ftl_service.py                duty events, proactive alerts, midnight recalc
│
├── agent/                            ← Service 5: Conversation Layer (LangGraph)
│   ├── state.py                      ConversationState — session, intent, pending confirmation
│   ├── nodes.py                      classify_intent, route, simulate, confirm, apply, respond
│   └── graph.py                      LangGraph graph wiring all nodes
│
├── tools/
│   ├── query_tools.py                get_roster, get_crew_status, get_leg_status (read only)
│   ├── simulate_tools.py             simulate_replacement, simulate_swap, simulate_cancellation
│   └── action_tools.py               mark_unavailable, assign_crew, swap_crew (write — gated by confirmation)
│
├── notifications/
│   └── notifier.py
│
├── api/
│   ├── main.py
│   ├── chat.py                       POST /v1/chat — main conversation endpoint
│   └── decisions.py                  GET/POST /v1/decisions/pending — confirmation queue
│
├── config/
│   ├── fdp_table.json
│   ├── cost_config.json
│   └── planner_config.json
│
└── ui/
    └── app.py
```
