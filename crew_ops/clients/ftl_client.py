"""
FTL State Client — API 6 (internally managed)

FTL state is always read from the database.
It is never fetched from an external API — your system owns and calculates it.
"""

from typing import Optional
from crew_ops.db.database import SessionLocal
from crew_ops.models.crew_ftl_state import CrewFTLState
from crew_ops.db.repositories import ftl_repository


def get_all_ftl_states() -> list[CrewFTLState]:
    with SessionLocal() as session:
        return ftl_repository.get_all_ftl_states(session)


def get_ftl_state(crew_id: str) -> Optional[CrewFTLState]:
    with SessionLocal() as session:
        return ftl_repository.get_ftl_state_by_crew_id(session, crew_id)


def update_ftl_state(ftl_state: CrewFTLState) -> None:
    with SessionLocal() as session:
        ftl_repository.upsert_ftl_state(session, ftl_state)
