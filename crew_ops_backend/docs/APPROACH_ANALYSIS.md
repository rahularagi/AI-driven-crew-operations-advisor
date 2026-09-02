# CrewOps Advisor — Approach Analysis, Data Requirements & Real-Time Strategy

---

## Why This Approach

### The Core Problem

An airline crew controller handles 10–15 disruptions per shift. Each one requires:
1. Finding who is available
2. Checking if they are legally allowed to fly
3. Picking the best option
4. Updating the roster
5. Notifying affected crew

Manually this takes 15–30 minutes. A delayed decision means a delayed flight. A wrong decision (assigning an illegal crew member) means a regulatory violation, potential fine, and safety risk.

The system must do all 5 steps in under 10 seconds, with full explainability, and close the loop — not just recommend, but act.

---

## Why Each Design Decision Matters

### 1. Deterministic Constraint Checking BEFORE the LLM

**What it means:** Run all legality rules in pure Python first. Only pass survivors to the LLM for ranking and narration.

**Why it matters:**
- LLMs can hallucinate. If the LLM decides legality, it might assign a crew member who is 1 hour over their duty limit.
- Aviation is a safety-critical domain. A wrong assignment is not a UX bug — it is a regulatory violation.
- Judges and real airline operators will ask: "What if the AI makes a mistake on legality?" The answer must be: "It can't — legality is checked in pure Python before the LLM sees any candidate."

**What happens without it:**
- LLM reasons about duty hours and gets it wrong on edge cases
- No audit trail of which rule failed and why
- System is not certifiable for real airline use

**The rule:**
```
Deterministic gate (Python) → survivors only → LLM ranks + narrates
LLM cannot change the legal verdict. Ever.
```

---

### 2. Closed Loop — Roster Update + Crew Notification

**What it means:** After a recommendation is approved (or auto-approved), the system actually updates the roster and sends notifications to affected crew.

**Why it matters:**
- Team 1 (Velaire) shows a dashboard. Team 2 (dCortex) stores a mock approval in memory.
- Neither team closes the loop. The controller still has to manually update the roster and call the crew.
- A system that recommends but doesn't act is a fancy search tool, not an operational system.
- "Operational superintelligence" (the problem statement's own words) means the system acts, not just advises.

**What it enables in the demo:**
- Controller types disruption → system recommends → controller approves → roster is updated → crew receives notification
- The entire 30-minute manual process is done in one flow

---

### 3. Cascade Detection

**What it means:** When a crew member is removed from a flight, check all other flights they are assigned to and flag ripple effects.

**Why it matters:**
- Neither competing team has this.
- In real operations, a sick call on Flight A often creates a gap on Flight B (same crew was assigned to both).
- Without cascade detection, the controller fixes Flight A and discovers Flight B is now uncovered 2 hours later — too late.
- This is the feature that separates a reactive tool from a proactive one.

**Example:**
```
Captain Singh sick → AI-305 Mumbai 10AM needs replacement
Cascade: Singh was also on AI-410 Mumbai 3PM
System flags both simultaneously, finds replacements for both in one pass
```

---

### 4. Proactive Alerts (Before Disruption Happens)

**What it means:** Every 15 minutes, scan all crew on tomorrow's roster for upcoming legality violations, expiring licenses, and flights with no backup identified.

**Why it matters:**
- Reactive systems wait for a disruption to happen. Proactive systems prevent it.
- A crew member approaching their 14-hour duty limit mid-flight is a safety emergency. Catching it 2 hours before departure is a scheduling fix.
- This is what "superintelligence" means in the problem statement — the system sees problems before humans do.

**What it catches:**
- Crew within 2 hours of FDP (Flight Duty Period) limit
- Licenses or medicals expiring in next 7 days
- Flights with no identified backup crew
- Crew on Day 4+ of consecutive duty (high fatigue risk)

---

### 5. Pure Delay Fallback Option

**What it means:** When no legal replacement is found, always return "delay the flight" as a guaranteed option.

**Why it matters:**
- Without this, the system crashes or returns an empty response when no candidates pass the legal gate.
- In a live demo, "no candidates found" with no fallback is a demo killer.
- In real operations, delaying a flight is always a valid (if costly) option. The system must present it with its cost so the controller can make an informed decision.

**What it looks like:**
```
Option 1: Captain Priya Sharma — legal ✓, fatigue 32%, no deadhead
Option 2: Captain Ravi Nair — legal ✓, fatigue 55%, deadhead from BOM
Option 3: Delay flight 90 min — cost $4,200 (45/min × 90), 0 crew changes needed
```

---

### 6. What-If Copilot

**What it means:** Controller asks "what if we delay AI-202 by 2 hours?" — system re-runs the entire pipeline with the modified flight parameters and returns new ranked options.

**Why it matters:**
- Only Team 2 has this. It is the highest-impact interactive demo moment.
- Judges always ask "what if" questions. Having a live answer beats explaining it theoretically.
- Controllers in real operations constantly explore scenarios before committing to a decision.

**How it works:**
```
Controller: "what if we delay AI-202 by 2 hours?"
Parser: { action: extend_delay, flight_id: AI-202, additional_delay_minutes: 120 }
Pipeline: re-run constraint check + ranking with modified departure time
Output: new ranked options with updated legality (some crew may now breach FDP)
```

---

### 7. Cost Breakdown Per Option

**What it means:** Each ranked option shows itemized costs — deadhead ticket, delay cost per minute, passenger impact, overtime flag.

**Why it matters:**
- Ranking by fatigue score alone is not credible to airline operators. They think in dollars.
- A recommendation without cost is a suggestion. A recommendation with cost is a business decision.
- Makes the ranking formula transparent and auditable.

**Formula (from Team 2, worth adopting):**
```
C_total = w1 * deadhead_cost + w2 * delay_cost + w3 * passenger_impact - w4 * crew_preference
```

---

### 8. Crew Location & Rest Place Tracking

**What it means:** Every crew member has a home base (permanent, from contract), a current airport (changes after every landing), and a rest location (home or layover hotel). The platform tracks all three and automatically determines rest type, minimum rest required, hotel need, and return-to-base plan.

**Why it matters:**
- Minimum rest is different at home base (12 hrs) vs away (10 hrs). Without tracking location, the legality checker uses the wrong threshold.
- A crew member stranded at LHR with no return flight assigned is an operational gap. The platform must detect this and flag it.
- Neither competing team tracks crew location post-landing. They only track crew status.

**Three location states a crew member can be in:**

```
State 1 — Duty ends at home base
  current_airport == home_base → at_home_base = true
  rest_type = HOME_REST, min_rest = max(12hrs, preceding duty)
  hotel = not needed
  next: available for duty at home base

State 2 — Duty ends away from home base (layover)
  current_airport != home_base → at_home_base = false
  rest_type = LAYOVER_REST, min_rest = 10 hrs
  hotel = trigger booking at current_airport
  next: operate back toward home base OR deadhead as passenger

State 3 — Deadheading back to home base
  deadhead_status = POSITIONING
  deadhead counts as duty — FDP clock running
  on arrival at home base: at_home_base = true, home rest applies
```

**New fields added to crew_ftl_state:**

| Field | Purpose |
|-------|---------|
| home_base | permanent base airport — never changes |
| current_airport | where crew physically is right now — updated every landing |
| at_home_base | true when current_airport == home_base |
| rest_type | HOME_REST / LAYOVER_REST |
| hotel_location | airport where crew is staying away from base |
| hotel_checkin | when rest started at hotel |
| earliest_checkout | hotel_checkin + min_rest_required |
| next_positioning_flight | deadhead flight back to home base |
| return_to_base_eta | when crew expected back at home base |

---

### 9. Flight Data Fetching — Leg-Based, List Then Filter

**The answer to list vs individual:** Fetch all flights for your airline as a list on startup. Then poll only legs that have crew assigned.

**The answer to route vs leg:** Always leg-based. Never track a route end-to-end.

```
On startup:     GET /flights?airline_iata=AI  → all legs in memory (1 API call)
Every 60 sec:   poll only legs where assigned_crew is not empty
On landing:     update crew location, start rest clock, trigger hotel if away from base
On delay:       estimated_arrival changed → recalculate projected_fdp_end → re-run alerts
On cancel:      trigger disruption pipeline
```

**The only field that drives FTL recalculation:** `estimated_arrival`.
Every time it changes → delay_minutes recalculated → projected_fdp_end updated → legality re-checked → alerts fired if needed.

**Polling frequency by leg status:**

| Leg Status | Poll Frequency | Why |
|-----------|---------------|-----|
| scheduled (> 2hrs away) | every 15 min | nothing happening yet |
| boarding / delayed at gate | every 5 min | departure imminent |
| active (airborne) | every 60 sec | estimated_arrival updating |
| landed / cancelled | stop polling | write final times, trigger FTL update |

**Scope:** filter by `airline_iata` only. Never query global. Never query by country. Your platform only cares about your airline's crew.

---

### 10. Multi-Leg Journey & Augmented Crew Handling

**What it means:** Long-haul and multi-stop routes require leg-based crew assignment, deadhead tracking, augmented crew rotation, and automatic layover triggering. A simple crew-to-flight model breaks on these cases.

**Why it matters:**
- Neither competing team handles this. It is a real operational requirement that any judge with airline domain knowledge will ask about.
- Without leg-based assignment, the system cannot legally model a Pune → Delhi → London route — it would assign the same crew to a 14+ hour journey, which is a regulatory violation.
- Deadhead time counts toward FDP. Ignoring it means the legality checker produces wrong results for any crew that is positioning to their operating airport.

**Three things the platform must handle:**

**1. Leg-based assignment (never route-based)**
```
WRONG: assign Captain Mehta to flight AI-101 (PNQ→DEL→LHR)
RIGHT: assign Captain Mehta to leg AI-101-PNQ-DEL only
       assign Captain Singh  to leg AI-101-DEL-LHR only
```

**2. Augmented crew for ultra-long non-stop flights**
- Aircraft carries 3–4 pilots instead of 2; crew rotate in shifts using onboard rest bunks
- Extended FDP only legal if aircraft has certified rest facility (bunk > seat > none)
- FDP extension: +3.0 hrs (3 pilots, bunk), +4.0 hrs (4 pilots, bunk), +1.5 hrs (seat only)
- Each crew member's `flight_time_current_duty` accumulates only during their active operating window

**3. Deadhead (positioning) tracking**
- Crew travelling as passengers to reach their operating airport are on duty — their FDP clock is running
- Legality checker must add `deadhead_duration` to `projected_duty` before checking the operating leg
- On arrival at hub: `rest_start_time` set, `at_home_base` = false, hotel notification triggered, `earliest_available_at` = rest_start + 10 hrs

**New data fields required:**

| Field | Model | Purpose |
|-------|-------|---------|
| legs[] | Flight | list of Leg objects — each leg is a separate crew assignment |
| leg_id | Leg | sector identifier (e.g., AI-101-DEL-LHR) |
| assigned_crew[] | Leg | crew operating this leg only |
| deadhead_crew[] | Leg | crew positioning on this leg (not operating) |
| swap_airport | Leg | ICAO where crew change happens |
| augmented_crew[] | Leg | extra crew in relief rotation |
| has_crew_rest_facility | Aircraft | bool — extended FDP only legal if true |
| rest_facility_type | Aircraft | BUNK / SEAT / NONE |
| deadhead_counts_as_duty | bool | always true — deadhead adds to FDP |

---

### 11. Roster Planning Layer (Weekly / Monthly)

**What it means:** A separate planning layer that assigns crew to legs days or weeks in advance. The real-time layer stress-tests this plan continuously as flights get delayed or disrupted.

**Why it matters:**
- Without a roster, the disruption pipeline has no baseline to compare against. It cannot know who was supposed to be on a flight, who is on standby, or who is on approved leave.
- The reserve schedule is the first place the system looks when a disruption happens — standby crew at the right airport are the fastest fix.
- Pre-publishing FTL validation catches violations before they happen in operations, not during.
- Neither competing team has a roster planning layer. They only handle disruptions reactively.

**Three roster types:**

| Roster | Built When | Flexibility | Purpose |
|--------|-----------|-------------|--------|
| Monthly | 3–4 weeks ahead | Low | full month plan, crew plan personal lives around it |
| Weekly | 7 days ahead | Medium | confirmed duties, hotel bookings triggered |
| Day-of | Live, continuous | High | real-time updates, disruption handling |

**Three new tables required:**

- `crew_roster` — one row per crew-leg assignment (PLANNED/CONFIRMED/MODIFIED/CANCELLED)
- `crew_leave` — approved leave periods (ANNUAL/SICK/TRAINING/MEDICAL)
- `crew_reserve_schedule` — standby assignments with callable_within minutes

**How disruption pipeline uses all three:**
```
Disruption arrives
  → crew_reserve_schedule: who is on standby at this airport right now?
  → crew_ftl_state: of those, who is legally available?
  → crew_leave: confirm none are on approved leave
  → crew_roster: update assignment on approval, log modified_by + reason
```

**Pre-publish validation (same legality checker, future mode):**
```
Before publishing weekly roster:
  simulate each crew member's full 7-day plan
  run legality checker against planned duties
  flag any FDP breach, rest violation, weekly cap breach
  suggest swap before it becomes a live disruption
```

**Data flow:**
```
Flight schedule → Monthly roster (PLANNED)
                → Weekly roster (CONFIRMED) → hotel bookings triggered
                → Day-of roster (LIVE) → real-time API updates
                                          → FTL recalculation
                                          → disruption pipeline if needed
```

---

### 12. LangGraph ReAct Agent for Reasoning

**What it means:** The AI agent uses a tool-calling loop — it calls find_crew, check_legality, calculate_cost, cascade_check in sequence, reasoning about what to do next after each tool result.

**Why it matters:**
- Simple prompt → response cannot handle multi-step reasoning (find crew, then check each one, then rank survivors, then check cascade).
- ReAct pattern makes the reasoning visible and auditable — judges can see exactly what the agent did and why.
- Tool calls are deterministic — the agent cannot invent crew members or fake legality results.

---

### 13. Flight Schedule Source & Delay Propagation

**How to get scheduled flight data:**

Airlines publish season schedules 6 months in advance via IATA slot coordination. You can pull a full month of scheduled legs in one API call:

```
Aviationstack: GET /flights?airline_iata=AI&flight_status=scheduled
OAG / Cirium:  GET /schedules?airline=AI&from=2024-02-01&to=2024-02-29
```

Pull once on startup → store as your leg table → poll only active legs for real-time status.

**How a single delay affects the week — aircraft vs crew:**

| | Aircraft | Crew |
|-|----------|------|
| Same day | Delay carries to next leg on same aircraft | Delay extends duty, may breach FDP |
| Next day | Usually recovers overnight (aircraft swapped or absorbed) | Depends on severity |
| Rest of week | No effect | 7-day rolling counter stays elevated |

**Crew recovery timeline by delay severity:**

```
< 2 hrs:   no cascading effect, rest still sufficient
2–4 hrs:   proactive alert, monitor, recovers Day 2
4+ hrs:    roster modification, crew out 1–2 days, 7-day counter elevated
FDP breach: compensatory rest, crew out 2+ days, counter elevated all week
```

**Why it takes 2–4 days to fully recover:**
The 7-day rolling duty counter stays elevated until the delayed day's hours roll off the 7-day window. Until then, the crew has fewer available hours for the rest of the week.

**What the platform does on every delay update:**
1. Recalculate `projected_fdp_end` for all crew on the delayed leg
2. Check if next duty rest is still legal
3. If rest violated: Option A (push report time) or Option B (find replacement)
4. Every midnight: recalculate rolling 7-day and 28-day counters for all crew

---

### 14. Summary — What Makes This Platform Complete

Most crew handling tools handle one thing. This platform handles the full lifecycle:

```
Planning:     Monthly/weekly roster built from season schedule
              Pre-validated against FTL before publishing
              Reserve schedule and standby assignments tracked

Operations:   Real-time flight status polling (leg-based)
              FTL state recalculated on every delay
              Proactive alerts before violations happen
              Crew location tracked after every landing
              Hotel triggered automatically for layovers

Disruptions:  Deterministic legality check (pure Python, no LLM)
              Cascade detection across multiple flights
              Cost-ranked replacement options
              Human-in-the-loop for major decisions (crew swap)
              Closed loop: roster updated + crew notified

Recovery:     Rolling counter recalculation every midnight
              Rest violation detection for next-day duties
              Return-to-base planning for stranded crew
```

---

## Data Required

### 0. crew_ftl_state — Live FTL Tracking Table (New, Critical)

This is a **separate, dedicated table** that exists purely to track every crew member's current position against all regulatory limits in real time. It is not part of the crew profile (which is static HR data). It is not part of the flight schedule. It is its own live ledger.

**Why it needs to be a separate table:**
- Crew profile data (name, role, licenses) changes rarely — maybe once a month
- FTL state changes on every duty event — report-in, takeoff, landing, rest start, rest end
- Mixing them means every duty event rewrites the crew profile record, creating race conditions and audit trail loss
- The legality checker needs to read FTL state in under 1ms for every candidate — it must be a fast, flat lookup, not a join across multiple tables
- Proactive alerts scan all crew every 15 minutes — they need a single table to scan, not a computed view

**When it is updated:**
- Crew reports for duty → duty_start_time set, status → ON_DUTY
- Flight departs → flight_time_current_duty starts accumulating
- Flight lands → flight_time_current_duty += sector block hours
- Crew released from duty → duty_end_time set, rest_start_time set, status → OFF_DUTY or AVAILABLE
- Rest period ends (rest_start + min_rest elapsed) → status → AVAILABLE, last_rest_end_time updated
- Commander's discretion invoked → fdp_extension_used set, extension_hours logged, safety_report_required flagged
- Any delay while on duty → projected_fdp_end recalculated automatically

**The table:**

| Field | Type | Description | Updated When |
|-------|------|-------------|-------------|
| crew_id | string | FK to crew profile | — |
| role | PILOT / CABIN | copied from profile for fast filtering | profile change |
| **— Current Duty Window —** | | | |
| duty_start_time | datetime | when crew reported for current duty | report-in |
| duty_end_time | datetime \| null | when current duty ended (null if on duty) | release |
| projected_fdp_end | datetime | duty_start + max allowed FDP for this start time | recalculated on every delay |
| flight_time_current_duty | float (hrs) | block hours flown in this duty period so far | each landing |
| sectors_current_duty | int | number of landings in this duty period | each landing |
| **— Rest Tracking —** | | | |
| rest_start_time | datetime \| null | when current rest period began | duty release |
| last_rest_end_time | datetime | when last rest period ended (= duty_start of current duty) | report-in |
| rest_hours_available | float | hours since last_rest_end_time (live, recalculated) | continuous |
| at_home_base | bool | true if resting at home base (affects min rest threshold) | location update |
| **— Rolling Cumulative Counters —** | | | |
| flight_hours_28_day | float | block hours in last 28 consecutive days | each landing |
| flight_hours_calendar_year | float | block hours in current calendar year | each landing |
| duty_hours_7_day | float | total duty hours in last 7 consecutive days | duty end |
| duty_hours_28_day | float | total duty hours in last 28 consecutive days | duty end |
| consecutive_duty_days | int | how many days in a row crew has had a duty period | duty start |
| last_weekly_rest_end | datetime | when last 36hr+ continuous rest ended | rest end |
| **— FDP Limit for Current Duty —** | | | |
| max_fdp_allowed | float (hrs) | looked up from FDP table at duty_start_time | report-in |
| wocl_encroachment | bool | true if duty window overlaps 02:00–06:00 | report-in |
| fdp_reduction_applied | float (hrs) | hours subtracted from max_fdp due to WOCL | report-in |
| **— Commander's Discretion —** | | | |
| fdp_extension_used | bool | true if captain invoked discretion this duty | discretion event |
| extension_hours | float | how many hours extended (max 2.0) | discretion event |
| safety_report_required | bool | always true when extension_used = true | discretion event |
| compensatory_rest_required | float (hrs) | extra rest owed after discretion use | discretion event |
| **— Crew Location & Rest Place —** | | | |
| home_base | ICAO code | permanent base airport from contract — never changes | profile change |
| current_airport | ICAO code | where crew physically is right now | every landing |
| at_home_base | bool | true when current_airport == home_base | every landing |
| rest_type | HOME_REST / LAYOVER_REST | determines min rest threshold | duty release |
| hotel_location | ICAO code | airport where crew is staying away from base | duty release |
| hotel_checkin | datetime | when crew checked in to layover hotel | duty release |
| earliest_checkout | datetime | hotel_checkin + min_rest_required | duty release |
| next_positioning_flight | string | flight_id of deadhead back to home base | roster assignment |
| return_to_base_eta | datetime | when crew expected back at home_base | roster assignment |
| **— Status —** | | | |
| status | AVAILABLE / ON_DUTY / RESTING / SICK / OFF_DUTY | current state | every event |
| last_updated | datetime | timestamp of last write | every event |

---

**How the FDP limit is calculated at report-in:**

The maximum FDP is not a single number — it depends on three factors at the moment of report:

```
1. Report time (local) → look up base FDP from time bracket table
2. Number of sectors planned → reduce FDP if > 2 sectors
3. WOCL encroachment → reduce FDP further if duty window crosses 02:00–06:00
```

FDP bracket table (DGCA / EASA aligned):

| Report Time (Local) | Max FDP (1–2 sectors) | Max FDP (3 sectors) | Max FDP (4+ sectors) |
|--------------------|-----------------------|---------------------|----------------------|
| 0600 – 0659 | 13.0 hrs | 12.0 hrs | 11.0 hrs |
| 0700 – 1259 | 13.0 hrs | 12.0 hrs | 11.0 hrs |
| 1300 – 1759 | 12.0 hrs | 11.0 hrs | 10.0 hrs |
| 1800 – 2159 | 11.0 hrs | 10.0 hrs | 9.0 hrs |
| 2200 – 2259 | 10.0 hrs | 9.0 hrs | 8.0 hrs |
| 2300 – 0459 | 9.0 hrs | 8.0 hrs | 7.5 hrs |
| 0500 – 0559 | 10.0 hrs | 9.0 hrs | 8.0 hrs |

WOCL reduction: if duty window overlaps 02:00–06:00 by more than 2 hours → subtract 1.0 hr from max_fdp_allowed.

---

**How the legality checker uses this table:**

```
check_legality(crew_id, flight) → (is_legal, reasons[], warnings[]):

  ftl = crew_ftl_state[crew_id]

  # Hard gates — any failure = ILLEGAL, crew excluded
  projected_duty = (now - ftl.duty_start_time) + flight.duration_hours
  if projected_duty > ftl.max_fdp_allowed:          FAIL: "FDP breach — {projected_duty:.1f}h > {ftl.max_fdp_allowed}h limit"
  if ftl.rest_hours_available < min_rest_required:  FAIL: "Insufficient rest — {ftl.rest_hours_available:.1f}h < 10h required"
  if flight.aircraft_type not in crew.licenses:     FAIL: "Not type-rated for {flight.aircraft_type}"
  if ftl.flight_hours_28_day + flight.duration > 100: FAIL: "28-day block hour cap breach"
  if ftl.duty_hours_7_day + projected_duty > 60:    FAIL: "7-day duty cap breach"
  if ftl.status != AVAILABLE:                       FAIL: "Status is {ftl.status}"

  # Soft warnings — legal but flagged
  if projected_duty > ftl.max_fdp_allowed - 1.0:    WARN: "Within 1hr of FDP limit"
  if ftl.wocl_encroachment:                         WARN: "Duty crosses WOCL window — reduced alertness expected"
  if ftl.consecutive_duty_days >= 4:                WARN: "Day {ftl.consecutive_duty_days} of consecutive duty"
  if ftl.flight_hours_28_day + flight.duration > 90: WARN: "Approaching 28-day block hour cap"

  # Commander's discretion availability
  if all hard gates pass but projected_duty > ftl.max_fdp_allowed:
    if not ftl.fdp_extension_used and extension <= 2.0:
      return LEGAL_WITH_DISCRETION: "Captain may extend FDP by up to 2hrs — safety report required"
```

---

**How proactive alerts use this table:**

```
Every 15 minutes, scan all rows in crew_ftl_state:

  Alert type 1 — FDP approaching:
    if status == ON_DUTY and (projected_fdp_end - now) < 2 hours
    → "Captain Mehta: FDP limit in 1h 45min on current duty"

  Alert type 2 — Rest violation risk:
    if status == RESTING and next_scheduled_duty - rest_start < min_rest_required
    → "Cabin crew Anita: only 9.5h rest before AI-450 — minimum is 10h"

  Alert type 3 — Weekly rest overdue:
    if (now - last_weekly_rest_end) > 6 days
    → "Captain Singh: no 36hr rest block in last 6 days — required within 24hrs"

  Alert type 4 — Cumulative cap approaching:
    if flight_hours_28_day > 90
    → "FO Sharma: 92h block hours in 28 days — 8h remaining before cap"

  Alert type 5 — WOCL duty tomorrow:
    if tomorrow's scheduled duty_start is between 0000–0600
    → "Cabin crew Priya: tomorrow's report time 04:30 — WOCL duty, reduced FDP applies"
```

---

**Minimum rest thresholds (what at_home_base controls):**

| Situation | Minimum Rest Required |
|-----------|----------------------|
| At home base | max(12 hrs, preceding duty period duration) |
| Away from base (layover hotel) | 10 hrs in suitable accommodation |
| After commander's discretion use | normal minimum + compensatory_rest_required |
| After WOCL duty (02:00–06:00 encroachment) | 12 hrs minimum regardless of base |
| Weekly rest | 36 hrs continuous (48 hrs recommended) |

---

### 1. Crew Data (Static Profile)

| Field | Type | Source | Used For |
|-------|------|--------|----------|
| crew_id | string | HRMS | unique identifier |
| employee_id | string | HRMS | official HR ID |
| name | string | HRMS | display + notifications |
| designation | CAPTAIN/FIRST_OFFICER/SENIOR_PURSER/CABIN_CREW | HRMS | role filtering |
| date_of_joining | date | HRMS | seniority calculation |
| seniority_number | int | HRMS | reserve bidding (lower = more senior) |
| home_base | ICAO | HRMS | permanent base, never changes |
| employment_status | ACTIVE/ON_LEAVE/SUSPENDED/RESIGNED | HRMS | exclude non-active crew |
| licenses | list[string] | AIMS | aircraft type ratings |
| license_expiry | dict {type: date} | AIMS | per-license expiry tracking |
| medical_expiry | date | AIMS | proactive alert when expiring |
| simulator_check_due | date | AIMS | recurrent training tracking |
| phone | string | HRMS | notifications |
| email | string | HRMS | notifications |

**Source systems:**
- HRMS (SAP HR, Oracle HCM, Workday) — static profile, nightly sync
- AIMS (Jeppesen Crew, IBS CrewStar) — licenses + training, updates on completion

**For hackathon:** seed 25 crew members with realistic variety — see `data/seed.py`

---

### 2. Reserve Pool Data

| Field | Type | Used For |
|-------|------|----------|
| crew_id | string | identifier |
| name | string | display |
| role | PILOT / CABIN | filtering |
| base_airport | ICAO | deadhead detection |
| current_airport | ICAO | deadhead detection |
| qualifications | list[string] | license check |
| callable_at | datetime | earliest availability |
| contact | string | notification |

**Note:** Reserve crew are treated as fully rested (duty_hours = 0, last_rest = 10+ hrs ago). They have no accumulated duty history until called.

**Source:** Reserve scheduling system or crew management system reserve module

---

### 3. Flight Schedule Data

| Field | Type | Used For |
|-------|------|----------|
| flight_id | string | identifier |
| origin | ICAO | airport match check |
| destination | ICAO | display |
| scheduled_departure | datetime | FDP calculation |
| actual_departure | datetime | delay detection |
| aircraft_type | string | license match check |
| status | SCHEDULED / DELAYED / CANCELLED / IN_FLIGHT | disruption context |
| assigned_crew | list[crew_id] | cascade detection |
| duration_hours | float | FDP projection |
| delay_minutes | int | what-if scenarios |
| passenger_count | int | passenger impact cost |

**Source:** Flight operations system (IBS iFlight, Sabre, Amadeus, or airline OCC system)

---

### 4. Regulatory Constraints

| Field | Type | Used For |
|-------|------|----------|
| max_fdp_by_time_bracket | dict | FDP hard gate (time-of-day dependent) |
| min_rest_hours | float (10.0) | rest hard gate |
| max_duty_hours_today | float (14.0) | daily duty hard gate |
| max_monthly_flight_hours | float (100.0) | monthly cap hard gate |
| max_cumulative_7_day | float (60.0) | weekly cap hard gate |

**FDP table (Part 117 / DGCA equivalent):**
```
Report time 0000–0459 → max FDP 9.0 hrs
Report time 0500–0559 → max FDP 9.0 hrs
Report time 0600–0659 → max FDP 9.0 hrs
Report time 0700–1259 → max FDP 9.0 hrs
Report time 1300–1659 → max FDP 9.0 hrs
Report time 1700–2159 → max FDP 9.0 hrs
Report time 2200–2359 → max FDP 9.0 hrs
```
(Actual brackets vary by regulator — DGCA India, FAA Part 117, EASA FTL)

**Source:** Static config file — regulatory rules do not change frequently. Update manually when regulations change.

---

### 5. Cost Configuration

| Field | Type | Used For |
|-------|------|----------|
| deadhead_ticket_cost | float ($220) | cost formula w1 |
| delay_cost_per_minute | float ($45) | cost formula w2 |
| passenger_impact_per_hour | float ($12/pax) | cost formula w3 |
| crew_preference_weight | float | cost formula w4 |

**Source:** Static config file — set by airline operations finance team.

---

### 6. Airport Reference Data

| Field | Type | Used For |
|-------|------|----------|
| icao_code | string | matching |
| city | string | display |
| timezone | string | local time calculations |
| is_hub | bool | deadhead cost estimation |

**Source:** Static reference file — airports don't change.

---

### 7. Disruption Events (Runtime Input)

| Field | Type | Used For |
|-------|------|----------|
| type | SICK_CALL / DELAY / AIRCRAFT_SWAP / NO_SHOW / CANCELLATION | pipeline routing |
| affected_flight_id | string | flight lookup |
| affected_crew_id | string (optional) | crew lookup |
| description | string | LLM parsing |
| timestamp | datetime | audit trail |

**Source:** Controller types free text → LLM parses into this structure.

---

## Real-Time Data Feeding — Approaches Compared

### Option A — Direct Database / API Polling (Recommended for Hackathon)

```
Crew Management System API
        │
        ▼ (poll every 60 seconds or on-demand)
  Local cache (Redis or in-memory dict)
        │
        ▼
  Pipeline reads from cache
```

**How it works:**
- On startup, load all crew + flights into memory
- Background thread polls the source API every 60 seconds for updates
- Pipeline always reads from the in-memory cache (fast, no latency)
- Cache is refreshed in the background without blocking requests

**Pros:** Simple, fast, works without a message broker
**Cons:** Up to 60 seconds stale on crew status changes

**Best for:** Hackathon demo, small airline (< 500 crew)

---

### Option B — Webhook / Event Push (Best for Production)

```
Crew Management System
        │
        │ POST /events/crew-status-changed
        │ POST /events/flight-updated
        ▼
  CrewOps Advisor Event Endpoint
        │
        ▼
  Update in-memory state immediately
```

**How it works:**
- Airline's crew management system sends a webhook when crew status changes (e.g., crew calls sick)
- CrewOps Advisor receives the event and updates its state immediately
- Zero polling delay — state is always current

**Pros:** Real-time, no polling overhead, event-driven
**Cons:** Requires the source system to support webhooks (most modern AIMS systems do)

**Best for:** Production deployment

---

### Option C — Kafka / Message Stream (Best for Scale)

```
Crew Management System → Kafka topic: crew.status.updates
Flight Ops System      → Kafka topic: flight.schedule.updates
        │
        ▼
  CrewOps Advisor Kafka Consumer
        │
        ▼
  Update state in real-time
```

**How it works:**
- All source systems publish events to Kafka topics
- CrewOps Advisor consumes these streams and maintains current state
- Multiple instances of CrewOps Advisor can consume the same stream (horizontal scale)

**Pros:** Handles high volume, supports multiple consumers, full event history
**Cons:** Requires Kafka infrastructure, more complex setup

**Best for:** Large airline (500K+ operations/day), multi-region deployment

---

### Option D — Simulated Real-Time (Hackathon Fallback)

```
seed.py generates 25 crew + 15 flights
        │
        ▼
  Background thread mutates state every 30 seconds:
  - randomly changes crew status (AVAILABLE → ON_DUTY)
  - adds delay_minutes to random flights
  - triggers proactive alert checks
```

**How it works:**
- Seed data is loaded on startup
- A background simulation thread makes realistic state changes
- Proactive alert scanner fires every 15 minutes and finds real violations in the simulated data

**Pros:** No external dependencies, always works in demo, shows real-time behavior
**Cons:** Not real data

**Best for:** Hackathon demo when no real airline API is available

---

## Recommended Data Architecture for This Build

```
┌─────────────────────────────────────────────────────┐
│                   Data Layer                        │
│                                                     │
│  seed.py ──► in-memory store (dict)                 │
│                    │                                │
│                    │ (production: replace with)     │
│                    │ AIMS API poll / webhook         │
│                    │                                │
│  regulatory_constraints.json  (static, never polls) │
│  cost_config.json             (static, never polls) │
│  airport_reference.json       (static, never polls) │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              CrewOps Pipeline                       │
│                                                     │
│  1. Parse disruption text → DisruptionEvent         │
│  2. Fetch flight from in-memory store               │
│  3. Fetch candidate crew (roster + reserves)        │
│  4. Run deterministic constraint checks (Python)    │
│  5. Score survivors (cost formula)                  │
│  6. LLM ranks + narrates                            │
│  7. Cascade check                                   │
│  8. Update roster in store                          │
│  9. Send notifications                              │
└─────────────────────────────────────────────────────┘
```

---

## What Each Competing Team Gets Right (and What to Steal)

| Feature | Team 1 (Velaire) | Team 2 (dCortex) | Us |
|---------|-----------------|-----------------|-----|
| Deterministic constraint gate | ❌ mixed with UI logic | ✅ pure Python before LLM | ⚠ needs separation |
| Cost formula with $ breakdown | ❌ | ✅ explicit w1–w4 formula | ⚠ add this |
| Pure delay fallback | ❌ | ✅ always appended | ❌ add this |
| What-if copilot | ❌ | ✅ re-runs pipeline | ❌ add this |
| Cascade detection | ❌ | ❌ | ✅ only us |
| Roster update (closed loop) | ❌ UI only | ❌ mock only | ✅ only us |
| Crew notification | ❌ | ❌ | ✅ only us |
| Proactive alerts | ✅ "103 agents" | ❌ | ✅ |
| Reserve pool separate from roster | ❌ | ✅ | ⚠ add this |
| Real-time data strategy | ✅ 30s polling + fallback | ❌ static JSON | ⚠ add simulation thread |
| Multi-leg / leg-based assignment | ❌ | ❌ | ✅ only us |
| Augmented crew (in-flight relief) | ❌ | ❌ | ✅ only us |
| Deadhead FDP tracking | ❌ | ❌ | ✅ only us |
| Live FTL tracking table (crew_ftl_state) | ❌ | ❌ | ✅ only us |
| Roster planning layer (weekly/monthly) | ❌ | ❌ | ✅ only us |
| Reserve schedule + standby tracking | ❌ | ❌ | ✅ only us |
| Crew location + rest place tracking | ❌ | ❌ | ✅ only us |
| Flight data fetching (leg-based polling) | ❌ | ❌ | ✅ only us |

---

## Priority Build Order (What to Add Next)

| Priority | Feature | Why | Effort |
|----------|---------|-----|--------|
| 1 | Pure delay fallback | Demo breaks without it | 30 min |
| 2 | Separate deterministic constraint check | Safety credibility, judge question | 1 hr |
| 3 | crew_roster + crew_leave + crew_reserve tables | Disruption pipeline needs baseline | 1 hr |
| 4 | Roster validator (pre-publish FTL check) | Catches violations before operations | 1 hr |
| 5 | Cost breakdown per option ($ numbers) | Makes ranking credible | 1 hr |
| 6 | Reserve pool + standby schedule in seed data | Realistic disruption demo | 1 hr |
| 7 | Leg model + leg-based assignment | Required for any multi-stop route | 2 hrs |
| 8 | Deadhead FDP tracking in legality checker | Correctness on positioning crew | 1 hr |
| 9 | Crew location update on landing + hotel trigger | Closes the loop on layovers | 1 hr |
| 10 | Flight status simulation thread | Makes demo feel live | 1 hr |
| 11 | Augmented crew fields + FDP extension rules | Ultra-long-haul correctness | 1 hr |
| 12 | What-if copilot endpoint | Highest demo interactivity | 2–3 hrs |
| 13 | "No replacement found" graceful path | Robustness | 1 hr |
