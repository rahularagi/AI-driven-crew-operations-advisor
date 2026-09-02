from sqlalchemy.orm import Session
from sqlalchemy import text
from crew_ops_backend.models.crew_leave import CrewLeaveRecord


def get_all_leave_records(session: Session) -> list[CrewLeaveRecord]:
    rows = session.execute(text("SELECT * FROM crew_leave_records ORDER BY start_date")).mappings().all()
    return [CrewLeaveRecord(**dict(row)) for row in rows]


def get_leave_records_for_crew_member(session: Session, crew_id: str) -> list[CrewLeaveRecord]:
    rows = session.execute(
        text("SELECT * FROM crew_leave_records WHERE crew_id = :crew_id ORDER BY start_date"),
        {"crew_id": crew_id}
    ).mappings().all()
    return [CrewLeaveRecord(**dict(row)) for row in rows]


def insert_leave_record(session: Session, leave_record: CrewLeaveRecord) -> None:
    session.execute(text("""
        INSERT INTO crew_leave_records (crew_id, leave_type, start_date, end_date)
        VALUES (:crew_id, :leave_type, :start_date, :end_date)
    """), leave_record.model_dump(exclude={"created_at"}))
    session.commit()
