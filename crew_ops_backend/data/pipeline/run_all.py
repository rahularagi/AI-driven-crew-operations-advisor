"""
Initial data pipeline — loads all mock data into PostgreSQL on first startup.
Run this once after docker-compose up.

Usage:
    python -m crew_ops.data.pipeline.run_all
"""

from crew_ops_backend.db.database import SessionLocal, check_database_connection
from crew_ops_backend.data.mock.crew import MOCK_CREW_MEMBERS
from crew_ops_backend.data.mock.licenses import MOCK_CREW_LICENSES
from crew_ops_backend.data.mock.leave_records import MOCK_CREW_LEAVE_RECORDS
from crew_ops_backend.data.mock.reserve_schedule import MOCK_RESERVE_SCHEDULE
from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.models.crew_license import CrewLicense
from crew_ops_backend.models.crew_leave import CrewLeaveRecord
from crew_ops_backend.models.crew_reserve import CrewReserveSchedule
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.db.repositories import (
    crew_repository,
    license_repository,
    leave_repository,
    reserve_repository,
    leg_repository,
    ftl_repository,
)

# Import seed data from existing seed files (reuse what is already written)
from crew_ops_backend.data.seed_legs import LEGS
from crew_ops_backend.data.seed_ftl import FTL_STATES


def load_crew_members(session) -> int:
    for raw in MOCK_CREW_MEMBERS:
        crew_repository.upsert_crew_member(session, CrewMember(**raw))
    return len(MOCK_CREW_MEMBERS)


def load_licenses(session) -> int:
    for raw in MOCK_CREW_LICENSES:
        license_repository.upsert_crew_license(session, CrewLicense(**raw))
    return len(MOCK_CREW_LICENSES)


def load_ftl_states(session) -> int:
    for raw in FTL_STATES:
        ftl_repository.upsert_ftl_state(session, CrewFlightTimeLimitsState(**raw))
    return len(FTL_STATES)


def load_leave_records(session) -> int:
    for raw in MOCK_CREW_LEAVE_RECORDS:
        leave_repository.insert_leave_record(session, CrewLeaveRecord(**raw))
    return len(MOCK_CREW_LEAVE_RECORDS)


def load_reserve_schedule(session) -> int:
    for raw in MOCK_RESERVE_SCHEDULE:
        reserve_repository.insert_reserve_schedule(session, CrewReserveSchedule(**raw))
    return len(MOCK_RESERVE_SCHEDULE)


def load_flight_legs(session) -> int:
    for raw in LEGS:
        # Remove internal scenario field before creating model
        leg_data = {key: value for key, value in raw.items() if not key.startswith("_")}
        leg_repository.upsert_flight_leg(session, FlightLeg(**leg_data))
    return len(LEGS)


def run_all_pipelines():
    print("Checking database connection...")
    if not check_database_connection():
        print("ERROR: Cannot connect to database. Is PostgreSQL running?")
        print("Run: docker-compose up -d")
        return

    print("Database connected.\n")

    with SessionLocal() as session:
        print(f"Loading crew members...    {load_crew_members(session)} records")
        print(f"Loading licenses...        {load_licenses(session)} records")
        print(f"Loading FTL states...      {load_ftl_states(session)} records")
        print(f"Loading leave records...   {load_leave_records(session)} records")
        print(f"Loading reserve schedule...{load_reserve_schedule(session)} records")
        print(f"Loading flight legs...     {load_flight_legs(session)} records")

    print("\nAll mock data loaded successfully.")


if __name__ == "__main__":
    run_all_pipelines()
