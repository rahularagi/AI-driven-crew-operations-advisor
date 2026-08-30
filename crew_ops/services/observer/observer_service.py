"""
Service 2 — Observer

Watches flight legs via the flight status client.
Detects delays, cancellations, diversions, and landings.

Triggers:
  - Live today view : get_todays_active_legs() + poll() — automatic polling loop
  - Manager view    : get_legs(target_date) or get_legs(offset=1) — read-only plan view

Publishes: FlightDisruptedEvent, LegCompletedEvent
"""

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
            severity = self._delay_severity(delay)
            if severity:
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

        Examples:
          get_legs(date(2024, 3, 5))  → specific date
          get_legs(offset=1)          → tomorrow
          get_legs(offset=2)          → day after tomorrow
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
