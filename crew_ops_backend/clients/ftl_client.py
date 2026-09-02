"""
Crew Duty State Client (internally managed)

Tracks each crew member's live duty/rest state — hours flown, rest clock, rolling counters.
Always read from and written to the internal database. No external API.
"""

from typing import Optional
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.db.repositories import ftl_repository


def get_all_crew_duty_states() -> list[CrewFlightTimeLimitsState]:
    with SessionLocal() as session:
        return ftl_repository.get_all_ftl_states(session)


def get_crew_duty_state(crew_id: str) -> Optional[CrewFlightTimeLimitsState]:
    with SessionLocal() as session:
        return ftl_repository.get_ftl_state_by_crew_id(session, crew_id)


def update_crew_duty_state(state: CrewFlightTimeLimitsState) -> None:
    with SessionLocal() as session:
        ftl_repository.upsert_ftl_state(session, state)
