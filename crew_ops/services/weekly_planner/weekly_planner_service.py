"""
Service 1 — Weekly Planner

Job A: RosterPlanner   — builds crew roster for a given date window
  Scheduled trigger : build() — Sunday night, uses configured planning horizon
  Manual trigger    : build(requested_by="manager_01") — same as scheduled, on demand
  Date range        : build(start, end, requested_by) — manager specifies exact window
  Publishes         : CrewDisruptedEvent (if validation finds issues after build)

Job B: DailyValidator  — re-checks all future planned weeks against current reality
  Scheduled trigger : validate() — 3AM daily
  Manual trigger    : validate(requested_by) — manager forces a re-check on demand
  Subscribes to     : RosterModifiedEvent → on_roster_modified()
  Publishes         : CrewDisruptedEvent per affected leg
"""

from crew_ops.clients.crew_profile_client import get_all_crew_members
from crew_ops.clients.flight_schedule_client import get_all_scheduled_legs
from crew_ops.clients.ftl_client import get_all_ftl_states
from crew_ops.models.events import CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.services.event_bus import event_bus
from crew_ops.config.settings import settings
from datetime import date, timedelta


class RosterPlanner:
    """
    Single build() method handles all trigger types.

    - No arguments         → scheduler call, uses today + settings.roster_planning_weeks
    - requested_by only    → manual full rebuild, same window as scheduler
    - start + end + requested_by → manager-specified date range

    Examples:
      planner.build()                                                    # scheduler
      planner.build(requested_by="manager_01")                          # manual full rebuild
      planner.build(date(2024,3,1), date(2024,3,14), "manager_01")      # specific window
    """

    def build(
        self,
        start: date | None = None,
        end: date | None = None,
        requested_by: str = "SCHEDULER",
    ) -> None:
        resolved_start = start or date.today()
        resolved_end = end or (resolved_start + timedelta(weeks=settings.roster_planning_weeks))

        if resolved_end < resolved_start:
            raise ValueError(f"end date {resolved_end} cannot be before start date {resolved_start}")

        self._run_build(start=resolved_start, end=resolved_end, triggered_by=requested_by)

    def _run_build(self, start: date, end: date, triggered_by: str) -> None:
        all_legs = get_all_scheduled_legs()
        legs = [leg for leg in all_legs if start <= leg.scheduled_departure.date() <= end]
        crew = get_all_crew_members()
        ftl_states = get_all_ftl_states()
        # TODO: implement 3-pass planning algorithm over legs in [start, end]
        # On any validation failure → event_bus.publish(CrewDisruptedEvent(...))
        raise NotImplementedError


class DailyValidator:

    def validate(self, requested_by: str = "SCHEDULER") -> None:
        """
        Scheduled trigger    : validate()
        Manual trigger       : validate(requested_by="manager_01")
        """
        self._run_validation(triggered_by=requested_by)

    def on_roster_modified(self, event: RosterModifiedEvent) -> None:
        """
        Subscribed to RosterModifiedEvent via event bus.
        Re-validates future weeks for crew affected by the roster change.
        Registered at startup: event_bus.subscribe(RosterModifiedEvent, daily_validator.on_roster_modified)
        """
        self._run_validation(triggered_by="ROSTER_MODIFIED", crew_id=event.added_crew_id)

    def _run_validation(self, triggered_by: str, crew_id: str | None = None) -> None:
        crew = get_all_crew_members()
        ftl_states = get_all_ftl_states()
        # TODO: iterate future roster entries (filtered by crew_id if provided)
        # re-run legality check, publish CrewDisruptedEvent on failure:
        # event_bus.publish(CrewDisruptedEvent(...))
