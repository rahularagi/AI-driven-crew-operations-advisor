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
