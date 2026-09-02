"""
Reserve Schedule Client — API 7 (internally managed)

Reserve schedule is always read from the database.
"""

from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.crew_reserve import CrewReserveSchedule
from crew_ops_backend.db.repositories import reserve_repository


def get_all_reserve_schedules() -> list[CrewReserveSchedule]:
    with SessionLocal() as session:
        return reserve_repository.get_all_reserve_schedules(session)


def get_reserve_schedules_for_date_and_airport(date: str, base_airport: str) -> list[CrewReserveSchedule]:
    with SessionLocal() as session:
        return reserve_repository.get_reserve_schedules_by_date_and_airport(session, date, base_airport)
