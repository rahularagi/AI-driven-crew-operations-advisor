# Mock API Responses

> Exact mock data for both API calls.
> Part 1 — GET /flights?airline_iata=AI (Weekly Planner startup fetch)
> Part 2 — GET /flights?flight_iata=AI854&flight_date=... (Observer live poll)

---

## CALL 1 — GET /flights?airline_iata=AI

**Who calls it:** Weekly Planner, once on startup
**Purpose:** Pull all scheduled legs for Air India → store in memory as leg table

```
GET https://api.aviationstack.com/v1/flights
  ?access_key=YOUR_KEY
  &airline_iata=AI
  &flight_status=scheduled
  &limit=100
```

### Full Mock Response

```json
{
  "pagination": {
    "limit": 100,
    "offset": 0,
    "count": 15,
    "total": 15
  },
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
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "854", "iata": "AI854", "icao": "AIC854" },
      "aircraft": { "registration": "VT-ABC", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-05T11:00:00+05:30",
        "estimated": "2024-02-05T11:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Heathrow Airport",
        "iata": "LHR",
        "icao": "EGLL",
        "scheduled": "2024-02-05T15:15:00+00:00",
        "estimated": "2024-02-05T15:15:00+00:00",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "101", "iata": "AI101", "icao": "AIC101" },
      "aircraft": { "registration": "VT-XYZ", "iata": "B788", "icao": "B788" }
    },
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-05T09:00:00+05:30",
        "estimated": "2024-02-05T09:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-05T11:00:00+05:30",
        "estimated": "2024-02-05T11:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "202", "iata": "AI202", "icao": "AIC202" },
      "aircraft": { "registration": "VT-DEF", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-05T10:00:00+05:30",
        "estimated": "2024-02-05T10:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Netaji Subhas Chandra Bose International Airport",
        "iata": "CCU",
        "icao": "VECC",
        "scheduled": "2024-02-05T12:30:00+05:30",
        "estimated": "2024-02-05T12:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "305", "iata": "AI305", "icao": "AIC305" },
      "aircraft": { "registration": "VT-GHI", "iata": "B737", "icao": "B737" }
    },
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-05T15:00:00+05:30",
        "estimated": "2024-02-05T15:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-05T17:00:00+05:30",
        "estimated": "2024-02-05T17:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "410", "iata": "AI410", "icao": "AIC410" },
      "aircraft": { "registration": "VT-JKL", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-06",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-06T07:30:00+05:30",
        "estimated": "2024-02-06T07:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Kempegowda International Airport",
        "iata": "BLR",
        "icao": "VOBL",
        "scheduled": "2024-02-06T10:15:00+05:30",
        "estimated": "2024-02-06T10:15:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "501", "iata": "AI501", "icao": "AIC501" },
      "aircraft": { "registration": "VT-MNO", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-06",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Kempegowda International Airport",
        "iata": "BLR",
        "icao": "VOBL",
        "scheduled": "2024-02-06T13:00:00+05:30",
        "estimated": "2024-02-06T13:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-06T14:30:00+05:30",
        "estimated": "2024-02-06T14:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "602", "iata": "AI602", "icao": "AIC602" },
      "aircraft": { "registration": "VT-PQR", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-06",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-06T08:00:00+05:30",
        "estimated": "2024-02-06T08:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-06T10:00:00+05:30",
        "estimated": "2024-02-06T10:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "703", "iata": "AI703", "icao": "AIC703" },
      "aircraft": { "registration": "VT-STU", "iata": "B737", "icao": "B737" }
    },
    {
      "flight_date": "2024-02-07",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-07T06:30:00+05:30",
        "estimated": "2024-02-07T06:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-07T08:30:00+05:30",
        "estimated": "2024-02-07T08:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "804", "iata": "AI804", "icao": "AIC804" },
      "aircraft": { "registration": "VT-VWX", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-07",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-07T14:00:00+05:30",
        "estimated": "2024-02-07T14:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Pune Airport",
        "iata": "PNQ",
        "icao": "VAPU",
        "scheduled": "2024-02-07T16:15:00+05:30",
        "estimated": "2024-02-07T16:15:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "905", "iata": "AI905", "icao": "AIC905" },
      "aircraft": { "registration": "VT-YZA", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-08",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-08T10:30:00+05:30",
        "estimated": "2024-02-08T10:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Heathrow Airport",
        "iata": "LHR",
        "icao": "EGLL",
        "scheduled": "2024-02-08T14:45:00+00:00",
        "estimated": "2024-02-08T14:45:00+00:00",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "111", "iata": "AI111", "icao": "AIC111" },
      "aircraft": { "registration": "VT-XYZ", "iata": "B788", "icao": "B788" }
    },
    {
      "flight_date": "2024-02-08",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-08T09:00:00+05:30",
        "estimated": "2024-02-08T09:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Kempegowda International Airport",
        "iata": "BLR",
        "icao": "VOBL",
        "scheduled": "2024-02-08T10:30:00+05:30",
        "estimated": "2024-02-08T10:30:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "222", "iata": "AI222", "icao": "AIC222" },
      "aircraft": { "registration": "VT-BCD", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-09",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Kempegowda International Airport",
        "iata": "BLR",
        "icao": "VOBL",
        "scheduled": "2024-02-09T11:00:00+05:30",
        "estimated": "2024-02-09T11:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-09T13:45:00+05:30",
        "estimated": "2024-02-09T13:45:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "333", "iata": "AI333", "icao": "AIC333" },
      "aircraft": { "registration": "VT-EFG", "iata": "B737", "icao": "B737" }
    },
    {
      "flight_date": "2024-02-10",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Indira Gandhi International Airport",
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-10T07:00:00+05:30",
        "estimated": "2024-02-10T07:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-10T09:00:00+05:30",
        "estimated": "2024-02-10T09:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "444", "iata": "AI444", "icao": "AIC444" },
      "aircraft": { "registration": "VT-HIJ", "iata": "A320", "icao": "A320" }
    },
    {
      "flight_date": "2024-02-11",
      "flight_status": "scheduled",
      "departure": {
        "airport": "Chhatrapati Shivaji Maharaj International Airport",
        "iata": "BOM",
        "icao": "VABB",
        "scheduled": "2024-02-11T16:00:00+05:30",
        "estimated": "2024-02-11T16:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "airport": "Pune Airport",
        "iata": "PNQ",
        "icao": "VAPU",
        "scheduled": "2024-02-11T16:45:00+05:30",
        "estimated": "2024-02-11T16:45:00+05:30",
        "actual": null,
        "delay": null
      },
      "airline": { "name": "Air India", "iata": "AI", "icao": "AIC" },
      "flight": { "number": "555", "iata": "AI555", "icao": "AIC555" },
      "aircraft": { "registration": "VT-KLM", "iata": "A320", "icao": "A320" }
    }
  ]
}
```

---

### What the Weekly Planner builds from this response

Each item in `data[]` becomes one Leg stored in memory:

```
API response item                     →   Leg stored in memory
─────────────────────────────────────────────────────────────────
flight.iata + departure.iata          →   leg_id
  + arrival.iata + flight_date              "AI854-PNQ-DEL-20240205"

flight.iata                           →   flight_number  "AI854"
departure.iata / icao                 →   origin_iata / origin_icao
arrival.iata / icao                   →   destination_iata / destination_icao
departure.scheduled                   →   scheduled_departure
arrival.scheduled                     →   scheduled_arrival
arrival.scheduled - departure.sched   →   duration_hours  (computed)
aircraft.iata                         →   aircraft_type   "A320"
aircraft.registration                 →   aircraft_registration
flight_status                         →   status          "SCHEDULED"
(not yet assigned)                    →   assigned_crew   []
(zero at start)                       →   delay_minutes   0
```


---

## CALL 2 — GET /flights?flight_iata=AI854&flight_date=2024-02-05

**Who calls it:** Observer, polling active legs
**Purpose:** Get live status of one specific leg — check if estimated_arrival changed

```
GET https://api.aviationstack.com/v1/flights
  ?access_key=YOUR_KEY
  &flight_iata=AI854
  &flight_date=2024-02-05
```

---

### Scenario A — On time, not yet departed (status: scheduled)

Observer polls every 15 min. No change detected. No event emitted.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "iata": "PNQ",
        "icao": "VAPU",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "estimated": "2024-02-05T06:00:00+05:30",
        "actual": null,
        "delay": null
      },
      "arrival": {
        "iata": "DEL",
        "icao": "VIDP",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T08:15:00+05:30",
        "actual": null,
        "delay": null
      },
      "flight": { "iata": "AI854" },
      "aircraft": { "registration": "VT-ABC", "iata": "A320" }
    }
  ]
}
```

```
Observer check:
  stored estimated_arrival  = 08:15
  new    estimated_arrival  = 08:15
  delta = 0 min → no change → no event
```

---

### Scenario B — Small delay at gate (status: scheduled, delay starting)

Observer polls every 5 min (now in boarding window). Delay detected but below threshold.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "scheduled",
      "departure": {
        "iata": "PNQ",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "estimated": "2024-02-05T06:25:00+05:30",
        "actual": null,
        "delay": 25
      },
      "arrival": {
        "iata": "DEL",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T08:40:00+05:30",
        "actual": null,
        "delay": 25
      },
      "flight": { "iata": "AI854" },
      "aircraft": { "registration": "VT-ABC", "iata": "A320" }
    }
  ]
}
```

```
Observer check:
  stored estimated_arrival  = 08:15
  new    estimated_arrival  = 08:40
  delta = 25 min
  25 < 30 → below LOW threshold → no event emitted
  update stored leg.estimated_arrival = 08:40
  update stored leg.delay_minutes = 25
```

---

### Scenario C — Medium delay, airborne (status: active)

Observer polls every 60 sec. Delay crossed MEDIUM threshold. FlightDisrupted emitted.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "active",
      "departure": {
        "iata": "PNQ",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "estimated": "2024-02-05T08:30:00+05:30",
        "actual": "2024-02-05T08:32:00+05:30",
        "delay": 152
      },
      "arrival": {
        "iata": "DEL",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T10:47:00+05:30",
        "actual": null,
        "delay": 152
      },
      "flight": { "iata": "AI854" },
      "aircraft": { "registration": "VT-ABC", "iata": "A320" }
    }
  ]
}
```

```
Observer check:
  stored estimated_arrival  = 08:15  (original)
  new    estimated_arrival  = 10:47
  delta = 152 min

  152 > 30  → severity LOW
  152 > 120 → severity MEDIUM  ← this wins

  emit FlightDisrupted:
  {
    "event": "FlightDisrupted",
    "leg_id": "AI854-PNQ-DEL-20240205",
    "flight_number": "AI854",
    "origin": "PNQ",
    "destination": "DEL",
    "disruption_type": "DELAY",
    "severity": "MEDIUM",
    "scheduled_departure": "2024-02-05T06:00:00+05:30",
    "actual_departure": "2024-02-05T08:32:00+05:30",
    "delay_minutes": 152,
    "assigned_crew": ["C-001", "C-002", "C-011", "C-012", "C-016", "C-017"],
    "detected_at": "2024-02-05T09:15:00+05:30"
  }
```

---

### Scenario D — Flight landed (status: landed)

Observer detects landing. Emits LegCompleted. Stops polling this leg.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "landed",
      "departure": {
        "iata": "PNQ",
        "scheduled": "2024-02-05T06:00:00+05:30",
        "actual": "2024-02-05T08:32:00+05:30",
        "delay": 152
      },
      "arrival": {
        "iata": "DEL",
        "scheduled": "2024-02-05T08:15:00+05:30",
        "estimated": "2024-02-05T10:47:00+05:30",
        "actual": "2024-02-05T10:51:00+05:30",
        "delay": 156
      },
      "flight": { "iata": "AI854" },
      "aircraft": { "registration": "VT-ABC", "iata": "A320" }
    }
  ]
}
```

```
Observer check:
  flight_status = "landed"
  actual_arrival is set = 10:51

  emit LegCompleted:
  {
    "event": "LegCompleted",
    "leg_id": "AI854-PNQ-DEL-20240205",
    "actual_arrival": "2024-02-05T10:51:00+05:30",
    "destination": "DEL",
    "crew": ["C-001", "C-002", "C-011", "C-012", "C-016", "C-017"],
    "delay_minutes": 156
  }

  stop polling AI854 on 2024-02-05
  FTL Service receives LegCompleted → closes duty window for all 6 crew
```

---

### Scenario E — Flight cancelled (status: cancelled)

Observer detects cancellation. Emits FlightDisrupted with type CANCELLATION. Stops polling.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "cancelled",
      "departure": {
        "iata": "BOM",
        "scheduled": "2024-02-05T10:00:00+05:30",
        "estimated": null,
        "actual": null,
        "delay": null
      },
      "arrival": {
        "iata": "CCU",
        "scheduled": "2024-02-05T12:30:00+05:30",
        "estimated": null,
        "actual": null,
        "delay": null
      },
      "flight": { "iata": "AI305" },
      "aircraft": { "registration": "VT-GHI", "iata": "B737" }
    }
  ]
}
```

```
Observer check:
  flight_status = "cancelled"

  emit FlightDisrupted:
  {
    "event": "FlightDisrupted",
    "leg_id": "AI305-BOM-CCU-20240205",
    "flight_number": "AI305",
    "origin": "BOM",
    "destination": "CCU",
    "disruption_type": "CANCELLATION",
    "severity": "CRITICAL",
    "scheduled_departure": "2024-02-05T10:00:00+05:30",
    "actual_departure": null,
    "delay_minutes": null,
    "assigned_crew": ["C-003", "C-008", "C-013", "C-014", "C-018"],
    "detected_at": "2024-02-05T09:45:00+05:30"
  }

  stop polling AI305 on 2024-02-05
```

---

### Scenario F — Long-haul flight airborne, no delay (AI101 DEL→LHR)

Observer polls every 60 sec. estimated_arrival unchanged. No event.

```json
{
  "data": [
    {
      "flight_date": "2024-02-05",
      "flight_status": "active",
      "departure": {
        "iata": "DEL",
        "scheduled": "2024-02-05T11:00:00+05:30",
        "actual": "2024-02-05T11:04:00+05:30",
        "delay": 4
      },
      "arrival": {
        "iata": "LHR",
        "scheduled": "2024-02-05T15:15:00+00:00",
        "estimated": "2024-02-05T15:19:00+00:00",
        "actual": null,
        "delay": 4
      },
      "flight": { "iata": "AI101" },
      "aircraft": { "registration": "VT-XYZ", "iata": "B788" }
    }
  ]
}
```

```
Observer check:
  stored estimated_arrival  = 15:15
  new    estimated_arrival  = 15:19
  delta = 4 min
  4 < 30 → below LOW threshold → no event
  update stored leg.delay_minutes = 4
```

---

## Severity Thresholds (Observer Decision Table)

| delay_minutes | severity | Event emitted |
|--------------|----------|--------------|
| 0 – 29 | — | none |
| 30 – 119 | LOW | FlightDisrupted (LOW) |
| 120 – 239 | MEDIUM | FlightDisrupted (MEDIUM) |
| 240+ | HIGH | FlightDisrupted (HIGH) |
| status = cancelled | CRITICAL | FlightDisrupted (CRITICAL) |
| status = diverted | CRITICAL | FlightDisrupted (CRITICAL) |
| status = landed | — | LegCompleted |

---

## What Disruption Handler Does With Each Severity

| Severity | FTL Impact Check | Action |
|----------|-----------------|--------|
| LOW | Recalculate projected_fdp_end | Log only, no roster change unless breach detected |
| MEDIUM | Recalculate + check next duty rest | Alert controller if rest violation risk found |
| HIGH | Full impact check on all crew | Find replacement candidates, present to controller |
| CRITICAL | Full impact check + cascade check | Run full disruption pipeline immediately |
