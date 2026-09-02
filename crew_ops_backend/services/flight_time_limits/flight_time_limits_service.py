"""
Service 4 — Flight Time Limits Service

Subscribes to : LegCompletedEvent, RosterModifiedEvent
Publishes      : FlightTimeLimitsAlertEvent
Scheduled      : run_proactive_alert_scan() every 15 min, run_midnight_recalculation() every midnight

Never imports or calls any other service directly.
Registered at startup:
    event_bus.subscribe(LegCompletedEvent, ftl_service.on_leg_completed)
    event_bus.subscribe(RosterModifiedEvent, ftl_service.on_roster_modified)
"""

from crew_ops_backend.clients.ftl_client import get_crew_duty_state, update_crew_duty_state, get_all_crew_duty_states
from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.models.events import LegCompletedEvent, RosterModifiedEvent, FlightTimeLimitsAlertEvent
from crew_ops_backend.services.event_bus import event_bus
from datetime import datetime, timezone, timedelta


_FDP_ALERT_BUFFER_HOURS = 2.0
_CUMULATIVE_HOURS_WARNING = 90.0
_WEEKLY_REST_OVERDUE_DAYS = 6


class FlightTimeLimitsService:

    def on_leg_completed(self, event: LegCompletedEvent) -> None:
        """
        Subscribed to LegCompletedEvent via event bus.
        Updates FTL state for each crew member after a leg lands.
        """
        from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
        leg = get_flight_leg(event.leg_id)
        leg_hours = 0.0
        if leg:
            leg_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600

        for crew_id in event.crew:
            ftl = get_crew_duty_state(crew_id)
            if not ftl:
                continue
            crew = get_crew_member(crew_id)
            at_home = bool(crew and event.destination == crew.home_base)

            ftl.flight_hours_current_duty += leg_hours
            ftl.flight_hours_28_day       += leg_hours
            ftl.duty_hours_7_day          += leg_hours
            ftl.duty_hours_28_day         += leg_hours
            ftl.sectors_current_duty      += 1
            ftl.current_airport            = event.destination
            ftl.at_home_base               = at_home
            ftl.rest_start_time            = datetime.now(timezone.utc) + timedelta(minutes=30)
            ftl.rest_type                  = "HOME_REST" if at_home else "HOTEL_REST"
            if not at_home:
                ftl.earliest_checkout = ftl.rest_start_time + timedelta(hours=10)
            else:
                ftl.earliest_checkout = None
            ftl.status       = "RESTING"
            ftl.last_updated = datetime.now(timezone.utc)
            update_crew_duty_state(ftl)

    def on_roster_modified(self, event: RosterModifiedEvent) -> None:
        """
        Subscribed to RosterModifiedEvent via event bus.
        Registered at startup: event_bus.subscribe(RosterModifiedEvent, ftl_service.on_roster_modified)
        """
        if event.removed_crew_id:
            ftl = get_crew_duty_state(event.removed_crew_id)
            if ftl:
                ftl.status = "UNAVAILABLE"
                ftl.last_updated = datetime.now(timezone.utc)
                update_crew_duty_state(ftl)

        if event.added_crew_id:
            ftl = get_crew_duty_state(event.added_crew_id)
            if ftl:
                ftl.duty_start_time = datetime.now(timezone.utc)
                ftl.status = "AVAILABLE"
                ftl.last_updated = datetime.now(timezone.utc)
                update_crew_duty_state(ftl)

    def run_proactive_alert_scan(self) -> None:
        """Scheduled every 15 min. Publishes FlightTimeLimitsAlertEvent for each breach found."""
        now = datetime.now(timezone.utc)
        for ftl in get_all_crew_duty_states():
            if ftl.status == "AVAILABLE" and ftl.projected_duty_period_end:
                remaining = (ftl.projected_duty_period_end - now).total_seconds() / 3600
                if 0 < remaining < _FDP_ALERT_BUFFER_HOURS:
                    event_bus.publish(self._make_alert(
                        ftl.crew_id, "DUTY_PERIOD_APPROACHING",
                        f"Duty period limit in {remaining:.1f}h",
                    ))

            if ftl.flight_hours_28_day > _CUMULATIVE_HOURS_WARNING:
                event_bus.publish(self._make_alert(
                    ftl.crew_id, "CUMULATIVE_HOURS_WARNING",
                    f"{ftl.flight_hours_28_day:.1f}h of 100h 28-day cap used",
                ))

            if ftl.last_weekly_rest_end:
                days_since = (now - ftl.last_weekly_rest_end).days
                if days_since >= _WEEKLY_REST_OVERDUE_DAYS:
                    event_bus.publish(self._make_alert(
                        ftl.crew_id, "WEEKLY_REST_OVERDUE",
                        f"No 36h rest block in {days_since} days",
                    ))

    def run_midnight_recalculation(self) -> None:
        """Scheduled every midnight. Resets per-duty counters for crew who completed rest."""
        now = datetime.now(timezone.utc)
        for ftl in get_all_crew_duty_states():
            if ftl.status != "RESTING":
                continue
            # If earliest_checkout has passed, crew is now available
            if ftl.earliest_checkout and now >= ftl.earliest_checkout:
                ftl.status                    = "AVAILABLE"
                ftl.last_rest_end_time        = ftl.earliest_checkout
                ftl.flight_hours_current_duty = 0.0
                ftl.sectors_current_duty      = 0
                ftl.duty_start_time           = None
                ftl.projected_duty_period_end = None
                ftl.last_updated              = now
                update_crew_duty_state(ftl)

    def _make_alert(self, crew_id: str, alert_type: str, message: str) -> FlightTimeLimitsAlertEvent:
        return FlightTimeLimitsAlertEvent(
            crew_id=crew_id,
            alert_type=alert_type,
            message=message,
            detected_at=datetime.now(timezone.utc),
        )
