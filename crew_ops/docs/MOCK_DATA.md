# Mock Data — Reference Guide

> All seed and mock files live in `data/`. They replace every external API and internal system
> for local development and testing. Nothing calls a real endpoint except `fetch_flights.py`.

---

## Overview

```
data/
├── seed_crew.py        API 3  — HRMS (25 crew profiles)
├── seed_legs.py        API 1  — Flight schedule (15 scenario legs)
├── seed_ftl.py         API 4b — AIMS FTL state (25 crew states)
├── seed_roster.py      API 5  — Crew leave  +  API 6 — Reserve schedule
├── mock_observer.py    API 2  — Live flight status (Observer poll sequences)
└── fetch_flights.py           — Real Aviationstack fetch (run once, not used at runtime)
```

---

## File 1 — `seed_crew.py` (API 3 — HRMS)

**What it is:** 25 Air India crew members. Static profiles — name, role, base, licenses, medical expiry.

**Import:**
```python
from crew_ops.data.seed_crew import CREW
```

**Shape (one member):**
```python
{
    "crew_id": "C-001",
    "employee_id": "EMP-4421",
    "name": "Capt Arjun Mehta",
    "designation": "CAPTAIN",
    "role": "PILOT",
    "home_base": "VIDP",
    "date_of_joining": "2008-03-15",
    "seniority_number": 12,
    "employment_status": "ACTIVE",
    "phone": "+91-9800000001",
    "email": "a.mehta@airline.in",
    "licenses": ["A320", "B787"],
    "license_expiry": {"A320": "2025-06-30", "B787": "2025-08-01"},
    "medical_expiry": "2025-08-15",
    "simulator_check_due": "2025-04-01",
}
```

**Crew breakdown:**

| crew_id | Name | Role | Base | Notable |
|---------|------|------|------|---------|
| C-001 | Capt Arjun Mehta | PILOT / CAPTAIN | VIDP | A320 + B787 rated |
| C-002 | FO Priya Sharma | PILOT / FIRST_OFFICER | VIDP | A320 only |
| C-003 | Capt Ravi Singh | PILOT / CAPTAIN | VABB | B737 + A320, sick call demo |
| C-004 | FO Anita Nair | PILOT / FIRST_OFFICER | VABB | A320 only |
| C-005 | Capt Suresh Kumar | PILOT / CAPTAIN | VOBL | A320 + B737 |
| C-006 | FO Deepa Rao | PILOT / FIRST_OFFICER | VIDP | UNAVAILABLE (sick) |
| C-007 | Capt Vikram Joshi | PILOT / CAPTAIN | VIDP | Best reserve candidate |
| C-008 | FO Neha Patel | PILOT / FIRST_OFFICER | VABB | At different base — deadhead demo |
| C-009 | Capt Arun Iyer | PILOT / CAPTAIN | VOBL | A320 + B787, near 28-day cap |
| C-010 | FO Kavya Menon | PILOT / FIRST_OFFICER | VIDP | A320 only |
| C-011 | SP Sunita Kapoor | CABIN / SENIOR_PURSER | VIDP | — |
| C-012 | CC Rahul Verma | CABIN / CABIN_CREW | VIDP | — |
| C-013 | CC Pooja Gupta | CABIN / CABIN_CREW | VABB | — |
| C-014 | CC Amit Shah | CABIN / CABIN_CREW | VABB | On sick leave all week |
| C-015 | SP Divya Krishnan | CABIN / SENIOR_PURSER | VOBL | — |
| C-016 | CC Rohit Malhotra | CABIN / CABIN_CREW | VIDP | — |
| C-017 | CC Sneha Desai | CABIN / CABIN_CREW | VIDP | — |
| C-018 | CC Kiran Reddy | CABIN / CABIN_CREW | VABB | — |
| C-019 | SP Meera Pillai | CABIN / SENIOR_PURSER | VIDP | — |
| C-020 | CC Ajay Tiwari | CABIN / CABIN_CREW | VOBL | On leave D4–D6 |
| C-021 | Capt Nisha Bose | PILOT / CAPTAIN | VIDP | A320 + B737 |
| C-022 | FO Sanjay Kulkarni | PILOT / FIRST_OFFICER | VABB | B737 only |
| C-023 | CC Lakshmi Nair | CABIN / CABIN_CREW | VIDP | — |
| C-024 | Capt Mohan Das | PILOT / CAPTAIN | VABB | A320 + B737 |
| C-025 | FO Tanya Mishra | PILOT / FIRST_OFFICER | VOBL | On sick leave D5 |

---

## File 2 — `seed_legs.py` (API 1 — Flight Schedule)

**What it is:** 15 legs across the demo week (D1=Feb 05 to D7=Feb 11). Each leg is already
mapped to the `roster_leg` schema. Every leg has a `_scenario` field explaining what it demos.

**Import:**
```python
from crew_ops.data.seed_legs import LEGS
```

**Shape (one leg):**
```python
{
    "leg_id": "AI202-DEL-BOM-20240205",
    "flight_number": "AI202",
    "origin_iata": "DEL",       "origin_icao": "VIDP",
    "destination_iata": "BOM",  "destination_icao": "VABB",
    "scheduled_departure": "2024-02-05T09:00:00+05:30",
    "scheduled_arrival":   "2024-02-05T11:00:00+05:30",
    "estimated_arrival":   "2024-02-05T11:00:00+05:30",
    "actual_departure": None,
    "actual_arrival":   None,
    "aircraft_type": "A320",
    "aircraft_registration": "VT-PPM",
    "status": "SCHEDULED",
    "delay_status": "ON_TIME",
    "delay_minutes": 0,
    "assigned_crew": ["C-007", "C-010", "C-019", "C-023"],
    "_scenario": "Delay scenario — Observer will push delay updates",
}
```

**All 15 legs:**

| leg_id | Route | Day | Aircraft | Scenario |
|--------|-------|-----|----------|---------|
| AI854-PNQ-DEL-20240205 | PNQ→DEL | D1 | A320 | Normal |
| AI101-DEL-LHR-20240205 | DEL→LHR | D1 | B787 | Long-haul, augmented crew — **cancelled** in Observer mock |
| AI202-DEL-BOM-20240205 | DEL→BOM | D1 | A320 | **Delay grows 0→150 min** → FlightDisrupted MEDIUM |
| AI305-BOM-CCU-20240205 | BOM→CCU | D1 | B737 | **C-003 sick call** → CrewDisrupted CRITICAL |
| AI410-BOM-DEL-20240205 | BOM→DEL | D1 | A320 | **Delay 240 min** → FlightDisrupted HIGH + cascade |
| AI501-DEL-BLR-20240206 | DEL→BLR | D2 | A320 | Normal |
| AI602-BLR-BOM-20240206 | BLR→BOM | D2 | A320 | Normal |
| AI703-DEL-BOM-20240206 | DEL→BOM | D2 | B737 | **No legal crew at origin** — gap demo |
| AI804-BOM-DEL-20240207 | BOM→DEL | D3 | A320 | Normal |
| AI905-DEL-PNQ-20240207 | DEL→PNQ | D3 | A320 | Normal |
| AI111-DEL-LHR-20240208 | DEL→LHR | D4 | B787 | **C-009 near 28-day cap** — FDP warning |
| AI222-BOM-BLR-20240208 | BOM→BLR | D4 | A320 | Normal |
| AI333-BLR-DEL-20240209 | BLR→DEL | D5 | B737 | Normal |
| AI444-DEL-BOM-20240210 | DEL→BOM | D6 | A320 | Normal |
| AI555-BOM-PNQ-20240211 | BOM→PNQ | D7 | A320 | Normal — end of week |

---

## File 3 — `seed_ftl.py` (API 4b — AIMS FTL State)

**What it is:** One FTL state row per crew member. Seeded with deliberate variety so every
FTL scenario can be demonstrated without waiting for real duty events.

**Import:**
```python
from crew_ops.data.seed_ftl import FTL_STATES
```

**Shape (one state):**
```python
{
    "crew_id": "C-001",
    "role": "PILOT",
    "status": "AVAILABLE",                          # AVAILABLE / RESTING / UNAVAILABLE
    "duty_start_time": None,
    "duty_end_time": None,
    "projected_fdp_end": None,
    "flight_time_current_duty": 0.0,
    "sectors_current_duty": 0,
    "rest_start_time": "2024-02-04T21:30:00+05:30",
    "last_rest_end_time": "2024-02-04T07:00:00+05:30",
    "rest_hours_available": 10.5,
    "flight_hours_28_day": 72.0,                    # rolling counter
    "duty_hours_7_day": 38.5,                       # rolling counter
    "duty_hours_28_day": 145.0,                     # rolling counter
    "consecutive_duty_days": 3,
    "last_weekly_rest_end": "2024-02-01T08:00:00+05:30",
    "max_fdp_allowed": 13.0,                        # per-duty, resets each duty
    "wocl_encroachment": False,                     # per-duty
    "fdp_reduction_applied": 0.0,                   # per-duty
    "fdp_extension_used": False,                    # per-duty
    "extension_hours": 0.0,                         # per-duty
    "home_base": "VIDP",
    "current_airport": "VIDP",
    "at_home_base": True,
    "rest_type": "HOME_REST",                       # HOME_REST / HOTEL_REST / None
    "earliest_checkout": None,
    "last_updated": "2024-02-04T21:30:00+05:30",
}
```

**Seeded scenarios (C-001 to C-009):**

| crew_id | Status | Scenario seeded | What it demos |
|---------|--------|----------------|---------------|
| C-001 | AVAILABLE | `flight_hours_28_day: 72`, fresh | Normal available pilot |
| C-002 | AVAILABLE | `flight_hours_28_day: 91` | Near 100hr cap — planner limits assignments |
| C-003 | AVAILABLE | `consecutive_duty_days: 5` | Must get weekly rest — cannot be assigned Day 6 |
| C-004 | AVAILABLE | `duty_hours_7_day: 54` | Near 60hr weekly cap |
| C-005 | RESTING | `at_home_base: False`, `current_airport: VIDP` | Away from base, in layover hotel |
| C-006 | UNAVAILABLE | — | Sick — triggers disruption demo |
| C-007 | AVAILABLE | `flight_hours_28_day: 45`, fresh | Best candidate — low hours, at VIDP |
| C-008 | AVAILABLE | `current_airport: VABB` | At different base — deadhead needed |
| C-009 | AVAILABLE | `flight_hours_28_day: 88` | Near 28-day cap — FDP warning on D4 long-haul |
| C-010–C-025 | AVAILABLE | Standard states | Normal crew pool |

> **FDP fields vs rolling counters:**
> `max_fdp_allowed`, `wocl_encroachment`, `fdp_reduction_applied`, `fdp_extension_used`, `extension_hours`
> are **per-duty** — they reset when a duty ends.
> `flight_hours_28_day`, `duty_hours_7_day`, `duty_hours_28_day`, `consecutive_duty_days`
> are **rolling counters** — they carry history forward and never reset.

---

## File 4 — `seed_roster.py` (API 5 + API 6)

**What it is:** Crew leave records (external AIMS/HR input) and reserve/standby schedule.

**Import:**
```python
from crew_ops.data.seed_roster import CREW_LEAVE, RESERVE_SCHEDULE
```

### CREW_LEAVE shape:
```python
{"crew_id": "C-003", "leave_type": "ANNUAL", "start_date": "2024-02-05", "end_date": "2024-02-07"}
```

### All leave records:

| crew_id | Type | Dates | Impact |
|---------|------|-------|--------|
| C-003 | ANNUAL | Feb 05–07 | Excluded from D1–D3 assignments |
| C-014 | SICK | Feb 05–11 | Excluded all week |
| C-009 | TRAINING | Feb 06 | Excluded D2 only |
| C-020 | ANNUAL | Feb 08–10 | Excluded D4–D6 |
| C-025 | SICK | Feb 09 | Excluded D5 only |

### RESERVE_SCHEDULE shape:
```python
{
    "reserve_id": "RSV-001",
    "crew_id": "C-007",
    "date": "2024-02-05",
    "standby_start": "2024-02-05T06:00:00+05:30",
    "standby_end": "2024-02-05T18:00:00+05:30",
    "base_airport": "VIDP",
    "callable_within": 120,         # minutes
    "status": "SCHEDULED",          # SCHEDULED / ACTIVATED / RELEASED
    "activated_for": None,          # leg_id if activated
}
```

### All reserve slots:

| reserve_id | crew_id | Date | Base | Notes |
|------------|---------|------|------|-------|
| RSV-001 | C-007 | D1 | VIDP | Best candidate for sick call replacement |
| RSV-002 | C-010 | D1 | VIDP | Backup VIDP reserve |
| RSV-003 | C-019 | D1 | VABB | VABB standby |
| RSV-004 | C-022 | D1 | VABB | VABB backup |
| RSV-005 | C-002 | D2 | VIDP | — |
| RSV-006 | C-016 | D2 | VIDP | — |
| RSV-007 | C-018 | D2 | VABB | — |
| RSV-008 | C-021 | D3 | VIDP | — |
| RSV-009 | C-006 | D4 | VIDP | C-006 back from sick by D4 |
| RSV-010 | C-025 | D5 | VOBL | — |

---

## File 5 — `mock_observer.py` (API 2 — Live Flight Status)

**What it is:** Simulated Aviationstack poll responses for 5 key flights. Each flight has a
sequence of responses showing how its status evolves across multiple Observer polls.
The raw shape matches the real Aviationstack API exactly.

**Import:**
```python
from crew_ops.data.mock_observer import get_poll_sequence, get_all_leg_ids
```

**Usage:**
```python
# Get the full poll sequence for a leg
polls = get_poll_sequence("AI202-DEL-BOM-20240205")

for i, response in enumerate(polls):
    dep_delay = response["departure"]["delay"]
    arr_delay = response["arrival"]["delay"]
    status    = response["flight_status"]
    est_arr   = response["arrival"]["estimated"]
    print(f"Poll {i+1}: status={status}  dep_delay={dep_delay}  arr_delay={arr_delay}  est_arr={est_arr}")
```

**Output:**
```
Poll 1: status=scheduled  dep_delay=None   arr_delay=None   est_arr=2024-02-05T11:00:00+05:30
Poll 2: status=scheduled  dep_delay=45     arr_delay=45     est_arr=2024-02-05T11:45:00+05:30
Poll 3: status=active     dep_delay=150    arr_delay=150    est_arr=2024-02-05T13:30:00+05:30
Poll 4: status=landed     dep_delay=150    arr_delay=148    est_arr=2024-02-05T13:30:00+05:30
```

**What Observer extracts from each poll (mapped to roster_leg fields):**
```python
{
    "leg_id":           "AI202-DEL-BOM-20240205",
    "status":           "AIRBORNE",           # mapped from flight_status
    "actual_departure": "2024-02-05T11:30:00+05:30",
    "estimated_arrival":"2024-02-05T13:30:00+05:30",
    "delay_minutes":    150,
    "delay_status":     "DELAYED",
}
```

**All 5 mocked sequences and what they trigger:**

| leg_id | Poll sequence | Disruption triggered |
|--------|--------------|---------------------|
| AI854-PNQ-DEL-20240205 | scheduled → active → landed | None — clean flight |
| AI305-BOM-CCU-20240205 | scheduled → active → landed | None — disruption is crew-side (C-003 sick) |
| AI202-DEL-BOM-20240205 | scheduled → delayed(45) → active(150) → landed | `FlightDisrupted` severity=MEDIUM at poll 3 |
| AI410-BOM-DEL-20240205 | scheduled → delayed(240) → active(245) → landed | `FlightDisrupted` severity=HIGH at poll 2 |
| AI101-DEL-LHR-20240205 | scheduled → cancelled | `FlightDisrupted` severity=CRITICAL at poll 2 |

**Observer severity thresholds (from SYSTEM_DESIGN.md):**

| delay_minutes | Severity |
|--------------|----------|
| 0–29 | no event |
| 30–119 | LOW |
| 120–239 | MEDIUM |
| 240+ | HIGH |
| cancelled / diverted | CRITICAL |

---

## How the Services Use This Data

```
WEEKLY PLANNER (Job A)
  reads:  LEGS, CREW, FTL_STATES, CREW_LEAVE, RESERVE_SCHEDULE
  uses:   LEGS to build roster_leg rows
          CREW to find candidates (role, base, licenses)
          FTL_STATES to simulate forward and check legality
          CREW_LEAVE to exclude crew on leave
          RESERVE_SCHEDULE to fill standby slots

OBSERVER
  reads:  seed_legs (which legs to watch today)
  polls:  get_poll_sequence(leg_id) — one call per poll cycle
  emits:  FlightDisrupted when delay crosses threshold or status = cancelled

DISRUPTION HANDLER
  reads:  CREW, FTL_STATES, RESERVE_SCHEDULE, CREW_LEAVE
  uses:   FTL_STATES to check legality of replacement candidates
          RESERVE_SCHEDULE to find on-standby crew first
          CREW_LEAVE to confirm candidate is not on leave

FTL SERVICE
  reads:  FTL_STATES (initial load)
  writes: updates in memory on every LegCompleted / RosterModified event
```

---

## Quick Reference — Scenario to Data Mapping

| Scenario | Leg | Crew involved | Data file |
|----------|-----|--------------|-----------|
| Delay → MEDIUM disruption | AI202-DEL-BOM | C-007, C-010 | mock_observer.py poll 3 |
| Delay → HIGH disruption | AI410-BOM-DEL | C-024, C-022 | mock_observer.py poll 2 |
| Cancellation → CRITICAL | AI101-DEL-LHR | C-001, C-002 | mock_observer.py poll 2 |
| Sick call → CRITICAL | AI305-BOM-CCU | C-003 (sick) | seed_ftl C-006 status=UNAVAILABLE |
| Near 28-day cap | AI111-DEL-LHR | C-009 (88hrs) | seed_ftl C-009 |
| Near weekly cap | any D1 leg | C-004 (54hrs) | seed_ftl C-004 |
| Must rest (5 days) | any D6 leg | C-003 | seed_ftl C-003 |
| Away from base | any VIDP leg | C-005 at VIDP | seed_ftl C-005 |
| Deadhead needed | any VIDP leg | C-008 at VABB | seed_ftl C-008 |
| No legal crew at origin | AI703-DEL-BOM | C-006 UNAVAILABLE | seed_ftl C-006 |
| Best reserve candidate | AI305 replacement | C-007 (45hrs, VIDP) | seed_ftl C-007 + seed_roster RSV-001 |
