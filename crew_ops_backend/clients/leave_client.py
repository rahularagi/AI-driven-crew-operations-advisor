"""
Leave Client (internally managed)

Leave records are entered by the manager via POST /crew/{crew_id}/unavailable
and stored in the database. This client reads and writes from that table.
No external API involved.
"""

from datetime import date, datetime, timezone
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.models.crew_leave import CrewLeaveRecord
from crew_ops_backend.models.events import CrewDisruptedEvent
from crew_ops_backend.db.repositories import leave_repository, roster_repository
from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.services.event_bus import event_bus


def get_all_leave_records() -> list[CrewLeaveRecord]:
    with SessionLocal() as session:
        return leave_repository.get_all_leave_records(session)


def get_leave_records_for_crew(crew_id: str) -> list[CrewLeaveRecord]:
    with SessionLocal() as session:
        return leave_repository.get_leave_records_for_crew_member(session, crew_id)


def add_leave_record(leave_record: CrewLeaveRecord) -> None:
    with SessionLocal() as session:
        leave_repository.insert_leave_record(session, leave_record)

    # Publish CrewDisruptedEvent for every assigned leg that falls within the leave window
    with SessionLocal() as session:
        assignments = roster_repository.get_assignments_for_crew_in_range(
            session, leave_record.crew_id, leave_record.start_date, leave_record.end_date
        )

    if not assignments:
        return

    crew = get_crew_member(leave_record.crew_id)
    crew_name = crew.full_name if crew else leave_record.crew_id
    today = date.today()

    for assignment in assignments:
        days_until = (assignment["scheduled_departure"].date() - today).days
        severity = "CRITICAL" if days_until < 1 else "HIGH" if days_until <= 2 else "MEDIUM" if days_until <= 7 else "LOW"
        event_bus.publish(CrewDisruptedEvent(
            crew_id=leave_record.crew_id,
            crew_name=crew_name,
            leg_id=assignment["leg_id"],
            reason="LEAVE_ADDED",
            days_until_departure=days_until,
            severity=severity,
            source="OPS_DESK",
            detected_at=datetime.now(timezone.utc),
        ))
