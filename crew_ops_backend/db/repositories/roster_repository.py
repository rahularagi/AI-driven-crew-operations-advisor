from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import text


def upsert_roster_leg(session: Session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO roster_leg (leg_id, plan_start, plan_end, status, triggered_by)
        VALUES (:leg_id, :plan_start, :plan_end, :status, :triggered_by)
        ON CONFLICT (leg_id, plan_start) DO UPDATE SET
            status       = EXCLUDED.status,
            triggered_by = EXCLUDED.triggered_by,
            updated_at   = NOW()
    """), data)


def upsert_roster_crew_assignment(session: Session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO roster_crew_assignment (leg_id, crew_id, status, assigned_by)
        VALUES (:leg_id, :crew_id, :status, :assigned_by)
        ON CONFLICT (leg_id, crew_id) DO UPDATE SET
            status      = EXCLUDED.status,
            assigned_by = EXCLUDED.assigned_by,
            assigned_at = NOW()
    """), data)


def replace_roster_crew_assignment(session: Session, leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> None:
    session.execute(text("""
        UPDATE roster_crew_assignment
        SET status = 'REPLACED', replaced_by = :new_crew_id, replaced_at = NOW()
        WHERE leg_id = :leg_id AND crew_id = :old_crew_id
    """), {"leg_id": leg_id, "old_crew_id": old_crew_id, "new_crew_id": new_crew_id})
    session.execute(text("""
        INSERT INTO roster_crew_assignment (leg_id, crew_id, status, assigned_by)
        VALUES (:leg_id, :crew_id, 'CONFIRMED', :assigned_by)
        ON CONFLICT (leg_id, crew_id) DO UPDATE SET
            status = 'CONFIRMED', assigned_by = EXCLUDED.assigned_by, assigned_at = NOW()
    """), {"leg_id": leg_id, "crew_id": new_crew_id, "assigned_by": requested_by})
    # Stamp roster_leg so it reflects the latest crew change
    session.execute(text("""
        UPDATE roster_leg
        SET triggered_by = :triggered_by, updated_at = NOW()
        WHERE leg_id = :leg_id
    """), {"leg_id": leg_id, "triggered_by": requested_by})


def approve_roster_leg(session: Session, leg_id: str, approved_by: str) -> None:
    session.execute(text("""
        UPDATE roster_leg SET status = 'PUBLISHED', updated_at = NOW()
        WHERE leg_id = :leg_id
    """), {"leg_id": leg_id})
    session.execute(text("""
        UPDATE roster_crew_assignment SET status = 'CONFIRMED', assigned_by = :approved_by
        WHERE leg_id = :leg_id AND status = 'DRAFT'
    """), {"leg_id": leg_id, "approved_by": approved_by})


def get_future_assignments(
    session: Session, from_date: date, to_date: date, crew_id: str | None = None
) -> list[dict]:
    query = """
        SELECT rca.leg_id, rca.crew_id, rca.status
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE fl.scheduled_departure::date BETWEEN :from_date AND :to_date
          AND rca.status IN ('DRAFT', 'CONFIRMED')
    """
    params: dict = {"from_date": from_date, "to_date": to_date}
    if crew_id:
        query += " AND rca.crew_id = :crew_id"
        params["crew_id"] = crew_id
    rows = session.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


def get_roster_for_date_range(session: Session, start: date, end: date) -> list[dict]:
    rows = session.execute(text("""
        SELECT rca.leg_id, rca.crew_id, rca.status, rca.assigned_by,
               fl.scheduled_departure, fl.scheduled_arrival, fl.origin_iata, fl.destination_iata,
               fl.aircraft_type, fl.flight_number
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE fl.scheduled_departure::date BETWEEN :start AND :end
        ORDER BY fl.scheduled_departure
    """), {"start": start, "end": end}).mappings().all()
    return [dict(row) for row in rows]


def get_assignment_for_crew(session: Session, leg_id: str, crew_id: str) -> dict | None:
    row = session.execute(text("""
        SELECT rca.leg_id, rca.crew_id, rca.status, cm.role
        FROM roster_crew_assignment rca
        JOIN crew_members cm ON cm.crew_id = rca.crew_id
        WHERE rca.leg_id = :leg_id AND rca.crew_id = :crew_id
    """), {"leg_id": leg_id, "crew_id": crew_id}).mappings().first()
    return dict(row) if row else None


def get_assignments_for_crew_in_range(session: Session, crew_id: str, from_date: date, to_date: date) -> list[dict]:
    rows = session.execute(text("""
        SELECT rca.leg_id, fl.scheduled_departure
        FROM roster_crew_assignment rca
        JOIN flight_legs fl ON fl.leg_id = rca.leg_id
        WHERE rca.crew_id = :crew_id
          AND fl.scheduled_departure::date BETWEEN :from_date AND :to_date
          AND rca.status IN ('DRAFT', 'CONFIRMED')
    """), {"crew_id": crew_id, "from_date": from_date, "to_date": to_date}).mappings().all()
    return [dict(row) for row in rows]


def invalidate_assignment(session: Session, leg_id: str, crew_id: str, reason: str) -> None:
    """Marks one crew member's assignment as INVALIDATED. Used by Disruption Handler."""
    session.execute(text("""
        UPDATE roster_crew_assignment
        SET status = 'INVALIDATED', invalidation_reason = :reason
        WHERE leg_id = :leg_id AND crew_id = :crew_id
    """), {"leg_id": leg_id, "crew_id": crew_id, "reason": reason})


def invalidate_roster_leg(session: Session, leg_id: str, reason: str) -> None:
    """
    Marks the roster_leg as INVALIDATED and invalidates all its crew assignments.
    Used when a flight is cancelled — both the leg plan and all crew slots are cleared.
    """
    session.execute(text("""
        UPDATE roster_leg
        SET status = 'INVALIDATED', updated_at = NOW(), triggered_by = :reason
        WHERE leg_id = :leg_id
    """), {"leg_id": leg_id, "reason": reason})
    session.execute(text("""
        UPDATE roster_crew_assignment
        SET status = 'INVALIDATED', invalidation_reason = :reason
        WHERE leg_id = :leg_id AND status IN ('DRAFT', 'CONFIRMED')
    """), {"leg_id": leg_id, "reason": reason})
