from sqlalchemy.orm import Session
from sqlalchemy import text
from crew_ops_backend.models.crew_reserve import CrewReserveSchedule


def get_all_reserve_schedules(session: Session) -> list[CrewReserveSchedule]:
    rows = session.execute(text("SELECT * FROM crew_reserve_schedule ORDER BY date")).mappings().all()
    return [CrewReserveSchedule(**dict(row)) for row in rows]


def get_reserve_schedules_by_date_and_airport(
    session: Session, date: str, base_airport: str
) -> list[CrewReserveSchedule]:
    rows = session.execute(
        text("""
            SELECT * FROM crew_reserve_schedule
            WHERE date = :date AND base_airport = :base_airport
            ORDER BY standby_start
        """),
        {"date": date, "base_airport": base_airport}
    ).mappings().all()
    return [CrewReserveSchedule(**dict(row)) for row in rows]


def insert_reserve_schedule(session: Session, reserve: CrewReserveSchedule) -> None:
    session.execute(text("""
        INSERT INTO crew_reserve_schedule (
            reserve_id, crew_id, date, standby_start, standby_end,
            base_airport, callable_within, status, activated_for
        ) VALUES (
            :reserve_id, :crew_id, :date, :standby_start, :standby_end,
            :base_airport, :callable_within, :status, :activated_for
        )
        ON CONFLICT (reserve_id) DO NOTHING
    """), reserve.model_dump(exclude={"created_at"}))
    session.commit()
