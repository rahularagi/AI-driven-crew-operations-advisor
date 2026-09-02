# CrewOps Advisor — Complete Implementation Plan

> AI-Driven Operational Superintelligence for Airline Crew Control

This document is the single source of truth for the full implementation.
Each component section contains the complete implementation detail — flows, code, edge cases, DB schema, API endpoints, and end-to-end tests.

---

## Table of Contents

1. Architecture Overview
2. Component 1 — Weekly Planner (Job A + Job B)
3. Component 2 — Observer
4. Component 3 — Disruption Handler
5. Component 4 — FTL Service
6. Component 5 — Conversation Layer
7. Scheduled Jobs
8. Event List
9. API Endpoints Reference
10. Database Tables
11. Mock Data Spec
12. Demo Scenarios

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  CONVERSATION LAYER  — only human entry point                       │
│  Intent: QUERY / SIMULATE / ACTION                                  │
│  LLM: classify intent, narrate results, detect ambiguity            │
│  Pure Python: all legality, scoring, cascade — never the LLM        │
└──────┬──────────┬──────────┬──────────┬──────────────────────────── ┘
       │          │          │          │
       ▼          ▼          ▼          ▼
┌──────────┐ ┌─────────┐ ┌────────┐ ┌──────────────────────────────┐
│ WEEKLY   │ │OBSERVER │ │DISRUPT │ │ FTL SERVICE                  │
│ PLANNER  │ │         │ │HANDLER │ │ duty events / alerts / recalc│
└──────────┘ └─────────┘ └────────┘ └──────────────────────────────┘
       │          │          ▲ ▲              ▲
       │ Crew     │ Flight   │ │              │
       │ Disrupted│ Disrupted│ │ Roster       │ Leg
       └──────────┴──────────┘ │ Modified     │ Completed
                               └──────────────┘
                               EventBus (in-process pub/sub)
```

All 5 components communicate only through events. No direct imports between services.

---

## Scheduled Jobs

| Job | Schedule | Method |
|-----|----------|--------|
| observer_poll | every 5 min | FlightObserver.poll_all_today() |
| ftl_alert_scan | every 15 min | FlightTimeLimitsService.run_proactive_alert_scan() |
| ftl_midnight_recalc | midnight | FlightTimeLimitsService.run_midnight_recalculation() |
| expire_proposals | every 5 min | DisruptionHandler.expire_stale_proposals() |
| daily_validation | 03:00 daily | DailyValidator.validate() |
| roster_build | Sunday 23:00 | RosterPlanner.build() |

---

## Event List

| Event | Emitted by | Consumed by |
|-------|-----------|-------------|
| FlightDisruptedEvent | Observer | Disruption Handler |
| LegCompletedEvent | Observer | FTL Service |
| CrewDisruptedEvent | Planner Job B / Ops Desk API | Disruption Handler |
| RosterModifiedEvent | Disruption Handler | Planner (re-validate), FTL Service |
| FlightTimeLimitsAlertEvent | FTL Service | Notification service |

---

## API Endpoints Reference

| Method | Path | Purpose |
|--------|------|---------|
| POST | /chat | Conversation layer — main human entry point |
| GET | /health | Health check + mock flags |
| POST | /crew/{id}/unavailable | Mark crew unavailable, emit CrewDisruptedEvent |
| GET | /crew/{id}/ftl | Current FTL state for a crew member |
| GET | /disruptions/proposals | All PENDING proposals sorted by severity |
| POST | /disruptions/proposals/{id}/accept | Accept proposal, write roster change |
| POST | /disruptions/proposals/{id}/reject | Reject, trigger next candidate |
| GET | /observer/legs/today | Today's active legs with current status |
| GET | /observer/legs?offset=1 | Legs for a future date |
| POST | /planner/build | Manual roster build trigger |
| POST | /planner/validate | Manual validation trigger |
| POST | /planner/roster/{leg_id}/approve | Approve DRAFT leg → PUBLISHED |
| POST | /planner/roster/{leg_id}/reassign | Manual crew swap on existing assignment |
| POST | /ftl/scan | Manual proactive alert scan |
| POST | /ftl/recalculate | Manual midnight recalculation |

---

## Database Tables

| Table | Purpose |
|-------|---------|
| crew_members | static crew profile |
| crew_licenses | type ratings + expiry per crew |
| crew_leave_records | approved leave periods |
| crew_reserve_schedule | standby assignments |
| crew_ftl_states | live FTL ledger — one row per crew |
| flight_legs | leg schedule |
| roster_leg | planned leg with status (DRAFT/PUBLISHED/INVALIDATED) |
| roster_crew_assignment | crew-to-leg assignments with status + audit |
| disruption_proposals | PENDING/ACCEPTED/REJECTED/EXPIRED proposals |

---

## Mock Data Spec

25 crew members across VIDP (Delhi) / VABB (Mumbai) / VOBL (Bangalore):
- Mix of PILOT and CABIN roles
- Varying FTL states: some AVAILABLE, some RESTING, some near duty caps
- 3 crew near 28-day block hour cap (> 90h) — triggers cumulative warning
- 2 crew with licenses expiring within 30 days — triggers license alert
- 1 crew on leave — excluded from candidate pool

15 flight legs:
- 3 pre-seeded with disruption scenarios ready for demo
- Mix of A320 and B737 type requirements

5 disruption proposals pre-seeded:
- 1 CRITICAL (departure in 45 min, crew sick)
- 1 HIGH (departure tomorrow morning)
- 2 MEDIUM
- 1 LOW (auto-resolved in demo)

---

## Demo Scenarios

### Scenario 1 — Simple Sick Call
Controller marks Capt Ravi sick → CrewDisruptedEvent → DisruptionHandler pipeline → PENDING proposal → controller approves Capt Vikram → roster updated → both crew notified.

### Scenario 2 — What-If Simulation
Controller asks "If Capt Ravi is sick, who can cover?" → SIMULATE in memory → "Want me to raise this?" → "yes, apply it" → CrewDisruptedEvent published → DisruptionHandler full pipeline → PENDING proposal in inbox.

### Scenario 3 — Cascade Disruption
Capt Singh sick on AI305 → cascade detected: Singh also on AI410 → two proposals created simultaneously.

### Scenario 4 — Proactive Alert
FTL scan detects Capt Mehta projected duty 13.5h with only 30min buffer → alert pushed → pre-identify backup now.

### Scenario 5 — Direct Reassignment
Controller says "Assign FO Deepa to AI305 instead of FO Sharma" → legality check → confirmation → direct roster write → RosterModifiedEvent.

---


---

## Component 1 — Weekly Planner

# Weekly Planner — End to End Implementation

---

## What This Service Does

The Weekly Planner is responsible for two things:

1. **Job A — Build**: Every Sunday night, assign crew to every flight leg for the next 7 weeks. Write the result to the database as a draft roster. On controller approval, publish it.

2. **Job B — Validate**: Every morning at 3AM, re-check every future planned assignment against current reality. If anything has changed (new leave, expired license, FTL drift), emit a `CrewDisruptedEvent` so the Disruption Handler can fix it.

Both jobs share the same legality checker. The only difference is Job A simulates future FTL state, Job B uses live FTL state.

Job A fetches flight legs **week by week**, not all at once. Each week is planned and committed to DB independently. The simulated FTL state carries forward from one week into the next.

---

## Current State of the Codebase

Before implementing, here is exactly what exists and what is missing.

### What exists

| File | Status |
|------|--------|
| `models/crew_member.py` | ✅ Complete |
| `models/crew_leave.py` | ✅ Complete |
| `models/crew_license.py` | ✅ Complete |
| `models/crew_reserve.py` | ✅ Complete |
| `models/flight_leg.py` | ✅ Complete |
| `models/crew_flight_time_limits_state.py` | ✅ Complete |
| `models/events.py` | ✅ Complete |
| `clients/crew_profile_client.py` | ✅ Complete |
| `clients/license_client.py` | ✅ Complete |
| `clients/ftl_client.py` | ✅ Complete |
| `clients/flight_schedule_client.py` | ✅ Complete |
| `clients/leave_client.py` | ✅ Complete |
| `clients/reserve_client.py` | ✅ Complete |
| `db/repositories/leave_repository.py` | ✅ Complete |
| `db/repositories/roster_repository.py` | ✅ Complete |
| `services/weekly_planner/weekly_planner_service.py` | ✅ Complete |
| `api/routers/planner_router.py` | ✅ Complete |
| `rules/legality.py` | ✅ Complete |
| `rules/crew_requirements.py` | ✅ Complete |
| `rules/duty_period_limits.py` | ✅ Complete |
| `rules/ftl_simulator.py` | ✅ Complete |
| `docker/init.sql` | ✅ Complete — all tables and correct column names |

### What is missing

Nothing — all files are complete and all known bugs are fixed.

---

## Data Fetching — What the Planner Needs and Where It Comes From

The planner needs 5 data sources. Crew, licenses, leave, and FTL states are fetched **once** at the start of the build and held in memory for the full run. Flight legs are fetched **week by week** inside the planning loop — one API call per week, not a bulk fetch for the entire horizon.

| Data | Client | Repository | Table |
|------|--------|-----------|-------|
| All crew members | `crew_profile_client.get_all_crew_members()` | `crew_repository` | `crew_members` |
| All licenses | `license_client.get_all_licenses()` | `license_repository` | `crew_licenses` |
| All leave records | `leave_client.get_all_leave_records()` | `leave_repository` | `crew_leave_records` |
| All FTL states | `ftl_client.get_all_ftl_states()` | `ftl_repository` | `crew_ftl_states` |
| Legs (per week) | `flight_schedule_client.get_legs_for_date_range(start, end)` | `leg_repository` | `flight_legs` |

### Leave Client

Leave is always internal. The manager enters it via `POST /crew/{crew_id}/unavailable` — that API call writes to `crew_leave_records` in the database. The planner reads it back from the same table.

No external API. No mock/real split. `clients/leave_client.py` wraps the repository with three functions:

- `get_all_leave_records()` — used by Job A and Job B to load all leave upfront
- `get_leave_records_for_crew(crew_id)` — used when validating a single crew member
- `add_leave_record(leave_record)` — called by the crew router when manager marks crew unavailable. **Also automatically publishes `CrewDisruptedEvent(reason=LEAVE_ADDED)` per assigned leg that falls within the leave window** — Disruption Handler picks this up and finds a replacement without any manual ops desk action.

### In-Memory Lookup Maps

After fetching, build lookup maps once. Avoids O(n²) scans inside the assignment loop.

```python
crew_by_id:    dict[str, CrewMember]              = {c.crew_id: c for c in all_crew}
ftl_by_id:     dict[str, CrewFlightTimeLimitsState] = {f.crew_id: f for f in all_ftl_states}
licenses_by_crew: dict[str, list[CrewLicense]]    = defaultdict(list)
for lic in all_licenses:
    licenses_by_crew[lic.crew_id].append(lic)

leave_by_crew: dict[str, list[CrewLeaveRecord]]   = defaultdict(list)
for leave in all_leave_records:
    leave_by_crew[leave.crew_id].append(leave)
```

---

## Legality Checker

The legality checker is a pure function. It takes a crew member, a leg, and a (possibly simulated) FTL state. Returns `(passed: bool, reason: str | None)`. No side effects, no DB calls.

It is used in three places:
- Job A Pass 1 — with simulated FTL state (future projection)
- Job A Pass 3 — full horizon replay with simulated FTL state
- Job B — with live FTL state from DB

### Input

```python
def check_legality(
    crew: CrewMember,
    leg: FlightLeg,
    ftl: CrewFlightTimeLimitsState,
    licenses: list[CrewLicense],
    leave_records: list[CrewLeaveRecord],
    leg_date: date,
) -> tuple[bool, str | None]:
```

### 11 Gates — in order of cheapest to most expensive check

```
Gate 1 — Employment status
  crew.employment_status == "ACTIVE"
  fail reason: "INACTIVE_CREW"

Gate 2 — Role match
  Pass 1 runs separate pools for pilots and cabin — this gate is enforced by pool separation, not a field check
  Pilots only evaluated against pilot slots, cabin only against cabin slots
  fail reason: "ROLE_MISMATCH" (used by Job B validator which checks existing assignments)

Gate 3 — Aircraft type rating
  any(lic.aircraft_type == leg.aircraft_type for lic in licenses)
  fail reason: "NO_TYPE_RATING"

Gate 4 — License not expired
  license for this aircraft_type: lic.expiry_date >= leg_date
  fail reason: "LICENSE_EXPIRED"

Gate 5 — Medical not expired
  license.medical_expiry >= leg_date  (medical is stored on the license record)
  fail reason: "MEDICAL_EXPIRED"

Gate 6 — Not on leave
  no leave record where start_date <= leg_date <= end_date
  fail reason: "ON_LEAVE"

Gate 7 — FTL status allows duty
  ftl.status in ("AVAILABLE", "RESTING")
  if RESTING: leg.scheduled_departure >= ftl.earliest_checkout
  fail reason: "IN_REST_PERIOD" or "FTL_UNAVAILABLE"

Gate 8 — Duty period will not be breached
  leg_duration_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600
  report_hour = leg.scheduled_departure.hour  (hour crew first reported for this duty period)
  limit = max_duty_hours(report_hour, sectors=ftl.sectors_current_duty + 1)
  check: ftl.flight_hours_current_duty + leg_duration_hours <= limit
  fail reason: "DUTY_PERIOD_BREACH"

Gate 9 — 7-day duty hours cap
  ftl.duty_hours_7_day + leg_duration_hours <= 60
  fail reason: "7_DAY_CAP_BREACH"

Gate 10 — 28-day flight hours cap
  ftl.flight_hours_28_day + leg_duration_hours <= 100
  fail reason: "28_DAY_CAP_BREACH"

Gate 11 — Consecutive duty days cap
  ftl.consecutive_duty_days < 6
  fail reason: "CONSECUTIVE_DAYS_CAP"
```

### Duty Period Limits Table

```python
# rules/duty_period_limits.py

# max_duty_hours[duty_start_window][sectors_in_duty]
# duty_start_window: "night", "morning", "afternoon", "evening"
# sectors capped at 4 — beyond 4 sectors the limit does not reduce further

_MAX_DUTY_HOURS = {
    "night":     {1: 11.0, 2: 10.5, 3: 10.0, 4: 9.5},
    "morning":   {1: 13.0, 2: 12.5, 3: 12.0, 4: 11.5},
    "afternoon": {1: 12.0, 2: 11.5, 3: 11.0, 4: 10.5},
    "evening":   {1: 11.5, 2: 11.0, 3: 10.5, 4: 10.0},
}

# Duty start time windows:
#   night     = 00:00 – 05:59  (body clock at lowest — tightest limits)
#   morning   = 06:00 – 13:59  (peak alertness — highest limits)
#   afternoon = 14:00 – 17:59  (post-lunch dip — moderate limits)
#   evening   = 18:00 – 23:59  (winding down — moderate-low limits)
#
# Each additional sector reduces the limit by 30 minutes.
# Example: morning start, 1 sector = 13h. morning start, 4 sectors = 11h 30m.

def _duty_start_window(report_hour: int) -> str:
    if report_hour < 6:   return "night"
    if report_hour < 14:  return "morning"
    if report_hour < 18:  return "afternoon"
    return "evening"

def max_duty_hours(report_hour: int, sectors: int) -> float:
    window = _duty_start_window(report_hour)
    capped_sectors = min(max(sectors, 1), 4)
    return _MAX_DUTY_HOURS[window][capped_sectors]
```

---

## FTL State Simulator

Job A needs to simulate FTL state forward in time without touching the database. The simulator is a pure in-memory copy of the FTL state that advances as legs are assigned.

```python
# Deepcopy the real FTL state at the start of Job A
# Advance it as each leg is assigned in Pass 1

def simulate_leg_assigned(
    ftl: CrewFlightTimeLimitsState,
    leg: FlightLeg,
) -> CrewFlightTimeLimitsState:
    """
    Returns a new FTL state after assigning this leg.
    Does not mutate the input.
    """
    leg_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600

    new = ftl.model_copy(deep=True)
    new.flight_hours_current_duty += leg_hours
    new.sectors_current_duty      += 1
    new.flight_hours_28_day       += leg_hours
    new.duty_hours_7_day          += leg_hours
    new.duty_hours_28_day         += leg_hours
    new.current_airport            = leg.destination_icao

    # Increment consecutive duty days only when this leg is on a new calendar day
    leg_day = leg.scheduled_departure.date()
    last_duty_day = ftl.duty_start_time.date() if ftl.duty_start_time else None
    if last_duty_day is None or leg_day > last_duty_day:
        new.consecutive_duty_days += 1

    # Project duty period end
    report_hour = leg.scheduled_departure.hour
    sectors     = new.sectors_current_duty
    limit = max_duty_hours(report_hour, sectors)
    if new.duty_start_time is None:
        new.duty_start_time = leg.scheduled_departure
    new.projected_duty_period_end = new.duty_start_time + timedelta(hours=limit)

    return new


def simulate_rest_after_leg(
    ftl: CrewFlightTimeLimitsState,
    leg: FlightLeg,
) -> CrewFlightTimeLimitsState:
    """
    Returns FTL state after rest following this leg.
    Resets current duty counters. Advances rest clock.
    Min rest = max(duty_duration, 11h flat floor).
    """
    duty_duration = (
        (leg.scheduled_arrival - ftl.duty_start_time).total_seconds() / 3600
        if ftl.duty_start_time else 0.0
    )
    min_rest = max(duty_duration, 11.0)

    new = ftl.model_copy(deep=True)
    new.flight_hours_current_duty = 0.0
    new.sectors_current_duty      = 0
    new.duty_start_time           = None
    new.projected_duty_period_end = None
    new.status                    = "AVAILABLE"
    new.rest_start_time           = leg.scheduled_arrival + timedelta(minutes=30)
    new.earliest_checkout         = new.rest_start_time + timedelta(hours=min_rest)
    new.last_rest_end_time        = new.earliest_checkout
    return new
```

---

---

## Job A — Week-by-Week Planning Loop

Instead of fetching all legs for 7 weeks at once, the planner iterates one week at a time. Each week:
1. Fetches only that week's legs from the flight schedule
2. Runs all 3 passes against those legs
3. Commits that week's roster to DB
4. Carries the simulated FTL state forward into the next week

This means a failure in week 4 does not undo weeks 1–3. Each week is independently committed.

```python
def _run_build(self, start: date, end: date, triggered_by: str) -> None:
    # Fetch crew data once — shared across all weeks
    all_crew     = get_all_crew_members()
    all_licenses = get_all_licenses()
    all_leave    = get_all_leave_records()

    crew_by_id       = {c.crew_id: c for c in all_crew}
    licenses_by_crew = defaultdict(list)
    for lic in all_licenses:
        licenses_by_crew[lic.crew_id].append(lic)
    leave_by_crew = defaultdict(list)
    for leave in all_leave:
        leave_by_crew[leave.crew_id].append(leave)

    # Simulated FTL state starts from live state, carries forward week to week
    simulated_ftl = {f.crew_id: f.model_copy(deep=True) for f in get_all_crew_duty_states()}

    week_start = start
    while week_start <= end:
        week_end = min(week_start + timedelta(days=6), end)

        # Fetch only this week's legs
        legs = get_legs_for_date_range(week_start, week_end)

        if not legs:
            week_start += timedelta(weeks=1)
            continue

        assignments  = _pass1_assign_crew(legs, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)
        reserve_slots = _pass2_fill_reserve(legs, assignments, crew_by_id, simulated_ftl, week_start, week_end)
        failures     = _pass3_validate(legs, assignments, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)

        # Commit this week to DB — independent transaction per week
        _write_roster(assignments, reserve_slots, week_start, week_end, triggered_by)

        # Advance simulated FTL state for next week
        for leg in sorted(legs, key=lambda l: l.scheduled_departure):
            for crew_id in assignments.get(leg.leg_id, []):
                crew = crew_by_id.get(crew_id)
                if crew:
                    simulated_ftl[crew_id] = simulate_leg_assigned(simulated_ftl[crew_id], leg)

        week_start += timedelta(weeks=1)
```

---

## Re-Plan: Leg Already Has a PUBLISHED Assignment

When `build()` runs and finds a leg that already has a `roster_crew_assignment` with status `PUBLISHED`, the planner must check two things in order:

**Step 1 — Did the flight itself change?**

Compare the current leg from the flight schedule against what was planned. If the flight changed, emit `FlightDisruptedEvent`.

| What changed | disruption_type | Who handles it |
|-------------|----------------|---------------|
| Leg not found in schedule | `CANCELLATION` | Disruption Handler |
| Departure time shifted > 30 min | `SCHEDULE_CHANGE` | Disruption Handler |
| Aircraft type swapped | `AIRCRAFT_SWAP` | Disruption Handler |
| Route changed (origin/destination) | `ROUTE_CHANGE` | Disruption Handler |

**Step 2 — Is the assigned crew still legal?**

Only reached if the flight itself is unchanged. Run legality check on the existing crew. If it fails, emit `CrewDisruptedEvent`.

| What changed | reason | Who handles it |
|-------------|--------|---------------|
| New leave covers this leg | `LEAVE_ADDED` | Disruption Handler |
| License expired | `LICENSE_EXPIRED` | Disruption Handler |
| Medical expired | `MEDICAL_EXPIRED` | Disruption Handler |
| FTL hours will breach cap | `FTL_BREACH_PROJECTED` | Disruption Handler |
| Aircraft swapped + crew not rated | `AIRCRAFT_TYPE_CHANGED` | Disruption Handler |

**The rule:**

```
existing assignment found, status = PUBLISHED:

  Step 1 — check the flight
    current_leg = get_flight_leg(leg_id)
    if not current_leg:
        emit FlightDisruptedEvent(disruption_type="CANCELLATION", source="WEEKLY_PLANNER_REPLAN")
        mark assignment INVALIDATED
        continue
    if abs(current_leg.scheduled_departure - planned_departure) > 30min:
        emit FlightDisruptedEvent(disruption_type="SCHEDULE_CHANGE", source="WEEKLY_PLANNER_REPLAN")
        continue   ← do not overwrite, Disruption Handler takes over
    if current_leg.aircraft_type != planned_aircraft_type:
        emit FlightDisruptedEvent(disruption_type="AIRCRAFT_SWAP", source="WEEKLY_PLANNER_REPLAN")
        continue

  Step 2 — check the crew
    passed, reason = check_legality(crew, current_leg, live_ftl, licenses, leave, leg_date)
    if not passed:
        emit CrewDisruptedEvent(reason=reason, source="WEEKLY_PLANNER_REPLAN")
        continue   ← do not overwrite, Disruption Handler takes over

  if both checks pass:
    keep existing assignment unchanged
    skip re-assignment for this leg
```

**Key rule:** the planner emits the event and stops. It never overwrites a PUBLISHED assignment directly. The Disruption Handler receives the event and runs the full replacement pipeline with controller visibility.

**DRAFT assignments** (not yet approved) are overwritten silently — no event needed, no crew has been notified yet.

---

### Pass 1 — Assign operating crew to legs

```python
def _pass1_assign_crew(
    legs: list[FlightLeg],          # sorted by scheduled_departure asc
    crew_by_id: dict,
    ftl_by_id: dict,                # starts as live state, advanced in-memory as legs assigned
    licenses_by_crew: dict,
    leave_by_crew: dict,
    start: date,
    end: date,
    triggered_by: str,
) -> dict[str, list[str]]:          # leg_id → [crew_id, ...]
    """
    Returns assignments dict. Does not write to DB.
    ftl_by_id is mutated in-place (simulated forward).
    """
    assignments: dict[str, list[str]] = {}

    for leg in sorted(legs, key=lambda l: l.scheduled_departure):
        leg_date       = leg.scheduled_departure.date()
        need_pilots    = required_pilots(leg.aircraft_type)
        need_cabin     = required_cabin(leg.aircraft_type)

        pilot_candidates = []
        cabin_candidates = []

        for crew in crew_by_id.values():
            ftl = ftl_by_id.get(crew.crew_id)
            if ftl is None:
                continue
            passed, _ = check_legality(
                crew, leg, ftl,
                licenses_by_crew.get(crew.crew_id, []),
                leave_by_crew.get(crew.crew_id, []),
                leg_date,
            )
            if passed:
                score = _score_candidate(crew, ftl, leg)
                if crew.role == "PILOT":
                    pilot_candidates.append((score, crew, ftl))
                else:
                    cabin_candidates.append((score, crew, ftl))

        pilot_candidates.sort(key=lambda x: x[0], reverse=True)
        cabin_candidates.sort(key=lambda x: x[0], reverse=True)

        assigned = []
        for score, crew, ftl in pilot_candidates[:need_pilots] + cabin_candidates[:need_cabin]:
            assigned.append(crew.crew_id)
            ftl_by_id[crew.crew_id] = simulate_leg_assigned(ftl, leg)

        if len(assigned) < need_pilots + need_cabin:
            # Could not fill all seats — log the gap, do not fail the whole build
            # This leg will appear in the validation report as UNDERSTAFFED
            pass

        assignments[leg.leg_id] = assigned

    return assignments
```

### Candidate Scoring

Max possible score = 100. Four factors:

- **40 pts** — crew is already at the leg's departure airport. Biggest factor — avoids a deadhead positioning flight.
- **30 pts** — scaled by fatigue. A crew at 0% fatigue gets full 30, at 100% fatigue gets 0.
- **20 pts** — crew is at their home base. They know the airport, no hotel logistics.
- **10 pts** — this leg's destination is the crew's home base, or crew is already home. Biases planner toward assignments that bring crew home rather than stranding them further away.
- **-10 pts** — crew is already away from home base AND this leg takes them further away (destination is also not home). Penalises chaining assignments that leave crew stranded far from home at week end.

Note: the planner does not guarantee crew return home — the flight schedule may not have a convenient return leg. The scoring only biases toward it.

```python
def _score_candidate(
    crew: CrewMember,
    ftl: CrewFlightTimeLimitsState,
    leg: FlightLeg,
) -> float:
    fatigue  = _fatigue_score(ftl)
    score    = 0.0
    score   += 40.0 if ftl.current_airport == leg.origin_icao else 0          # already at departure airport
    score   += 30.0 * (1 - fatigue / 100)                                      # lower fatigue = higher score
    score   += 20.0 if ftl.current_airport == crew.home_base else 0            # at home base
    score   += 10.0 if leg.destination_icao == crew.home_base else 0           # leg brings crew home
    if ftl.current_airport != crew.home_base and leg.destination_icao != crew.home_base:
        score -= 10.0                                                           # already away, going further away
    return score


def _fatigue_score(ftl: CrewFlightTimeLimitsState) -> float:
    score  = min(ftl.flight_hours_current_duty * 5, 55)
    score += min(ftl.consecutive_duty_days * 10,    20)
    score += min(ftl.flight_hours_28_day / 5,       25)
    return min(score, 100.0)
```

### Crew Requirements Per Aircraft Type

Crew requirements are a static internal rule — not from the flight schedule, not from the DB.
Pilots are always 2 (1 Captain + 1 First Officer) regardless of aircraft type.
Cabin count is set by the aircraft type based on minimum regulatory requirements per number of exits.

```python
# rules/crew_requirements.py

_REQUIREMENTS = {
    # aircraft_type → (pilots, cabin)
    # pilots: always 2 — 1 Captain + 1 First Officer, fixed by regulation
    # cabin: minimum per aircraft exits — A320/B737 have 4 exits, B787 has 8
    "A320": (2, 3),
    "B737": (2, 3),
    "B787": (2, 6),
}

def required_pilots(aircraft_type: str) -> int:
    return _REQUIREMENTS.get(aircraft_type, (2, 3))[0]

def required_cabin(aircraft_type: str) -> int:
    return _REQUIREMENTS.get(aircraft_type, (2, 3))[1]
```

### Pass 2 — Fill reserve slots

```python
def _pass2_fill_reserve(
    legs: list[FlightLeg],
    assignments: dict[str, list[str]],   # from Pass 1
    crew_by_id: dict,
    ftl_by_id: dict,
    start: date,
    end: date,
) -> list[dict]:
    """
    For each date × base airport, find crew not on operating duties that day.
    Returns list of reserve slot dicts to be written to crew_reserve_schedule.
    """
    reserve_slots = []
    assigned_crew_by_date: dict[date, set[str]] = defaultdict(set)

    for leg in legs:
        leg_date = leg.scheduled_departure.date()
        for crew_id in assignments.get(leg.leg_id, []):
            assigned_crew_by_date[leg_date].add(crew_id)

    airports = {c.home_base for c in crew_by_id.values()}

    for current_date in _date_range(start, end):
        for airport in airports:
            on_duty = assigned_crew_by_date.get(current_date, set())
            available_for_reserve = [
                crew for crew in crew_by_id.values()
                if crew.home_base == airport
                and crew.crew_id not in on_duty
                and ftl_by_id.get(crew.crew_id, CrewFlightTimeLimitsState(
                    crew_id=crew.crew_id, role=crew.role,
                    home_base=crew.home_base, current_airport=crew.home_base
                )).status == "AVAILABLE"
            ]
            for crew in available_for_reserve:
                reserve_slots.append({
                    "reserve_id": f"RSV-{crew.crew_id}-{current_date.isoformat()}",
                    "crew_id": crew.crew_id,
                    "date": current_date,
                    "standby_start": datetime.combine(current_date, time(6, 0)),
                    "standby_end":   datetime.combine(current_date, time(22, 0)),
                    "base_airport":  airport,
                    "callable_within": 120,
                    "status": "SCHEDULED",
                })

    return reserve_slots
```

### Pass 3 — Full horizon validation

```python
def _pass3_validate(
    legs: list[FlightLeg],
    assignments: dict[str, list[str]],
    crew_by_id: dict,
    ftl_by_id: dict,                    # simulated state after Pass 1
    licenses_by_crew: dict,
    leave_by_crew: dict,
) -> list[dict]:
    """
    Replays every crew member's full plan through the legality checker.
    Returns list of validation failures.
    Each failure: {crew_id, leg_id, reason, leg_date}
    """
    failures = []

    for leg in sorted(legs, key=lambda l: l.scheduled_departure):
        leg_date = leg.scheduled_departure.date()
        for crew_id in assignments.get(leg.leg_id, []):
            crew = crew_by_id.get(crew_id)
            ftl  = ftl_by_id.get(crew_id)
            if not crew or not ftl:
                continue
            passed, reason = check_legality(
                crew, leg, ftl,
                licenses_by_crew.get(crew_id, []),
                leave_by_crew.get(crew_id, []),
                leg_date,
            )
            if not passed:
                failures.append({
                    "crew_id": crew_id,
                    "leg_id":  leg.leg_id,
                    "reason":  reason,
                    "leg_date": leg_date,
                })

    return failures
```

### Writing to Database

```python
def _write_roster(
    assignments: dict[str, list[str]],
    reserve_slots: list[dict],
    start: date,
    end: date,
    triggered_by: str,
    session: Session,
) -> None:
    for leg_id, crew_ids in assignments.items():
        # Write roster_leg row
        roster_repository.upsert_roster_leg(session, {
            "leg_id":       leg_id,
            "plan_start":   start,
            "plan_end":     end,
            "status":       "DRAFT",
            "triggered_by": triggered_by,
        })
        # Write one roster_crew_assignment row per crew member
        for crew_id in crew_ids:
            roster_repository.upsert_roster_crew_assignment(session, {
                "leg_id":      leg_id,
                "crew_id":     crew_id,
                "status":      "DRAFT",
                "assigned_by": triggered_by,
            })

    for slot in reserve_slots:
        reserve_repository.insert_reserve_schedule(session, CrewReserveSchedule(**slot))

    session.commit()
```

### Edge Cases — Job A

| Situation | Handling |
|-----------|---------|
| No legal crew found for a leg | Assign what is available (even if understaffed), mark leg as `UNDERSTAFFED` in roster_leg, include in validation report |
| All crew on leave for a date | Same as above — flag, do not crash the build |
| `end < start` passed by API | Raise `ValueError` before any DB call — already handled in `build()` |
| Leg already has assignments from a previous build | `upsert_roster_leg` with `ON CONFLICT (leg_id, plan_start) DO UPDATE` — overwrites previous draft |
| Pass 3 finds failures | Do not block the write — write the draft, include failures in the return value so the controller sees them before approving |
| DB write fails mid-way | Wrap entire write in a single transaction — roll back on any error, return error to caller |
| Same crew assigned to two overlapping legs | Prevented by Pass 1 — once a crew is assigned to a leg, their simulated FTL state advances and the rest check (Gate 7) will block them from the next overlapping leg |

---

## Job B — Daily Validator

Runs every morning at 3AM. Also triggered by `RosterModifiedEvent`.

**What it validates:** every future `DRAFT` or `CONFIRMED` crew assignment — re-checks whether each assigned crew member is still legally allowed to operate their leg using live data, not simulated. It never fixes anything itself — if legality fails it emits `CrewDisruptedEvent` and the Disruption Handler takes over.

```python
def _run_validation(
    triggered_by: str,
    crew_id: str | None = None,   # if set, only validate this crew member's future legs
) -> None:
    today = date.today()

    # Fetch all data fresh — this is a live check, not simulated
    all_crew        = get_all_crew_members()
    all_licenses    = get_all_licenses()
    all_leave       = get_all_leave_records()
    all_ftl_states  = get_all_crew_duty_states()

    crew_by_id      = {c.crew_id: c for c in all_crew}
    ftl_by_id       = {f.crew_id: f for f in all_ftl_states}
    licenses_by_crew: dict = defaultdict(list)
    for lic in all_licenses:
        licenses_by_crew[lic.crew_id].append(lic)
    leave_by_crew: dict = defaultdict(list)
    for leave in all_leave:
        leave_by_crew[leave.crew_id].append(leave)

    # Fetch and process assignments 2 days at a time — avoids holding full 7-week window in memory
    current = today
    with SessionLocal() as session:
        while True:
            batch_end = current + timedelta(days=1)
            batch = roster_repository.get_future_assignments(
                session, from_date=current, to_date=batch_end, crew_id=crew_id
            )
            if not batch:
                break

            for assignment in batch:
                leg  = get_flight_leg(assignment["leg_id"])
                crew = crew_by_id.get(assignment["crew_id"])
                ftl  = ftl_by_id.get(assignment["crew_id"])

                if not leg or not crew or not ftl:
                    continue

                leg_date = leg.scheduled_departure.date()
                passed, reason = check_legality(
                    crew, leg, ftl,
                    licenses_by_crew.get(assignment["crew_id"], []),
                    leave_by_crew.get(assignment["crew_id"], []),
                    leg_date,
                )

                if not passed:
                    days_until = (leg_date - today).days
                    event_bus.publish(CrewDisruptedEvent(
                        crew_id              = assignment["crew_id"],
                        crew_name            = crew.full_name,
                        leg_id               = assignment["leg_id"],
                        reason               = reason,
                        days_until_departure = days_until,
                        severity             = _classify_severity(days_until),
                        source               = "WEEKLY_PLANNER_VALIDATOR",
                        detected_at          = datetime.now(timezone.utc),
                    ))

            current = batch_end + timedelta(days=1)


def _classify_severity(days_until_departure: int) -> str:
    if days_until_departure < 2:  return "CRITICAL"
    if days_until_departure < 7:  return "HIGH"
    if days_until_departure < 14: return "MEDIUM"
    return "LOW"
```

### Edge Cases — Job B

| Situation | Handling |
|-----------|---------|
| Leg no longer exists in flight schedule | Skip — leg was cancelled, assignment is stale. Mark assignment as `INVALIDATED` |
| Crew member no longer active | Gate 1 catches it — emit `CrewDisruptedEvent(reason="INACTIVE_CREW")` |
| FTL state missing for a crew member | Skip that crew member, log warning — do not crash the full validation run |
| Same crew member has 10 future legs all now invalid | Emit one `CrewDisruptedEvent` per leg — Disruption Handler handles each independently |
| `RosterModifiedEvent` arrives with `added_crew_id = None` | Only validate `removed_crew_id`'s future legs — guard against None before querying |
| Validator runs while Job A build is in progress | Both read from DB, neither blocks the other. Validator may see a partially written draft — acceptable, it will re-run next morning |

---

---

## Roster Repository

New file: `db/repositories/roster_repository.py`

```python
def upsert_roster_leg(session: Session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO roster_leg (leg_id, plan_start, plan_end, status, triggered_by)
        VALUES (:leg_id, :plan_start, :plan_end, :status, :triggered_by)
        ON CONFLICT (leg_id, plan_start) DO UPDATE SET
            status       = EXCLUDED.status,
            triggered_by = EXCLUDED.triggered_by,
            updated_at   = NOW()
    """), data)


def upsert_roster_crew_assignment(session: Session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO roster_crew_assignment (leg_id, crew_id, status, assigned_by)
        VALUES (:leg_id, :crew_id, :status, :assigned_by)
        ON CONFLICT (leg_id, crew_id) DO UPDATE SET
            status      = EXCLUDED.status,
            assigned_by = EXCLUDED.assigned_by,
            assigned_at = NOW()
    """), data)


def replace_roster_crew_assignment(session: Session, leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> None:
    session.execute(text("""
        UPDATE roster_crew_assignment
        SET status = 'REPLACED', replaced_by = :new_crew_id, replaced_at = NOW()
        WHERE leg_id = :leg_id AND crew_id = :old_crew_id
    """), {"leg_id": leg_id, "old_crew_id": old_crew_id, "new_crew_id": new_crew_id})
    session.execute(text("""
        INSERT INTO roster_crew_assignment (leg_id, crew_id, status, assigned_by)
        VALUES (:leg_id, :crew_id, 'CONFIRMED', :assigned_by)
        ON CONFLICT (leg_id, crew_id) DO UPDATE SET
            status = 'CONFIRMED', assigned_by = EXCLUDED.assigned_by, assigned_at = NOW()
    """), {"leg_id": leg_id, "crew_id": new_crew_id, "assigned_by": requested_by})


def approve_roster_leg(session: Session, leg_id: str, approved_by: str) -> None:
    session.execute(text("""
        UPDATE roster_leg SET status = 'PUBLISHED', updated_at = NOW()
        WHERE leg_id = :leg_id
    """), {"leg_id": leg_id})
    session.execute(text("""
        UPDATE roster_crew_assignment SET status = 'CONFIRMED', assigned_by = :approved_by
        WHERE leg_id = :leg_id AND status = 'DRAFT'
    """), {"leg_id": leg_id, "approved_by": approved_by})


def get_future_assignments(
    session: Session, from_date: date, to_date: date, crew_id: str | None = None
) -> list[dict]:
    query = """
        SELECT rca.leg_id, rca.crew_id, rca.status
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE fl.scheduled_departure::date BETWEEN :from_date AND :to_date
          AND rca.status IN ('DRAFT', 'CONFIRMED')
    """
    params: dict = {"from_date": from_date, "to_date": to_date}
    if crew_id:
        query += " AND rca.crew_id = :crew_id"
        params["crew_id"] = crew_id
    rows = session.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


def get_assignments_for_crew_in_range(session: Session, crew_id: str, from_date: date, to_date: date) -> list[dict]:
    rows = session.execute(text("""
        SELECT rca.leg_id, fl.scheduled_departure
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE rca.crew_id = :crew_id
          AND fl.scheduled_departure::date BETWEEN :from_date AND :to_date
          AND rca.status IN ('DRAFT', 'CONFIRMED')
    """), {"crew_id": crew_id, "from_date": from_date, "to_date": to_date}).mappings().all()
    return [dict(row) for row in rows]


def get_roster_for_date_range(session: Session, start: date, end: date) -> list[dict]:
    rows = session.execute(text("""
        SELECT rca.leg_id, rca.crew_id, rca.status, rca.assigned_by,
               fl.scheduled_departure, fl.origin_iata, fl.destination_iata,
               fl.aircraft_type, fl.flight_number
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE fl.scheduled_departure::date BETWEEN :start AND :end
        ORDER BY fl.scheduled_departure
    """), {"start": start, "end": end}).mappings().all()
    return [dict(row) for row in rows]

---

## API Endpoints

```
POST /planner/build
  body: { requested_by, start?, end? }
  → calls RosterPlanner.build()
  → returns: { status, start, end, requested_by }

POST /planner/validate
  body: { requested_by }
  → calls DailyValidator.validate()
  → returns: { status, requested_by }

GET /planner/roster?start=YYYY-MM-DD&end=YYYY-MM-DD
  → returns all assignments in the date range
  → used by controller to review the draft before approving

POST /planner/roster/{leg_id}/approve
  body: { approved_by }
  → updates roster_leg.status = PUBLISHED
  → updates all roster_crew_assignment.status = CONFIRMED for this leg

POST /planner/roster/{leg_id}/reassign
  body: { crew_id, replaced_by, reason, requested_by }
  → manual crew swap on an existing assignment
  → runs legality check on new crew before making any change
  → if legality fails: return 400 with reason, no change made
  → if legality passes:
      old crew row → status = REPLACED, replaced_by = new crew_id
      new crew row → status = CONFIRMED, assigned_by = requested_by
  → publishes RosterModifiedEvent(added_crew_id, removed_crew_id, leg_id)
  → DailyValidator re-validates future legs for both crew members automatically
```

---

## Scheduler Wiring (already in `api/main.py`)

```python
# Job A — every Sunday at 23:00
scheduler.add_job(
    roster_planner.build,
    CronTrigger(day_of_week="sun", hour=23, minute=0),
    id="roster_build",
)

# Job B — every morning at 03:00
scheduler.add_job(
    daily_validator.validate,
    CronTrigger(hour=3, minute=0),
    id="daily_validation",
)
```

Both are already registered. No changes needed here. The jobs will work once the service methods are implemented.

---

## End to End Test

```bash
# Start server
uv run uvicorn crew_ops.api.main:app --reload --port 8000

# Trigger a manual build
curl -X POST http://localhost:8000/planner/build \
  -H "Content-Type: application/json" \
  -d '{"requested_by": "test_manager"}'

# Check what was written
docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, status, triggered_by FROM roster_leg LIMIT 10;"

docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, crew_id, status FROM roster_crew_assignment LIMIT 20;"

# Trigger a manual validation
curl -X POST http://localhost:8000/planner/validate \
  -H "Content-Type: application/json" \
  -d '{"requested_by": "test_manager"}'
```

---

---

## Manual Roster Change

When a manager wants to manually swap a crew member on an already-planned leg.

### Flow

```
Manager calls POST /planner/roster/{leg_id}/reassign
  body: { crew_id, replaced_by, reason, requested_by }

Step 1 — Legality check on new crew
  check_legality(new_crew, leg, ftl, licenses, leave, leg_date)
  if fails → return 400 with reason, stop here, no change made

Step 2 — Update roster_crew_assignment
  old crew row → status = REPLACED, replaced_by = new_crew_id, replaced_at = now
  new crew row → INSERT with status = CONFIRMED, assigned_by = requested_by

Step 3 — Publish RosterModifiedEvent
  added_crew_id   = new crew_id
  removed_crew_id = old crew_id
  leg_id          = leg_id

Step 4 — DailyValidator picks up RosterModifiedEvent automatically
  re-validates all future legs for both removed and added crew
  if anything breaks → emits CrewDisruptedEvent per affected leg
```

### Key Rules

- Manager cannot assign crew who fail legality check — API blocks it before any DB write
- Works on both DRAFT and PUBLISHED assignments
- Replacing crew always emits `RosterModifiedEvent` — validator re-checks both crew members' full future schedule automatically
- Manager never writes directly to `roster_crew_assignment` — always goes through the service which runs legality check first

---

## What the Planner Does NOT Do

These are explicitly out of scope for this service. Documenting to avoid scope creep.

| Not the planner's job | Who handles it |
|-----------------------|---------------|
| Detect live flight delays | Observer |
| Fix a disruption after it is detected | Disruption Handler |
| Update FTL state after a leg lands | FTL Service |
| Send notifications to crew | Notification service (not yet built) |
| Approve the roster | Controller via API — human decision |
| Calculate actual duty hours after flight | FTL Service |
| Handle crew sick calls on the day | Ops Desk via `POST /crew/{id}/unavailable` |

---

## Component 2 — Observer

# Observer — End to End Implementation

---

## What This Service Does

The Observer is responsible for one thing: **watch live flight status for today's active legs and publish events when something changes**.

It never fixes anything. It never touches crew data. It only detects what is happening to flights right now and tells the rest of the system about it.

Two outputs:

1. **`FlightDisruptedEvent`** — flight is delayed or cancelled. Disruption Handler picks this up and re-checks crew legality.
2. **`LegCompletedEvent`** — flight has landed. FTL Service picks this up to update crew duty hours.

The Observer only watches **today's legs**. Future flight changes (aircraft swap, schedule change, route change, cancellation before the day of operation) are detected by the **Weekly Planner re-plan**, not the Observer.

---

## Current State of the Codebase

### What exists

| File | Status |
|------|--------|
| `services/observer/observer_service.py` | ✅ Complete — delay threshold fixed, `poll()`, `get_todays_active_legs()`, `get_legs()` all implemented |
| `api/routers/observer_router.py` | ✅ Complete |
| `clients/flight_status_client.py` | ✅ Complete |
| `clients/flight_schedule_client.py` | ✅ Complete |
| `models/events.py` | ✅ Complete |
| `services/event_bus.py` | ✅ Complete |
| `api/main.py` | ✅ Observer polling loop registered in scheduler |

### What is missing

Nothing — all files are complete.

---

## Responsibility Boundary

This is the most important thing to understand about the Observer.

| Disruption type | Who detects it | Why |
|----------------|---------------|-----|
| `DELAY` | Observer | Comes from live status API — flight is airborne or at gate with a delay |
| `CANCELLATION` (day of) | Observer | Comes from live status API — flight cancelled on the day |
| `CANCELLATION` (future) | Weekly Planner re-plan | Leg disappears from schedule during weekly re-plan |
| `AIRCRAFT_SWAP` | Weekly Planner re-plan | Aircraft type change detected by comparing schedule vs planned roster |
| `SCHEDULE_CHANGE` | Weekly Planner re-plan | Departure time shift > 30 min detected during re-plan |
| `ROUTE_CHANGE` | Weekly Planner re-plan | Origin or destination changed during re-plan |
| Crew legality breach | Weekly Planner Validator (Job B) | Runs legality check on all future assignments every morning at 3AM |
| Crew sick call / no-show / medical | Ops Desk | Human marks crew unavailable via `POST /crew/{id}/unavailable` — publishes `CrewDisruptedEvent` |
| Leave added covering assigned leg | Leave Client | `add_leave_record()` auto-publishes `CrewDisruptedEvent(reason=LEAVE_ADDED)` per affected leg — no human needed |

The Observer does **not** detect `AIRCRAFT_SWAP`, `SCHEDULE_CHANGE`, or `ROUTE_CHANGE` because those are schedule-level changes, not operational status changes. The live status API only reports what is happening to a flight right now — it does not compare against what was previously planned.

---

## Events the Observer Publishes

### `FlightDisruptedEvent`

```python
FlightDisruptedEvent(
    leg_id              = "AI101-VIDP-EGLL-20240205",
    flight_number       = "AI101",
    origin              = "VIDP",
    destination         = "EGLL",
    disruption_type     = "DELAY",        # DELAY / CANCELLATION — only these two from Observer
    severity            = "HIGH",
    scheduled_departure = datetime(...),
    actual_departure    = datetime(...),
    delay_minutes       = 95,
    assigned_crew       = ["C-001", "C-002", "C-011", "C-012"],
    detected_at         = datetime(...),
)
```

Consumed by: **Disruption Handler** — re-checks crew legality against new departure time, runs replacement flow if needed.

### `LegCompletedEvent`

```python
LegCompletedEvent(
    leg_id        = "AI101-VIDP-EGLL-20240205",
    actual_arrival = datetime(...),
    destination   = "EGLL",
    crew          = ["C-001", "C-002", "C-011", "C-012"],
    delay_minutes = 20,
)
```

Consumed by: **FTL Service** — updates crew duty hours, rest clock, and FTL state after landing.

---

## Delay Severity Mapping

```python
_SEVERITY_THRESHOLDS = [
    (240, "HIGH"),
    (120, "MEDIUM"),
    (30,  "LOW"),
]
```

| Delay | Severity | Meaning |
|-------|----------|---------|
| ≥ 240 min | HIGH | Major delay — crew FTL breach very likely |
| ≥ 120 min | MEDIUM | Significant delay — FTL breach possible |
| ≥ 30 min | LOW | Minor delay — FTL breach unlikely but must still be checked |
| < 30 min | LOW (floored) | Any delay published — Disruption Handler re-checks legality and takes no action if crew still pass |

Cancellation is always `CRITICAL` regardless of notice time — crew must be released immediately.

---

## Poll Flow — Step by Step

```
Scheduler calls poll(leg) for each active leg
        ↓
Step 1 — Fetch next live status from flight_status_client
  result = get_next_live_status_poll(leg.leg_id)
  if no result → skip (no new data)

        ↓
Step 2 — What is the flight status?

  "landed":
    → reset poll index for this leg (stop polling it)
    → publish LegCompletedEvent
    → done

  "cancelled":
    → publish FlightDisruptedEvent(disruption_type=CANCELLATION, severity=CRITICAL)
    → done

  delay > 0:
    → map delay_minutes to severity, floor at LOW if < 30 min
    → always publish FlightDisruptedEvent(disruption_type=DELAY)
    → Disruption Handler re-checks crew legality and decides whether action is needed
```

---

## Known Issues

None — all previously identified issues are resolved.

---

## Full Service Implementation

```python
# services/observer/observer_service.py

from crew_ops.clients.flight_status_client import get_next_live_status_poll, reset_poll_index_for_leg
from crew_ops.clients.flight_schedule_client import get_all_scheduled_legs
from crew_ops.models.events import FlightDisruptedEvent, LegCompletedEvent
from crew_ops.models.flight_leg import FlightLeg
from crew_ops.services.event_bus import event_bus
from datetime import date, datetime, timedelta, timezone


_SEVERITY_THRESHOLDS = [
    (240, "HIGH"),
    (120, "MEDIUM"),
    (30,  "LOW"),
]


class FlightObserver:

    # ─── Live today (automatic) ───────────────────────────────────────────────

    def get_todays_active_legs(self) -> list[FlightLeg]:
        """Returns today's legs with crew assigned. Used by the automated polling loop."""
        return self.get_legs(date.today(), assigned_crew_only=True)

    def poll(self, leg: FlightLeg) -> None:
        """
        Poll live status for one leg and publish the resulting event to the bus.
        Consumers (DisruptionHandler, FTL Service) react via their subscriptions.
        """
        result = get_next_live_status_poll(leg.leg_id)
        if not result:
            return

        status = result.get("flight_status")

        if status == "landed":
            reset_poll_index_for_leg(leg.leg_id)
            event_bus.publish(LegCompletedEvent(
                leg_id=leg.leg_id,
                actual_arrival=result["arrival"]["actual"],
                destination=result["arrival"]["iata"],
                crew=leg.assigned_crew,
                delay_minutes=result["arrival"].get("delay") or 0,
            ))
            return

        if status == "cancelled":
            event_bus.publish(self._build_disruption_event(leg, result, "CANCELLATION", "CRITICAL"))
            return

        delay = result["departure"].get("delay") or 0
        if delay > 0:
            severity = self._delay_severity(delay) or "LOW"   # floor at LOW — never drop any delay
            event_bus.publish(self._build_disruption_event(leg, result, "DELAY", severity))

    # ─── Manager date view (manual) ───────────────────────────────────────────

    def get_legs(
        self,
        target_date: date | None = None,
        offset: int | None = None,
        assigned_crew_only: bool = False,
    ) -> list[FlightLeg]:
        """
        Returns scheduled legs for a given date — read-only, no polling.

        Provide either target_date or offset, not both.
          target_date → exact date
          offset      → days from today (1 = tomorrow, 2 = day after, 7 = next week)
        """
        if target_date is not None and offset is not None:
            raise ValueError("provide either target_date or offset, not both")
        if target_date is None and offset is None:
            raise ValueError("provide either target_date or offset")

        resolved_date = target_date if target_date is not None else date.today() + timedelta(days=offset)
        all_legs = get_all_scheduled_legs()
        legs = [leg for leg in all_legs if leg.scheduled_departure.date() == resolved_date]
        if assigned_crew_only:
            legs = [leg for leg in legs if leg.assigned_crew]
        return legs

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _delay_severity(self, delay_minutes: int) -> str | None:
        for threshold, severity in _SEVERITY_THRESHOLDS:
            if delay_minutes >= threshold:
                return severity
        return None

    def _build_disruption_event(
        self, leg: FlightLeg, poll: dict, disruption_type: str, severity: str
    ) -> FlightDisruptedEvent:
        return FlightDisruptedEvent(
            leg_id=leg.leg_id,
            flight_number=leg.flight_number,
            origin=leg.origin_iata,
            destination=leg.destination_iata,
            disruption_type=disruption_type,
            severity=severity,
            scheduled_departure=leg.scheduled_departure,
            actual_departure=poll["departure"].get("actual"),
            delay_minutes=poll["departure"].get("delay"),
            assigned_crew=leg.assigned_crew,
            detected_at=datetime.now(timezone.utc),
        )
```

---

## API Endpoints

```
GET /observer/legs/today
  → returns today's active legs that have crew assigned
  → used by the automated polling loop and controller dashboard

GET /observer/legs?target_date=YYYY-MM-DD
GET /observer/legs?offset=1
  → manager view — returns scheduled legs for a given date
  → read-only, no polling, no events published
  → use target_date OR offset, not both
```

---

## Scheduler Wiring

Registered in `api/main.py`:

```python
from crew_ops.services.observer.observer_service import FlightObserver
from apscheduler.triggers.interval import IntervalTrigger

flight_observer = FlightObserver()

def _run_observer_poll():
    for leg in flight_observer.get_todays_active_legs():
        flight_observer.poll(leg)

scheduler.add_job(
    _run_observer_poll,
    IntervalTrigger(minutes=5),
    id="observer_poll",
)
```

---

## Edge Cases

| Situation | Handling |
|-----------|---------|
| Leg has no crew assigned | `get_todays_active_legs()` filters with `assigned_crew_only=True` — legs without crew are never polled |
| Live status API returns no data for a leg | `get_next_live_status_poll` returns `None` — `poll()` returns early, no event published |
| Delay < 30 min | Floored to LOW severity and published — Disruption Handler re-checks legality and takes no action if crew still pass |
| Same leg polled multiple times with same delay | Disruption Handler guards against duplicate proposals — if a PENDING proposal already exists for the same `leg_id` + `removed_crew_id`, it skips silently |
| Flight lands with a delay | `status == "landed"` branch fires first — publishes `LegCompletedEvent` with `delay_minutes` included. FTL Service uses actual arrival time, not scheduled |
| Flight cancelled after already being delayed | Observer will have already published a `FlightDisruptedEvent(DELAY)` on a previous poll. On the next poll it publishes `FlightDisruptedEvent(CANCELLATION)`. Disruption Handler invalidates all assignments and publishes `RosterModifiedEvent` per crew — the earlier delay proposal becomes stale and will be expired by the nightly expiry job |
| Leg departs before Observer polls it | `poll()` will get `status == "landed"` or no result — publishes `LegCompletedEvent` or nothing. No disruption event published for a leg that already departed |
| `assigned_crew` list is empty on the leg | `FlightDisruptedEvent(CANCELLATION)` still published. Disruption Handler calls `invalidate_roster_leg` — no crew rows to update, no `RosterModifiedEvent` published. Safe |
| Observer polls a leg that was cancelled by Weekly Planner re-plan | Weekly Planner marks assignments `INVALIDATED`. Observer publishes `FlightDisruptedEvent(CANCELLATION)`. Disruption Handler calls `invalidate_roster_leg` — assignments already `INVALIDATED`, UPDATE is a no-op |
| Two Observer poll results arrive out of order | Poll index is sequential per leg — out-of-order delivery not possible with current mock client |
| Polling loop crashes mid-run | Each `poll(leg)` call is independent — a crash on one leg does not affect others. Scheduler restarts the job on the next interval |

---

## Crew Disruption Entry Points

The Observer only watches flights. Crew disruptions enter the system from three separate places:

| Entry point | File | Trigger | reason |
|------------|------|---------|--------|
| Ops desk — sick call, no-show, medical, emergency leave | `api/routers/crew_router.py` `POST /crew/{id}/unavailable` | Human action | `SICK_CALL / NO_SHOW / MEDICAL_GROUNDING / EMERGENCY_LEAVE / URGENT_TRAINING` |
| Leave added covering assigned leg | `clients/leave_client.py` `add_leave_record()` | Automatic on any leave insert | `LEAVE_ADDED` |
| Weekly Planner Validator (Job B) | `services/weekly_planner/weekly_planner_service.py` | Runs at 3AM daily or on `RosterModifiedEvent` | Any legality gate failure |

All three publish `CrewDisruptedEvent` to the event bus. The Disruption Handler receives all of them via the same subscription.

---

## What the Observer Does NOT Do

| Not its job | Who handles it |
|-------------|---------------|
| Detect aircraft swaps | Weekly Planner re-plan |
| Detect schedule changes (departure time shift) | Weekly Planner re-plan |
| Detect route changes | Weekly Planner re-plan |
| Detect future cancellations | Weekly Planner re-plan |
| Re-check crew legality after a delay | Disruption Handler — reacts to `FlightDisruptedEvent` |
| Update FTL state after landing | FTL Service — reacts to `LegCompletedEvent` |
| Watch legs for future dates | Observer only watches today. Future dates are the Weekly Planner's domain |
| Send notifications to crew | Notification service (not yet built) |

---

## End to End Test

```bash
# Start server
uv run uvicorn crew_ops.api.main:app --reload --port 8000

# Check today's active legs
curl http://localhost:8000/observer/legs/today

# Check legs for a specific date
curl "http://localhost:8000/observer/legs?offset=1"

# Manually trigger a poll by hitting the scheduler or calling poll() directly
# Then check disruption proposals were created
curl http://localhost:8000/disruptions/proposals
```

---

## Component 3 — Disruption Handler

# Disruption Handler — End to End Implementation

---

## What This Service Does

The Disruption Handler is responsible for one thing: **when something breaks, find a replacement and present it to the controller**.

It never detects disruptions — that is the Observer's and Weekly Planner Validator's job. It only reacts to events that are already published.

Two types of disruptions it handles:

1. **Flight disrupted** — the flight itself changed (delay, cancellation, aircraft swap). Crew may need to be reassigned or released.
2. **Crew disrupted** — a specific crew member can no longer legally operate a leg (sick call, license expired, FTL breach, leave added).

Most paths end the same way: find the best available replacement, present to controller, await confirmation, publish `RosterModifiedEvent`.

Exception: **CANCELLATION** — no replacement is needed. All crew are released immediately, `roster_leg` and all assignments are invalidated, and `RosterModifiedEvent` is published per released crew member so the FTL Service can update their state.

---

## Current State of the Codebase

### What exists

| File | Status |
|------|--------|
| `services/disruption_handler/disruption_handler_service.py` | ✅ Complete — full implementation with all guards |
| `db/repositories/disruption_repository.py` | ✅ Complete |
| `db/repositories/roster_repository.py` | ✅ Complete — includes `invalidate_assignment`, `invalidate_roster_leg`, `replace_roster_crew_assignment` |
| `api/routers/disruption_router.py` | ✅ Complete — accept, reject, get proposals |
| `models/events.py` | ✅ Complete — `FlightDisruptedEvent`, `CrewDisruptedEvent`, `RosterModifiedEvent` all defined |
| `services/event_bus.py` | ✅ Complete |
| `api/main.py` | ✅ Event subscriptions registered, expiry job scheduled |
| `rules/legality.py` | ✅ Complete |
| `rules/ftl_simulator.py` | ✅ Complete |
| `docker/init.sql` | ✅ `disruption_proposals` table added |

### What is missing

Nothing — all files are complete.

---

## Events the Disruption Handler Receives

### `FlightDisruptedEvent`

Published by: Observer (live delay/cancellation), Weekly Planner (re-plan found flight changed)

```python
FlightDisruptedEvent(
    leg_id             = "AI101-VIDP-EGLL-20240205",
    flight_number      = "AI101",
    origin             = "VIDP",
    destination        = "EGLL",
    disruption_type    = "DELAY",           # DELAY / CANCELLATION / AIRCRAFT_SWAP / SCHEDULE_CHANGE / ROUTE_CHANGE
    severity           = "HIGH",
    scheduled_departure = datetime(...),
    actual_departure   = datetime(...),
    delay_minutes      = 95,
    assigned_crew      = ["C-001", "C-002", "C-011", "C-012"],
    detected_at        = datetime(...),
)
```

### `CrewDisruptedEvent`

Published by: Weekly Planner Validator, Weekly Planner Re-Plan, Ops Desk (sick call via API), Leave Client (leave added covering an assigned leg)

```python
CrewDisruptedEvent(
    crew_id              = "C-003",
    crew_name            = "Rahul Sharma",
    leg_id               = "AI305-VABB-VECC-20240205",
    reason               = "LICENSE_EXPIRED",   # see full list below
    days_until_departure = 2,
    severity             = "HIGH",
    source               = "WEEKLY_PLANNER_VALIDATOR",  # or "WEEKLY_PLANNER_REPLAN" or "OPS_DESK"
    detected_at          = datetime(...),
)
```

Possible `reason` values from legality checker (Gates 1–11):
```
INACTIVE_CREW
ROLE_MISMATCH
NO_TYPE_RATING
LICENSE_EXPIRED
MEDICAL_EXPIRED
ON_LEAVE
IN_REST_PERIOD
FTL_UNAVAILABLE
DUTY_PERIOD_BREACH
7_DAY_CAP_BREACH
28_DAY_CAP_BREACH
CONSECUTIVE_DAYS_CAP
```

Additional `reason` values emitted by Weekly Planner Re-Plan (not from legality gates — set directly by the planner before emitting):
```
LEAVE_ADDED             ← new leave record now covers this leg
FTL_BREACH_PROJECTED    ← FTL hours will breach a cap on this leg
AIRCRAFT_TYPE_CHANGED   ← aircraft swapped, crew not rated for new type
```

`LEAVE_ADDED` is also emitted by the **Leave Client** (`clients/leave_client.py`) when `add_leave_record()` is called and the leave window covers one or more assigned legs. This handles same-day leave without requiring manual ops desk intervention.

#### Leave Added — Full Flow

```
add_leave_record(leave_record) called
        ↓
Insert leave record into crew_leave_records table
        ↓
Query roster_crew_assignment JOIN flight_legs
  WHERE crew_id = leave_record.crew_id
    AND scheduled_departure BETWEEN start_date AND end_date
    AND status IN ('DRAFT', 'CONFIRMED')
        ↓
No assignments found → return, nothing to do
        ↓
Assignments found → fetch crew name from crew_profile_client
        ↓
For each affected leg:
  days_until = scheduled_departure.date() - today
  severity:
    < 1 day  → CRITICAL   (same-day leave)
    ≤ 2 days → HIGH
    ≤ 7 days → MEDIUM
    > 7 days → LOW
  publish CrewDisruptedEvent(
    reason   = "LEAVE_ADDED",
    source   = "OPS_DESK",
    severity = severity,
  )
        ↓
Disruption Handler receives CrewDisruptedEvent
  → validates leg exists, not departed, not cancelled
  → finds replacement candidates
  → creates PENDING proposal in disruption_proposals
        ↓
Controller sees proposal in GET /disruptions/proposals
  → accepts → roster swap + RosterModifiedEvent published
  → rejects → next candidate proposed
```

---

## Database Table — `disruption_proposals`

Stores each proposed replacement while it waits for controller confirmation. One row per disruption event.

```sql
CREATE TABLE IF NOT EXISTS disruption_proposals (
    id                  SERIAL          PRIMARY KEY,
    proposal_id         VARCHAR(50)     NOT NULL UNIQUE,
    leg_id              VARCHAR(50)     NOT NULL REFERENCES flight_legs(leg_id),
    disruption_type     VARCHAR(20)     NOT NULL,   -- FLIGHT_DISRUPTED / CREW_DISRUPTED
    disruption_reason   VARCHAR(50)     NOT NULL,   -- from event
    removed_crew_id     VARCHAR(10)     REFERENCES crew_members(crew_id),
    proposed_crew_id    VARCHAR(10)     REFERENCES crew_members(crew_id),
    proposal_score      FLOAT           NOT NULL DEFAULT 0.0,
    status              VARCHAR(15)     NOT NULL DEFAULT 'PENDING',
    -- PENDING   → waiting for controller decision
    -- ACCEPTED  → controller approved, RosterModifiedEvent published
    -- REJECTED  → controller rejected, handler must propose next candidate
    -- EXPIRED   → leg departed before controller acted
    severity            VARCHAR(10)     NOT NULL,
    source              VARCHAR(50)     NOT NULL,
    proposed_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    decided_at          TIMESTAMPTZ,
    decided_by          VARCHAR(50),
    rejection_reason    VARCHAR(100)
);
```

---

## Handle Flight Disrupted — Full Flow

```
FlightDisruptedEvent received
        ↓
Step 1 — What type of disruption?

  CANCELLATION:
    → mark roster_leg.status = INVALIDATED
    → mark all roster_crew_assignment.status = INVALIDATED for this leg (DRAFT and CONFIRMED only)
    → single call to invalidate_roster_leg() handles both in one transaction
    → publish RosterModifiedEvent(removed_crew_id=crew_id, added_crew_id=None) per released crew
      → FTL Service sets each crew member status = UNAVAILABLE
      → Daily Validator re-validates each crew member's other future legs
    → done — no proposal created

  DELAY (any duration) or SCHEDULE_CHANGE:
    → always re-check legality of all assigned crew against new departure time
    → even a short delay can push a crew member past their duty period limit if they are near the cap
    → crew who still pass → keep assignment, no action
    → crew who now fail → treat as CREW_DISRUPTED
      → run crew replacement flow for each failing crew member

  AIRCRAFT_SWAP:
    → new aircraft_type may require different type ratings
    → cabin crew have no type ratings in this system — skip them, only re-check pilots
    → re-check Gate 3 (type rating) and Gate 4 (license) for pilot crew only
    → pilots who fail → treat as CREW_DISRUPTED with reason = AIRCRAFT_TYPE_CHANGED
      → run crew replacement flow for each failing pilot

  ROUTE_CHANGE:
    → emit to controller for manual review — too complex to auto-handle
    → create proposal with proposed_crew_id = None, status = PENDING
    → controller must manually reassign via POST /planner/roster/{leg_id}/reassign
```

---

## Handle Crew Disrupted — Full Flow

This is the main path. One crew member cannot operate one leg.

```
CrewDisruptedEvent received
        ↓
Step 1 — Validate leg and crew context

  leg = get_flight_leg(event.leg_id)

  if leg is None
    → leg removed from schedule entirely, skip

  if leg.scheduled_departure <= now()
    → leg already departed or landed, too late to act, skip

  if leg.status == "CANCELLED"
    → flight cancelled, no point finding a replacement, skip

  crew = get_crew_member(event.crew_id)

  if crew is None
    → do NOT skip — leg still needs coverage
    → look up role from roster_crew_assignment via get_assignment_for_crew(leg_id, crew_id)
    → if no assignment record found either → skip (nothing to replace)
    → if assignment found → use assignment.role to find replacement candidates

        ↓
Step 2 — Find replacement candidates
  role    = crew.role  (PILOT or CABIN — replacement must match)
  airport = leg.origin_icao  (prefer crew already at departure airport)

  For every active crew member with matching role:
    - fetch their live FTL state
    - fetch their licenses
    - fetch their leave records
    - run check_legality(candidate, leg, ftl, licenses, leave, leg_date)
    - if passes → add to candidates list with score

        ↓
Step 3 — Score and rank candidates
  Score each candidate (same 4-factor scoring as Weekly Planner):
    +40  already at leg's departure airport
    +30  scaled by fatigue (lower fatigue = higher score)
    +20  at home base
    +10  leg destination is their home base
    -10  already away from home AND leg takes them further away

        ↓
Step 4 — Create proposal for top candidate
  proposal_id = f"PROP-{leg_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

  Write to disruption_proposals:
    leg_id           = event.leg_id
    disruption_type  = "CREW_DISRUPTED"
    disruption_reason = event.reason
    removed_crew_id  = event.crew_id
    proposed_crew_id = top_candidate.crew_id
    proposal_score   = top_candidate.score
    status           = "PENDING"
    severity         = event.severity

        ↓
Step 5 — Controller reviews and decides
  GET  /disruptions/proposals          → controller sees all pending proposals
  POST /disruptions/proposals/{id}/accept  → controller approves
  POST /disruptions/proposals/{id}/reject  → controller rejects, handler proposes next

        ↓
Step 6 — On ACCEPT
  update disruption_proposals.status = ACCEPTED
  update roster_crew_assignment:
    old crew → status = REPLACED, replaced_by = new_crew_id
    new crew → INSERT with status = CONFIRMED
  update roster_leg:
    triggered_by = decided_by
    updated_at   = NOW()
    (status stays PUBLISHED — the leg is still active, crew composition changed)
  publish RosterModifiedEvent(
    leg_id          = leg_id,
    removed_crew_id = old_crew_id,
    added_crew_id   = new_crew_id,
  )
  → FTL Service updates live FTL state for both crew immediately
  → DailyValidator re-validates both crew members' future legs automatically

        ↓
Step 7 — On REJECT
  update disruption_proposals.status = REJECTED
  remove top candidate from candidate list
  propose next best candidate → repeat from Step 4
  if no more candidates → create proposal with proposed_crew_id = None
    → controller must handle manually
```

---

## Candidate Scoring

Same scoring logic as Weekly Planner. Shared from `rules/` — not duplicated.

```python
def _score_candidate(crew, ftl, leg) -> float:
    fatigue = _fatigue_score(ftl)
    score   = 0.0
    score  += 40.0 if ftl.current_airport == leg.origin_icao else 0
    score  += 30.0 * (1 - fatigue / 100)
    score  += 20.0 if ftl.current_airport == crew.home_base else 0
    score  += 10.0 if leg.destination_icao == crew.home_base else 0
    if ftl.current_airport != crew.home_base and leg.destination_icao != crew.home_base:
        score -= 10.0
    return score


def _fatigue_score(ftl) -> float:
    score  = min(ftl.flight_hours_current_duty * 5, 55)
    score += min(ftl.consecutive_duty_days * 10,    20)
    score += min(ftl.flight_hours_28_day / 5,       25)
    return min(score, 100.0)
```

---

## Severity and Response Time

The severity from the event drives how urgently the controller must act.

| Severity | Days until departure | Expected response |
|----------|---------------------|-------------------|
| CRITICAL | < 2 days | Immediate — ops desk alerted directly |
| HIGH | 2–7 days | Same day response |
| MEDIUM | 7–14 days | Within 24 hours |
| LOW | 14+ days | Within 48 hours |

A proposal that is not acted on before the leg departs is automatically marked `EXPIRED`.

---

## Full Service Implementation

```python
# services/disruption_handler/disruption_handler_service.py

from collections import defaultdict
from datetime import datetime, timezone
from crew_ops.clients.crew_profile_client import get_all_crew_members, get_crew_member
from crew_ops.clients.ftl_client import get_all_crew_duty_states, get_crew_duty_state
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.license_client import get_licenses_for_crew_member
from crew_ops.clients.leave_client import get_leave_records_for_crew
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository, disruption_repository
from crew_ops.models.events import FlightDisruptedEvent, CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.rules.legality import check_legality
from crew_ops.services.event_bus import event_bus


class DisruptionHandler:

    def handle_flight_disrupted(self, event: FlightDisruptedEvent) -> None:
        leg = get_flight_leg(event.leg_id)
        if not leg:
            return

        if event.disruption_type == "CANCELLATION":
            with SessionLocal() as session:
                for crew_id in event.assigned_crew:
                    roster_repository.invalidate_assignment(session, event.leg_id, crew_id, "FLIGHT_CANCELLED")
                session.commit()
            return

        if event.disruption_type == "ROUTE_CHANGE":
            # Too complex to auto-handle — create a manual review proposal
            self._create_proposal(
                leg_id            = event.leg_id,
                disruption_type   = "FLIGHT_DISRUPTED",
                disruption_reason = "ROUTE_CHANGE",
                removed_crew_id   = None,
                candidates        = [],
                severity          = event.severity,
                source            = event.event,
            )
            return

        if event.disruption_type in ("DELAY", "SCHEDULE_CHANGE"):
            # Re-check legality for all assigned crew against updated leg — any delay can breach FTL
            for crew_id in event.assigned_crew:
                self._check_and_propose(crew_id, leg, reason="DELAY_FTL_BREACH", source=event.event)

        if event.disruption_type == "AIRCRAFT_SWAP":
            # Only re-check pilots — cabin crew have no type ratings, Gate 3 always fails for them
            for crew_id in event.assigned_crew:
                crew = get_crew_member(crew_id)
                if crew and crew.role == "PILOT":
                    self._check_and_propose(crew_id, leg, reason="AIRCRAFT_TYPE_CHANGED", source=event.event)

    def expire_stale_proposals(self) -> None:
        with SessionLocal() as session:
            disruption_repository.expire_stale_proposals(session)
            session.commit()

    def handle_crew_disrupted(self, event: CrewDisruptedEvent) -> None:
        leg = get_flight_leg(event.leg_id)
        if not leg:
            return
        if leg.scheduled_departure <= datetime.now(timezone.utc):
            return  # too late

        crew = get_crew_member(event.crew_id)
        if not crew:
            return

        candidates = self._find_and_rank_candidates(crew.role, leg)
        self._create_proposal(
            leg_id           = event.leg_id,
            disruption_type  = "CREW_DISRUPTED",
            disruption_reason = event.reason,
            removed_crew_id  = event.crew_id,
            candidates       = candidates,
            severity         = event.severity,
            source           = event.source,
        )

    # ─── Internal pipeline ────────────────────────────────────────────────────

    def _check_and_propose(self, crew_id: str, leg, reason: str, source: str) -> None:
        crew     = get_crew_member(crew_id)
        ftl      = get_crew_duty_state(crew_id)
        licenses = get_licenses_for_crew_member(crew_id)
        leave    = get_leave_records_for_crew(crew_id)
        if not crew or not ftl:
            return
        passed, fail_reason = check_legality(crew, leg, ftl, licenses, leave, leg.scheduled_departure.date())
        if not passed:
            candidates = self._find_and_rank_candidates(crew.role, leg)
            self._create_proposal(
                leg_id            = leg.leg_id,
                disruption_type   = "FLIGHT_DISRUPTED",
                disruption_reason = fail_reason or reason,
                removed_crew_id   = crew_id,
                candidates        = candidates,
                severity          = "HIGH",
                source            = source,
            )

    def _find_and_rank_candidates(self, role: str, leg) -> list[dict]:
        all_crew   = get_all_crew_members()
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}
        leg_date   = leg.scheduled_departure.date()

        candidates = []
        for crew in all_crew:
            if crew.role != role or crew.employment_status != "ACTIVE":
                continue
            ftl      = ftl_states.get(crew.crew_id)
            licenses = get_licenses_for_crew_member(crew.crew_id)
            leave    = get_leave_records_for_crew(crew.crew_id)
            if not ftl:
                continue
            passed, _ = check_legality(crew, leg, ftl, licenses, leave, leg_date)
            if passed:
                score = _score_candidate(crew, ftl, leg)
                candidates.append({"crew": crew, "ftl": ftl, "score": score})

        return sorted(candidates, key=lambda x: x["score"], reverse=True)

    def _create_proposal(
        self,
        leg_id: str,
        disruption_type: str,
        disruption_reason: str,
        removed_crew_id: str | None,
        candidates: list[dict],
        severity: str,
        source: str,
    ) -> None:
        # Guard — do not create duplicate PENDING proposal for same leg + removed crew
        with SessionLocal() as session:
            if removed_crew_id and disruption_repository.pending_proposal_exists(session, leg_id, removed_crew_id):
                return

            # Invalidate the disrupted crew's assignment so they no longer appear assigned
            if removed_crew_id:
                roster_repository.invalidate_assignment(session, leg_id, removed_crew_id, disruption_reason)

            proposed_crew_id = candidates[0]["crew"].crew_id if candidates else None
            proposal_score   = candidates[0]["score"] if candidates else 0.0
            proposal_id      = f"PROP-{leg_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

            disruption_repository.insert_proposal(session, {
                "proposal_id":       proposal_id,
                "leg_id":            leg_id,
                "disruption_type":   disruption_type,
                "disruption_reason": disruption_reason,
                "removed_crew_id":   removed_crew_id,
                "proposed_crew_id":  proposed_crew_id,
                "proposal_score":    proposal_score,
                "status":            "PENDING",
                "severity":          severity,
                "source":            source,
            })
            session.commit()
```

---

## Disruption Repository

New file: `db/repositories/disruption_repository.py`

```python
def pending_proposal_exists(session, leg_id: str, removed_crew_id: str) -> bool:
    row = session.execute(text("""
        SELECT 1 FROM disruption_proposals
        WHERE leg_id = :leg_id AND removed_crew_id = :removed_crew_id AND status = 'PENDING'
        LIMIT 1
    """), {"leg_id": leg_id, "removed_crew_id": removed_crew_id}).first()
    return row is not None


def insert_proposal(session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO disruption_proposals (
            proposal_id, leg_id, disruption_type, disruption_reason,
            removed_crew_id, proposed_crew_id, proposal_score,
            status, severity, source
        ) VALUES (
            :proposal_id, :leg_id, :disruption_type, :disruption_reason,
            :removed_crew_id, :proposed_crew_id, :proposal_score,
            :status, :severity, :source
        )
    """), data)


def get_pending_proposals(session) -> list[dict]:
    rows = session.execute(text("""
        SELECT dp.*, fl.scheduled_departure, fl.origin_iata, fl.destination_iata,
               fl.flight_number, fl.aircraft_type
        FROM disruption_proposals dp
        JOIN flight_legs fl ON fl.leg_id = dp.leg_id
        WHERE dp.status = 'PENDING'
        ORDER BY
            CASE dp.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                ELSE 4
            END,
            dp.proposed_at ASC
    """)).mappings().all()
    return [dict(row) for row in rows]


def accept_proposal(session, proposal_id: str, decided_by: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'ACCEPTED', decided_at = NOW(), decided_by = :decided_by
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by}).mappings().first()
    return dict(row) if row else {}


def reject_proposal(session, proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'REJECTED', decided_at = NOW(), decided_by = :decided_by,
            rejection_reason = :rejection_reason
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by, "rejection_reason": rejection_reason}).mappings().first()
    return dict(row) if row else {}


def expire_stale_proposals(session) -> int:
    result = session.execute(text("""
        UPDATE disruption_proposals dp
        SET status = 'EXPIRED'
        FROM flight_legs fl
        WHERE dp.leg_id = fl.leg_id
          AND dp.status = 'PENDING'
          AND fl.scheduled_departure <= NOW()
    """))
    return result.rowcount
```

---

## API Endpoints

```
GET /disruptions/proposals
  → returns all PENDING proposals sorted by severity then age
  → controller uses this to see what needs a decision

POST /disruptions/proposals/{proposal_id}/accept
  body: { decided_by }
  → marks proposal ACCEPTED
  → updates roster_crew_assignment (old crew REPLACED, new crew CONFIRMED)
  → updates roster_leg (triggered_by, updated_at)
  → publishes RosterModifiedEvent
  → FTL Service + Daily Validator react immediately
  → returns { status, leg_id, removed, added }

POST /disruptions/proposals/{proposal_id}/reject
  body: { decided_by, rejection_reason }
  → marks proposal REJECTED
  → excludes all previously proposed crew from next search
  → creates new PENDING proposal with next best candidate
  → if no more candidates → proposal with proposed_crew_id = None (manual handling)
  → returns { status, new_proposal_id, next_candidate }
```

## Published Roster Disruption — Full Status Flow

Starting state: `roster_leg = PUBLISHED`, all crew `roster_crew_assignment = CONFIRMED`

| Disruption | Who detects | roster_leg after | roster_crew_assignment after | disruption_proposals | RosterModifiedEvent |
|-----------|------------|-----------------|-----------------------------|--------------------|--------------------|
| CANCELLATION | Observer | `INVALIDATED` | all → `INVALIDATED` | none | ✅ per released crew |
| DELAY — crew still legal | Observer | `PUBLISHED` | `CONFIRMED` unchanged | none | ❌ |
| DELAY — crew fails legality | Observer | `PUBLISHED` | failing crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| SCHEDULE_CHANGE | Weekly Planner re-plan | `PUBLISHED` | failing crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| AIRCRAFT_SWAP — pilot fails | Weekly Planner re-plan | `PUBLISHED` | failing pilots → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| ROUTE_CHANGE | Weekly Planner re-plan | `PUBLISHED` | `CONFIRMED` unchanged until manual reassign | `PENDING` (no candidate) | ✅ on manual reassign |
| Crew disrupted — replacement found | Daily Validator / Ops Desk | `PUBLISHED` | disrupted crew → `INVALIDATED` → `REPLACED` on accept | `PENDING` → `ACCEPTED` | ✅ on accept |
| Crew disrupted — no replacement | Daily Validator / Ops Desk | `PUBLISHED` | disrupted crew → `INVALIDATED` | `PENDING` (proposed_crew_id=None) | ❌ |
| Controller rejects all candidates | Controller | `PUBLISHED` | `INVALIDATED` stays | all `REJECTED` → final `PENDING` (None) | ❌ |
| Proposal expires (leg departs) | Nightly job 00:30 | `PUBLISHED` | `INVALIDATED` stays | `EXPIRED` | ❌ |

---

## Status Reference

### `roster_leg.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `DRAFT` | Weekly Planner Job A | Planned, not yet approved by controller |
| `PUBLISHED` | Controller via `POST /planner/roster/{leg_id}/approve` | Approved, crew notified |
| `INVALIDATED` | Disruption Handler on CANCELLATION | Flight cancelled, all crew released |

### `roster_crew_assignment.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `DRAFT` | Weekly Planner Job A | Planned, not yet approved |
| `CONFIRMED` | Controller approval or Disruption Handler accept | Crew member confirmed on this leg |
| `REPLACED` | Disruption Handler accept or manual reassign | Crew swapped out, `replaced_by` points to new crew |
| `INVALIDATED` | Disruption Handler on CANCELLATION, or legality breach | Crew released from this leg |

### `disruption_proposals.status`

| Status | Set by | Meaning |
|--------|--------|---------|
| `PENDING` | Disruption Handler | Waiting for controller decision |
| `ACCEPTED` | Controller via `POST /disruptions/proposals/{id}/accept` | Approved — roster updated, `RosterModifiedEvent` published |
| `REJECTED` | Controller via `POST /disruptions/proposals/{id}/reject` | Rejected — next candidate proposed automatically |
| `EXPIRED` | Nightly job at 00:30 | Leg departed before controller acted |

---

## Complete Flow After Proposal Accepted

```
Controller POST /disruptions/proposals/{id}/accept
        ↓
disruption_proposals.status = ACCEPTED
        ↓
roster_crew_assignment:
  old crew → REPLACED  (replaced_by = new_crew_id)
  new crew → CONFIRMED (inserted fresh)
roster_leg:
  triggered_by = decided_by
  updated_at   = NOW()
  status stays PUBLISHED — leg is still active
        ↓
RosterModifiedEvent published
        ↓
    ┌───────────────────────────────────────┐
    │                                       │
FTL Service                          Daily Validator
on_roster_modified()                 on_roster_modified()
    │                                       │
removed crew → UNAVAILABLE           re-validates all future legs
added crew   → duty_start = now      for both removed + added crew
               status = AVAILABLE          │
                                    if any leg fails legality
                                           ↓
                                    CrewDisruptedEvent published
                                           ↓
                                    Disruption Handler
                                    creates new proposal
                                           ↓
                                    chain repeats until clean
```

---

## Edge Cases

| Situation | Handling |
|-----------|---------|
| No replacement candidate found | Invalidate the disrupted crew's assignment first. Then create proposal with `proposed_crew_id = NULL` — controller must handle manually. Without invalidating, the disrupted crew member remains shown as assigned |
| Leg already departed when event arrives | Skip — check `leg.scheduled_departure <= now()` before doing anything |
| Flight cancelled — no replacement needed | Invalidate all assignments, no proposal created |
| Controller rejects all candidates | Final proposal has `proposed_crew_id = NULL` — leg marked UNDERSTAFFED |
| Same crew disrupted on 3 future legs | One `CrewDisruptedEvent` per leg — one proposal per leg. Problem: handler fetches live FTL state each time, so the same replacement candidate can be proposed for all 3 legs before any is confirmed. Guard: after proposing a candidate for leg 1, exclude that candidate from the pool for legs 2 and 3 until their proposal is resolved |
| Delay threshold for crew re-check | Re-run legality for all assigned crew against the new departure time on any delay — no minimum threshold. Even a short delay can push a crew member past their duty period limit if they are already near the cap |
| Aircraft swap — cabin crew | Cabin crew have no type ratings in this system. Gate 3 always fails for cabin on an aircraft swap. Skip type rating check for cabin crew on AIRCRAFT_SWAP — only re-check pilots |
| Duplicate event for same leg + crew | If a PENDING proposal already exists for the same `leg_id` + `removed_crew_id`, do not insert a second one. Check before inserting — if found, skip silently |
| ROUTE_CHANGE disruption type | Must be explicitly handled — create proposal with `proposed_crew_id = NULL` and `status = PENDING`. Without this branch the event falls through silently and nothing is created |
| Proposal expires (leg departs before decision) | Nightly job marks all PENDING proposals for departed legs as EXPIRED. The expiry job must be a method on `DisruptionHandler` that calls `disruption_repository.expire_stale_proposals` — the scheduler cannot call the repository directly |

---

## What the Disruption Handler Does NOT Do

| Not its job | Who handles it |
|-------------|---------------|
| Detect delays or cancellations | Observer |
| Detect FTL breaches in future roster | Weekly Planner Validator |
| Update FTL state after a leg lands | FTL Service |
| Send notifications to crew | Notification service (not yet built) |
| Approve its own proposals | Controller via API — human decision always required |
| Handle sick calls directly | Ops Desk calls `POST /crew/{id}/unavailable` → emits `CrewDisruptedEvent` → handler picks it up |
| Detect leave added covering an assigned leg | Leave Client (`add_leave_record`) publishes `CrewDisruptedEvent(reason=LEAVE_ADDED)` automatically — handler picks it up |

---

## End to End Test

```bash
# Trigger a crew disruption manually
curl -X POST http://localhost:8000/crew/C-003/unavailable \
  -H "Content-Type: application/json" \
  -d '{"reason": "SICK", "from_datetime": "2024-02-05T00:00:00", "to_datetime": "2024-02-06T23:59:59"}'

# Check proposals created
curl http://localhost:8000/disruptions/proposals

# Accept the top proposal
curl -X POST http://localhost:8000/disruptions/proposals/{proposal_id}/accept \
  -H "Content-Type: application/json" \
  -d '{"decided_by": "ops_controller_01"}'

# Verify roster updated
docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, crew_id, status, replaced_by FROM roster_crew_assignment WHERE leg_id LIKE '%20240205%';"

# Verify roster_leg stamped
docker exec -it crew_ops_postgres psql -U crew_ops_user -d crew_ops \
  -c "SELECT leg_id, status, triggered_by, updated_at FROM roster_leg WHERE leg_id LIKE '%20240205%';"
```

---

## Component 4 — FTL Service

# Crew Handling Implementation — Roster Planner

> Implementation doc for the Roster Planner service. This is the first service to build. Every other service (disruption pipeline, legality checker, proactive alerts) depends on the roster existing as a baseline.

---

## What the Planner Does

Takes a flight schedule (list of legs) + crew pool + constraints → produces a valid weekly roster where:
- Every leg has the minimum required crew assigned (pilots + cabin)
- Every assignment is FTL-legal before the week starts
- Reserve/standby slots are filled for each operating day
- No crew member has a rest violation, FDP breach, or cap overage in their planned week

The planner runs in **future-simulation mode** — it uses the same `CrewLegalityChecker` as the disruption pipeline, but simulates each crew member's state day by day across the full week instead of checking a single real-time event.

---

## 1. Inputs

| Input | Source | Description |
|-------|--------|-------------|
| `legs[]` | Flight schedule (seed / OAG) | All legs for the planning week, sorted by departure |
| `crew_profiles[]` | `crew` table | All active crew — role, base, licenses, seniority |
| `crew_ftl_state[]` | `crew_ftl_state` table | Carry-over counters from previous week (28-day block hours, 7-day duty hours, consecutive duty days, last weekly rest end) |
| `crew_leave[]` | `crew_leave` table | Approved leave for the planning week — these crew are excluded |
| `crew_reserve_schedule[]` | `crew_reserve_schedule` table | Existing standby slots (planner fills gaps) |
| `fdp_bracket_table` | `rules/fdp_table.py` | Report time × sector count → max FDP |
| `cost_config` | `config/cost_config.json` | Deadhead cost, delay cost/min, passenger impact |

---

## 2. Output

| Output | Written To | Description |
|--------|-----------|-------------|
| `RosterEntry` rows | `crew_roster` table | One row per crew-leg assignment, status = PLANNED |
| `CrewReserveSchedule` rows | `crew_reserve_schedule` table | Standby slots for each day at each base airport |
| Projected `crew_ftl_state` | In-memory only (not persisted) | Used during planning to simulate week — not written to DB until roster is published |
| Validation report | Returned to caller | List of flagged violations before publish |

---

## 3. Planning Algorithm

The planner works in 3 passes:

```
Pass 1 — Assign operating crew to legs (earliest departure first)
Pass 2 — Fill reserve slots for each day at each base
Pass 3 — Full week validation (simulate every crew member's 7-day plan)
```

### Pass 1 — Assign Operating Crew

```
Sort all legs by scheduled_departure ascending

For each leg:
  required = leg.required_crew  # e.g. {PILOT: 2, CABIN: 4}

  For each role in required:
    candidates = find_candidates(role, leg)
    legal      = [c for c in candidates if legality_check(c, leg, simulated_ftl).is_legal]

    if len(legal) == 0:
      flag_gap(leg, role)   # no legal crew — escalate
      continue

    ranked = rank_candidates(legal, leg)
    assigned = ranked[:required[role]]

    for crew in assigned:
      create_roster_entry(crew.crew_id, leg.leg_id, OPERATING)
      update_simulated_ftl(crew.crew_id, leg)   # advance their projected state
```

### find_candidates(role, leg)

```
1. Filter crew_profiles:
   - role matches
   - employment_status == ACTIVE
   - not in crew_leave for leg.departure date
   - home_base or current_airport == leg.origin
     (if current_airport != leg.origin → flag as deadhead candidate, add deadhead_duration to FDP)

2. Filter by simulated_ftl_state (projected state at time of this leg):
   - status == AVAILABLE (not already assigned to overlapping duty)
   - consecutive_duty_days < 6 (leave buffer for weekly rest)

3. Return filtered list
```

### legality_check in future-simulation mode

Same `CrewLegalityChecker.check()` used in the disruption pipeline, but reads from `simulated_ftl` (the projected state built up during Pass 1) instead of the live `crew_ftl_state` table.

```
simulated_ftl[crew_id] starts as a copy of crew_ftl_state[crew_id] (carry-over from last week)

After each assignment:
  simulated_ftl[crew_id].duty_start_time      = leg.report_time
  simulated_ftl[crew_id].duty_end_time        = leg.estimated_arrival + debrief_buffer
  simulated_ftl[crew_id].flight_time_current_duty += leg.duration_hours
  simulated_ftl[crew_id].sectors_current_duty += 1
  simulated_ftl[crew_id].duty_hours_7_day     += duty_window_hours
  simulated_ftl[crew_id].flight_hours_28_day  += leg.duration_hours
  simulated_ftl[crew_id].consecutive_duty_days += 1
  simulated_ftl[crew_id].last_rest_end_time   = duty_end_time + min_rest_required
  simulated_ftl[crew_id].status               = AVAILABLE (after rest)
```

### rank_candidates(legal, leg)

```
Score each legal candidate:

  seniority_score  = 1 - (crew.seniority_number / max_seniority)   # senior crew get priority
  fatigue_score    = 1 - (simulated_ftl.fatigue_percent / 100)      # lower fatigue = higher score
  location_score   = 1 if current_airport == leg.origin else 0      # no deadhead preferred
  hours_remaining  = 1 - (simulated_ftl.flight_hours_28_day / 100)  # more hours left = preferred

  total = 0.3 * seniority_score
        + 0.3 * fatigue_score
        + 0.25 * location_score
        + 0.15 * hours_remaining

Sort descending by total. Return ranked list.
```

### Pass 2 — Fill Reserve Slots

After all operating duties are assigned, fill standby slots for each day at each base airport.

```
For each date in planning_week:
  For each base_airport in [DEL, BOM, BLR]:
    required_reserves = config.min_reserves_per_base  # e.g. 2 pilots + 3 cabin

    already_on_standby = crew_reserve_schedule.get(date, base_airport)
    gap = required_reserves - len(already_on_standby)

    if gap > 0:
      available = [
        c for c in crew_profiles
        if c.home_base == base_airport
        and not assigned_to_operating_duty(c.crew_id, date)
        and not in_crew_leave(c.crew_id, date)
        and simulated_ftl[c.crew_id].status == AVAILABLE
      ]
      ranked = rank_candidates(available, base_airport)
      for crew in ranked[:gap]:
        create_reserve_entry(crew.crew_id, date, base_airport, callable_within=120)
```

### Pass 3 — Full Week Validation

Simulate each crew member's complete 7-day plan through the legality checker. Flag any violation before the roster is published.

```
For each crew_member:
  assignments = crew_roster.get_week(crew_member.crew_id, planning_week)
  simulated   = copy(crew_ftl_state[crew_member.crew_id])  # start from carry-over

  For each assignment in assignments (sorted by duty_start_time):
    result = legality_check(crew_member.crew_id, assignment.leg, simulated)

    if result.is_legal == False:
      flag_violation(crew_member, assignment, result.reasons)

    update_simulated_ftl(crew_member.crew_id, assignment.leg, simulated)

  # End-of-week checks
  if simulated.duty_hours_7_day > 60:
    flag_violation(crew_member, "7-day duty cap breach: {simulated.duty_hours_7_day}h")

  if simulated.flight_hours_28_day > 100:
    flag_violation(crew_member, "28-day block hour cap breach: {simulated.flight_hours_28_day}h")

  if not has_36hr_rest_block(assignments):
    flag_violation(crew_member, "No 36hr continuous rest block in planned week")

  if assignments[-1].leg.destination != crew_member.home_base:
    flag_violation(crew_member, "Crew does not return to home base by end of week")
```

---

## Disruption Types

Two categories of disruption feed into the same Disruption Handler pipeline.

### Type 1 — Flight-Side
- Trigger: delay, cancellation, diversion, aircraft swap
- Detected by: Observer (live polling)
- Event: `FlightDisrupted`

### Type 2 — Crew-Side
- Trigger: sick call, emergency leave, medical grounding, no-show, urgent training, or future assignment invalid (leave added, license expired, FTL drifted)
- Detected by: Ops Desk (today) via `POST /v1/crew/{crew_id}/unavailable`, or Planner Job B (future) automatically
- Event: `CrewDisrupted` (one per affected leg, `source` field distinguishes origin)
- Disruption Handler receives it and runs the same replacement pipeline

---

## Disruption Handler — Classify Step

```
FlightDisrupted → urgency from severity field
CrewDisrupted   → urgency from days_until_departure + severity (already computed at emit time)
```

Both event types flow through the same Steps 2–8 (FTL check → cascade → find candidates → rank → narrate → human decision → update roster).

---

## 4. Conflict Resolution

When `flag_gap()` is called (no legal crew for a leg):

```
Priority 1 — Activate reserve:
  Check crew_reserve_schedule for that date + airport
  If reserve crew is legal for the leg → assign them, update reserve slot to ACTIVATED

Priority 2 — Deadhead from nearest base:
  Find legal crew at nearest base airport
  Add deadhead leg to their roster (DEADHEAD assignment type)
  Deadhead duration added to their FDP — re-run legality check

Priority 3 — Escalate to human:
  Create a GAP record: { leg_id, role, reason, flagged_at }
  Surface in validation report
  Do not publish roster until gap is resolved

Priority 4 — Flag for delay:
  If no crew found after Priority 1–3:
  Append to validation report: "No legal crew for {leg_id} — consider delaying flight"
```

---

## 5. Pre-Publish Validation Report

The planner returns a validation report before writing anything to the database. The roster is only published (written to `crew_roster` table) after the controller reviews and approves.

```json
{
  "planning_week": "2024-02-05 to 2024-02-11",
  "total_legs": 42,
  "total_assignments": 168,
  "gaps": [
    {
      "leg_id": "AI-305-BOM-DEL",
      "role": "PILOT",
      "departure": "2024-02-07T10:00:00",
      "reason": "No legal pilot at BOM — all near 28-day cap",
      "suggested_action": "Activate reserve Captain Nair or deadhead from DEL"
    }
  ],
  "violations": [
    {
      "crew_id": "C-012",
      "name": "Captain Mehta",
      "day": "2024-02-09",
      "violation": "7-day duty cap breach — 62.5h planned vs 60h limit",
      "suggested_action": "Remove AI-450 assignment on Feb 9, reassign to C-018"
    }
  ],
  "warnings": [
    {
      "crew_id": "C-007",
      "name": "FO Sharma",
      "warning": "Approaching 28-day block hour cap — 91h planned, 9h remaining"
    }
  ],
  "reserve_gaps": [
    {
      "date": "2024-02-08",
      "airport": "BLR",
      "role": "CABIN",
      "required": 3,
      "filled": 2,
      "shortfall": 1
    }
  ],
  "status": "NEEDS_REVIEW"   // READY_TO_PUBLISH if gaps=[] and violations=[]
}
```

---

## 6. Data Models

### RosterEntry

```python
@dataclass
class RosterEntry:
    roster_id:        str           # uuid
    crew_id:          str           # FK to crew profile
    leg_id:           str           # FK to leg (sector) — never a route
    duty_start_time:  datetime      # report time (1–2 hrs before departure)
    duty_end_time:    datetime      # estimated release after landing + 30min debrief
    assignment_type:  str           # OPERATING / DEADHEAD / RESERVE / TRAINING / LEAVE
    status:           str           # PLANNED / CONFIRMED / MODIFIED / CANCELLED
    modified_reason:  str | None
    modified_by:      str | None    # controller_id or AI_SYSTEM or PLANNER
    created_at:       datetime
    modified_at:      datetime
```

### CrewLeave

```python
@dataclass
class CrewLeave:
    leave_id:    str
    crew_id:     str
    start_date:  date
    end_date:    date
    leave_type:  str    # ANNUAL / SICK / TRAINING / MEDICAL
    status:      str    # APPROVED / PENDING
```

### CrewReserveSchedule

```python
@dataclass
class CrewReserveSchedule:
    reserve_id:       str
    crew_id:          str
    date:             date
    standby_start:    datetime      # when they must be reachable
    standby_end:      datetime      # end of standby window
    base_airport:     str           # ICAO — where they are on standby
    callable_within:  int           # minutes to report (e.g. 120)
    status:           str           # SCHEDULED / ACTIVATED / RELEASED
    activated_for:    str | None    # leg_id if activated
```

### PlannerGap (internal, not persisted)

```python
@dataclass
class PlannerGap:
    leg_id:           str
    role:             str
    departure:        datetime
    reason:           str
    suggested_action: str
```

---

## 7. File Structure

```
roster/
  planner.py            RosterPlanner — main planning logic (Pass 1, 2, 3)
  validator.py          RosterValidator — pre-publish validation, gap detection
  roster_service.py     RosterService — CRUD for crew_roster, change log, conflict detection

models/
  roster_entry.py       RosterEntry dataclass
  crew_leave.py         CrewLeave dataclass
  crew_reserve.py       CrewReserveSchedule dataclass
  planner_gap.py        PlannerGap dataclass (internal)

data/
  seed.py               25 crew + 15 legs + ftl_states (existing)
  roster_seed.py        NEW — seed crew_roster + crew_leave + crew_reserve for demo week

config/
  cost_config.json      deadhead cost, delay cost/min, passenger impact
  planner_config.json   min_reserves_per_base, debrief_buffer_minutes, planning_horizon_days
```

---

## 8. Seed Data Spec

The seed data must produce a realistic demo roster. Required variety:

### Crew States (crew_ftl_state carry-over)

| Crew | State | Why Needed |
|------|-------|-----------|
| 2 pilots | `flight_hours_28_day` = 88–92 | Near 100hr cap — planner must limit their assignments |
| 1 pilot | `consecutive_duty_days` = 5 | Must get weekly rest — planner cannot assign Day 6 |
| 3 crew | `status` = AVAILABLE, fresh | Ideal candidates — planner assigns these first |
| 2 crew | `status` = RESTING, away from base | Planner must wait for rest to complete before assigning |
| 1 pilot | `duty_hours_7_day` = 52 | Near 60hr weekly cap — limited availability |

### Leave Entries (crew_leave)

| Crew | Leave Type | Dates |
|------|-----------|-------|
| 1 pilot | ANNUAL | covers 3 days of planning week |
| 1 cabin | SICK | covers full planning week |
| 1 pilot | TRAINING | 1 day simulator check |

### Reserve Schedule (crew_reserve_schedule)

| Date | Airport | Role | Count |
|------|---------|------|-------|
| Day 1–7 | DEL | PILOT | 2 |
| Day 1–7 | DEL | CABIN | 3 |
| Day 1–7 | BOM | PILOT | 1 |
| Day 1–7 | BOM | CABIN | 2 |

### Flight Schedule (legs for planning week)

- 15 legs across DEL/BOM/BLR
- Mix of short-haul (1–2 hrs) and medium-haul (3–4 hrs)
- 1 leg with no legal crew available at origin → triggers gap + reserve activation demo
- 1 leg where assigned crew approaches FDP limit → triggers warning in validation report

---

## 9. Integration Points

### → Disruption Pipeline

When a disruption happens, the pipeline checks `crew_reserve_schedule` first:

```python
# In candidate finding (Step 16):
reserves = crew_reserve_schedule.get_active(
    date=flight.departure.date(),
    airport=flight.origin,
    role=required_role
)
# These are the fastest fix — already at the right airport, already on standby
```

The planner is what populates `crew_reserve_schedule`. Without it, the disruption pipeline has no standby pool to draw from.

### → FTL Service

On roster publish, the FTL service initialises `crew_ftl_state` projections for the week:

```python
# ftl_service.py
def on_roster_published(roster_entries: list[RosterEntry]):
    for entry in roster_entries:
        ftl_service.project_duty_event(
            crew_id=entry.crew_id,
            duty_start=entry.duty_start_time,
            duty_end=entry.duty_end_time,
            leg=entry.leg_id
        )
```

### → Notification Service

On roster publish, notifications go out to all assigned crew:

```python
# notifier.py
def on_roster_published(roster_entries: list[RosterEntry]):
    for entry in roster_entries:
        notifier.send_assignment_notice(
            crew_id=entry.crew_id,
            leg_id=entry.leg_id,
            report_time=entry.duty_start_time,
            assignment_type=entry.assignment_type
        )
        if entry.assignment_type == DEADHEAD:
            notifier.send_positioning_notice(crew_id, leg_id, entry.duty_start_time)
```

Hotel bookings triggered for any crew whose `duty_end` airport != `home_base`:

```python
    if leg.destination != crew.home_base:
        notifier.send_hotel_booking(
            crew_id=entry.crew_id,
            airport=leg.destination,
            checkin=entry.duty_end_time,
            earliest_checkout=entry.duty_end_time + min_rest_required
        )
```

### → API Endpoint

```
POST /v1/roster/plan
  body: { week_start: "2024-02-05", airline_iata: "AI" }
  → runs planner, returns validation report
  → status: NEEDS_REVIEW or READY_TO_PUBLISH

POST /v1/roster/publish
  body: { week_start: "2024-02-05" }
  → writes crew_roster rows to DB
  → triggers FTL projections + notifications

GET  /v1/roster/week/{week_start}
  → returns full roster for the week (all legs + assigned crew)

GET  /v1/roster/crew/{crew_id}/week/{week_start}
  → returns one crew member's full week schedule

GET  /v1/roster/gaps/{week_start}
  → returns all unresolved gaps for the week
```

---

## 10. planner.py — Skeleton

```python
class RosterPlanner:

    def __init__(self, crew_profiles, ftl_states, leaves, reserves, legs, fdp_table, config):
        self.crew       = {c.crew_id: c for c in crew_profiles}
        self.ftl        = {f.crew_id: copy(f) for f in ftl_states}   # simulated copy
        self.leaves     = leaves
        self.reserves   = reserves
        self.legs       = sorted(legs, key=lambda l: l.scheduled_departure)
        self.fdp_table  = fdp_table
        self.config     = config
        self.checker    = CrewLegalityChecker(fdp_table)
        self.roster     = []   # RosterEntry list built during planning
        self.gaps       = []   # PlannerGap list

    def plan(self) -> ValidationReport:
        self._pass1_assign_operating()
        self._pass2_fill_reserves()
        return self._pass3_validate()

    def _pass1_assign_operating(self):
        for leg in self.legs:
            for role, count in leg.required_crew.items():
                candidates = self._find_candidates(role, leg)
                legal      = [c for c in candidates
                              if self.checker.check(c.crew_id, leg, self.ftl[c.crew_id]).is_legal]
                if not legal:
                    self.gaps.append(PlannerGap(leg.leg_id, role, leg.scheduled_departure,
                                                "No legal crew available", self._suggest(leg, role)))
                    continue
                ranked   = self._rank(legal, leg)
                assigned = ranked[:count]
                for crew in assigned:
                    entry = RosterEntry(
                        roster_id=uuid4(),
                        crew_id=crew.crew_id,
                        leg_id=leg.leg_id,
                        duty_start_time=leg.scheduled_departure - timedelta(hours=1.5),
                        duty_end_time=leg.estimated_arrival + timedelta(minutes=30),
                        assignment_type="OPERATING",
                        status="PLANNED",
                        modified_reason=None,
                        modified_by="PLANNER",
                        created_at=datetime.utcnow(),
                        modified_at=datetime.utcnow()
                    )
                    self.roster.append(entry)
                    self._update_simulated_ftl(crew.crew_id, leg, entry)

    def _pass2_fill_reserves(self): ...
    def _pass3_validate(self) -> ValidationReport: ...
    def _find_candidates(self, role, leg) -> list: ...
    def _rank(self, candidates, leg) -> list: ...
    def _update_simulated_ftl(self, crew_id, leg, entry): ...
    def _suggest(self, leg, role) -> str: ...
```

---

## 11. Build Order for This Service

| Step | Task | File | Time |
|------|------|------|------|
| 1 | Data models | `models/roster_entry.py`, `crew_leave.py`, `crew_reserve.py` | 20 min |
| 2 | Seed data | `data/roster_seed.py` — crew states, leave, reserves, 15 legs | 30 min |
| 3 | Pass 1 — operating assignment | `roster/planner.py` | 45 min |
| 4 | Pass 2 — reserve filling | `roster/planner.py` | 20 min |
| 5 | Pass 3 — validation | `roster/validator.py` | 30 min |
| 6 | Roster service CRUD | `roster/roster_service.py` | 20 min |
| 7 | API endpoints | `api/main.py` — plan + publish + get | 20 min |
| 8 | Integration test | curl `/v1/roster/plan` → review report → curl `/v1/roster/publish` | 15 min |

Total: ~3 hrs

---

## Component 5 — Conversation Layer

# Conversation Layer — End to End Implementation

---

## What This Service Does

The Conversation Layer is the **only entry point for human interaction** with the system.

It translates free-text requests into structured intents, routes them to the right service, and returns human-readable responses. All four existing services (Weekly Planner, Observer, Disruption Handler, FTL Service) remain completely unaware of the human. They never change. The Conversation Layer sits in front of them as a thin translation and routing layer.

Three things it does:

1. **Classify intent** — is this a query, a simulation, or an action?
2. **Execute** — call the right pure-Python functions (legality check, candidate ranking, roster read) or write APIs
3. **Format response** — narrate the result in plain English

One thing it explicitly does NOT do: implement any business logic. Every legality check, FTL calculation, candidate score, and roster write already exists. The Conversation Layer only calls what is already built.

---

## Package Structure

The Conversation Layer lives in its own package, completely separate from the four services.

```
crew_ops/
└── conversation/
    ├── __init__.py
    ├── agent.py                  ← LangGraph graph definition, entry point
    ├── intent.py                 ← Intent dataclass + classifier prompt
    ├── tools.py                  ← All tool functions (read + write)
    ├── formatter.py              ← LLM response formatting
    ├── session.py                ← Per-session state (pending confirmations, context)
    └── router.py                 ← FastAPI router — POST /chat
```

No imports from `conversation/` into any existing service. The dependency arrow is one-way: `conversation/` imports from services, never the reverse.

---

## Architecture

```
Human (chat / UI)
      │
      ▼  POST /chat  { session_id, message }
┌─────────────────────────────────────────────────────────────┐
│  CONVERSATION LAYER  (LangGraph agent)                      │
│                                                             │
│  1. Intent Classifier  →  QUERY / SIMULATE / ACTION        │
│  2. Router             →  selects tool set for intent       │
│  3. Tool Executor      →  calls pure-Python functions       │
│  4. Response Formatter →  LLM narrates result               │
│                                                             │
│  Session state: pending confirmations, last query context   │
└──────┬──────────┬──────────┬──────────┬────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
   Roster     Disruption  Planner    FTL
   (read)     (write)     (simulate) (read)
```

The LangGraph graph has four nodes:

```
classify_intent → route → execute_tools → format_response
                    │
                    └── (ACTION only) → build_confirmation → await_confirm → execute_tools
```

---

## Three Interaction Modes

### Mode 1 — QUERY (read only, no confirmation)

Examples:
- "What is the status of AI305?"
- "Who is assigned to AI101 tomorrow?"
- "Show me Capt Mehta's schedule this week"
- "How many hours does FO Sharma have left this month?"

Flow:
```
classify_intent → QUERY
      ↓
execute read-only tools
      ↓
format_response (LLM narrates)
      ↓
return response
```

No state change. No confirmation. No pending anything.

---

### Mode 2 — SIMULATE (what-if, no confirmation)

Examples:
- "If Capt Ravi is not available tomorrow, who can replace him?"
- "What happens if AI305 gets cancelled?"
- "If I swap Capt Mehta and FO Sharma on AI202, is that legal?"

Flow:
```
classify_intent → SIMULATE
      ↓
run in-memory only — no DB writes
      ↓
legality check (pure Python)
      ↓
cascade impact check (pure Python)
      ↓
rank replacement options (pure Python)
      ↓
format_response — LLM narrates outcome
      ↓
append "Want me to raise this as a disruption?" to response
      ↓
store {crew_id, leg_id, reason, severity} in session as pending_simulation
      ↓
return response
```

No DB write. Session state stores the simulation context so the next turn can act on it.

--- next turn: human says "yes, apply it" ---

```
classify_intent → detects pending_simulation in session → ACTION
      ↓
publish CrewDisruptedEvent(crew_id, leg_id, reason, severity)
      ↓
DisruptionHandler.handle_crew_disrupted() runs full pipeline:
    _find_and_rank_candidates()  — legality check + scoring for all crew
    _create_proposal()           — writes PENDING row to disruption_proposals table
      ↓
response: "Disruption raised. Proposal PROP-xxx is now pending approval in the inbox."
```

"Apply it" does not bypass the Disruption Handler. It triggers it — identical to what happens when the Observer detects a disruption automatically. The proposal lands in the disruption inbox as PENDING and goes through the normal confirm/reject approval flow from there.

---

### Mode 3 — ACTION (writes to system, requires confirmation)

Examples:
- "Mark Capt Ravi as sick for today"
- "Assign FO Deepa to AI305 instead of FO Sharma"
- "Swap Capt Mehta and Capt Nisha on tomorrow's flights"

Flow:
```
classify_intent → ACTION
      ↓
legality check (pure Python) — fail fast before showing confirmation
      ↓
cascade impact check (pure Python)
      ↓
build_confirmation_package — LLM writes the summary
      ↓
present to human: "Here is what will change. Confirm? [YES / NO]"
      ↓
human confirms
      ↓
execute service call (write to DB)
      ↓
event emitted → pipeline runs (Disruption Handler, FTL Service, Validator)
      ↓
format_response — LLM narrates what changed
      ↓
return response
```

If legality fails before confirmation, the agent returns the failure reason and stops. No confirmation shown for an illegal action.

---

## System-Initiated Decisions (Push to Human)

When the Disruption Handler creates a PENDING proposal with severity HIGH or CRITICAL, the system pushes it to the human without waiting for them to ask.

This is a separate flow from the three modes above. It is triggered by a background job that polls `disruption_proposals` for new PENDING proposals and pushes them into the active session (or a notification queue if no session is open).

```
Disruption Handler creates PENDING proposal
      ↓
severity check:
  CRITICAL → push immediately, auto-escalate after 15 min if no response
  HIGH     → push immediately, 1hr window
  MEDIUM   → push to human, 4hr window
  LOW      → auto-resolve if clean replacement found, notify only
      ↓
format_push_notification — LLM writes the alert message:
  "AI305 BOM→CCU departs in 90min. Capt Ravi called sick.
   Best replacement: Capt Vikram (reserve at BOM, FTL legal).
   Second option: FO Nair (deadhead from DEL, adds 45min to duty period).
   Confirm Capt Vikram? [YES / NO / SHOW MORE OPTIONS]"
      ↓
human responds YES / NO / SHOW MORE OPTIONS
      ↓
YES  → POST /disruptions/proposals/{id}/accept
NO   → POST /disruptions/proposals/{id}/reject  → next candidate pushed
SHOW → fetch next 2 candidates, re-format, push again
```

The push notification is formatted by the LLM using the same `formatter.py` used for regular responses. The data (proposal, leg, candidates) comes from `disruption_repository.get_pending_proposals()` — already built.

---

## What LLM Does vs Pure Python

| Task | Who |
|------|-----|
| Classify intent from free text | LLM |
| Extract entities (crew name, flight number, date) | LLM |
| Detect ambiguity ("which Sharma?") | LLM |
| Legality check (hard gates 1–11) | Pure Python — `rules/legality.py` |
| Cascade impact check | Pure Python — `rules/legality.py` + `rules/ftl_simulator.py` |
| Fatigue score calculation | Pure Python — `_fatigue_score()` in disruption handler |
| Rank replacement candidates | Pure Python — `_score_candidate()` in disruption handler |
| Write confirmation package narrative | LLM |
| Format final response | LLM |
| Apply the actual change | Pure Python — service call via `tools.py` |
| Proposal expiry / escalation timing | Pure Python — APScheduler job |

The LLM never touches numbers. It only reads structured results and writes natural language.

---

## Intent Classifier

The classifier is a single LLM call with a structured output schema. It runs first on every message.

```python
# conversation/intent.py

from pydantic import BaseModel
from typing import Literal

class Intent(BaseModel):
    mode:        Literal["QUERY", "SIMULATE", "ACTION"]
    action_type: str | None   # MARK_UNAVAILABLE / REASSIGN / SWAP / APPROVE / CANCEL
    entities:    dict         # crew_id, leg_id, flight_number, date — extracted from message
    raw_message: str
    ambiguous:   bool         # True if LLM could not resolve entities unambiguously
    clarification_needed: str | None  # what to ask the human if ambiguous
```

Classifier prompt (system message):

```
You are an airline operations assistant. Classify the user's message into one of three modes:

QUERY   — user wants to read information. No change to the system.
SIMULATE — user wants to explore a what-if scenario. No change to the system.
ACTION  — user wants to make a change that modifies the roster or crew state.

Extract all entities mentioned: crew names, flight numbers, dates, airports.
Resolve crew names to crew_id using the provided crew list.
If a name is ambiguous (multiple matches), set ambiguous=true and clarification_needed.

Return JSON matching the Intent schema.
```

The crew list is injected into the classifier prompt as a compact lookup table (crew_id, full_name, role, home_base) — small enough to fit in context.

---

## Tool Definitions

All tools are pure functions in `conversation/tools.py`. They call existing clients and repositories. No business logic lives here.

### Read Tools (QUERY + SIMULATE)

```python
def get_leg_status(leg_id: str) -> dict:
    """Returns current leg data including status, delay, assigned crew."""
    leg = get_flight_leg(leg_id)
    return leg.model_dump() if leg else {"error": "leg not found"}


def get_crew_schedule(crew_id: str, start: date, end: date) -> list[dict]:
    """Returns all assignments for a crew member in a date range."""
    with SessionLocal() as session:
        return roster_repository.get_future_assignments(session, start, end, crew_id=crew_id)


def get_crew_ftl(crew_id: str) -> dict:
    """Returns current FTL state for a crew member."""
    ftl = get_crew_duty_state(crew_id)
    return ftl.model_dump() if ftl else {"error": "FTL state not found"}


def get_pending_proposals() -> list[dict]:
    """Returns all PENDING disruption proposals sorted by severity."""
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


def get_roster(start: date, end: date) -> list[dict]:
    """Returns full roster for a date range."""
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)
```

### Simulate Tools (SIMULATE only — in-memory, no DB write)

```python
def simulate_crew_removal(crew_id: str, leg_id: str) -> dict:
    """
    Simulates removing a crew member from a leg.
    Returns: legality result for current crew, ranked replacement candidates, cascade impact.
    No DB write.
    """
    leg  = get_flight_leg(leg_id)
    crew = get_crew_member(crew_id)
    if not leg or not crew:
        return {"error": "leg or crew not found"}

    candidates = _find_and_rank_candidates_in_memory(crew.role, leg)
    cascade    = _check_cascade_impact(crew_id, leg)

    return {
        "removed_crew":  crew.model_dump(),
        "leg":           leg.model_dump(),
        "candidates":    [{"crew_id": c["crew"].crew_id, "score": c["score"]} for c in candidates[:3]],
        "cascade_impact": cascade,
    }


def simulate_crew_swap(crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str) -> dict:
    """
    Simulates swapping two crew members across two legs.
    Runs legality check for both in both new positions.
    No DB write.
    """
    ...


def simulate_leg_cancellation(leg_id: str) -> dict:
    """
    Simulates cancelling a leg.
    Returns: which crew are released, their next assignments, FTL impact.
    No DB write.
    """
    ...
```

### Action Tools (ACTION only — writes to DB)

```python
def action_mark_crew_unavailable(crew_id: str, leg_id: str, reason: str) -> dict:
    """
    Publishes CrewDisruptedEvent for the given leg.
    DisruptionHandler.handle_crew_disrupted() runs the full pipeline:
      - finds and ranks replacement candidates
      - creates PENDING proposal in disruption_proposals
    Does NOT write to roster directly — the proposal must be approved first.
    """
    leg = get_flight_leg(leg_id)
    if not leg:
        return {"error": f"leg {leg_id} not found"}

    days_until = (leg.scheduled_departure.date() - date.today()).days
    severity   = _classify_severity(days_until)

    crew = get_crew_member(crew_id)
    crew_name = crew.full_name if crew else crew_id

    event_bus.publish(CrewDisruptedEvent(
        crew_id              = crew_id,
        crew_name            = crew_name,
        leg_id               = leg_id,
        reason               = reason,
        days_until_departure = days_until,
        severity             = severity,
        source               = "OPS_DESK",
        detected_at          = datetime.now(timezone.utc),
    ))
    return {"status": "disruption_raised", "crew_id": crew_id, "leg_id": leg_id, "severity": severity}


def action_reassign_crew(leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> dict:
    """
    Human has already decided the replacement — skips DisruptionHandler candidate search.
    Steps:
      1. Legality check on new_crew for this leg — fail fast, no DB write if illegal
      2. replace_roster_crew_assignment: old crew → REPLACED, new crew → CONFIRMED
      3. Publish RosterModifiedEvent → FTL Service + DailyValidator react immediately
    """
    leg      = get_flight_leg(leg_id)
    new_crew = get_crew_member(new_crew_id)
    ftl      = get_crew_duty_state(new_crew_id)
    licenses = get_licenses_for_crew_member(new_crew_id)
    leave    = get_leave_records_for_crew(new_crew_id)

    if not leg or not new_crew or not ftl:
        return {"error": "leg or crew not found"}

    passed, fail_reason = check_legality(
        new_crew, leg, ftl, licenses, leave, leg.scheduled_departure.date()
    )
    if not passed:
        return {"error": f"legality check failed: {fail_reason}"}

    with SessionLocal() as session:
        roster_repository.replace_roster_crew_assignment(
            session, leg_id, old_crew_id, new_crew_id, requested_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = old_crew_id,
        added_crew_id   = new_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))
    return {"status": "reassigned", "leg_id": leg_id, "removed": old_crew_id, "added": new_crew_id}


def action_accept_proposal(proposal_id: str, decided_by: str) -> dict:
    """
    Accepts a PENDING disruption proposal.
    Steps:
      1. Mark proposal ACCEPTED in disruption_proposals
      2. replace_roster_crew_assignment: removed_crew → REPLACED, proposed_crew → CONFIRMED
      3. Publish RosterModifiedEvent → FTL Service updates both crew, DailyValidator re-checks
    If proposal has no proposed_crew_id (manual review case) — mark accepted, skip roster write.
    """
    with SessionLocal() as session:
        result = disruption_repository.accept_proposal(session, proposal_id, decided_by)
        if not result:
            return {"error": "proposal not found"}

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        added_crew_id   = result["proposed_crew_id"]

        if not added_crew_id:
            session.commit()
            return {"status": "accepted", "leg_id": leg_id, "added": None, "note": "no candidate — manual handling required"}

        roster_repository.replace_roster_crew_assignment(
            session, leg_id, removed_crew_id, added_crew_id, decided_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = removed_crew_id,
        added_crew_id   = added_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))
    return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": added_crew_id}


def action_reject_proposal(proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    """
    Rejects a PENDING disruption proposal and surfaces the next best candidate.
    Steps:
      1. Mark proposal REJECTED
      2. Fetch all crew already proposed for this leg + removed_crew (to exclude them)
      3. Re-run _find_and_rank_candidates excluding already-proposed crew
      4. Insert new PENDING proposal with next best candidate
         If no more candidates → proposed_crew_id = None (controller must handle manually)
    """
    with SessionLocal() as session:
        result = disruption_repository.reject_proposal(session, proposal_id, decided_by, rejection_reason)
        if not result:
            return {"error": "proposal not found"}

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        already_proposed = disruption_repository.get_already_proposed_crew(session, leg_id, removed_crew_id)
        session.commit()

    leg = get_flight_leg(leg_id)
    if not leg:
        return {"status": "rejected", "new_proposal_id": None, "reason": "leg no longer exists"}

    removed_crew = get_crew_member(removed_crew_id)
    role = removed_crew.role if removed_crew else None
    if not role:
        with SessionLocal() as session:
            assignment = roster_repository.get_assignment_for_crew(session, leg_id, removed_crew_id)
        role = assignment.get("role") if assignment else None
    if not role:
        return {"status": "rejected", "new_proposal_id": None, "reason": "cannot determine role"}

    from crew_ops.services.disruption_handler.disruption_handler_service import DisruptionHandler
    handler    = DisruptionHandler()
    candidates = handler._find_and_rank_candidates(role, leg)
    candidates = [c for c in candidates if c["crew"].crew_id not in already_proposed]

    proposed_crew_id = candidates[0]["crew"].crew_id if candidates else None
    proposal_score   = candidates[0]["score"] if candidates else 0.0
    new_proposal_id  = f"PROP-{leg_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    with SessionLocal() as session:
        disruption_repository.insert_proposal(session, {
            "proposal_id":       new_proposal_id,
            "leg_id":            leg_id,
            "disruption_type":   "CREW_DISRUPTED",
            "disruption_reason": rejection_reason,
            "removed_crew_id":   removed_crew_id,
            "proposed_crew_id":  proposed_crew_id,
            "proposal_score":    proposal_score,
            "status":            "PENDING",
            "severity":          "HIGH",
            "source":            "CONTROLLER_REJECT",
        })
        session.commit()

    return {"status": "rejected", "new_proposal_id": new_proposal_id, "next_candidate": proposed_crew_id}


def action_approve_roster_leg(leg_id: str, approved_by: str) -> dict:
    """
    Approves a DRAFT roster leg → status PUBLISHED.
    Also flips all DRAFT roster_crew_assignment rows for this leg to CONFIRMED.
    After this, crew are officially notified and the leg is live.
    """
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "published", "leg_id": leg_id, "approved_by": approved_by}
```

---

## Session State

Each conversation session holds minimal state. No conversation history is stored in the DB — only what is needed to handle the current pending confirmation.

```python
# conversation/session.py

from pydantic import BaseModel
from typing import Any

class PendingConfirmation(BaseModel):
    action_type:    str          # MARK_UNAVAILABLE / REASSIGN / SWAP / ACCEPT_PROPOSAL
    action_args:    dict         # the exact args to pass to the action tool on confirm
    summary:        str          # the human-readable summary shown before confirmation
    expires_at:     datetime     # confirmation window — after this, discard and ask again

class SessionState(BaseModel):
    session_id:          str
    last_intent:         str | None = None
    last_entities:       dict       = {}
    pending_confirmation: PendingConfirmation | None = None
```

Session state is held in memory (dict keyed by session_id). For production, replace with Redis. The session is stateless between restarts — acceptable for ops desk use where sessions are short-lived.

---

## LangGraph Graph Definition

```python
# conversation/agent.py

from langgraph.graph import StateGraph, END
from conversation.intent import classify_intent
from conversation.tools import execute_tool
from conversation.formatter import format_response, build_confirmation_package
from conversation.session import SessionState, get_session, save_session

def build_graph():
    graph = StateGraph(dict)

    graph.add_node("classify",     classify_node)
    graph.add_node("route",        route_node)
    graph.add_node("execute",      execute_node)
    graph.add_node("confirm",      confirm_node)
    graph.add_node("format",       format_node)

    graph.set_entry_point("classify")

    graph.add_edge("classify", "route")
    graph.add_conditional_edges("route", route_decision, {
        "query":    "execute",
        "simulate": "execute",
        "confirm":  "confirm",   # pending confirmation from previous turn
        "action":   "confirm",   # new action — build confirmation first
    })
    graph.add_edge("execute",  "format")
    graph.add_edge("confirm",  "execute")   # after human confirms, execute the action
    graph.add_edge("format",   END)

    return graph.compile()
```

The graph is compiled once at startup and reused across all requests. Each request passes its own state dict — no shared mutable state between requests.

---

## Confirmation Package

Before executing any ACTION, the agent builds a confirmation package and presents it to the human. The LLM writes the narrative. The data comes from pure-Python functions.

```python
# conversation/formatter.py

def build_confirmation_package(action_type: str, action_args: dict, legality_result: dict) -> str:
    """
    LLM writes a plain-English summary of what will change.
    Called before any ACTION is executed.
    """
    prompt = f"""
    The controller wants to: {action_type}
    Details: {action_args}
    Legality check result: {legality_result}

    Write a concise confirmation message (3-5 lines) that:
    1. States exactly what will change
    2. Names the crew members and flight affected
    3. Mentions any FTL or legality notes
    4. Ends with: "Confirm? [YES / NO]"

    Do not add any information not present in the details above.
    """
    return llm.invoke(prompt)
```

Example output:

```
Capt Ravi Singh (C-003) will be removed from AI305 BOM→CCU (10:00, today).
Replacement: Capt Vikram Joshi (C-007) — currently at VABB, FTL legal, score 87.
Capt Vikram's duty period after this leg: 4.5h of 13h limit.
This will publish a RosterModifiedEvent. FTL Service and Validator will re-check both crew.
Confirm? [YES / NO]
```

---

## Ambiguity Handling

The classifier detects ambiguity when entity extraction is uncertain. The agent stops and asks for clarification before doing anything.

```
Human: "Mark Sharma as sick"
      ↓
Classifier: ambiguous=True, clarification_needed="Multiple crew named Sharma: FO Priya Sharma (C-002, VIDP) and FO Neha Patel née Sharma (C-008, VABB). Which one?"
      ↓
Agent returns clarification question, no tool called
      ↓
Human: "Priya Sharma"
      ↓
Classifier: ambiguous=False, entities={crew_id: "C-002"}
      ↓
Normal flow continues
```

The session stores `last_entities` so the human does not need to repeat the flight number or date after a clarification.

---

## API Endpoint

```python
# conversation/router.py

from fastapi import APIRouter
from pydantic import BaseModel
from conversation.agent import build_graph
from conversation.session import get_session, save_session

router = APIRouter(prefix="/chat", tags=["Conversation"])

_graph = build_graph()

class ChatRequest(BaseModel):
    session_id: str
    message:    str
    user_id:    str        # ops controller ID — used as decided_by in action tools

class ChatResponse(BaseModel):
    session_id: str
    response:   str
    mode:       str        # QUERY / SIMULATE / ACTION / CONFIRM / CLARIFY
    requires_confirmation: bool = False

@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result  = _graph.invoke({
        "message":    req.message,
        "user_id":    req.user_id,
        "session":    session,
    })
    save_session(req.session_id, result["session"])
    return ChatResponse(
        session_id            = req.session_id,
        response              = result["response"],
        mode                  = result["mode"],
        requires_confirmation = result.get("requires_confirmation", False),
    )
```

Registered in `api/main.py`:

```python
from crew_ops.conversation.router import router as conversation_router
app.include_router(conversation_router)
```

---

## What Needs Confirmation vs What Does Not

| Action | Confirmation | Why |
|--------|-------------|-----|
| Query current status | No | Read only |
| Simulate what-if | No | No state change |
| Mark crew unavailable | Yes | Triggers disruption pipeline |
| Assign replacement | Yes | Modifies roster |
| Swap two crew | Yes | Modifies roster for both |
| Approve weekly roster leg | Yes | Publishes to all crew |
| Accept disruption proposal | Yes | Modifies roster |
| Reject disruption proposal | Yes | Triggers next candidate search |
| Auto-resolve LOW severity | No | System handles, notifies only |

---

## Severity-Driven Push Behaviour

| Severity | Push timing | Escalation | Auto-resolve |
|----------|------------|------------|-------------|
| CRITICAL | Immediately | After 15 min if no response | Never |
| HIGH | Immediately | After 1hr | Never |
| MEDIUM | Immediately | After 4hr | Never |
| LOW | After resolution attempt | None | Yes — if clean replacement found |

LOW severity auto-resolve flow:

```
LOW proposal created
      ↓
top candidate passes legality check
      ↓
auto-accept: POST /disruptions/proposals/{id}/accept with decided_by="AUTO_RESOLVE"
      ↓
RosterModifiedEvent published
      ↓
notify human: "AI555 BOM→PNQ (D7): FO Tanya Mishra replaced by FO Kavya Menon. Auto-resolved."
```

If no clean candidate found for LOW, escalate to MEDIUM and push to human.

---

## Dependencies

New dependencies required in `pyproject.toml`:

```toml
"langgraph>=0.2.0",
"langchain-openai>=0.1.0",    # or langchain-anthropic / langchain-aws for Bedrock
"langchain-core>=0.2.0",
```

LLM provider is configured via environment variable:

```env
# .env
LLM_PROVIDER=openai          # openai / anthropic / bedrock
OPENAI_API_KEY=your_key
# or
ANTHROPIC_API_KEY=your_key
# or (for Bedrock)
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

Added to `config/settings.py`:

```python
llm_provider:    str = "openai"
openai_api_key:  str = ""
anthropic_api_key: str = ""
bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
aws_region:      str = "us-east-1"
```

---

## What the Conversation Layer Does NOT Do

| Not its job | Who handles it |
|-------------|---------------|
| Legality checks | `rules/legality.py` — pure Python |
| FTL calculations | `rules/ftl_simulator.py` — pure Python |
| Candidate ranking | `_score_candidate()` in disruption handler |
| Writing to DB directly | Service calls via `tools.py` which call existing repositories |
| Scheduling jobs | APScheduler in `api/main.py` — already running |
| Detecting flight disruptions | Observer |
| Detecting crew legality breaches | Weekly Planner Validator |
| Sending push notifications to crew phones | Notification service (not yet built) |

---

## File Checklist

| File | Status |
|------|--------|
| `conversation/__init__.py` | Create — empty |
| `conversation/agent.py` | Create — LangGraph graph |
| `conversation/intent.py` | Create — Intent model + classifier |
| `conversation/tools.py` | Create — all tool functions |
| `conversation/formatter.py` | Create — LLM response formatting |
| `conversation/session.py` | Create — session state |
| `conversation/router.py` | Create — FastAPI router |
| `api/main.py` | Update — register conversation router |
| `config/settings.py` | Update — add LLM provider settings |
| `pyproject.toml` | Update — add langgraph + langchain deps |
| `docker/init.sql` | No change — no new tables needed |
| All 4 existing services | No change — zero modifications |

---

## End to End Test

```bash
# Start server
uv run uvicorn crew_ops.api.main:app --reload --port 8000

# QUERY
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "Who is assigned to AI305 today?"}'

# SIMULATE
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "If Capt Ravi is sick today, who can cover AI305?"}'

# ACTION — step 1: agent returns confirmation package
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "Mark Capt Ravi as sick for AI305 today"}'

# ACTION — step 2: human confirms
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "YES"}'

# Verify disruption proposal was created
curl http://localhost:8000/disruptions/proposals
```
