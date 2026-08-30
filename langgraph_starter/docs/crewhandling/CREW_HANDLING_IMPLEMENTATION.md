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
