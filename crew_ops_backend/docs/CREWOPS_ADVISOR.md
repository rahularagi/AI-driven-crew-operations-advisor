# CrewOps Advisor — AI-Driven Operational Superintelligence for Airline Crew Control

> AI system that helps airline crew controllers instantly resolve disruptions, find legal replacements, update rosters, and notify affected crew — in seconds instead of 30 minutes.

---

## What This System Does

An airline's Crew Control department manages hundreds of crew members daily. When disruptions happen (sick calls, delays, aircraft swaps), a human controller manually:
1. Finds who is available
2. Checks if they are legally allowed to fly (duty hours, rest, license)
3. Picks the best option (cost, fatigue, location)
4. Updates the roster
5. Notifies the affected crew member

This takes 15–30 minutes per disruption. CrewOps Advisor does all 5 steps in under 10 seconds.

---

## System Architecture

```
Controller types: "Captain Rahul sick, Flight AI-202, 9AM Delhi"
                              │
                              ▼
                    ┌─────────────────┐
                    │    Analyzer     │  parse text → DisruptionEvent
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   ReAct Agent   │  LangGraph tool-calling loop
                    │  find_crew      │
                    │  check_legality │
                    │  calc_cost      │
                    │  cascade_check  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Ranker      │  score: legal + location + fatigue + cost
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │     Advisor     │  human-readable recommendation
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Roster Updater │  apply change + log reason
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │    Notifier     │  SMS/email to removed + replacement crew
                    └─────────────────┘
```

---

## Folder Structure

```
crew-ops-advisor/
├── models/
│   ├── crew.py              CrewMember — id, role, base, licenses, fatigue (static profile)
│   ├── crew_ftl_state.py    CrewFTLState — live duty/rest/cumulative counters per crew member
│   ├── flight.py            Flight — origin, dest, departure, aircraft type, assigned crew
│   └── disruption.py        DisruptionEvent — type, affected flight, affected crew
├── rules/
│   ├── legality.py          CrewLegalityChecker — reads crew_ftl_state, pure Python hard gates
│   └── fdp_table.py         FDP bracket table — report time × sector count → max FDP
├── data/
│   ├── seed.py              25 crew + 15 flights mock data
│   └── ftl_seed.py          initial crew_ftl_state rows seeded from crew duty history
├── tools/
│   └── crew_tools.py        4 LangGraph @tools
├── agent/
│   ├── state.py             CrewOpsState TypedDict
│   ├── nodes.py             analyzer, ranker, advisor, roster_updater, notifier nodes
│   └── graph.py             LangGraph wiring
├── ftl/
│   └── ftl_service.py       read/write crew_ftl_state, recalculate on duty events
├── roster/
│   └── roster_service.py    read/write roster, change log
├── notifications/
│   └── notifier.py          crew notification with message templates
├── api/
│   └── main.py              FastAPI endpoints
└── ui/
    └── app.py               Streamlit dashboard
```

---

## Step 1 — Models

Four core dataclasses everything else depends on.

**CrewMember** (static profile) — id, name, role (PILOT/CABIN), base_airport, current_airport, status, licenses (["A320","B737"]), phone, email

**CrewFTLState** (live ledger, one row per crew member) — see Step 2 for full field list. This is the source of truth for all legality checks. Never stored inside CrewMember.

**Flight** — flight_id, origin, destination, scheduled_departure, status, aircraft_type, required_crew ({PILOT:2, CABIN:4}), assigned_crew ([crew_ids]), duration_hours

**DisruptionEvent** — type (SICK_CALL/DELAY/CANCELLATION/AIRCRAFT_SWAP/NO_SHOW), affected_flight_id, affected_crew_id, details, timestamp

---

## Step 2 — Live FTL Tracking Table (crew_ftl_state)

This is a dedicated live ledger — separate from the crew profile — that tracks every crew member's current position against all regulatory limits in real time.

**Why it is a separate table, not part of the crew profile:**
- Crew profile (name, role, licenses) changes once a month. FTL state changes on every duty event — report-in, takeoff, landing, rest start, rest end.
- Mixing them creates race conditions and destroys the audit trail.
- The legality checker needs a flat, fast lookup per candidate — not a join across tables.
- Proactive alerts scan all crew every 15 minutes — they need one table to scan, not a computed view.

**When it is updated:**
- Crew reports for duty → `duty_start_time` set, `status` → ON_DUTY, `max_fdp_allowed` calculated from FDP bracket table
- Flight departs → `flight_time_current_duty` starts accumulating
- Flight lands → `flight_time_current_duty` += sector block hours, `sectors_current_duty` += 1
- Crew released from duty → `duty_end_time` set, `rest_start_time` set, rolling counters updated
- Rest period ends → `status` → AVAILABLE, `last_rest_end_time` updated
- Delay occurs while on duty → `projected_fdp_end` recalculated immediately
- Commander's discretion invoked → `fdp_extension_used` = true, `safety_report_required` = true, `compensatory_rest_required` calculated

**The table:**

| Field | Type | Description | Updated When |
|-------|------|-------------|-------------|
| crew_id | string | FK to crew profile | — |
| role | PILOT / CABIN | copied from profile for fast filtering | profile change |
| **— Current Duty Window —** | | | |
| duty_start_time | datetime | when crew reported for current duty | report-in |
| duty_end_time | datetime\|null | when current duty ended (null if on duty) | release |
| projected_fdp_end | datetime | duty_start + max_fdp_allowed, recalculated on every delay | every delay event |
| flight_time_current_duty | float (hrs) | block hours flown in this duty period so far | each landing |
| sectors_current_duty | int | number of landings in this duty period | each landing |
| **— Rest Tracking —** | | | |
| rest_start_time | datetime\|null | when current rest period began | duty release |
| last_rest_end_time | datetime | when last rest period ended | report-in |
| rest_hours_available | float | hours elapsed since last_rest_end_time (live) | continuous |
| at_home_base | bool | true if resting at home base (affects min rest threshold) | location update |
| **— Rolling Cumulative Counters —** | | | |
| flight_hours_28_day | float | block hours in last 28 consecutive days | each landing |
| flight_hours_calendar_year | float | block hours in current calendar year | each landing |
| duty_hours_7_day | float | total duty hours in last 7 consecutive days | duty end |
| duty_hours_28_day | float | total duty hours in last 28 consecutive days | duty end |
| consecutive_duty_days | int | how many days in a row crew has had a duty period | duty start |
| last_weekly_rest_end | datetime | when last 36hr+ continuous rest ended | rest end |
| **— FDP Limit for Current Duty —** | | | |
| max_fdp_allowed | float (hrs) | looked up from FDP bracket table at duty_start_time | report-in |
| wocl_encroachment | bool | true if duty window overlaps 02:00–06:00 | report-in |
| fdp_reduction_applied | float (hrs) | hours subtracted from max_fdp due to WOCL | report-in |
| **— Commander's Discretion —** | | | |
| fdp_extension_used | bool | true if captain invoked discretion this duty | discretion event |
| extension_hours | float | how many hours extended (max 2.0) | discretion event |
| safety_report_required | bool | always true when fdp_extension_used = true | discretion event |
| compensatory_rest_required | float (hrs) | extra rest owed after discretion use | discretion event |
| **— Crew Location & Rest Place —** | | | |
| home_base | ICAO code | permanent base airport from contract — never changes | profile change |
| current_airport | ICAO code | where crew physically is right now | every landing |
| at_home_base | bool | true when current_airport == home_base | every landing |
| rest_type | HOME_REST / LAYOVER_REST | determines min rest threshold | duty release |
| hotel_location | ICAO code | airport where crew is staying (null if at home base) | duty release away from base |
| hotel_checkin | datetime | when crew checked in to layover hotel | duty release |
| earliest_checkout | datetime | hotel_checkin + min_rest_required | duty release |
| next_positioning_flight | string | flight_id of deadhead back to home base (if needed) | roster assignment |
| return_to_base_eta | datetime | when crew expected back at home_base | roster assignment |
| **— Status —** | | | |
| status | AVAILABLE/ON_DUTY/RESTING/SICK/OFF_DUTY | current state | every event |
| last_updated | datetime | timestamp of last write | every event |

---

**FDP bracket table — max FDP by report time and sector count:**

| Report Time (Local) | 1–2 sectors | 3 sectors | 4+ sectors |
|--------------------|-------------|-----------|------------|
| 0600 – 0659 | 13.0 hrs | 12.0 hrs | 11.0 hrs |
| 0700 – 1259 | 13.0 hrs | 12.0 hrs | 11.0 hrs |
| 1300 – 1759 | 12.0 hrs | 11.0 hrs | 10.0 hrs |
| 1800 – 2159 | 11.0 hrs | 10.0 hrs | 9.0 hrs |
| 2200 – 2259 | 10.0 hrs | 9.0 hrs | 8.0 hrs |
| 2300 – 0459 | 9.0 hrs | 8.0 hrs | 7.5 hrs |
| 0500 – 0559 | 10.0 hrs | 9.0 hrs | 8.0 hrs |

WOCL reduction: if duty window overlaps 02:00–06:00 by more than 2 hours → subtract 1.0 hr from max_fdp_allowed.

---

**Minimum rest thresholds:**

| Situation | Minimum Rest Required |
|-----------|----------------------|
| At home base | max(12 hrs, preceding duty period duration) |
| Away from base (layover hotel) | 10 hrs in suitable accommodation |
| After commander's discretion use | normal minimum + compensatory_rest_required |
| After WOCL duty (02:00–06:00 encroachment) | 12 hrs minimum regardless of base |
| Weekly rest | 36 hrs continuous (48 hrs recommended) |

---

**How the legality checker reads this table:**

```
check_legality(crew_id, flight) → (is_legal, reasons[], warnings[]):

  ftl = crew_ftl_state[crew_id]

  # Hard gates — any failure = ILLEGAL, crew excluded entirely
  projected_duty = (now - ftl.duty_start_time).hours + flight.duration_hours
  if projected_duty > ftl.max_fdp_allowed:              FAIL: "FDP breach — {projected:.1f}h > {ftl.max_fdp_allowed}h"
  if ftl.rest_hours_available < min_rest_required:      FAIL: "Insufficient rest — {ftl.rest_hours_available:.1f}h < 10h"
  if flight.aircraft_type not in crew.licenses:         FAIL: "Not type-rated for {flight.aircraft_type}"
  if ftl.flight_hours_28_day + flight.duration > 100:   FAIL: "28-day block hour cap breach"
  if ftl.duty_hours_7_day + projected_duty > 60:        FAIL: "7-day duty cap breach"
  if ftl.status != AVAILABLE:                           FAIL: "Status is {ftl.status}"

  # Soft warnings — legal but flagged in recommendation
  if projected_duty > ftl.max_fdp_allowed - 1.0:        WARN: "Within 1hr of FDP limit"
  if ftl.wocl_encroachment:                             WARN: "Duty crosses WOCL — reduced alertness expected"
  if ftl.consecutive_duty_days >= 4:                    WARN: "Day {ftl.consecutive_duty_days} of consecutive duty"
  if ftl.flight_hours_28_day + flight.duration > 90:    WARN: "Approaching 28-day block hour cap"

  # Commander's discretion path
  if not ftl.fdp_extension_used and overage <= 2.0:
    return LEGAL_WITH_DISCRETION: "Captain may extend FDP by up to 2hrs — safety report required"
```

---

**How proactive alerts scan this table (every 15 min):**

```
Alert 1 — FDP approaching:
  status == ON_DUTY and (projected_fdp_end - now) < 2 hours
  → "Captain Mehta: FDP limit in 1h 45min on current duty"

Alert 2 — Rest violation risk:
  status == RESTING and next_scheduled_duty - rest_start < min_rest_required
  → "Cabin crew Anita: only 9.5h rest before AI-450 — minimum is 10h"

Alert 3 — Weekly rest overdue:
  (now - last_weekly_rest_end) > 6 days
  → "Captain Singh: no 36hr rest block in last 6 days — required within 24hrs"

Alert 4 — Cumulative cap approaching:
  flight_hours_28_day > 90
  → "FO Sharma: 92h block hours in 28 days — 8h remaining before cap"

Alert 5 — WOCL duty tomorrow:
  tomorrow's scheduled duty_start between 0000–0600
  → "Cabin crew Priya: tomorrow's report time 04:30 — WOCL duty, reduced FDP applies"
```

---

## Step 3 — Rules Engine

`CrewLegalityChecker.check(crew_id, flight)` → `(is_legal, reasons[], warnings[], discretion_available)`

Reads directly from `crew_ftl_state`. All checks are pure Python — no LLM involvement. The full runtime execution of this checker (candidate loop, hard gates, discretion path) runs in Step 16.

| Rule | Check | Source Field |
|------|-------|--------------|
| 1 | projected_duty <= max_fdp_allowed | ftl.duty_start_time, ftl.max_fdp_allowed |
| 2 | rest_hours_available >= min_rest_required | ftl.last_rest_end_time, ftl.at_home_base |
| 3 | flight.aircraft_type in crew.licenses | crew profile |
| 4 | flight_hours_28_day + flight.duration <= 100 | ftl.flight_hours_28_day |
| 5 | status == AVAILABLE | ftl.status |
| 6 | current_airport == flight.origin (else deadhead flagged) | crew profile |
| 7 | deadhead_duration + leg.duration <= max_fdp (multi-leg) | ftl + leg model |
| 8 | has_crew_rest_facility if augmented FDP extension needed | aircraft model |

---

## Step 4 — Tools

4 `@tool` functions the LangGraph ReAct agent calls (same pattern as `example_agent.py`):

- `find_available_crew(flight_id, role)` — returns all crew filtered by role + status
- `check_legality(crew_id, flight_id)` — runs all 6 rules, returns pass/fail + reasons
- `calculate_assignment_cost(crew_id, flight_id)` — deadhead cost, overtime flag, fatigue score
- `get_cascade_impact(crew_id)` — returns other flights this crew is assigned to (ripple effect)

---

## Step 5 — LangGraph Agent

**State** flowing through the graph:

```
disruption_text       raw input from controller
disruption            parsed DisruptionEvent
affected_flight       Flight object
candidates            list of crew with legality + cost per candidate
ranked_candidates     sorted by composite score
recommendation        final human-readable output
cascade_warnings      ripple effects detected
roster_updated        bool
notifications_sent    list of crew IDs notified
messages              LangGraph message list
```

**Graph node flow:**

```
START
  │
  ▼
[analyzer]        LLM parses free text → DisruptionEvent + affected Flight
  │
  ▼
[react_agent]     ReAct loop — calls tools until all candidates evaluated
  │               find_available_crew → check_legality → calculate_cost → cascade_check
  ▼
[ranker]          scores each candidate:
  │               legal(40pts) + same_airport(30pts) + low_fatigue(20pts) + low_cost(10pts)
  ▼
[advisor]         LLM writes recommendation with per-rule ✓/✗ explanation
  │
  ▼
[roster_updater]  removes old crew, assigns new crew, logs reason + timestamp
  │
  ▼
[notifier]        notifies removed crew + replacement crew
  │
  ▼
END
```

**Conditional edges:**
- After react_agent: if tool calls remain → tools node, else → ranker
- After ranker: if no legal candidates found → advisor (explain why, suggest options)
- After advisor: if disruption is routine (sick call, simple swap) → roster_updater → notifier → END
- After advisor: if mid-journey crew swap required → **interrupt_before(swap_approver)** → wait for controller → roster_updater → notifier → END

---

## Step 6 — Multi-Leg Journeys & Augmented Crew Handling

Long-haul and multi-stop routes require special handling that a simple crew-to-flight assignment model cannot support. Two distinct strategies exist and the platform must handle both.

---

### Method 1 — In-Flight Relief (Augmented Crew)

Used for ultra-long non-stop flights (e.g., Delhi → London, ~9–10 hrs). The aircraft carries extra crew who rotate in shifts while others rest in onboard bunks.

**How it works:**
- Instead of 2 pilots, the flight carries 3 or 4 (e.g., 2 Captains + 2 First Officers)
- While 2 pilots fly, the other 2 rest in certified crew rest bunks above the cabin
- Cabin crew rotate similarly — some work the service, others rest in designated crew seats
- Regulatory rule: extended FDP is only permitted if the aircraft has certified, isolated rest facilities onboard

**What the platform must track for augmented crew:**

| Field | Added To | Purpose |
|-------|----------|---------|
| augmented_crew | Flight model | list of crew_ids in relief rotation (beyond minimum required) |
| has_crew_rest_facility | Flight / Aircraft model | bool — extended FDP only legal if true |
| rest_facility_type | Aircraft model | BUNK / SEAT / NONE — determines FDP extension allowed |
| active_operating_crew | Flight model | which crew_ids are currently at controls vs resting |
| relief_rotation_minutes | Flight model | how long each crew pair operates before switching |

**FDP extension rules for augmented crew (DGCA/EASA):**

| Rest Facility | Crew Configuration | Max FDP Extension |
|--------------|-------------------|------------------|
| Bunk (isolated, lie-flat) | 3 pilots | +3.0 hrs beyond normal FDP |
| Bunk (isolated, lie-flat) | 4 pilots | +4.0 hrs beyond normal FDP |
| Seat (curtained, reclinable) | 3 pilots | +1.5 hrs beyond normal FDP |
| No facility | Any | No extension permitted |

**FTL tracking for augmented crew:**
- Each crew member's `flight_time_current_duty` only accumulates during their active operating window, not during rest rotation
- `sectors_current_duty` increments for all augmented crew on landing (they are all on duty for the full FDP even if resting)
- `max_fdp_allowed` is recalculated at report-in using the augmented FDP extension rules above

---

### Method 2 — Mid-Journey Crew Swap (Hub / Intermediate Stop)

**This is a last-resort, human-in-the-loop action only.** The AI never auto-executes a crew swap. It detects the need, prepares the full swap plan, and surfaces it to the controller for approval. A mid-journey swap involves hotel bookings, deadhead positioning, fresh crew coordination, and significant cost — a controller must own that decision.

**When the AI triggers this (emergency / urgency conditions only):**
- Current crew will breach FDP before reaching the final destination and no augmented crew option is available
- A crew member becomes incapacitated or sick mid-journey at an intermediate stop
- Aircraft swap at hub requires a different type-rated crew for the onward leg
- Commander's discretion has already been used and no further extension is legal

**What the AI does when it detects a swap is needed:**
1. Identifies the hub airport where the swap must happen
2. Finds available Crew B at that hub (or deadheading from nearest base) who are fully legal for the onward leg
3. Calculates full cost: deadhead ticket + hotel for Crew A + delay impact if Crew B needs positioning time
4. Checks Crew B legality against the onward leg FDP from their fresh report time
5. Prepares the complete swap plan with all details
6. **Pauses and presents to controller** — does not execute

**What the controller sees:**
```
⚠ CREW SWAP REQUIRED — Controller Action Needed

Flight AI-101 DEL→LHR (9.5 hrs)
Current crew (Crew A) will breach FDP at DEL. Cannot operate onward leg.

Proposed swap at DEL:
  Release: Captain Mehta + FO Sharma + 4 cabin → layover hotel DEL
  Board:   Captain Singh (DEL base, legal ✔, fatigue 28%) + FO Priya + 6 cabin

Cost: ₹42,000 (hotel x6 crew) + 0 deadhead (Crew B already at DEL)
Delay impact: 45 min for Crew B boarding + briefing

[APPROVE SWAP]  [MODIFY]  [ESCALATE TO SENIOR CONTROLLER]
```

**Only on controller approval:**
- Leg 1 (PNQ→DEL) closed for Crew A, rest clock started, hotel notification sent
- Leg 2 (DEL→LHR) assigned to Crew B, their FTL state updated, report time set
- Roster change logged with reason + controller ID + timestamp
- Both crews notified

**Why this is human-in-the-loop and not auto-executed:**
- Cost and operational impact are too high for autonomous action
- Controller may know context the system doesn’t (Crew B has a personal conflict, alternate aircraft available, flight can be cancelled)
- Regulatory accountability — a roster change of this magnitude requires a named human decision-maker in the audit trail

**What the platform must track for crew swaps:**

| Field | Added To | Purpose |
|-------|----------|---------|
| legs | Flight model | list of Leg objects — each leg is a separate crew assignment unit |
| leg_id | Leg model | unique identifier per sector (e.g., AI-101-PNQ-DEL, AI-101-DEL-LHR) |
| assigned_crew | Leg model | crew_ids operating this specific leg only |
| swap_airport | Leg model | ICAO code where crew change happens |
| deadhead_crew | Leg model | crew_ids travelling as passengers (positioning, not operating) |
| swap_approved_by | Leg model | controller_id who approved the swap |
| swap_approved_at | Leg model | timestamp of approval |
| swap_reason | Leg model | why the swap was triggered (FDP_BREACH / SICK / AIRCRAFT_SWAP) |

**The core rule — leg-based assignment:**
```
NEVER assign crew to a Route.
ALWAYS assign crew to a Leg (sector).

AI-101 PNQ→DEL→LHR is NOT one assignment.
It is two assignments:
  Leg 1: AI-101-PNQ-DEL → Crew A (Captain Mehta, FO Sharma, 4 cabin)
  Leg 2: AI-101-DEL-LHR → Crew B (Captain Singh, FO Priya, 6 cabin)

Leg 2 is only activated after controller approves the swap.
Until then, it exists as a PENDING_APPROVAL plan in the system.
```

---

### Deadhead (Positioning) Tracking

When Crew B needs to travel from Mumbai to Delhi just to operate the Delhi → London leg, they are deadheading — travelling as passengers to reach their work location.

**What the platform must track:**

| Field | Added To | Purpose |
|-------|----------|---------|
| deadhead_flight_id | CrewFTLState / assignment | which flight they are deadheading on |
| deadhead_status | POSITIONING / OPERATING | distinguishes working crew from positioning crew |
| deadhead_counts_as_duty | bool | true — deadhead time counts toward FDP even though not operating |
| positioning_start_time | datetime | when deadhead duty begins (adds to FDP clock) |

**Critical FTL rule for deadheading:**
- Deadhead time counts as duty time for FDP purposes
- A crew member deadheading 2 hrs from BOM to DEL before a 9hr DEL→LHR flight has an 11hr FDP, not 9hr
- The legality checker must add `deadhead_duration` to `projected_duty` when checking the operating leg

---

### Automatic Layover & Hotel Sync

When Crew A steps off at Delhi after the PNQ→DEL leg, the platform must immediately:

1. Set `rest_start_time` = actual landing time + taxi/debrief buffer (30 min)
2. Set `at_home_base` = false (Delhi is not their base — stricter rest applies)
3. Calculate `min_rest_required` = 10 hrs (away from base rule)
4. Calculate `earliest_available_at` = rest_start_time + 10 hrs
5. Trigger hotel booking notification (mock for hackathon: log to file)
6. Update `current_airport` = DEL
7. Set `status` = RESTING

**Notification sent to Crew A on release at hub:**
```
"Your duty on AI-101 PNQ→DEL is complete. Mandatory rest: 10 hrs.
 Hotel: [hotel near DEL airport]. Ground transport arranged.
 Earliest available for next duty: [earliest_available_at].
 Your next assignment: deadhead AI-105 DEL→BOM at [time]."
```

---

### How the Legality Checker Handles Multi-Leg

```
check_legality_for_leg(crew_id, leg) → (is_legal, reasons[], warnings[]):

  ftl = crew_ftl_state[crew_id]

  # For deadheading crew: add positioning time to projected duty
  if leg.deadhead_crew contains crew_id:
    positioning_hours = (leg.departure - ftl.duty_start_time).hours
    projected_duty = positioning_hours + leg.duration_hours
  else:
    projected_duty = (now - ftl.duty_start_time).hours + leg.duration_hours

  # For augmented crew: check rest facility before allowing extended FDP
  if leg.augmented_crew contains crew_id:
    if not leg.aircraft.has_crew_rest_facility:
      FAIL: "Extended FDP requires certified rest facility — aircraft {leg.aircraft_type} has none"
    max_fdp = ftl.max_fdp_allowed + get_augmented_extension(leg.aircraft.rest_facility_type, augmented_count)
  else:
    max_fdp = ftl.max_fdp_allowed

  if projected_duty > max_fdp:
    FAIL: "FDP breach — {projected_duty:.1f}h > {max_fdp:.1f}h (including deadhead/augmented rules)"
```

---

### Updated Folder Structure for Multi-Leg Support

```
models/
  leg.py           Leg — leg_id, flight_id, origin, dest, departure, duration,
                         assigned_crew[], deadhead_crew[], swap_airport, augmented_crew[]
  aircraft.py      Aircraft — type, has_crew_rest_facility, rest_facility_type, cockpit_min, cabin_min
```

---

## Step 7 — Roster Service

The roster is the master schedule. `RosterService` handles:

- `get_crew_roster(crew_id)` — all upcoming assignments for a crew member
- `get_flight_crew(flight_id)` — who is currently assigned to a flight
- `assign_crew(flight_id, crew_id, reason)` — add crew to flight, log change
- `remove_crew(flight_id, crew_id, reason)` — remove crew, log change
- `get_change_log(flight_id)` — full audit trail of all roster changes
- `get_upcoming_conflicts()` — proactive: crew about to breach duty limits

Every change is stored as a `RosterChange` with: flight_id, crew_id, action (ASSIGNED/REMOVED), reason (e.g. "Sick call replacement for Captain Rahul"), changed_at, changed_by ("AI_SYSTEM").

**Roster update on every disruption:**
- Old crew removed with reason ("Sick call — replaced by AI system")
- New crew added with reason ("Sick call coverage for Captain Mehta")
- Timestamp + changed_by logged
- Crew notified immediately with updated schedule

**Proactive roster scanning** (runs every 15 min):
- Scans all crew on tomorrow's roster for upcoming legality violations
- Flags any crew within 2 hours of duty limit breach
- Flags any expired licenses or medicals in next 7 days
- Flags flights with no backup crew identified

**Why this impresses judges:**
The AI doesn't just recommend — it closes the loop. Roster is updated, crew is notified, audit trail exists. This is what "operational superintelligence" means — the system acts, not just advises.

---

## Step 8 — Notifications

Crew must be informed as early as possible — legal + operational requirement.

`CrewNotifier` sends 3 message types:

- **Removal notice** — "Your assignment on AI-202 DEL→BOM at 09:00 has been reassigned due to sick call coverage. Your updated roster is attached."
- **Assignment notice** — "You have been assigned to AI-202 DEL→BOM. Report time: 08:15. Please confirm receipt."
- **Proactive alert** — "Heads up: You will reach your 14hr duty limit by 18:30 on current assignment AI-305."

For hackathon: mock with print + log to file. Structure supports real SMS/email swap later.

---

## Step 9 — API Endpoints

```
POST /v1/disruptions/analyze        main endpoint — controller inputs disruption
GET  /v1/roster/{flight_id}         current crew assigned to a flight
GET  /v1/crew/{crew_id}/schedule    crew member's upcoming assignments
GET  /v1/alerts/proactive           upcoming legality violations before they happen
```

Response from `/v1/disruptions/analyze`:
```json
{
  "disruption_type": "SICK_CALL",
  "affected_flight": "AI-202",
  "recommendation": {
    "primary": {
      "crew_id": "C-007",
      "name": "Captain Priya Sharma",
      "reasons": ["Legal ✓", "Delhi base ✓", "Fatigue 32% ✓", "No deadhead ✓"]
    },
    "alternatives": []
  },
  "cascade_warnings": ["AI-305 now needs pilot — Captain Mehta available"],
  "roster_updated": true,
  "notifications_sent": ["C-007", "C-001"]
}
```

---

## Step 10 — Streamlit UI

3 panels:
- Left: chat input — controller types disruption in plain English
- Middle: recommendation card — primary pick + 2 alternatives, each with ✓/✗ per rule
- Right: live crew table — status, duty hours today, fatigue %, current airport

Roster change log at bottom — all changes made today with reasons and timestamps.

---

## Step 11 — Seed Data

25 crew members across DEL/BOM/BLR with varying:
- duty states (some on duty, some available, some off-duty)
- fatigue scores (20–85%)
- license types (A320, B737, mixed)
- monthly hours (some near the 100hr cap)

15 flights with 2–3 pre-seeded disruptions ready for demo.

---

## Step 12 — Flight Data Fetching Strategy

### The Core Answer: Leg-Based, Not Route-Based

Track each leg independently. Never track a route end-to-end as one unit.

```
DO NOT track:  PNQ → DEL → LHR as one journey
DO track:      AI854 PNQ→DEL  (leg 1) — independently
               AI111 DEL→LHR  (leg 2) — independently
```

Each leg has its own flight number, its own status, its own crew assignment, and its own delay counter. Your FTL calculations run per leg, not per route.

---

### List or Individual? — Use List Fetch, Then Filter

**On startup — fetch all flights for your airline at once:**
```
GET /flights?airline_iata=AI
→ returns all active Air India legs right now
→ store all of them in memory
→ takes 1 API call
```

**Every 60 seconds — only poll legs that have crew assigned:**
```
active_legs = [leg for leg in all_legs if leg.assigned_crew is not empty]
for leg in active_legs:
    GET /flights?flight_iata={leg.flight_number}
    update leg.estimated_arrival, leg.delay_minutes, leg.status
```

**Why not poll everything every 60 seconds:**
- An airline has 200–500 active legs at any time
- You only care about legs your crew is on
- Polling all 500 every 60 seconds wastes API quota and adds no value

---

### What to Track Per Leg and When

```
Leg status: scheduled
  → poll every 15 min (nothing is happening yet)

Leg status: boarding / delayed at gate
  → poll every 5 min (departure imminent, delays matter now)

Leg status: active (airborne)
  → poll every 60 sec (estimated_arrival updating continuously)
  → on every update: recalculate projected_fdp_end for all crew on this leg

Leg status: landed
  → write actual_arrival, stop polling this leg
  → trigger: rest_start_time for crew, at_home_base check, hotel notification if away
  → start polling next leg for same crew (if connecting)

Leg status: cancelled / diverted
  → stop polling
  → trigger disruption event → pipeline runs to find replacement plan
```

---

### The 4 Timestamps That Drive Everything

For crew FTL, only these 4 fields matter per leg. Everything else is display data.

| Field | When it’s set | What your platform does with it |
|-------|-------------|--------------------------------|
| scheduled_departure | fixed at schedule creation | baseline, never changes |
| actual_departure | set once when aircraft pushes back | start FDP clock for crew |
| estimated_arrival | updates continuously while airborne | recalculate projected_fdp_end on every change |
| actual_arrival | set once when aircraft lands | close duty window, start rest clock |

**The one field that drives FTL recalculation is `estimated_arrival`.**
Every time it changes → `delay_minutes` = estimated_arrival − scheduled_arrival → `projected_fdp_end` += delay → re-run legality check → fire alerts if needed.

---

### Crew Location Update on Every Landing

When `actual_arrival` is set for a leg:

```
for crew_id in leg.assigned_crew:
    ftl = crew_ftl_state[crew_id]

    # Update location
    crew.current_airport = leg.destination
    ftl.at_home_base     = (leg.destination == crew.home_base)

    # Update rest type and hotel
    if ftl.at_home_base:
        ftl.rest_type            = HOME_REST
        ftl.hotel_location       = null
        ftl.min_rest_required    = max(12, duty_hours_this_period)
    else:
        ftl.rest_type            = LAYOVER_REST
        ftl.hotel_location       = leg.destination
        ftl.hotel_checkin        = actual_arrival + 30min  # debrief buffer
        ftl.earliest_checkout    = ftl.hotel_checkin + 10hrs
        ftl.min_rest_required    = 10
        notify: hotel booking triggered

    # Check if crew needs positioning back to home base
    if not ftl.at_home_base:
        next_leg = roster.get_next_assignment(crew_id)
        if next_leg is None or next_leg.origin != leg.destination:
            ftl.next_positioning_flight = find_deadhead(leg.destination, crew.home_base)
            ftl.return_to_base_eta      = deadhead_flight.estimated_arrival
```

---

### Country-Level vs Global — What Scope to Use

| Scope | What you query | When to use |
|-------|---------------|-------------|
| Single airline | `airline_iata=AI` | Your platform — you only care about your airline's crew |
| Single airport | `dep_iata=DEL` | Useful for hub monitoring — all departures from Delhi |
| Single leg | `flight_iata=AI854` | When you need one specific leg's live status |
| Global | no filter | Never needed for crew handling |

For your platform: **filter by airline on startup, then filter by legs with crew assigned for ongoing polling.**

---

### For the Hackathon — Simulate This Without a Real API

```python
# background thread runs every 30 seconds
def simulate_flight_updates():
    for leg in active_legs:
        if leg.status == "active" and random.random() < 0.3:
            leg.delay_minutes += random.randint(5, 20)
            leg.estimated_arrival += timedelta(minutes=leg.delay_minutes)

            # cascade into FTL
            for crew_id in leg.assigned_crew:
                ftl_service.recalculate_projected_fdp(crew_id, leg.delay_minutes)
                alert_service.check_fdp_breach(crew_id)

        if leg.status == "active" and leg.estimated_arrival <= now:
            leg.status = "landed"
            leg.actual_arrival = now
            ftl_service.on_landing(leg)   # triggers rest clock + location update
```

This gives you live FTL recalculations, proactive alerts firing, and crew location updates during the demo — without needing a real API key.

---

## Step 13 — Roster Planning Layer

The roster is the planning layer — completely separate from the real-time disruption layer. It tells you what is planned. Real-time data stress-tests the plan continuously.

```
PLANNING LAYER (done in advance)
  Weekly roster / Monthly roster
  Created days/weeks before operations
  Assigns crew to legs in advance
  Stored in: crew_roster table
        │
        │ feeds into
        ▼
REAL-TIME LAYER (live operations)
  Flight status API polling
  FTL state recalculation
  Disruption handling
  Stored in: crew_ftl_state table
```

---

### The 3 Roster Types

**Monthly Roster** (published 3–4 weeks in advance)
- Full calendar month, all operating duties + known deadheads + training + leave
- Built by crew scheduling team or automated optimizer
- Crew have planned personal lives around it — low flexibility
- Validated against all FTL constraints before publishing

**Weekly Roster** (published 7 days in advance)
- Takes monthly roster as base, applies sick leave / training updates
- Confirms exact report times, triggers hotel bookings for layovers
- Re-validates FTL for the week before publishing

**Day-of Roster** (live, updated continuously by your platform)
- Takes weekly roster as base
- Applies real-time flight status updates
- Recalculates all FTL states as delays come in
- Triggers disruption pipeline when violations are detected

---

### Inputs the Roster Needs

```
1. Flight schedule     → which legs exist, when, what aircraft
2. Crew availability   → who is not on leave, training, sick
3. FTL constraints     → who has hours remaining this month
4. Crew preferences    → seniority-based bidding (senior crew pick first)
5. Base constraints    → crew must start and end at their home base
6. Rest requirements   → minimum rest between duties must be respected
7. Reserve schedule    → who is on standby and when
```

---

### What the Roster Assigns

Every assignment is leg-level, never route-level:

```
RosterEntry {
  roster_id
  crew_id
  leg_id                ← leg, not flight, not route
  duty_start_time       ← report time (1–2 hrs before departure)
  duty_end_time         ← estimated release after landing + debrief
  assignment_type       OPERATING / DEADHEAD / RESERVE / TRAINING
  status                PLANNED / CONFIRMED / MODIFIED / CANCELLED
  modified_reason
  modified_by           controller_id or AI_SYSTEM
  created_at
  modified_at
}
```

---

### Roster Validation Before Publishing

Before the roster goes live, run every crew member through the legality checker against their full planned week:

```
for each crew_member:
  simulate their entire week day by day:
    does any duty exceed max FDP?              → flag
    is rest between duties sufficient?         → flag
    does 7-day duty total exceed 60 hrs?       → flag
    does 28-day block hours exceed 100?        → flag
    do they get their weekly 36hr rest block?  → flag
    are they back at home base at week end?    → flag

  if any violation found:
    flag before publishing
    suggest swap or adjustment
```

This is the same legality checker used in real-time — run against future planned duties instead of current live state.

---

### How Real-Time Data Connects to the Roster

```
Roster says:    Captain Mehta on AI854 PNQ→DEL, departs 06:00
Reality:        AI854 delayed, now departing 08:30

Impact:
  duty_start_time unchanged (Mehta already reported at 04:30)
  duty_end_time shifts by +2.5 hrs
  projected_fdp_end recalculated
  next duty (AI111 DEL→LHR at 11:00) — is there still enough rest?
  if not → proactive alert → controller decides
```

---

### Data Flow End to End

```
Month −4 weeks:
  Flight schedule published
        │
        ▼
Month −3 weeks:
  Monthly roster built + validated
  crew_roster table populated with PLANNED entries
        │
        ▼
Week −7 days:
  Weekly roster confirmed
  Hotel bookings triggered for layovers
  crew_roster entries updated to CONFIRMED
        │
        ▼
Day of operations:
  Real-time API polling starts for today's legs
  crew_ftl_state populated from confirmed roster
        │
        ▼ (every 60 seconds)
  Flight status updates come in
  estimated_arrival changes
  crew_ftl_state.projected_fdp_end recalculated
  Proactive alerts fire if needed
        │
        ▼ (disruption happens)
  Sick call / delay / cancellation
  Disruption pipeline runs
  Replacement found, roster updated
  crew_roster entry modified with reason
  crew_ftl_state updated for affected crew
```

---

### New Tables for Roster

**crew_roster** — one row per crew-leg assignment

| Field | Type | Purpose |
|-------|------|---------|
| roster_id | string | unique identifier |
| crew_id | string | FK to crew profile |
| leg_id | string | FK to leg (sector) |
| duty_start_time | datetime | report time (1–2 hrs before departure) |
| duty_end_time | datetime | estimated release after landing + debrief |
| assignment_type | OPERATING/DEADHEAD/RESERVE/TRAINING/LEAVE | what crew is doing |
| status | PLANNED/CONFIRMED/MODIFIED/CANCELLED | current state |
| modified_reason | string | why it changed |
| modified_by | string | controller_id or AI_SYSTEM |
| created_at | datetime | when entry was created |
| modified_at | datetime | last change timestamp |

**crew_leave** — approved leave periods

| Field | Type | Purpose |
|-------|------|---------|
| leave_id | string | unique identifier |
| crew_id | string | FK to crew profile |
| start_date | date | leave start |
| end_date | date | leave end |
| leave_type | ANNUAL/SICK/TRAINING/MEDICAL | type of leave |
| status | APPROVED/PENDING | approval state |

**crew_reserve_schedule** — standby assignments

| Field | Type | Purpose |
|-------|------|---------|
| reserve_id | string | unique identifier |
| crew_id | string | FK to crew profile |
| date | date | standby date |
| standby_start | datetime | when they must be reachable |
| standby_end | datetime | end of standby window |
| base_airport | ICAO | where they are on standby |
| callable_within | int (minutes) | how fast they must report (e.g., 120 min) |

---

### How the Platform Uses All Three Tables Together

When a disruption comes in:

```
Disruption: "Captain Mehta sick, AI854 departing 09:00"

1. Check crew_roster       → who else is on AI854?
2. Check crew_reserve_schedule → who is on standby at PNQ right now?
3. Check crew_ftl_state    → of those on standby, who is legal?
4. Check crew_leave        → confirm none are on approved leave
5. Rank survivors          → recommend Captain Priya (standby, legal, fatigue 28%)
6. On approval             → update crew_roster (Mehta CANCELLED, Priya MODIFIED)
7. Update crew_ftl_state   → for both Mehta and Priya
8. Notify both crew
```

---

### Updated Folder Structure for Roster

```
models/
  roster_entry.py        RosterEntry — crew-leg assignment with status + audit
  crew_leave.py          CrewLeave — approved leave periods
  crew_reserve.py        CrewReserveSchedule — standby assignments
roster/
  roster_service.py      read/write roster, change log, conflict detection
  roster_validator.py    pre-publish FTL validation across full week/month
  roster_builder.py      builds weekly/monthly roster from flight schedule + constraints
```

---

## Step 14 — Flight Schedule Source & Delay Propagation

### How Flight Schedules Are Created

Airlines publish schedules in two layers:

```
Layer 1 — Season Schedule (published 6 months in advance)
  IATA publishes two seasons per year:
    Summer: last Sunday of March → last Saturday of October
    Winter: last Sunday of October → last Saturday of March

  Airlines submit slot requests to IATA
  Each slot = permission to use a specific runway at a specific time
  Once approved → fixed for the entire season

  What you get: every flight number, route, departure time, aircraft type
  for the entire 6-month season — all at once

Layer 2 — Operational Schedule (updated weekly/daily)
  Takes season schedule as base
  Applies real-world changes: aircraft swaps, route suspensions,
  frequency changes, charter additions
  Published weekly by airline's network planning team
```

**Yes — you can get 1 month of scheduled flight data right now:**

```
Aviationstack:
  GET /flights?airline_iata=AI&flight_status=scheduled
  → all scheduled Air India flights including weeks in advance

OAG / Cirium (production-grade):
  GET /schedules?airline=AI&from=2024-02-01&to=2024-02-29
  → full month schedule in one call
  → most accurate — this is what airlines use for crew rostering
```

**For your platform:** pull the full month schedule once on startup, store it as your leg table, then poll only active legs for real-time status.

---

### How a Single Delay Affects the Week

Two completely separate things behave differently:

```
Aircraft rotation  → does the delay carry forward to next leg?
Crew rotation      → does the delay affect the crew's next duty?
```

---

### Aircraft Rotation — Delay Carries Forward Same Day, Recovers Overnight

An aircraft flies multiple legs per day. If Leg 1 is delayed, Leg 2 on the same aircraft is automatically delayed because the aircraft isn't there yet.

```
Same aircraft VT-ABC:

  Leg 1: AI854  PNQ→DEL  scheduled 06:00, delayed → departs 08:30
                          arrives DEL 10:45 instead of 08:15
         ↓
  Leg 2: AI202  DEL→BOM  scheduled 09:30 (same aircraft)
                          cannot depart — aircraft not there
                          automatically delayed → departs ~11:30
         ↓
  Leg 3: AI305  BOM→CCU  scheduled 13:00 (same aircraft)
                          may or may not be affected depending on
                          buffer built into the schedule
```

Airlines build turnaround buffer between legs for exactly this reason. A 45-minute delay on Leg 1 may not affect Leg 3 if there was 2 hours of buffer at DEL.

**Does it carry to next day?**
```
Usually NO for aircraft.
Airlines have maintenance slots and overnight parking plans.
If significantly delayed, operations will:
  - swap to a different aircraft
  - cancel the last leg of the day
  - absorb the delay at the overnight station
Next morning: aircraft starts fresh from its overnight base
```

---

### Crew Rotation — More Complex, Affects Multiple Days

Crew delays are more persistent than aircraft delays because of FTL rules.

**Example: Captain Mehta's week**

```
Monday planned:
  AI854 PNQ→DEL departs 06:00, lands 08:15
  Report: 04:30, release: ~09:00
  Rest: 09:30 → Tuesday report 06:00 = 20.5 hrs rest ✓

Monday reality (delay +2.5 hrs):
  Departs 08:30, lands 10:45, release: ~11:30
  Rest: 11:30 → Tuesday report 06:00 = 18.5 hrs ✓ still legal

Monday reality (extreme delay, released 20:00):
  Rest = 10 hrs only
  Min rest at home base = max(12, preceding duty hours)
  Preceding duty = 15.5 hrs → min rest required = 15.5 hrs
  Mehta CANNOT report Tuesday 06:00 → replacement needed
```

**Recovery pattern by delay severity:**

```
Small delay (< 2 hrs):
  Absorbed same day
  Rest still sufficient for next day
  No cascading effect

Medium delay (2–4 hrs):
  Proactive alert fires
  Controller pre-positions backup just in case
  Usually recovers by Day 2

Large delay (4+ hrs) or FDP breach:
  Crew cannot legally operate next planned duty
  Roster modified — replacement assigned for next day
  Crew on extended rest → available again Day 3 or Day 4
  7-day duty counter elevated for rest of week

FDP breach mid-flight (worst case):
  Commander's discretion invoked (+2 hrs max)
  Mandatory safety report filed
  Compensatory rest required
  Crew out 2+ days before legally available again
```

**The 7-day rolling counter effect:**

```
Day 1 (Monday):   Large delay → crew released late, high duty hours logged
Day 2 (Tuesday):  Crew on extended rest, replacement operates flights
                  duty_hours_7_day counter now elevated
Day 3 (Wednesday): Crew available again but fewer hours left this week
                   Scheduler reduces Wednesday/Thursday duties
Day 4–5:          Back to normal rotation
Day 8 (next Mon): Monday's hours roll off the 7-day window
                  Full availability restored
```

---

### What Your Platform Does With This

**On every flight delay update:**

```
delay comes in: AI854 now +3 hrs

for each crew_id on AI854:
  recalculate duty_end_time += 3 hrs
  recalculate projected_fdp_end

  check FDP breach:
    if projected_fdp_end > duty_start + max_fdp_allowed:
      ALERT: FDP breach — invoke commander's discretion or find replacement

  check next duty rest:
    next_duty = crew_roster.get_next(crew_id, after=new_duty_end)
    rest_available = next_duty.duty_start - new_duty_end
    min_rest = max(12, new_duty_hours) if at_home_base else 10
    if rest_available < min_rest:
      ALERT: "Mehta cannot legally report for AI202 Tuesday 06:00"
      Option A: push report time if flight can absorb it
      Option B: find replacement from reserve_schedule
```

**On rest violation detected — two options:**

```
Option A — Push the report time (flight can wait):
  new_report_time = new_duty_end + min_rest
  if new_report_time < flight.scheduled_departure - 30min:
    update roster entry, notify crew of new report time
    no replacement needed

Option B — Find replacement (flight cannot wait):
  run disruption pipeline
  find available crew from reserve_schedule at that airport
  update roster: original crew MODIFIED (rest extension)
                 replacement crew ASSIGNED
  notify both
```

**Rolling counter recalculation (runs every midnight):**

```
for each crew_member:
  duty_hours_7_day    = sum of duty hours in last 7 rolling days
  flight_hours_28_day = sum of block hours in last 28 rolling days

  if duty_hours_7_day > 55:    WARN: approaching 60hr weekly cap
  if flight_hours_28_day > 90: WARN: approaching 100hr monthly cap
  update crew_ftl_state
```

---

### Direct Answers

| Question | Answer |
|----------|--------|
| Can you get 1 month of scheduled data in advance? | Yes — OAG/Cirium gives full season, Aviationstack gives weeks ahead |
| Does a mid-week delay affect the whole week? | For aircraft: usually no, recovers overnight. For crew: depends on severity |
| Does it recover next day? | Small delays: yes. Large delays / FDP breach: 2–4 days to fully recover |
| Why does it take 2–4 days? | 7-day rolling duty counter stays elevated until those hours roll off |
| What does your platform do? | Recalculate FTL on every delay, alert proactively, offer push-report-time or replacement |

---

## Step 15 — Crew Data Sources & Disruption Detection

Crew data does not come from a flight API. It comes from internal airline systems only.

```
Flight data  → external API (Aviationstack, OAG)
Crew data    → internal airline systems only (private HR + operational data)
```

### 3 Source Systems

**HRMS** (SAP HR / Oracle HCM / Workday) — static profile
- Who they are: employee_id, name, designation, home_base, date_of_joining, seniority
- Updates rarely — on join, promotion, base transfer, resignation
- Sync: nightly batch into crew profile table

**AIMS** (Jeppesen Crew / IBS CrewStar / NetLine) — operational brain
- What they can do: licenses, type ratings, license expiry, medical expiry, simulator check due
- What they have done: full duty history, every flight operated, every duty period
- Current state: roster assignments, leave records, reserve schedule
- Updates continuously — every duty event, every training completion
- Sync: webhook on every event → crew_ftl_state updated immediately

**Crew Mobile App** (Jeppesen CrewConnect / IBS iCrew) — self-service
- Sick call notifications, leave requests, roster acknowledgements
- Sync: webhook immediately on submission → triggers disruption pipeline

### New Fields Added to Crew Profile

| Field | Source | Purpose |
|-------|--------|---------|
| employee_id | HRMS | official HR ID |
| designation | HRMS | Captain/FO/Senior Purser/Cabin Crew |
| date_of_joining | HRMS | seniority calculation |
| seniority_number | HRMS | reserve bidding (lower = more senior) |
| employment_status | HRMS | ACTIVE/ON_LEAVE/SUSPENDED/RESIGNED |
| medical_expiry | AIMS | proactive alert when expiring |
| license_expiry | AIMS | per-license expiry dict {type: date} |
| simulator_check_due | AIMS | recurrent training tracking |

### Production Data Flow

```
HRMS → nightly sync → crew profile table (static)
AIMS → webhook on duty event → crew_ftl_state (live)
Crew app → webhook on sick call → disruption pipeline (immediate)
```

### How Disruptions Enter the Pipeline

DisruptionEvent types: SICK_CALL / DELAY / CANCELLATION / AIRCRAFT_SWAP / NO_SHOW

```
Path A — Crew mobile app (production):
  Mehta taps "Report Sick" → POST /events/sick-call
  crew_ftl_state[Mehta].status = SICK immediately
  crew_roster[Mehta][today].status = CANCELLED
  disruption_pipeline.run(SICK_CALL, crew=Mehta, flight=AI854)

Path B — Controller free text (primary demo path):
  Controller types: "Captain Mehta sick, AI854 departing Delhi 08:00"
  LLM analyzer parses → DisruptionEvent {
    type: SICK_CALL,
    affected_flight_id: AI854,
    affected_crew_id: C-001
  }
  Same pipeline runs

Path C — Proactive alert escalation (system-generated):
  Alert scanner detects FDP breach risk or rest violation
  Automatically creates DisruptionEvent
  Pipeline runs without controller input

Path D — Hackathon demo:
  Seed one crew member with status=SICK
  Or Streamlit button: "Simulate Sick Call"
```

---

## Step 16 — Candidate Finding & Deterministic Legality Check

### Candidate Pre-filtering (pure Python, no LLM)

```
1. Check crew_reserve_schedule:
   who is on standby at the affected airport right now?
   callable_at <= flight.departure - callable_within_minutes

2. Check crew_roster:
   who is AVAILABLE and not already assigned to another leg?

3. Merge both lists, deduplicate by crew_id

4. Filter by:
   role match (PILOT / CABIN)
   employment_status == ACTIVE
   not in crew_leave (no approved leave today)

5. Pass filtered candidate list to legality checker
```

### Legality Check — Hard Gates & Soft Warnings

Runs `CrewLegalityChecker.check(crew_id, flight)` against `crew_ftl_state` for every candidate. Any hard gate failure = excluded entirely. LLM never touches this logic.

```
Hard gates (FAIL = excluded):
  Rule 1: projected_duty <= max_fdp_allowed
  Rule 2: rest_hours_available >= min_rest_required
  Rule 3: flight.aircraft_type in crew.licenses
  Rule 4: flight_hours_28_day + duration <= 100
  Rule 5: duty_hours_7_day + projected_duty <= 60
  Rule 6: status == AVAILABLE
  Rule 7: deadhead_duration + leg_duration <= max_fdp (multi-leg)
  Rule 8: has_crew_rest_facility if augmented FDP extension needed

Soft warnings (legal but flagged in recommendation):
  Within 1hr of FDP limit
  WOCL encroachment
  Day 4+ consecutive duty
  Approaching 28-day block hour cap

Commander's discretion path:
  All hard gates pass but projected_duty slightly over max_fdp
  fdp_extension_used == false and overage <= 2.0 hrs
  → LEGAL_WITH_DISCRETION: safety report required

Output per candidate: (is_legal, reasons[], warnings[], discretion_available)
```

---

## Step 17 — Cost Scoring

For every candidate that passes the legality gate:

```
C_total = w1 × deadhead_cost
        + w2 × delay_cost
        + w3 × passenger_impact
        - w4 × crew_preference

where:
  deadhead_cost      = $220 if current_airport != flight.origin else 0
  delay_cost         = $45/min × delay_minutes caused by this assignment
  passenger_impact   = $12/pax/hr × passengers × delay_hours
  crew_preference    = preference_score (0–1, higher = preferred)

Always append as final option:
  "Delay the flight" → cost = $45/min × estimated_delay, 0 crew changes
  This is the guaranteed fallback — never return empty options
```

---

## Step 18 — Cascade Check

```
For the crew member being removed:
  get_cascade_impact(crew_id)
  → returns all other legs this crew is assigned to today/tomorrow

For each cascaded leg:
  flag: "Singh was also on AI-410 at 15:00 — now also needs coverage"
  run candidate finding + legality check for that leg too
  find replacement in the same pass

Output: cascade_warnings[] added to recommendation
Roster updated for all affected legs in one transaction
```

---

## Step 19 — Ranking + LLM Narration

```
Ranking (pure Python):
  legal(40pts) + same_airport(30pts) + low_fatigue(20pts) + low_cost(10pts)
  Sort by total score descending
  Return top 3 + delay fallback

LLM narration (after ranking is done):
  Takes structured facts dict — cannot change verdict or invent costs
  Writes per-rule ✓/✗ explanation for each candidate
  Writes cascade warnings in plain English
  Writes confidence score: "87% confident — 3 legal candidates, primary has lowest fatigue + no deadhead"
```

---

## Step 20 — Human Decision Point

```
Routine disruption (sick call, simple replacement):
  Present recommendation to controller
  One-click approve → pipeline continues to roster update

What-if copilot:
  Controller: "what if we delay AI-202 by 2 hours?"
  Parser: { action: extend_delay, flight_id: AI-202, additional_delay_minutes: 120 }
  Re-run Steps 18–21 with modified flight parameters
  Return new ranked options

Mid-journey crew swap (emergency only):
  graph.interrupt_before(swap_approver)
  Graph pauses — presents full swap plan with cost
  Controller: [APPROVE SWAP] / [MODIFY] / [ESCALATE]
  Only on approval: pipeline continues
```

---

## Step 21 — Roster Update + Closed Loop

```
On approval:
  crew_roster:
    removed crew → status = CANCELLED, modified_by, modified_reason, modified_at
    replacement  → status = MODIFIED, same audit fields

  crew_ftl_state:
    removed crew: status = SICK/OFF_DUTY, duty counters unchanged
    replacement:  duty_start_time set, projected_fdp_end calculated

  Notifications:
    removed crew  → "Your assignment on AI-854 has been reassigned"
    replacement   → "You have been assigned to AI-854. Report time: 06:30"
    cascade crew  → same for any cascaded leg changes

  If mid-journey swap:
    Crew A: rest_start_time set, hotel_location set, hotel notification sent
    Crew B: report_time set, leg activated from PENDING_APPROVAL
```

---

## Step 22 — Proactive Alert Scanner (Every 15 Min)

```
Alert 1: FDP approaching
  status == ON_DUTY and (projected_fdp_end - now) < 2 hrs

Alert 2: Rest violation risk
  next_scheduled_duty.start - current_duty_end < min_rest_required

Alert 3: Weekly rest overdue
  (now - last_weekly_rest_end) > 6 days

Alert 4: Cumulative cap approaching
  flight_hours_28_day > 90

Alert 5: WOCL duty tomorrow
  tomorrow's duty_start between 0000–0600

Alert 6: Medical expiring
  medical_expiry within 30 days

Alert 7: License expiring
  any license_expiry within 30 days

Alert 8: Simulator check due
  simulator_check_due within 14 days
```

---

## Step 23 — Rolling Counter Recalculation (Every Midnight)

```
for each crew_member:
  duty_hours_7_day     = sum of duty hours in last 7 rolling days (drop oldest)
  flight_hours_28_day  = sum of block hours in last 28 rolling days
  flight_hours_calendar_year = sum of block hours since Jan 1
  consecutive_duty_days = count of consecutive days with a duty period

  if duty_hours_7_day > 55:     WARN: approaching 60hr weekly cap
  if flight_hours_28_day > 90:  WARN: approaching 100hr monthly cap

  update crew_ftl_state
  re-run proactive alert scanner after update
```

---

## Build Order

| Day | Time | Task |
|-----|------|------|
| Day 1 | Morning | Models (CrewMember + CrewFTLState + RosterEntry + CrewLeave + CrewReserve + Leg + Aircraft) + FDP bracket table + seed data (25 crew, 15 legs, ftl_states, roster entries, reserve schedule) |
| Day 1 | Afternoon | Rules engine (Step 3) + Candidate finding + Legality check (Step 16) + Cost scoring (Step 17) + Cascade check (Step 18) + 4 LangGraph tools + ReAct agent wired end-to-end |
| Day 1 | Evening | FastAPI endpoints working, test all disruption types with curl |
| Day 2 | Morning | FTL service (duty events → ftl_state updates) + Roster service + Crew data sources + Disruption detection (Step 15) + Notifications (Step 21) |
| Day 2 | Afternoon | Proactive alert scanner (Step 22) + Rolling counter midnight job (Step 23) + Flight simulation thread (Step 12) + Streamlit UI |
| Day 2 | Buffer | What-if copilot (Step 20) + Commander's discretion path + Augmented crew FDP extension |

---

## 4 Demo Scenarios

---

### Scenario 1 — Simple Sick Call

**Input:** "Captain Mehta called sick for AI-101 departing Delhi 8AM"

**What the AI does:**
1. Analyzer identifies: SICK_CALL, flight AI-101, crew Captain Mehta
2. find_available_crew → 6 pilots at Delhi base
3. check_legality on each → 4 pass, 2 fail (one over duty hours, one license mismatch)
4. calculate_cost → 1 needs deadhead (deprioritized), 3 are local
5. Ranker scores remaining 3 → Captain Priya tops (lowest fatigue 32%, fully legal)
6. Roster updated: Mehta removed, Priya assigned
7. Notifications sent to both

**AI Output:**
```
Recommended: Captain Priya Sharma
✓ Legal — 6.5 hrs duty today, well within 14hr limit
✓ Delhi base — no deadhead needed
✓ A320 type-rated
✓ Fatigue score: 32% (lowest among candidates)

2 alternatives available if she declines.
Roster updated. Notifications sent to Mehta and Priya.
```

---

### Scenario 2 — Delay Causes Legality Breach

**Input:** "AI-202 delayed by 4 hours, new departure 13:00"

**What the AI does:**
1. Analyzer identifies: DELAY, flight AI-202, no specific crew mentioned
2. get_flight_crew → fetches currently assigned crew (Captain Singh + 4 cabin)
3. check_legality with new departure time → Captain Singh started duty at 05:00, 4hr delay pushes landing to 16:30 = 11.5hr duty. Legal. But Cabin crew Anita started at 04:30 → landing at 16:30 = 12hr duty. Legal but tight.
4. Proactive flag: "If further delay of 1.5hrs occurs, Anita breaches 14hr limit"
5. Finds standby cabin crew at Delhi as pre-identified backup

**AI Output:**
```
Current crew remains legal for 4hr delay.
⚠ Warning: Cabin crew Anita Rao will breach duty limit if further delay > 90 min.
Pre-identified backup: Cabin crew Sunita Kapoor (available, Delhi, fatigue 28%)
No roster change made yet. Recommend pre-positioning Sunita at gate.
```

---

### Scenario 3 — Cascade Disruption

**Input:** "Captain Singh sick, AI-305 departing Mumbai 10AM"

**What the AI does:**
1. Analyzer: SICK_CALL, AI-305, Captain Singh
2. get_cascade_impact(Singh) → Singh is also assigned to AI-410 Mumbai→Delhi at 3PM
3. find_available_crew for AI-305 → Captain Arjun available in Mumbai
4. check_legality(Arjun, AI-305) → legal ✓
5. But Arjun was backup for AI-410 → now AI-410 also needs a new backup
6. find_available_crew for AI-410 → Captain Nair available, legal ✓
7. Two roster changes made, three notifications sent

**AI Output:**
```
Primary fix: Captain Arjun → AI-305 (Mumbai, legal ✓, fatigue 41%)

⚠ Cascade detected: Singh was also assigned to AI-410 at 15:00.
   Arjun (now on AI-305) cannot cover AI-410.
   Secondary fix: Captain Ravi Nair → AI-410 (Mumbai, legal ✓, fatigue 55%)

Roster updated for both flights.
Notifications sent to: Singh, Arjun, Ravi.
```

---

### Scenario 4 — Proactive Alert (No Disruption Yet)

**Triggered automatically by:** `GET /v1/alerts/proactive` polled every 15 min

**What the AI detects:**
Captain Mehta started duty at 06:00, currently on AI-303 landing at 17:45 = 11.75hr duty. Assigned next to AI-450 departing 19:30 — that would be 13.5hr duty. Legal but only 30min buffer. If AI-450 departs even 31 minutes late, Mehta breaches 14hr limit mid-flight.

**AI Output (pushed to dashboard):**
```
⚠ Proactive Alert — Captain Mehta
   Current duty: 11.75 hrs (started 06:00)
   Assigned: AI-450 DEL→BOM at 19:30 (2hr flight = 13.5hr total duty)
   Risk: Any delay > 30 min causes duty breach mid-flight.

   Recommended action: Pre-identify replacement now.
   Standby available: Captain Priya Sharma (Delhi, 6hr duty, fatigue 29%)
   No roster change made. Controller decision required.
```

---

## Fatigue Score (0–100)

A number representing how tired a crew member is right now, calculated from their recent work history.

```
0   = fully rested, just woke up from 2 days off
100 = dangerously exhausted, should not fly
```

### What goes into calculating it

| Factor | How it increases fatigue |
|--------|--------------------------|
| Duty hours today | More hours worked = higher score |
| Time since last rest | Shorter rest = higher score |
| Night shifts / early starts | 4AM report time hits harder than 10AM |
| Consecutive duty days | Day 4 of flying is more tiring than Day 1 |
| Monthly hours | Near the 100hr cap = accumulated fatigue |

### Example calculation

**Captain Priya (low fatigue):**
- Worked 6 hrs today → +30 pts
- Had 11 hrs rest last night → +5 pts
- Started duty at 9AM (normal) → +0 pts
- Day 2 of consecutive duty → +10 pts
- **Total: ~35 (low, safe to assign)**

**Captain Mehta (high fatigue):**
- Worked 11 hrs today → +55 pts
- Had only 10.5 hrs rest (barely legal) → +20 pts
- Started duty at 5AM (early) → +15 pts
- Day 4 of consecutive duty → +20 pts
- **Total: ~85 (high, avoid assigning)**

### How the AI uses it in ranking

```
Fatigue 0–30   → full 20 pts  (very fresh)
Fatigue 31–60  → 10 pts       (moderate)
Fatigue 61–80  → 5 pts        (tired)
Fatigue 81–100 → 0 pts        (exhausted, deprioritized)
```

### Why airlines care about this

There's a real concept called **FRMS (Fatigue Risk Management System)** — airlines are required by aviation regulators to track crew fatigue. A fatigued pilot is a safety risk even if technically within legal duty hour limits. The legal rules (14hr duty, 10hr rest) are the floor — fatigue score is the smarter layer on top.

For the hackathon: a simple weighted sum of the above factors normalized to 0–100 is enough. The key is explainability — the AI can say "fatigue score 72% because 4 consecutive duty days + early 5AM start" and judges understand exactly what it means.

---

## Approach Rating: 7.5 / 10

### What's strong

- **End-to-end loop** — most hackathon teams stop at "AI gives recommendation." Closing the loop with roster update + crew notification is the difference between a demo and a real product.
- **LangGraph ReAct pattern** — tool-calling agent that reasons step by step is the right architecture. Not a simple prompt → response.
- **Cascade detection** — Scenario 3 (one sick call triggers two reassignments) is genuinely hard and impressive. Most teams won't think of this.
- **Proactive alerts** — Scenario 4 elevates it from "reactive tool" to "superintelligence." That word is in the problem statement — you need to earn it.
- **Explainability** — every recommendation shows ✓/✗ per rule. Aviation is a safety domain. Black-box AI is useless here.

### What's weak

- **Mock data only** — no real airline data, no real SMS/email. The more realistic the seed data, the more believable the demo.
- **No learning / adaptation** — the system doesn't improve over time. A true superintelligence would learn patterns like "Captain Mehta always calls sick on Mondays."
- **Single disruption at a time** — real crew control handles 10–15 disruptions simultaneously.
- **No uncertainty handling** — what if the AI can't find any legal replacement? The failure path isn't defined.
- **Fatigue score is hand-crafted** — a real FRMS uses biomathematical models (SAFTE, FAID). A knowledgeable judge will ask about this.

### What would push it to 9.5/10

| Addition | Impact |
|----------|--------|
| Natural language daily risk briefing — "3 crew near duty limits, 1 license expiring today" | High — shows superintelligence |
| Handle "no replacement found" gracefully — suggest delay, partial crew, escalate to human | High — shows robustness |
| Pattern detection — "This is the 3rd sick call from this crew member this month" | Medium — shows intelligence beyond rules |
| Confidence score on recommendation — "87% confident this is optimal" | Medium — shows AI maturity |
| Multi-disruption queue — resolve 3 disruptions in parallel | Medium — shows scale thinking |

### Bottom line

For a 2-day hackathon, 7.5 is very competitive. The architecture is sound, the scenarios are realistic, and the roster + notification loop sets you apart from teams that just build a chatbot. The gap to 9+ is mostly about depth of AI reasoning (learning, uncertainty, patterns) and demo polish — both achievable in Day 2 afternoon if the core is working by Day 2 morning.
