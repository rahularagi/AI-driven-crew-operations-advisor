"""
Service 2 — Observer

Watches flight legs via the flight status client.
Detects delays, cancellations, and landings.

Publishes: FlightDisruptedEvent, LegCompletedEvent
"""

from datetime import date, datetime, timedelta, timezone
from dateutil.parser import parse as parse_dt

from crew_ops_backend.clients.flight_status_client import get_next_live_status_poll, reset_poll_index_for_leg
from crew_ops_backend.clients.flight_schedule_client import get_all_scheduled_legs
from crew_ops_backend.models.events import FlightDisruptedEvent, LegCompletedEvent
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.services.event_bus import event_bus


# Thresholds in ascending order — first match wins
_SEVERITY_THRESHOLDS = [
    (240, "HIGH"),
    (120, "MEDIUM"),
    (30,  "LOW"),
]


class FlightObserver:

    def get_legs_for_range(self, start: date, end: date) -> list[FlightLeg]:
        """Returns scheduled legs for a date range. Used by conversation layer."""
        all_legs = get_all_scheduled_legs()
        return [leg for leg in all_legs if start <= leg.scheduled_departure.date() <= end]

    # ─── Live today (automatic) ───────────────────────────────────────────────

    def get_todays_active_legs(self) -> list[FlightLeg]:
        """Returns all of today's legs. Used by the automated polling loop and Flight Monitor."""
        return self.get_legs(date.today())

    def poll(self, leg: FlightLeg) -> None:
        """
        Poll live status for one leg and publish the resulting event to the bus.
        Called by the scheduler every 5 minutes per active leg.
        """
        result = get_next_live_status_poll(leg.leg_id)
        if not result:
            return

        status = result.get("flight_status")

        if status == "landed":
            reset_poll_index_for_leg(leg.leg_id)
            raw_arrival = result["arrival"].get("actual")
            actual_arrival = _parse_dt(raw_arrival) if raw_arrival else datetime.now(timezone.utc)
            event_bus.publish(LegCompletedEvent(
                leg_id=leg.leg_id,
                actual_arrival=actual_arrival,
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
            severity = self._delay_severity(delay)
            if severity:
                event_bus.publish(self._build_disruption_event(leg, result, "DELAY", severity))

    def poll_all_today(self) -> None:
        """Polls all of today's active legs. Called by the scheduler every 5 minutes."""
        for leg in self.get_todays_active_legs():
            self.poll(leg)

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
        raw_actual = poll["departure"].get("actual")
        return FlightDisruptedEvent(
            leg_id=leg.leg_id,
            flight_number=leg.flight_number,
            origin=leg.origin_iata,
            destination=leg.destination_iata,
            disruption_type=disruption_type,
            severity=severity,
            scheduled_departure=leg.scheduled_departure,
            actual_departure=_parse_dt(raw_actual) if raw_actual else None,
            delay_minutes=poll["departure"].get("delay"),
            assigned_crew=leg.assigned_crew,
            detected_at=datetime.now(timezone.utc),
        )


def _parse_dt(value: str | datetime) -> datetime:
    """Parse ISO string to timezone-aware datetime. No-op if already datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return parse_dt(value)
