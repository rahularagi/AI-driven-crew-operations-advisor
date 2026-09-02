# Data Sources & APIs

---

## Overview

```
EXTERNAL APIs (called by clients when mock flags are False)
  Aviationstack
    → flight schedule (legs, departure times, aircraft type)
    → live flight status (delay, cancellation, landed)

  SAP HR / Workday (HRMS)
    → crew static profile (name, role, base, designation)

INTERNAL SYSTEMS (always internal — no mock/real split)
  PostgreSQL database
    → crew_members, crew_licenses, crew_ftl_states
    → crew_leave_records, crew_reserve_schedule
    → flight_legs, roster_leg, roster_crew_assignment
    → disruption_proposals

MOCK DATA (used when mock flags are True — default for local dev)
  data/mock/crew.py              → 25 crew profiles
  data/mock/licenses.py          → 21 license records
  data/mock/leave_records.py     → 5 leave records
  data/mock/reserve_schedule.py  → 10 reserve slots
  data/mock_observer.py          → 5 flight poll sequences
  data/legs.json                 → 15 flight legs
  data/seed_ftl.py               → 25 FTL states
```

---

## Mock Flags

Each data source has its own flag in `.env`. All default to `True` for local development.

| Flag | Default | True | False |
|------|---------|------|-------|
| `MOCK_CREW_PROFILE` | True | reads from DB (seeded from `data/mock/crew.py`) | calls SAP HR / Workday API |
| `MOCK_LICENSE` | True | reads from DB (seeded from `data/mock/licenses.py`) | calls AIMS license API |
| `MOCK_FLIGHT_SCHEDULE` | True | reads from DB (seeded from `data/legs.json`) | calls Aviationstack schedule API |
| `MOCK_FLIGHT_STATUS` | True | returns next poll from `data/mock_observer.py` sequences | calls Aviationstack live status API |
| `MOCK_FTL_STATE` | True | reads/writes DB (seeded from `data/seed_ftl.py`) | always internal — flag has no effect |
| `MOCK_RESERVE_SCHEDULE` | True | reads from DB (seeded from `data/mock/reserve_schedule.py`) | calls crew scheduling system API |

---

## Client Layer — Swap Points

Each client is the only place in the codebase that knows whether to use mock or real data.
Services never import from `data/` directly — they always go through a client.

| Client | Mock source | Real source |
|--------|------------|-------------|
| `clients/crew_profile_client.py` | DB → `crew_members` table | SAP HR / Workday API |
| `clients/license_client.py` | DB → `crew_licenses` table | AIMS license API |
| `clients/flight_schedule_client.py` | DB → `flight_legs` table | Aviationstack schedule API |
| `clients/flight_status_client.py` | `data/mock_observer.py` poll sequences | Aviationstack live status API |
| `clients/ftl_client.py` | DB → `crew_ftl_states` table | always internal |
| `clients/leave_client.py` | DB → `crew_leave_records` table | always internal |
| `clients/reserve_client.py` | DB → `crew_reserve_schedule` table | crew scheduling system API |

---

## API 1 — Crew Profile (HRMS)

**Client:** `clients/crew_profile_client.py`
**Used by:** Weekly Planner, Disruption Handler, FTL Service, Leave Client

**Real API:** SAP HR / Workday
```
GET {HRMS_API_BASE_URL}/crew
GET {HRMS_API_BASE_URL}/crew/{crew_id}
Headers: Authorization: Bearer {HRMS_API_KEY}
```

**Mock data:** `data/mock/crew.py` → seeded into `crew_members` table

**25 crew members:**

| crew_id | Name | Role | Designation | Base |
|---------|------|------|-------------|------|
| C-001 | Capt Arjun Mehta | PILOT | CAPTAIN | VIDP |
| C-002 | FO Priya Sharma | PILOT | FIRST_OFFICER | VIDP |
| C-003 | Capt Ravi Singh | PILOT | CAPTAIN | VABB |
| C-004 | FO Anita Nair | PILOT | FIRST_OFFICER | VABB |
| C-005 | Capt Suresh Kumar | PILOT | CAPTAIN | VOBL |
| C-006 | FO Deepa Rao | PILOT | FIRST_OFFICER | VIDP |
| C-007 | Capt Vikram Joshi | PILOT | CAPTAIN | VIDP |
| C-008 | FO Neha Patel | PILOT | FIRST_OFFICER | VABB |
| C-009 | Capt Arun Iyer | PILOT | CAPTAIN | VOBL |
| C-010 | FO Kavya Menon | PILOT | FIRST_OFFICER | VIDP |
| C-011 | SP Sunita Kapoor | CABIN | SENIOR_PURSER | VIDP |
| C-012 | CC Rahul Verma | CABIN | CABIN_CREW | VIDP |
| C-013 | CC Pooja Gupta | CABIN | CABIN_CREW | VABB |
| C-014 | CC Amit Shah | CABIN | CABIN_CREW | VABB |
| C-015 | SP Divya Krishnan | CABIN | SENIOR_PURSER | VOBL |
| C-016 | CC Rohit Malhotra | CABIN | CABIN_CREW | VIDP |
| C-017 | CC Sneha Desai | CABIN | CABIN_CREW | VIDP |
| C-018 | CC Kiran Reddy | CABIN | CABIN_CREW | VABB |
| C-019 | SP Meera Pillai | CABIN | SENIOR_PURSER | VIDP |
| C-020 | CC Ajay Tiwari | CABIN | CABIN_CREW | VOBL |
| C-021 | Capt Nisha Bose | PILOT | CAPTAIN | VIDP |
| C-022 | FO Sanjay Kulkarni | PILOT | FIRST_OFFICER | VABB |
| C-023 | CC Lakshmi Nair | CABIN | CABIN_CREW | VIDP |
| C-024 | Capt Mohan Das | PILOT | CAPTAIN | VABB |
| C-025 | FO Tanya Mishra | PILOT | FIRST_OFFICER | VOBL |

**Model:** `models/crew_member.py` → `CrewMember`

---

## API 2 — Licenses (AIMS)

**Client:** `clients/license_client.py`
**Used by:** Weekly Planner (legality Gate 3/4/5), Disruption Handler (candidate check)

**Mock data:** `data/mock/licenses.py` → seeded into `crew_licenses` table — 21 records

Pilots only. Cabin crew have no aircraft type licenses.

| crew_id | Aircraft types | Notes |
|---------|---------------|-------|
| C-001 | A320, B787 | |
| C-002 | A320 | |
| C-003 | B737, A320 | |
| C-004 | A320 | |
| C-005 | A320, B737 | |
| C-006 | A320 | |
| C-007 | A320, B737 | Best reserve candidate |
| C-008 | A320 | |
| C-009 | A320, B787 | Near 28-day cap in seed FTL |
| C-010 | A320 | |
| C-021 | A320, B737 | |
| C-022 | B737 | B737 only |
| C-024 | A320, B737 | |
| C-025 | A320 | |

Each license record has: `crew_id`, `aircraft_type`, `expiry_date`, `medical_expiry`, `simulator_check_due`

**Model:** `models/crew_license.py` → `CrewLicense`

---

## API 3 — Flight Schedule (Aviationstack)

**Client:** `clients/flight_schedule_client.py`
**Used by:** Weekly Planner (Job A build), Observer (get today's legs), Disruption Handler (leg lookup)

**Real API:**
```
GET https://api.aviationstack.com/v1/flights
  ?access_key={AVIATIONSTACK_API_KEY}
  &airline_iata=AI
  &flight_status=scheduled
```

**Mock data:** `data/legs.json` → seeded into `flight_legs` table — 15 legs

**15 flight legs (demo week Feb 05–11 2024):**

| leg_id | Route | Day | Aircraft | Scenario |
|--------|-------|-----|----------|---------|
| AI854-PNQ-DEL-20240205 | PNQ→DEL | D1 | A320 | Normal — clean flight |
| AI101-DEL-LHR-20240205 | DEL→LHR | D1 | B787 | Cancellation → CRITICAL |
| AI202-DEL-BOM-20240205 | DEL→BOM | D1 | A320 | Delay 0→150 min → MEDIUM |
| AI305-BOM-CCU-20240205 | BOM→CCU | D1 | B737 | Crew sick call (C-003) |
| AI410-BOM-DEL-20240205 | BOM→DEL | D1 | A320 | Delay 240 min → HIGH |
| AI501-DEL-BLR-20240206 | DEL→BLR | D2 | A320 | Normal |
| AI602-BLR-BOM-20240206 | BLR→BOM | D2 | A320 | Normal |
| AI703-DEL-BOM-20240206 | DEL→BOM | D2 | B737 | No legal crew at origin |
| AI804-BOM-DEL-20240207 | BOM→DEL | D3 | A320 | Normal |
| AI905-DEL-PNQ-20240207 | DEL→PNQ | D3 | A320 | Normal |
| AI111-DEL-LHR-20240208 | DEL→LHR | D4 | B787 | C-009 near 28-day cap |
| AI222-BOM-BLR-20240208 | BOM→BLR | D4 | A320 | Normal |
| AI333-BLR-DEL-20240209 | BLR→DEL | D5 | B737 | Normal |
| AI444-DEL-BOM-20240210 | DEL→BOM | D6 | A320 | Normal |
| AI555-BOM-PNQ-20240211 | BOM→PNQ | D7 | A320 | Normal — end of week |

**Model:** `models/flight_leg.py` → `FlightLeg`

---

## API 4 — Live Flight Status (Aviationstack)

**Client:** `clients/flight_status_client.py`
**Used by:** Observer (polls every 5 min via scheduler)

**Real API:**
```
GET https://api.aviationstack.com/v1/flights
  ?access_key={AVIATIONSTACK_API_KEY}
  &flight_iata={flight_iata}
  &flight_date={YYYY-MM-DD}
```

**Mock data:** `data/mock_observer.py` — sequential poll responses per leg

Each leg has a list of poll responses. The client tracks a per-leg index and returns the next response on each call. Index resets when a leg lands (`reset_poll_index_for_leg`).

**5 mocked sequences:**

| leg_id | Poll sequence | Event triggered |
|--------|--------------|----------------|
| AI854-PNQ-DEL-20240205 | scheduled → active → landed | `LegCompletedEvent` |
| AI305-BOM-CCU-20240205 | scheduled → active → landed | `LegCompletedEvent` (disruption is crew-side) |
| AI202-DEL-BOM-20240205 | scheduled → delay(45) → active(150) → landed | `FlightDisruptedEvent(DELAY, MEDIUM)` at poll 3 |
| AI410-BOM-DEL-20240205 | scheduled → delay(240) → active(245) → landed | `FlightDisruptedEvent(DELAY, HIGH)` at poll 2 |
| AI101-DEL-LHR-20240205 | scheduled → cancelled | `FlightDisruptedEvent(CANCELLATION, CRITICAL)` at poll 2 |

**Poll response shape (Aviationstack format):**
```json
{
  "flight_date": "2024-02-05",
  "flight_status": "active",
  "departure": {
    "iata": "DEL",
    "scheduled": "2024-02-05T09:00:00+05:30",
    "actual": "2024-02-05T11:30:00+05:30",
    "delay": 150
  },
  "arrival": {
    "iata": "BOM",
    "scheduled": "2024-02-05T11:00:00+05:30",
    "estimated": "2024-02-05T13:30:00+05:30",
    "actual": null,
    "delay": 150
  },
  "flight": {"iata": "AI202"},
  "aircraft": {"registration": "VT-PPM"}
}
```

**Observer severity mapping:**

| delay_minutes | Severity | Action |
|--------------|----------|--------|
| > 0, any | LOW (floor) | Always published — Disruption Handler re-checks legality |
| ≥ 30 | LOW | |
| ≥ 120 | MEDIUM | |
| ≥ 240 | HIGH | |
| cancelled | CRITICAL | Invalidate roster_leg + all assignments, publish RosterModifiedEvent per crew |
| landed | — | Publish `LegCompletedEvent`, stop polling |

---

## API 5 — FTL State (Internal)

**Client:** `clients/ftl_client.py`
**Used by:** Weekly Planner, Disruption Handler, FTL Service
**Always internal** — `MOCK_FTL_STATE` flag has no effect. Always reads/writes DB.

**Mock seed:** `data/seed_ftl.py` → seeded into `crew_ftl_states` table — 25 states

**Key seeded scenarios:**

| crew_id | Status | Scenario |
|---------|--------|---------|
| C-001 | AVAILABLE | `flight_hours_28_day: 72` — normal available pilot |
| C-002 | AVAILABLE | `flight_hours_28_day: 91` — near 100hr cap |
| C-003 | AVAILABLE | `consecutive_duty_days: 5` — must rest, cannot be assigned Day 6 |
| C-004 | AVAILABLE | `duty_hours_7_day: 54` — near 60hr weekly cap |
| C-005 | RESTING | `at_home_base: False` — away from base, in layover |
| C-006 | UNAVAILABLE | Sick — triggers disruption demo |
| C-007 | AVAILABLE | `flight_hours_28_day: 45` — best replacement candidate |
| C-008 | AVAILABLE | `current_airport: VABB` — at different base |
| C-009 | AVAILABLE | `flight_hours_28_day: 88` — near cap, FDP warning on D4 long-haul |
| C-010–C-025 | AVAILABLE | Standard states |

**Model:** `models/crew_flight_time_limits_state.py` → `CrewFlightTimeLimitsState`

---

## API 6 — Leave Records (Internal)

**Client:** `clients/leave_client.py`
**Used by:** Weekly Planner (legality Gate 6), Disruption Handler (candidate check)
**Always internal** — reads/writes `crew_leave_records` table directly.

**Mock seed:** `data/mock/leave_records.py` → 5 records

| crew_id | Type | Dates | Impact |
|---------|------|-------|--------|
| C-003 | ANNUAL | Feb 05–07 | Excluded D1–D3 |
| C-014 | SICK | Feb 05–11 | Excluded all week |
| C-009 | TRAINING | Feb 06 | Excluded D2 only |
| C-020 | ANNUAL | Feb 08–10 | Excluded D4–D6 |
| C-025 | SICK | Feb 09 | Excluded D5 only |

**`add_leave_record()` side effect:** after inserting, automatically queries `roster_crew_assignment` for all assigned legs within the leave window and publishes `CrewDisruptedEvent(reason=LEAVE_ADDED)` per affected leg. Disruption Handler picks this up and finds a replacement — no manual ops desk action needed.

**Model:** `models/crew_leave.py` → `CrewLeaveRecord`

---

## API 7 — Reserve Schedule (Internal)

**Client:** `clients/reserve_client.py`
**Used by:** Weekly Planner (Pass 2 — fill reserve slots)

**Mock seed:** `data/mock/reserve_schedule.py` → 10 slots

| reserve_id | crew_id | Date | Base | Notes |
|------------|---------|------|------|-------|
| RSV-001 | C-007 | Feb 05 | VIDP | Best replacement candidate |
| RSV-002 | C-010 | Feb 05 | VIDP | Backup VIDP |
| RSV-003 | C-019 | Feb 05 | VABB | VABB standby |
| RSV-004 | C-022 | Feb 05 | VABB | VABB backup |
| RSV-005 | C-002 | Feb 06 | VIDP | |
| RSV-006 | C-016 | Feb 06 | VIDP | |
| RSV-007 | C-018 | Feb 06 | VABB | |
| RSV-008 | C-021 | Feb 07 | VIDP | |
| RSV-009 | C-006 | Feb 08 | VIDP | C-006 back from sick by D4 |
| RSV-010 | C-025 | Feb 09 | VOBL | |

**Model:** `models/crew_reserve.py` → `CrewReserveSchedule`

---

## Database Tables

All data ultimately lives in PostgreSQL. Schema defined in `docker/init.sql`.

| Table | Owned by | Description |
|-------|----------|-------------|
| `crew_members` | Seeded from mock/crew.py | Static crew profiles |
| `crew_licenses` | Seeded from mock/licenses.py | Type ratings + medical expiry |
| `crew_ftl_states` | Seeded from seed_ftl.py, updated live | Live FTL counters per crew |
| `crew_leave_records` | Seeded from mock/leave_records.py, writable via API | Leave periods |
| `crew_reserve_schedule` | Seeded from mock/reserve_schedule.py | Standby slots |
| `flight_legs` | Seeded from legs.json | Flight schedule |
| `roster_leg` | Written by Weekly Planner | One row per leg per planning cycle — DRAFT/PUBLISHED/INVALIDATED |
| `roster_crew_assignment` | Written by Weekly Planner + Disruption Handler | One row per crew per leg — DRAFT/CONFIRMED/REPLACED/INVALIDATED |
| `disruption_proposals` | Written by Disruption Handler | Pending replacement proposals — PENDING/ACCEPTED/REJECTED/EXPIRED |

---

## Events Published Between Services

All inter-service communication goes through `services/event_bus.py`. No service calls another directly.

| Event | Published by | Consumed by |
|-------|-------------|-------------|
| `FlightDisruptedEvent` | Observer (DELAY/CANCELLATION), Weekly Planner re-plan (AIRCRAFT_SWAP/SCHEDULE_CHANGE/ROUTE_CHANGE) | Disruption Handler |
| `LegCompletedEvent` | Observer (landed) | FTL Service |
| `CrewDisruptedEvent` | Ops Desk via `POST /crew/{id}/unavailable`, Leave Client (`add_leave_record`), Weekly Planner Validator (Job B) | Disruption Handler |
| `RosterModifiedEvent` | Disruption Handler (on proposal accept), Planner Router (manual reassign), Disruption Handler (CANCELLATION — per released crew) | FTL Service, Daily Validator |
| `FlightTimeLimitsAlertEvent` | FTL Service (proactive scan) | (not yet consumed — notification service not built) |

---

## Scheduled Jobs

Registered in `api/main.py` via APScheduler.

| Job ID | Schedule | What it does |
|--------|----------|-------------|
| `roster_build` | Sunday 23:00 | Weekly Planner Job A — builds 7-week roster |
| `daily_validation` | Daily 03:00 | Weekly Planner Job B — re-validates all future DRAFT/CONFIRMED assignments |
| `ftl_alert_scan` | Every 15 min | FTL Service — scans all crew for approaching duty limits |
| `ftl_midnight_recalc` | Daily 00:00 | FTL Service — recalculates rolling 7-day and 28-day counters |
| `expire_proposals` | Daily 00:30 | Disruption Handler — marks PENDING proposals EXPIRED if leg already departed |

---

## API Endpoints

### Health
```
GET  /health
```

### Observer
```
GET  /observer/legs/today              → today's active legs with crew assigned
GET  /observer/legs?target_date=...    → legs for a specific date (read-only)
GET  /observer/legs?offset=1           → legs N days from today (read-only)
```

### Planner
```
POST /planner/build                    → trigger Job A manually
POST /planner/validate                 → trigger Job B manually
GET  /planner/roster?start=&end=       → view assignments for date range
POST /planner/roster/{leg_id}/approve  → controller approves a leg (DRAFT → PUBLISHED)
POST /planner/roster/{leg_id}/reassign → manual crew swap with legality check
```

### Disruptions
```
GET  /disruptions/proposals            → all PENDING proposals sorted by severity
POST /disruptions/proposals/{id}/accept → accept proposal → roster updated + RosterModifiedEvent
POST /disruptions/proposals/{id}/reject → reject → next candidate proposed automatically
```

### Crew
```
GET  /crew/{crew_id}/ftl               → current FTL state for a crew member
POST /crew/{crew_id}/unavailable       → ops desk marks crew unavailable → publishes CrewDisruptedEvent
```

### FTL
```
POST /ftl/scan                         → manually trigger proactive alert scan
POST /ftl/recalculate                  → manually trigger rolling counter recalculation
```

---

## Crew Disruption Entry Points

`CrewDisruptedEvent` enters the system from three places:

| Entry point | File | Trigger | reason values |
|------------|------|---------|---------------|
| Ops desk | `api/routers/crew_router.py` `POST /crew/{id}/unavailable` | Human marks crew unavailable | `SICK_CALL / NO_SHOW / MEDICAL_GROUNDING / EMERGENCY_LEAVE / URGENT_TRAINING` |
| Leave added | `clients/leave_client.py` `add_leave_record()` | Any leave insert covering an assigned leg | `LEAVE_ADDED` |
| Weekly Planner Validator | `services/weekly_planner/weekly_planner_service.py` Job B | Runs at 03:00 daily or on `RosterModifiedEvent` | Any legality gate failure |

All three publish to the event bus. Disruption Handler receives all via the same subscription.

---

## Switching to Real APIs

Set flags in `.env`:

```env
MOCK_CREW_PROFILE=False
MOCK_LICENSE=False
MOCK_FLIGHT_SCHEDULE=False
MOCK_FLIGHT_STATUS=False
MOCK_RESERVE_SCHEDULE=False

AVIATIONSTACK_API_KEY=your_key
HRMS_API_BASE_URL=https://your-hrms.internal
HRMS_API_KEY=your_key
```

Each client has a `_get_..._from_real_api()` stub with `raise NotImplementedError` — fill these in per client when going live. Flags can be switched independently — e.g. real flight status but mock crew profile.
