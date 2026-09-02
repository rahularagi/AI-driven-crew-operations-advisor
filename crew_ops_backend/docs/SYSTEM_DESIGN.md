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
│    Emits: CrewDisrupted                                              │
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
               │                    ┌─── CrewDisrupted (from Planner Job B)
               │                    │
               │                    │    ┌─── CrewDisrupted (from Ops Desk / API)
               ▼                    ▼    ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. DISRUPTION HANDLER                                               │
│    Receives FlightDisrupted OR CrewDisrupted                         │
│    Checks FTL impact → finds replacement → updates roster            │
│    Emits: RosterModified, CrewNotified                               │
└──────────────┬───────────────────────────────────────────────────────┘
               │ RosterModified, LegCompleted
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. FLIGHT TIME LIMITS SERVICE (background, always running)          │
│    Closes duty windows on landing                                    │
│    Runs proactive alert scan every 15 min                            │
│    Recalculates rolling counters every midnight                      │
│    Emits: FlightTimeLimitsAlert                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Scheduler Wiring — How APScheduler Connects Everything

All scheduled jobs are registered in `api/main.py` at startup. The scheduler calls service methods directly. Services never know they are being scheduled — they expose plain methods.

```
api/main.py (startup)
│
├── roster_planner     = RosterPlanner()
├── daily_validator    = DailyValidator()
├── disruption_handler = DisruptionHandler()
├── ftl_service        = FlightTimeLimitsService()
│
├── event_bus.subscribe(FlightDisruptedEvent,  disruption_handler.handle_flight_disrupted)
├── event_bus.subscribe(CrewDisruptedEvent,    disruption_handler.handle_crew_disrupted)
├── event_bus.subscribe(LegCompletedEvent,     ftl_service.on_leg_completed)
├── event_bus.subscribe(RosterModifiedEvent,   ftl_service.on_roster_modified)
├── event_bus.subscribe(RosterModifiedEvent,   daily_validator.on_roster_modified)
│
└── scheduler (APScheduler BackgroundScheduler)
    ├── CronTrigger(day_of_week="sun", hour=23, minute=0)
    │     → roster_planner.build()
    │       reads: flight_schedule, crew_profiles, ftl_states, leave, reserve_schedule
    │       writes: roster_leg, roster_crew_assignment (DRAFT)
    │       on approval: status=PUBLISHED, emits RosterPublished (not yet wired — manual step)
    │
    ├── CronTrigger(hour=3, minute=0)
    │     → daily_validator.validate()
    │       reads: all future roster entries, live ftl_states, leave, license/medical expiry
    │       publishes: CrewDisruptedEvent per broken entry → event_bus → disruption_handler
    │
    ├── CronTrigger(minute="*/15")
    │     → ftl_service.run_proactive_alert_scan()
    │       reads: all ftl_states
    │       publishes: FlightTimeLimitsAlertEvent per crew crossing a threshold
    │
    └── CronTrigger(hour=0, minute=0)
          → ftl_service.run_midnight_recalculation()
            reads: duty history (last 7 and 28 days)
            writes: duty_hours_7_day, flight_hours_28_day, consecutive_duty_days
            publishes: FlightTimeLimitsAlertEvent for any crew crossing warning thresholds
```

### Trigger types per service method

| Method | Trigger type | Who calls it |
|--------|-------------|--------------|
| `RosterPlanner.build()` | Scheduled (Sunday 23:00) | APScheduler |
| `RosterPlanner.build(start, end, requested_by)` | Manual | `POST /planner/build` router |
| `DailyValidator.validate()` | Scheduled (daily 03:00) | APScheduler |
| `DailyValidator.validate(requested_by)` | Manual | `POST /planner/validate` router |
| `DailyValidator.on_roster_modified(event)` | Event | EventBus (RosterModifiedEvent) |
| `FlightObserver.get_todays_active_legs()` | Polling loop | Observer internal loop |
| `FlightObserver.poll(leg)` | Polling loop | Observer internal loop |
| `FlightObserver.get_legs(target_date, offset)` | Manual | `GET /observer/legs` router |
| `DisruptionHandler.handle_flight_disrupted(event)` | Event | EventBus (FlightDisruptedEvent) |
| `DisruptionHandler.handle_crew_disrupted(event)` | Event | EventBus (CrewDisruptedEvent) |
| `FlightTimeLimitsService.on_leg_completed(event)` | Event | EventBus (LegCompletedEvent) |
| `FlightTimeLimitsService.on_roster_modified(event)` | Event | EventBus (RosterModifiedEvent) |
| `FlightTimeLimitsService.run_proactive_alert_scan()` | Scheduled (every 15 min) | APScheduler |
| `FlightTimeLimitsService.run_midnight_recalculation()` | Scheduled (midnight) | APScheduler |

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
| `ftl_states[]` | FTL ledger | Carry-over: 28-day hours, 7-day hours, consecutive days |
| `crew_leave[]` | AIMS / HR | Approved leave — these crew excluded |
| `crew_reserve_schedule[]` | Scheduling system | Existing standby slots — planner fills gaps |

**Algorithm — 3 passes:**

```
Pass 1 — Assign operating crew to legs (earliest departure first)
  For each leg (sorted by scheduled_departure asc):
    find_candidates(role, base, not_on_leave, ftl_available)
    legality_check(crew, leg, simulated_ftl_state)   ← future-mode simulation
    rank(seniority, fatigue_score, same_airport, hours_remaining)
    assign top N crew, advance their simulated ftl_state forward

Pass 2 — Fill reserve/standby slots
  For each date × base airport:
    crew not on operating duties that day → fill reserve gaps

Pass 3 — Full horizon validation
  Replay every crew member's full 6–7 week plan through legality checker
  Flag: duty period breach, rest violation, 7-day cap, 28-day cap, no weekly rest block
  Return validation report — do not publish until clean
```

### Legality Check — Hard Gates (Pass 1 and Pass 3)

These are binary pass/fail checks. Any single failure disqualifies the crew for that leg.

```
1. Role match
   crew.role == leg.required_role
   PILOT legs require PILOT, CABIN legs require CABIN

2. Aircraft type rating
   leg.aircraft_type in crew.type_ratings
   e.g. A320 leg → crew must hold A320 rating

3. License not expired
   crew.license_expiry > leg.scheduled_departure.date()

4. Medical not expired
   crew.medical_expiry > leg.scheduled_departure.date()

5. Not on leave
   no crew_leave entry overlapping leg.scheduled_departure.date()

6. Rest before this leg is sufficient
   (leg.scheduled_departure - simulated_ftl.rest_start_time) >= min_rest_hours
   min_rest_hours = 12 if at_home_base else 10

7. Duty period will not be breached
   simulated_fdp_end = leg.scheduled_departure + max_duty_period_hours
   max_duty_period_hours = base_fdp(report_time, sector_count) - reductions
   check: simulated_fdp_end does not exceed regulatory cap

8. 7-day duty hours cap
   simulated_ftl.duty_hours_7_day + leg.estimated_duty_hours <= 60

9. 28-day flight hours cap
   simulated_ftl.flight_hours_28_day + leg.duration_hours <= 100

10. Consecutive duty days cap
    simulated_ftl.consecutive_duty_days < 7
    (after 6 consecutive days, crew must have a rest day before next duty)

11. Weekly rest block guaranteed
    crew must have at least one 36hr continuous rest block within any rolling 7-day window
    check that assigning this leg does not eliminate the only available rest window
```

### Fatigue Score — Ranking (Pass 1)

Used only for ranking among legal candidates. Does not disqualify.

```
fatigue_score(ftl_state) → float 0–100

  score  = min(ftl.flight_hours_current_duty * 5,  55)   ← current duty hours (max 55pts)
  score += min(ftl.consecutive_duty_days * 10,      20)   ← consecutive days   (max 20pts)
  score += min(ftl.flight_hours_28_day / 5,         25)   ← 28-day load        (max 25pts)
  return min(score, 100.0)
```

### Candidate Ranking Formula (Pass 1)

```
score = 40 (legal base)
      + 30 if crew.current_airport == leg.origin_iata   ← no deadhead needed
      + 20 * (1 - fatigue_score / 100)                  ← lower fatigue = higher score
      + 10 * (1 - cost_factor)                          ← lower cost = higher score

cost_factor = 1.0 if deadhead required, 0.0 if already at origin

Sort descending. Assign top N (N = leg.required_crew_count).
```

### Severity of Validation Failures (Pass 3 and Job B)

| days_until_departure | Severity | What happens |
|---------------------|----------|-------------|
| > 14 days | LOW | Planner quietly re-assigns in next planning cycle |
| 7 – 14 days | MEDIUM | Controller notified, re-plan this week |
| 2 – 7 days | HIGH | Disruption Handler runs full replacement pipeline |
| < 2 days | CRITICAL | Same urgency as a live FlightDisrupted event |

---

### Job B — DAILY VALIDATOR (every morning, 3AM)

Re-checks all future planned weeks against current reality.

**What can break a future plan:**

| What broke | How detected |
|-----------|-------------|
| Crew added sick leave | new `crew_leave` entry covers a future assigned leg |
| License expired | `crew.license_expiry` < leg date |
| Medical expired | `crew.medical_expiry` < leg date |
| FTL state drifted | actual hours higher than planner assumed — future leg will breach cap |
| Aircraft type changed | leg now requires different type rating than assigned crew holds |

**How it runs:**

```
Every morning at 3AM:

  For each future roster entry (status = PLANNED or CONFIRMED):
    load live crew_ftl_state      (not simulated — actual current state)
    load live crew_leave          (any new leave added since last plan?)
    load live crew.license_expiry + medical_expiry
    load live leg.aircraft_type   (did aircraft change?)

    re-run legality_check(crew_id, leg, live_ftl_state)

    if FAIL:
      compute days_until_departure = (leg.scheduled_departure.date() - today).days
      severity = classify_severity(days_until_departure)
      emit CrewDisruptedEvent(
        crew_id, crew_name, leg_id, reason, days_until_departure, severity,
        source="WEEKLY_PLANNER_VALIDATOR", detected_at=now
      )
```

**reason values emitted by Job B:**

| reason | Cause |
|--------|-------|
| `LEAVE_ADDED` | New leave entry covers a future assigned leg |
| `LICENSE_EXPIRED` | Type rating expired before leg date |
| `MEDICAL_EXPIRED` | Medical certificate expired before leg date |
| `FTL_BREACH_PROJECTED` | Accumulated hours will breach cap by that week |
| `AIRCRAFT_TYPE_CHANGED` | Leg now requires different type rating |

### Planner re-validates after RosterModified

When Disruption Handler fixes a live disruption and emits `RosterModifiedEvent`, the Planner re-checks future weeks for the affected crew.

```
RosterModifiedEvent received (added_crew_id = "C-007")

DailyValidator.on_roster_modified():
  load all future roster entries for C-007
  re-run legality_check for each
  if any future leg now breaches → emit CrewDisruptedEvent for that leg
```

This closes the loop — today's fix cannot silently break a future week.

---

## Service 2 — Observer

**Scope: today's active legs only.**

Watches every leg that has crew assigned and is departing today. Polls the live flight status API. Detects when reality deviates from plan. Emits an event. Does nothing else.

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

**Decision logic inside `poll(leg)`:**

```
result = get_next_live_status_poll(leg.leg_id)

if status == "landed":
  emit LegCompletedEvent(leg_id, actual_arrival, destination, crew, delay_minutes)
  stop polling this leg

if status == "cancelled":
  emit FlightDisruptedEvent(disruption_type="CANCELLATION", severity="CRITICAL")
  stop polling this leg

if status == "diverted":
  emit FlightDisruptedEvent(disruption_type="DIVERSION", severity="CRITICAL")
  stop polling this leg

delay = result.departure.delay or 0
if delay >= 240: emit FlightDisruptedEvent(severity="HIGH",   disruption_type="DELAY")
if delay >= 120: emit FlightDisruptedEvent(severity="MEDIUM", disruption_type="DELAY")
if delay >= 30:  emit FlightDisruptedEvent(severity="LOW",    disruption_type="DELAY")
if delay < 30:   no event
```

**What Observer does NOT know about:**
- Flight time limit rules
- Crew availability
- Whether the delay actually causes a problem
- Future weeks

---

## Service 3 — Disruption Handler

Receives `FlightDisruptedEvent` (from Observer) or `CrewDisruptedEvent` (from Planner Job B or Ops Desk via API). Same pipeline handles both.

**Processing pipeline:**

```
Step 1 — Classify urgency
  FlightDisruptedEvent → urgency from event.severity
  CrewDisruptedEvent   → urgency from event.severity (already computed at emit time)

  CRITICAL / HIGH → run pipeline immediately
  MEDIUM          → run pipeline, 4hr window for controller to respond
  LOW             → run pipeline, auto-resolve if clean replacement found

Step 2 — Identify affected crew
  FlightDisruptedEvent: affected_crew = event.assigned_crew (all crew on the leg)
  CrewDisruptedEvent:   affected_crew = [event.crew_id]

Step 3 — Duty period impact check
  For each affected crew member:
    ftl = get_ftl_state(crew_id)
    new_projected_end = leg.scheduled_departure + delay_minutes + leg.duration_hours
    if new_projected_end > ftl.projected_duty_period_end:
      duty_period_breached = True
    rest_before_next_duty = next_leg.scheduled_departure - new_projected_end
    if rest_before_next_duty < min_rest_hours:
      rest_violation = True
  if no breach and no violation → log and close (no replacement needed)

Step 4 — Cascade check
  For each affected crew member:
    find all other legs assigned to this crew in the next 48 hours
    simulate ripple: if this leg is delayed, does the crew make their next leg?
    flag each ripple leg as potentially affected

Step 5 — Find candidates (pure Python)
  airport = event.origin (FlightDisrupted) or ftl.current_airport (CrewDisrupted)
  role    = leg.required_role

  all_crew = get_all_crew_members()
  ftl_states = {s.crew_id: s for s in get_all_ftl_states()}

  candidates = [
    crew for crew in all_crew
    if crew.role == role
    and crew.employment_status == "ACTIVE"
    and ftl_states[crew.crew_id].status == "AVAILABLE"
    and leg.aircraft_type in crew.type_ratings
    and not on_leave(crew.crew_id, leg.scheduled_departure.date())
    and legality_check(crew, leg, ftl_states[crew.crew_id]) == PASS
  ]

Step 6 — Score and rank (pure Python)
  For each candidate:
    fatigue = fatigue_score(ftl_states[crew.crew_id])
    score   = 40                                              ← legal base
            + 30 if ftl.current_airport == leg.origin_iata   ← same airport
            + int(20 * (1 - fatigue / 100))                  ← low fatigue
            + 10 if not deadhead_required                    ← low cost

  Sort descending. Always append "delay the flight" as final fallback option.

Step 7 — LLM narration
  Input:  ranked list (structured facts — crew name, score, reason, ftl summary)
  Output: human-readable explanation of each option
  Constraint: LLM cannot change rankings or invent data

Step 8 — Human decision point
  CRITICAL → present to controller immediately, auto-escalate after 15min if no response
  HIGH     → present to controller immediately, 1hr window
  MEDIUM   → present to controller, 4hr window
  LOW      → auto-resolve if clean replacement found, notify controller only

Step 9 — Closed loop (on approval)
  Update roster_crew_assignment: remove old crew entry, add new crew entry
  Update crew_ftl_state for removed crew: status = UNAVAILABLE (counters unchanged)
  Update crew_ftl_state for added crew:   duty_start_time = now, status = AVAILABLE
  Emit RosterModifiedEvent(leg_id, removed_crew_id, added_crew_id)
    → DailyValidator re-validates future weeks for both crew
    → FlightTimeLimitsService updates ftl state for both crew
```

### Fatigue Score Calculation

```
fatigue_score(ftl: CrewFlightTimeLimitsState) → float 0–100

  score  = min(ftl.flight_hours_current_duty * 5,  55)
  score += min(ftl.consecutive_duty_days * 10,      20)
  score += min(ftl.flight_hours_28_day / 5,         25)
  return min(score, 100.0)

Examples:
  4h current duty + 3 consecutive days + 60h/28day → score = 20 + 30 + 12 = 62
  0h current duty + 0 consecutive days + 20h/28day → score =  0 +  0 +  4 =  4  (fresh)
  8h current duty + 6 consecutive days + 95h/28day → score = 40 + 60 + 25 = 100 (capped)
```

### Crew-Side Disruption — Manual Entry

**Trigger:** Controller calls `POST /crew/{crew_id}/unavailable`

```
body: { reason, affected_from, affected_until }

→ find all roster entries for crew_id where leg.scheduled_departure in [affected_from, affected_until]
→ for each affected leg:
    days_until = (leg.scheduled_departure.date() - today).days
    severity   = classify_severity(days_until)
    emit CrewDisruptedEvent(crew_id, leg_id, reason, days_until, severity, source="OPS_DESK")
→ return list of all affected legs immediately (controller sees full impact before pipeline runs)
```

**reason values from Ops Desk:**

| reason | Cause |
|--------|-------|
| `SICK_CALL` | Crew calls in sick |
| `EMERGENCY_LEAVE` | Family emergency, bereavement |
| `MEDICAL_GROUNDING` | Doctor grounds crew immediately |
| `NO_SHOW` | Crew did not report at check-in |
| `URGENT_TRAINING` | Regulator mandates emergency simulator check |

**Severity based on days_until_departure:**

| days_until_departure | Severity |
|---------------------|----------|
| < 1 day | CRITICAL |
| 1 – 2 days | HIGH |
| 2 – 7 days | HIGH |
| 7 – 14 days | MEDIUM |
| > 14 days | LOW |

---

## Service 4 — Flight Time Limits Service

Always running. Never called directly — only reacts to events and scheduled triggers.

### State Fields and What They Mean

```
CrewFlightTimeLimitsState

status                         AVAILABLE / RESTING / UNAVAILABLE
                               AVAILABLE  = on duty or ready for duty
                               RESTING    = in mandatory rest, cannot be assigned
                               UNAVAILABLE = sick, leave, grounded

── Current duty window ──────────────────────────────────────────────
duty_start_time                when crew reported for current duty
duty_end_time                  when current duty actually ended (set on LegCompleted)
projected_duty_period_end      duty_start_time + max_duty_period_hours (recalculated on each leg)
flight_hours_current_duty      block hours flown so far in this duty period
sectors_current_duty           number of legs flown in this duty period
max_duty_period_hours          regulatory cap for this duty (depends on report time + sector count)

── Rest state ───────────────────────────────────────────────────────
rest_start_time                when rest clock started (actual_arrival + 30min debrief)
last_rest_end_time             when last rest period ended (= duty_start_time of current duty)
rest_hours_available           hours of rest accumulated so far in current rest period
rest_type                      HOME_REST (at home_base) / HOTEL_REST (away)
earliest_checkout              rest_start_time + min_rest_hours (when crew can be called again)

── Rolling counters ─────────────────────────────────────────────────
flight_hours_28_day            total block hours in rolling 28-day window  (cap: 100h)
duty_hours_7_day               total duty hours in rolling 7-day window    (cap: 60h)
duty_hours_28_day              total duty hours in rolling 28-day window   (cap: 190h)
consecutive_duty_days          days with at least one duty in a row        (cap: 6)
last_weekly_rest_end           end of last 36hr continuous rest block

── Location ─────────────────────────────────────────────────────────
home_base                      crew's assigned base airport (ICAO)
current_airport                airport where crew is right now
at_home_base                   current_airport == home_base
```

### On LegCompleted — Duty Window Update

```
Triggered by: LegCompletedEvent

for each crew_id in event.crew:
  ftl = get_ftl_state(crew_id)
  crew = get_crew_member(crew_id)

  ftl.flight_hours_current_duty += leg.duration_hours
  ftl.sectors_current_duty      += 1
  ftl.current_airport            = event.destination
  ftl.at_home_base               = (event.destination == crew.home_base)

  ftl.rest_start_time  = event.actual_arrival + 30min   ← debrief time
  ftl.rest_type        = "HOME_REST" if at_home_base else "HOTEL_REST"
  ftl.min_rest_hours   = 12 if at_home_base else 10
  ftl.earliest_checkout = ftl.rest_start_time + ftl.min_rest_hours
  ftl.status           = "RESTING"

  if not at_home_base:
    trigger hotel notification

  ftl.last_updated = now
  update_ftl_state(ftl)
```

### On RosterModified — Assignment Change

```
Triggered by: RosterModifiedEvent

if event.removed_crew_id:
  ftl = get_ftl_state(removed_crew_id)
  ftl.status       = "UNAVAILABLE"    ← duty counters unchanged, just mark unavailable
  ftl.last_updated = now
  update_ftl_state(ftl)

if event.added_crew_id:
  ftl = get_ftl_state(added_crew_id)
  ftl.duty_start_time            = now
  ftl.projected_duty_period_end  = now + max_duty_period_hours
  ftl.status                     = "AVAILABLE"
  ftl.last_updated               = now
  update_ftl_state(ftl)
```

### Proactive Alert Scan — Every 15 Minutes

```
for each ftl in get_all_ftl_states():

  1. Duty period approaching
     if ftl.status == "AVAILABLE" and ftl.projected_duty_period_end:
       remaining_hours = (ftl.projected_duty_period_end - now).total_seconds() / 3600
       if 0 < remaining_hours < 2.0:
         emit FlightTimeLimitsAlertEvent(alert_type="DUTY_PERIOD_APPROACHING")

  2. Cumulative hours warning
     if ftl.flight_hours_28_day > 90:
       emit FlightTimeLimitsAlertEvent(alert_type="CUMULATIVE_HOURS_WARNING")

  3. Weekly rest overdue
     if ftl.last_weekly_rest_end:
       days_since_rest = (now - ftl.last_weekly_rest_end).days
       if days_since_rest >= 6:
         emit FlightTimeLimitsAlertEvent(alert_type="WEEKLY_REST_OVERDUE")

  4. Rest violation risk
     if ftl.status == "RESTING" and ftl.earliest_checkout:
       if next_assigned_duty_start < ftl.earliest_checkout:
         emit FlightTimeLimitsAlertEvent(alert_type="REST_VIOLATION_RISK")

  5. Circadian low window tomorrow
     if next_duty_report_time is between 00:00–06:00 local:
       emit FlightTimeLimitsAlertEvent(alert_type="CIRCADIAN_LOW_WINDOW")

  6. License expiring within 30 days
     crew = get_crew_member(ftl.crew_id)
     if crew.license_expiry - today <= 30 days:
       emit FlightTimeLimitsAlertEvent(alert_type="LICENSE_EXPIRING_SOON")

  7. Medical expiring within 30 days
     if crew.medical_expiry - today <= 30 days:
       emit FlightTimeLimitsAlertEvent(alert_type="MEDICAL_EXPIRING_SOON")
```

### Midnight Recalculation — Every Midnight

```
for each crew_id:
  duty_history = load_duty_records(crew_id, last_28_days)

  flight_hours_28_day    = sum(r.flight_hours for r in duty_history if r.date >= today - 28days)
  duty_hours_7_day       = sum(r.duty_hours   for r in duty_history if r.date >= today - 7days)
  duty_hours_28_day      = sum(r.duty_hours   for r in duty_history if r.date >= today - 28days)
  consecutive_duty_days  = count_consecutive_days_ending_today(duty_history)

  last_weekly_rest_end   = find_last_36hr_rest_block(duty_history)

  update_ftl_state(ftl)

  if flight_hours_28_day > 90:
    emit FlightTimeLimitsAlertEvent(alert_type="CUMULATIVE_HOURS_WARNING")
  if consecutive_duty_days >= 6:
    emit FlightTimeLimitsAlertEvent(alert_type="CONSECUTIVE_DAYS_WARNING")
```

### Max Duty Period Hours — How It Is Calculated

The regulatory cap on a duty period depends on two inputs: report time (local) and number of sectors planned.

```
Base FDP table (report time × sector count → max hours):

  Report time (local)   1 sector   2 sectors   3 sectors   4+ sectors
  00:00 – 05:59         11.0h      10.5h        10.0h        9.5h      ← circadian low
  06:00 – 13:59         13.0h      12.5h        12.0h        11.5h     ← peak alertness
  14:00 – 17:59         12.0h      11.5h        11.0h        10.5h
  18:00 – 23:59         11.5h      11.0h        10.5h        10.0h

Reductions applied on top:
  circadian_low_window_encroachment = True  → subtract 1.0h
  duty_period_reduction_hours > 0           → subtract that value (e.g. augmented crew rules)

Extensions allowed:
  duty_period_extended = True               → add duty_period_extension_hours (max 2.0h, once per duty)
  requires: commander discretion + no circadian low encroachment

Final:
  max_duty_period_hours = base_fdp(report_time, sectors)
                        - duty_period_reduction_hours
                        - (1.0 if circadian_low_window_encroachment else 0)
                        + (duty_period_extension_hours if duty_period_extended else 0)
```

---

## Complete Event List

| Event | Emitted by | Consumed by |
|-------|-----------|-------------|
| `FlightDisruptedEvent` | Observer | Disruption Handler |
| `LegCompletedEvent` | Observer | Flight Time Limits Service |
| `CrewDisruptedEvent` | Planner Job B / Ops Desk via API | Disruption Handler |
| `RosterModifiedEvent` | Disruption Handler | Weekly Planner (re-validate), FTL Service |
| `FlightTimeLimitsAlertEvent` | FTL Service | (notification service — not yet wired) |

---

## Full Timeline of a Flight

```
6–7 weeks before departure
  Planner Job A runs (Sunday 23:00)
  Pass 1: assigns crew to leg (legality check + ranking)
  Pass 2: fills reserve slots
  Pass 3: full horizon validation
  Writes roster_leg + roster_crew_assignment (status = DRAFT)
  On controller approval → status = PUBLISHED
        │
        ▼
Every morning (3AM) until departure
  Planner Job B runs
  Re-checks this leg against live ftl_state, leave, license/medical expiry, aircraft type
  If anything broken:
    emit CrewDisruptedEvent → event_bus → DisruptionHandler.handle_crew_disrupted()
    DisruptionHandler runs replacement pipeline → emits RosterModifiedEvent
    DailyValidator.on_roster_modified() re-checks future weeks for affected crew
        │
        ▼
Day before departure
  Planner Job B confirms: all crew still valid
  roster entry updated to CONFIRMED
        │
        ▼
Day of departure — Observer takes over
  Observer polls this leg (today only)
  Departure > 2hrs: every 15 min
  Boarding: every 5 min
  Airborne: every 60 sec
        │
        ├── delay >= 30min  → FlightDisruptedEvent → DisruptionHandler
        ├── cancelled       → FlightDisruptedEvent CRITICAL → DisruptionHandler
        ├── crew goes sick  → POST /crew/{id}/unavailable
        │                   → CrewDisruptedEvent → DisruptionHandler
        │
        ▼
Flight lands
  Observer detects status = "landed"
  Emits LegCompletedEvent(leg_id, actual_arrival, destination, crew, delay_minutes)
  Stops polling this leg
        │
        ▼
FTL Service receives LegCompletedEvent
  For each crew on the leg:
    flight_hours_current_duty += leg.duration_hours
    sectors_current_duty += 1
    current_airport = destination
    at_home_base = (destination == crew.home_base)
    rest_start_time = actual_arrival + 30min
    min_rest = 12h if at_home_base else 10h
    earliest_checkout = rest_start_time + min_rest
    status = "RESTING"
  If away from base → trigger hotel notification
        │
        ▼
Every 15 min — FTL proactive scan
  Check all crew for: duty period approaching, cumulative cap, weekly rest overdue,
  rest violation risk, circadian low window, license/medical expiring
  Emit FlightTimeLimitsAlertEvent per finding
        │
        ▼
Every midnight — FTL rolling recalculation
  Recalculate flight_hours_28_day, duty_hours_7_day, consecutive_duty_days
  Emit FlightTimeLimitsAlertEvent for any crew crossing warning thresholds
```

---

## What Each Service Owns

| | Planner Job A | Planner Job B | Observer | Disruption Handler | FTL Service |
|--|:---:|:---:|:---:|:---:|:---:|
| Reads flight schedule API | ✅ | ❌ | ✅ (today only) | ❌ | ❌ |
| Reads crew FTL state | ✅ (simulated) | ✅ (live) | ❌ | ✅ (live) | ✅ (live) |
| Runs legality checker | ✅ (future) | ✅ (future) | ❌ | ✅ (live) | ❌ |
| Writes roster_leg + roster_crew_assignment | ✅ DRAFT→PUBLISHED | ❌ | ❌ | ❌ | ❌ |
| Modifies roster_crew_assignment | ❌ | ❌ | ❌ | ✅ | ❌ |
| Writes crew_ftl_state | ❌ | ❌ | ❌ | ✅ (on approval) | ✅ (on events) |
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

Flow: Intent = SIMULATE → run in memory → legality check → cascade check
      → rank options → LLM narrates → respond with outcome
      → "Want me to apply it?"   No state change yet.
```

**Mode 3 — ACTION (writes to system, requires confirmation)**
```
"Mark Capt Ravi as sick for today"
"Assign FO Deepa to AI305 instead of FO Sharma"
"Swap Capt Mehta and Capt Nisha on tomorrow's flights"

Flow: Intent = ACTION → legality check → cascade check
      → build confirmation package → present to human
      → human confirms → service call → event emitted → pipeline runs
      → respond with what changed
```

### System-Initiated Decisions (push to human)

Disruption Handler reaches Step 8 and pushes to human when severity is HIGH or CRITICAL:

```
"AI305 BOM→CCU departs in 90min. Capt Ravi called sick.
 Best replacement: Capt Vikram (reserve at BOM, FTL legal).
 Second option: FO Nair (deadhead from DEL, adds 45min to duty period).
 Confirm Capt Vikram? [YES / NO / SHOW MORE OPTIONS]"
```

| Severity | Behaviour |
|----------|----------|
| CRITICAL | Push to human immediately. Auto-escalate after 15min if no response |
| HIGH | Push to human immediately. 1hr window |
| MEDIUM | Push to human. 4hr window to respond |
| LOW | Auto-resolve if clean replacement found. Notify human only |

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

### What LLM Does vs Pure Python

| Task | Who |
|------|-----|
| Classify intent from free text | LLM |
| Legality check (hard gates) | Pure Python |
| Cascade impact check | Pure Python |
| Fatigue score calculation | Pure Python |
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
│   └── SYSTEM_DESIGN.md              ← this file
│
├── models/
│   ├── flight_leg.py                 FlightLeg
│   ├── crew_member.py                CrewMember (static profile)
│   ├── crew_flight_time_limits_state.py  CrewFlightTimeLimitsState (live ledger)
│   ├── crew_leave.py                 CrewLeave
│   ├── crew_reserve.py               CrewReserveSchedule
│   ├── crew_license.py               CrewLicense
│   └── events.py                     all event shapes
│
├── services/
│   ├── event_bus.py                  EventBus singleton
│   ├── weekly_planner/
│   │   └── weekly_planner_service.py RosterPlanner (Job A), DailyValidator (Job B)
│   ├── observer/
│   │   └── observer_service.py       FlightObserver — polls today's legs
│   ├── disruption_handler/
│   │   └── disruption_handler_service.py  full replacement pipeline
│   └── flight_time_limits/
│       └── flight_time_limits_service.py  duty events, alerts, midnight recalc
│
├── clients/                          swap point — mock vs real API
│   ├── crew_profile_client.py
│   ├── flight_schedule_client.py
│   ├── flight_status_client.py
│   ├── ftl_client.py
│   ├── license_client.py
│   └── reserve_client.py
│
├── api/
│   ├── main.py                       service wiring, scheduler, event subscriptions
│   └── routers/
│       ├── planner_router.py         POST /planner/build, POST /planner/validate
│       ├── observer_router.py        GET /observer/legs/today, GET /observer/legs
│       ├── crew_router.py            GET /crew/{id}/ftl, POST /crew/{id}/unavailable
│       └── ftl_router.py             POST /ftl/scan, POST /ftl/recalculate
│
├── config/
│   └── settings.py                   env-backed settings, roster_planning_weeks
│
├── db/
│   ├── database.py
│   └── repositories/
│
└── data/
    ├── mock/                         raw mock data (never changes)
    └── pipeline/                     one-time database seeding scripts
```
