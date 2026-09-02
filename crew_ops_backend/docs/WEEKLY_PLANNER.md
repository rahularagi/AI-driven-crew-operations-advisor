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
