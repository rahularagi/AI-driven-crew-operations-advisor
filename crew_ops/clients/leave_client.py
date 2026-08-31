"""
Leave Client (internally managed)

Leave records are entered by the manager via POST /crew/{crew_id}/unavailable
and stored in the database. This client reads and writes from that table.
No external API involved.
"""

from crew_ops.db.database import SessionLocal
from crew_ops.models.crew_leave import CrewLeaveRecord
from crew_ops.db.repositories import leave_repository


def get_all_leave_records() -> list[CrewLeaveRecord]:
    with SessionLocal() as session:
        return leave_repository.get_all_leave_records(session)


def get_leave_records_for_crew(crew_id: str) -> list[CrewLeaveRecord]:
    with SessionLocal() as session:
        return leave_repository.get_leave_records_for_crew_member(session, crew_id)


def add_leave_record(leave_record: CrewLeaveRecord) -> None:
    with SessionLocal() as session:
        leave_repository.insert_leave_record(session, leave_record)
