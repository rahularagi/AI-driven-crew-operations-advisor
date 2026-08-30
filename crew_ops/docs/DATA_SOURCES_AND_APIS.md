# Data Sources, APIs & Mock Data

> What data we need, which API provides it, and exactly what the response looks like.
> Every section has a real API shape + mock example so you know what to expect.

---

## Overview — Where Each Data Type Comes From

```
┌─────────────────────────────────────────────────────────────────┐
│  EXTERNAL APIs (we call these)                                  │
│                                                                 │
│  Aviationstack / AeroDataBox                                    │
│    → flight schedule (legs, departure times, aircraft type)     │
│    → live flight status (delay, estimated arrival, status)      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  INTERNAL SYSTEMS (airline owns these — we mock them)           │
│                                                                 │
│  HRMS (SAP HR / Workday)                                        │
│    → crew static profile (name, role, base, seniority)          │
│                                                                 │
│  AIMS (Jeppesen Crew / IBS CrewStar)                            │
│    → crew licenses, medical expiry, duty history                │
│    → current roster assignments, leave records                  │
│    → FTL state (duty hours, rest state, cumulative counters)    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  STATIC CONFIG (we define these, never changes)                 │
│                                                                 │
│  fdp_table.json       → FDP limits by report time + sectors     │
│  cost_config.json     → deadhead cost, delay cost/min           │
│  airport_ref.json     → ICAO codes, timezones, hub flags        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## API 1 — Flight Schedule (Aviationstack)

**Used by:** Weekly Planner (on startup, fetch all legs for planning horizon)

**Call:**
```
GET https://api.aviationstack.com/v1/flights
  ?access_key=YOUR_KEY
  &airline_iata=AI
  &flight_status=scheduled
  &limit=100
```

**Real response shape:**
```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Pune Airport",
        "iata": "PNQ",
        "icao": "VAPU",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "estimated": "2024-02-05T06:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T08:15:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": {
        "name": "Air India",
        "iata": "AI",
        "icao": "AIC"
      },
      "flight": {
        "number": "854",
        "iata": "AI854",
        "icao": "AIC854"
      },
      "aircraft": {
        "registration": "VT-ABC",
        "iata": "A320",
        "icao": "A320"
      }
    }
  ]
}
```

**What we extract and store as a Leg:**
```json
{
  "leg_id": "AI854-PNQ-DEL-20240205",
  "flight_number": "AI854",
  "flight_id": "AI854",
  "origin_iata": "PNQ",
  "origin_icao": "VAPU",
  "destination_iata": "DEL",
  "destination_icao": "VIDP",
  "scheduled_departure": "2024-02-05T06:00:00+05:30",
  "scheduled_arrival": "2024-02-05T08:15:00+05:30",
  "estimated_arrival": "2024-02-05T08:15:00+05:30",
  "actual_departure": null,
  "actual_arrival": null,
  "duration_hours": 2.25,
  "aircraft_type": "A320",
  "aircraft_registration": "VT-ABC",
  "status": "SCHEDULED",
  "delay_minutes": 0,
  "assigned_crew": []
}
```

**Note on multi-leg flights:**
Aviationstack returns each leg as a separate record. AI-101 PNQ→DEL→LHR comes back as two separate rows — one for PNQ→DEL and one for DEL→LHR. We group them under the same `flight_id` and assign a `sequence` number.

---

## API 2 — Live Flight Status (Aviationstack / AeroDataBox)

**Used by:** Observer (polls active legs every 60 sec while airborne)

**Call:**
```
GET https://api.aviationstack.com/v1/flights
  ?access_key=YOUR_KEY
  &flight_iata=AI854
  &flight_date=2024-02-05
```

**Real response shape (flight airborne, delayed):**
```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "active",
      "departure": {
        "iata": "PNQ",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "actual": "2024-02-05T08:30:00+05:30",
        "delay": 150
      },
      "arrival": {
        "iata": "DEL",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T10:45:00+05:30",
        "actual": null,
        "delay": 150
      },
      "flight": {
        "iata": "AI854"
      },
      "aircraft": {
        "registration": "VT-ABC"
      }
    }
  ]
}
```

**What Observer extracts and compares against stored leg:**
```json
{
  "leg_id": "AI854-PNQ-DEL-20240205",
  "status": "active",
  "actual_departure": "2024-02-05T08:30:00+05:30",
  "estimated_arrival": "2024-02-05T10:45:00+05:30",
  "delay_minutes": 150
}
```

**Observer decision after this update:**
```
stored leg.estimated_arrival  = 08:15
new    leg.estimated_arrival  = 10:45
delta                         = 150 min

150 > 30  → severity LOW
150 > 120 → severity MEDIUM

emit FlightDisrupted {
  leg_id: "AI854-PNQ-DEL-20240205",
  disruption_type: "DELAY",
  severity: "MEDIUM",
  delay_minutes: 150,
  assigned_crew: ["C-001", "C-004", "C-011", "C-012", "C-013", "C-014"]
}
```

---

## API 3 — HRMS (Mocked — Internal Airline System)

**Used by:** Weekly Planner, Disruption Handler (candidate finding)

**In production:** nightly batch sync from SAP HR / Workday
**For us:** `data/seed_crew.py` — 25 crew members seeded on startup

**Mock data shape (one crew member):**
```json
{
  "crew_id": "C-001",
  "employee_id": "EMP-4421",
  "name": "Captain Arjun Mehta",
  "designation": "CAPTAIN",
  "role": "PILOT",
  "home_base": "VIDP",
  "date_of_joining": "2008-03-15",
  "seniority_number": 12,
  "employment_status": "ACTIVE",
  "phone": "+91-9800000001",
  "email": "a.mehta@airline.in"
}
```

**25 crew seed — variety required:**

| crew_id | Name | Role | Base | Seniority |
|---------|------|------|------|-----------|
| C-001 | Capt Arjun Mehta | PILOT / CAPTAIN | VIDP | 12 |
| C-002 | FO Priya Sharma | PILOT / FIRST_OFFICER | VIDP | 34 |
| C-003 | Capt Ravi Singh | PILOT / CAPTAIN | VABB | 8 |
| C-004 | FO Anita Nair | PILOT / FIRST_OFFICER | VABB | 41 |
| C-005 | Capt Suresh Kumar | PILOT / CAPTAIN | VOBL | 19 |
| C-006 | FO Deepa Rao | PILOT / FIRST_OFFICER | VIDP | 27 |
| C-007 | Capt Vikram Joshi | PILOT / CAPTAIN | VIDP | 5 |
| C-008 | FO Neha Patel | PILOT / FIRST_OFFICER | VABB | 52 |
| C-009 | Capt Arun Iyer | PILOT / CAPTAIN | VOBL | 23 |
| C-010 | FO Kavya Menon | PILOT / FIRST_OFFICER | VIDP | 38 |
| C-011 | SP Sunita Kapoor | CABIN / SENIOR_PURSER | VIDP | 15 |
| C-012 | CC Rahul Verma | CABIN / CABIN_CREW | VIDP | 44 |
| C-013 | CC Pooja Gupta | CABIN / CABIN_CREW | VABB | 31 |
| C-014 | CC Amit Shah | CABIN / CABIN_CREW | VABB | 58 |
| C-015 | SP Divya Krishnan | CABIN / SENIOR_PURSER | VOBL | 22 |
| C-016 | CC Rohit Malhotra | CABIN / CABIN_CREW | VIDP | 47 |
| C-017 | CC Sneha Desai | CABIN / CABIN_CREW | VIDP | 36 |
| C-018 | CC Kiran Reddy | CABIN / CABIN_CREW | VABB | 29 |
| C-019 | SP Meera Pillai | CABIN / SENIOR_PURSER | VIDP | 18 |
| C-020 | CC Ajay Tiwari | CABIN / CABIN_CREW | VOBL | 53 |
| C-021 | Capt Nisha Bose | PILOT / CAPTAIN | VIDP | 11 |
| C-022 | FO Sanjay Kulkarni | PILOT / FIRST_OFFICER | VABB | 45 |
| C-023 | CC Lakshmi Nair | CABIN / CABIN_CREW | VIDP | 33 |
| C-024 | Capt Mohan Das | PILOT / CAPTAIN | VABB | 16 |
| C-025 | FO Tanya Mishra | PILOT / FIRST_OFFICER | VOBL | 60 |

---

## API 4 — AIMS (Mocked — Internal Airline System)

**Used by:** Weekly Planner (licenses, leave), FTL Service (duty history), Disruption Handler (legality check)

**In production:** webhook on every duty event
**For us:** `data/seed_ftl.py` — initial FTL states seeded on startup

### 4a — Licenses & Medical (from AIMS)

```json
{
  "crew_id": "C-001",
  "licenses": ["A320", "B737"],
  "license_expiry": {
    "A320": "2025-06-30",
    "B737": "2024-09-15"
  },
  "medical_expiry": "2024-08-15",
  "simulator_check_due": "2024-04-01"
}
```

### 4b — FTL State (live ledger, one row per crew)

```json
{
  "crew_id": "C-001",
  "role": "PILOT",
  "status": "AVAILABLE",

  "duty_start_time": null,
  "duty_end_time": null,
  "projected_fdp_end": null,
  "flight_time_current_duty": 0.0,
  "sectors_current_duty": 0,

  "rest_start_time": "2024-02-04T21:30:00+05:30",
  "last_rest_end_time": "2024-02-04T07:00:00+05:30",
  "rest_hours_available": 10.5,

  "flight_hours_28_day": 72.0,
  "flight_hours_calendar_year": 180.0,
  "duty_hours_7_day": 38.5,
  "duty_hours_28_day": 145.0,
  "consecutive_duty_days": 3,
  "last_weekly_rest_end": "2024-02-01T08:00:00+05:30",

  "max_fdp_allowed": 13.0,
  "wocl_encroachment": false,
  "fdp_reduction_applied": 0.0,

  "fdp_extension_used": false,
  "extension_hours": 0.0,
  "safety_report_required": false,
  "compensatory_rest_required": 0.0,

  "home_base": "VIDP",
  "current_airport": "VIDP",
  "at_home_base": true,
  "rest_type": "HOME_REST",
  "hotel_location": null,
  "hotel_checkin": null,
  "earliest_checkout": null,
  "next_positioning_flight": null,
  "return_to_base_eta": null,

  "last_updated": "2024-02-04T21:30:00+05:30"
}
```

**Seed variety for FTL states — what we need to demo all scenarios:**

| crew_id | Scenario seeded | Why |
|---------|----------------|-----|
| C-001 | `flight_hours_28_day: 72`, fresh | Normal available pilot |
| C-002 | `flight_hours_28_day: 91` | Near 100hr cap — planner limits assignments |
| C-003 | `consecutive_duty_days: 5` | Must get weekly rest — cannot be assigned Day 6 |
| C-004 | `duty_hours_7_day: 54` | Near 60hr weekly cap |
| C-005 | `status: RESTING`, `at_home_base: false` | Away from base, in layover hotel |
| C-006 | `status: SICK` | Sick — triggers disruption demo |
| C-007 | `flight_hours_28_day: 45`, fresh | Best candidate — low hours, available |
| C-008 | `status: AVAILABLE`, `current_airport: VABB` | At different base — deadhead needed |

---

## API 5 — Crew Leave (Mocked — AIMS / HR)

**Used by:** Weekly Planner (exclude crew on leave), Disruption Handler (confirm not on leave)

```json
[
  {
    "leave_id": "LV-001",
    "crew_id": "C-003",
    "leave_type": "ANNUAL",
    "start_date": "2024-02-05",
    "end_date": "2024-02-07",
    "status": "APPROVED"
  },
  {
    "leave_id": "LV-002",
    "crew_id": "C-014",
    "leave_type": "SICK",
    "start_date": "2024-02-05",
    "end_date": "2024-02-11",
    "status": "APPROVED"
  },
  {
    "leave_id": "LV-003",
    "crew_id": "C-009",
    "leave_type": "TRAINING",
    "start_date": "2024-02-06",
    "end_date": "2024-02-06",
    "status": "APPROVED"
  }
]
```

---

## API 6 — Reserve Schedule (Mocked — Crew Scheduling System)

**Used by:** Disruption Handler (first place to look for replacements — already at the right airport)

```json
[
  {
    "reserve_id": "RSV-001",
    "crew_id": "C-007",
    "date": "2024-02-05",
    "standby_start": "2024-02-05T06:00:00+05:30",
    "standby_end": "2024-02-05T18:00:00+05:30",
    "base_airport": "VIDP",
    "callable_within": 120,
    "status": "SCHEDULED",
    "activated_for": null
  },
  {
    "reserve_id": "RSV-002",
    "crew_id": "C-010",
    "date": "2024-02-05",
    "standby_start": "2024-02-05T06:00:00+05:30",
    "standby_end": "2024-02-05T18:00:00+05:30",
    "base_airport": "VIDP",
    "callable_within": 120,
    "status": "SCHEDULED",
    "activated_for": null
  },
  {
    "reserve_id": "RSV-003",
    "crew_id": "C-019",
    "date": "2024-02-05",
    "standby_start": "2024-02-05T06:00:00+05:30",
    "standby_end": "2024-02-05T18:00:00+05:30",
    "base_airport": "VABB",
    "callable_within": 120,
    "status": "SCHEDULED",
    "activated_for": null
  }
]
```

---

## Static Config Files

### config/fdp_table.json

```json
{
  "brackets": [
    { "from": "0600", "to": "0659", "sectors_1_2": 13.0, "sectors_3": 12.0, "sectors_4_plus": 11.0 },
    { "from": "0700", "to": "1259", "sectors_1_2": 13.0, "sectors_3": 12.0, "sectors_4_plus": 11.0 },
    { "from": "1300", "to": "1759", "sectors_1_2": 12.0, "sectors_3": 11.0, "sectors_4_plus": 10.0 },
    { "from": "1800", "to": "2159", "sectors_1_2": 11.0, "sectors_3": 10.0, "sectors_4_plus": 9.0 },
    { "from": "2200", "to": "2259", "sectors_1_2": 10.0, "sectors_3": 9.0,  "sectors_4_plus": 8.0 },
    { "from": "2300", "to": "0459", "sectors_1_2": 9.0,  "sectors_3": 8.0,  "sectors_4_plus": 7.5 },
    { "from": "0500", "to": "0559", "sectors_1_2": 10.0, "sectors_3": 9.0,  "sectors_4_plus": 8.0 }
  ],
  "wocl_reduction_hours": 1.0,
  "wocl_window": { "start": "0200", "end": "0600" },
  "wocl_threshold_minutes": 120,
  "min_rest_home_base_hours": 12,
  "min_rest_away_hours": 10,
  "weekly_rest_hours": 36,
  "max_flight_hours_28_day": 100,
  "max_duty_hours_7_day": 60,
  "max_fdp_extension_discretion": 2.0
}
```

### config/cost_config.json

```json
{
  "deadhead_ticket_cost_usd": 220,
  "delay_cost_per_minute_usd": 45,
  "passenger_impact_per_hour_usd": 12,
  "crew_preference_weight": 0.1,
  "ranking_weights": {
    "legal": 0.40,
    "same_airport": 0.30,
    "low_fatigue": 0.20,
    "low_cost": 0.10
  }
}
```

### config/airport_ref.json

```json
[
  { "icao": "VIDP", "iata": "DEL", "city": "Delhi",   "timezone": "Asia/Kolkata", "is_hub": true  },
  { "icao": "VABB", "iata": "BOM", "city": "Mumbai",  "timezone": "Asia/Kolkata", "is_hub": true  },
  { "icao": "VOBL", "iata": "BLR", "city": "Bengaluru","timezone": "Asia/Kolkata", "is_hub": false },
  { "icao": "VAPU", "iata": "PNQ", "city": "Pune",    "timezone": "Asia/Kolkata", "is_hub": false },
  { "icao": "EGLL", "iata": "LHR", "city": "London",  "timezone": "Europe/London","is_hub": false }
]
```

---

## Mock Flight Schedule — 15 Legs for Demo Week

These are the legs seeded in `data/seed_legs.py`. Designed to cover all demo scenarios.

| leg_id | Flight | Route | Departure | Duration | Aircraft | Scenario |
|--------|--------|-------|-----------|----------|----------|---------|
| AI854-PNQ-DEL-D1 | AI854 | PNQ→DEL | 06:00 | 2.25h | A320 | Normal |
| AI101-DEL-LHR-D1 | AI101 | DEL→LHR | 11:00 | 9.25h | B787 | Long-haul, augmented crew |
| AI202-DEL-BOM-D1 | AI202 | DEL→BOM | 09:00 | 2.0h | A320 | Delay scenario |
| AI305-BOM-CCU-D1 | AI305 | BOM→CCU | 10:00 | 2.5h | B737 | Sick call scenario |
| AI410-BOM-DEL-D1 | AI410 | BOM→DEL | 15:00 | 2.0h | A320 | Cascade scenario |
| AI501-DEL-BLR-D2 | AI501 | DEL→BLR | 07:30 | 2.75h | A320 | Normal |
| AI602-BLR-BOM-D2 | AI602 | BLR→BOM | 13:00 | 1.5h | A320 | Normal |
| AI703-DEL-BOM-D2 | AI703 | DEL→BOM | 08:00 | 2.0h | B737 | No legal crew at origin → gap demo |
| AI804-BOM-DEL-D3 | AI804 | BOM→DEL | 06:30 | 2.0h | A320 | Normal |
| AI905-DEL-PNQ-D3 | AI905 | DEL→PNQ | 14:00 | 2.25h | A320 | Normal |
| AI111-DEL-LHR-D4 | AI111 | DEL→LHR | 10:30 | 9.25h | B787 | FDP limit warning demo |
| AI222-BOM-BLR-D4 | AI222 | BOM→BLR | 09:00 | 1.5h | A320 | Normal |
| AI333-BLR-DEL-D5 | AI333 | BLR→DEL | 11:00 | 2.75h | B737 | Normal |
| AI444-DEL-BOM-D6 | AI444 | DEL→BOM | 07:00 | 2.0h | A320 | Normal |
| AI555-BOM-PNQ-D7 | AI555 | BOM→PNQ | 16:00 | 0.75h | A320 | Normal |

**D1 = Day 1 of planning week, D2 = Day 2, etc.**

---

## How the 3 Services Use This Data

```
WEEKLY PLANNER
  reads:  seed_legs (all 15 legs)
          seed_crew (25 crew profiles + licenses)
          seed_ftl  (carry-over FTL states)
          seed_leave (3 leave entries)
          seed_reserve (existing standby slots)
          fdp_table.json
          cost_config.json
  writes: crew_roster (one row per crew × leg)
          crew_reserve_schedule (standby slots)

OBSERVER
  reads:  crew_roster (which legs have crew → which to watch)
  calls:  Aviationstack live status API every 15–60 sec
  writes: nothing (emits events only)
  emits:  FlightDisrupted, LegCompleted

DISRUPTION HANDLER
  reads:  crew_roster (who is on the affected leg)
          crew_ftl_state (live legality check)
          crew_reserve_schedule (standby pool)
          crew_leave (confirm not on leave)
          fdp_table.json
          cost_config.json
  writes: crew_roster (MODIFIED / CANCELLED entries)
          crew_ftl_state (updated for affected crew)
  emits:  RosterModified, CrewNotified
```

---

## Polling Strategy Summary

| What | Who polls | Frequency | Trigger to change |
|------|-----------|-----------|------------------|
| Full flight schedule | Weekly Planner | Once on startup + weekly | New planning cycle |
| Scheduled legs (> 2hr to departure) | Observer | Every 15 min | Status changes to BOARDING |
| Legs at gate / boarding | Observer | Every 5 min | Status changes to ACTIVE |
| Airborne legs | Observer | Every 60 sec | `estimated_arrival` changes |
| Landed / cancelled legs | Observer | Stop polling | LegCompleted event emitted |
| Crew FTL state | FTL Service | On every duty event (not polled) | LegCompleted, RosterModified |
