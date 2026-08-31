"""
Service 3 — Disruption Handler

Subscribes to : FlightDisruptedEvent, CrewDisruptedEvent
Publishes      : RosterModifiedEvent

Never imports or calls any other service directly.
Registered at startup:
    event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
    event_bus.subscribe(CrewDisruptedEvent, disruption_handler.handle_crew_disrupted)
"""

from crew_ops.clients.crew_profile_client import get_all_crew_members
from crew_ops.clients.ftl_client import get_all_crew_duty_states, get_crew_duty_state
from crew_ops.models.crew_member import CrewMember
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops.models.events import FlightDisruptedEvent, CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.services.event_bus import event_bus
from datetime import datetime, timezone


_WEIGHT_LEGAL = 40
_WEIGHT_SAME_AIRPORT = 30
_WEIGHT_LOW_FATIGUE = 20
_WEIGHT_LOW_COST = 10


class DisruptionHandler:

    def handle_flight_disrupted(self, event: FlightDisruptedEvent) -> None:
        """
        Subscribed to FlightDisruptedEvent via event bus.
        Registered at startup: event_bus.subscribe(FlightDisruptedEvent, disruption_handler.handle_flight_disrupted)
        """
        candidates = self._find_candidates(role="PILOT", airport=event.origin)
        ranked = self._rank_candidates(candidates, airport=event.origin)
        # TODO: present to controller, await confirmation
        # On approval → event_bus.publish(RosterModifiedEvent(...))

    def handle_crew_disrupted(self, event: CrewDisruptedEvent) -> None:
        """
        Subscribed to CrewDisruptedEvent via event bus.
        Registered at startup: event_bus.subscribe(CrewDisruptedEvent, disruption_handler.handle_crew_disrupted)
        """
        airport = self._get_crew_airport(event.crew_id)
        role = self._get_crew_role(event.crew_id)
        candidates = self._find_candidates(role=role, airport=airport)
        ranked = self._rank_candidates(candidates, airport=airport)
        # TODO: present to controller, await confirmation
        # On approval → event_bus.publish(RosterModifiedEvent(...))

    # ─── Internal pipeline steps ──────────────────────────────────────────────

    def _find_candidates(self, role: str, airport: str) -> list[CrewMember]:
        all_crew = get_all_crew_members()
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}
        return [
            crew for crew in all_crew
            if crew.role == role
            and crew.employment_status == "ACTIVE"
            and ftl_states.get(crew.crew_id, CrewFlightTimeLimitsState(
                crew_id=crew.crew_id, role=crew.role, home_base=crew.home_base, current_airport=crew.home_base
            )).status == "AVAILABLE"
        ]

    def _rank_candidates(self, candidates: list[CrewMember], airport: str) -> list[dict]:
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}
        scored = []
        for crew in candidates:
            ftl = ftl_states.get(crew.crew_id)
            score = (
                _WEIGHT_LEGAL
                + (_WEIGHT_SAME_AIRPORT if crew.home_base == airport else 0)
                + int(_WEIGHT_LOW_FATIGUE * (1 - self._fatigue_score(ftl) / 100))
            )
            scored.append({"crew": crew, "score": score, "fatigue": self._fatigue_score(ftl)})
        return sorted(scored, key=lambda x: x["score"], reverse=True)

    def _fatigue_score(self, ftl: CrewFlightTimeLimitsState | None) -> float:
        if not ftl:
            return 50.0
        score = min(ftl.flight_hours_current_duty * 5, 55)
        score += min(ftl.consecutive_duty_days * 10, 20)
        score += min(ftl.flight_hours_28_day / 5, 25)
        return min(score, 100.0)

    def _get_crew_role(self, crew_id: str) -> str:
        ftl = get_crew_duty_state(crew_id)
        return ftl.role if ftl else "PILOT"

    def _get_crew_airport(self, crew_id: str) -> str:
        ftl = get_crew_duty_state(crew_id)
        return ftl.current_airport if ftl else ""
