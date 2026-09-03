from sqlalchemy.orm import Session
from sqlalchemy import text


def pending_proposal_exists(session: Session, leg_id: str, removed_crew_id: str) -> bool:
    """Returns True if an active (non-expired) proposal already exists for this leg+crew.
    Blocks duplicate creation from repeated observer polls on the same disruption.
    """
    row = session.execute(text("""
        SELECT 1 FROM disruption_proposals
        WHERE leg_id = :leg_id AND removed_crew_id = :removed_crew_id
          AND status NOT IN ('EXPIRED')
        LIMIT 1
    """), {"leg_id": leg_id, "removed_crew_id": removed_crew_id}).first()
    return row is not None


def insert_proposal(session: Session, data: dict) -> None:
    session.execute(text("""
        INSERT INTO disruption_proposals (
            proposal_id, leg_id, disruption_type, disruption_reason,
            removed_crew_id, proposed_crew_id, proposal_score,
            status, severity, source
        ) VALUES (
            :proposal_id, :leg_id, :disruption_type, :disruption_reason,
            :removed_crew_id, :proposed_crew_id, :proposal_score,
            :status, :severity, :source
        )
    """), data)


def get_pending_proposals(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT dp.*, fl.scheduled_departure, fl.scheduled_arrival, fl.origin_iata, fl.destination_iata,
               fl.flight_number, fl.aircraft_type
        FROM disruption_proposals dp
        JOIN flight_legs fl ON fl.leg_id = dp.leg_id
        WHERE dp.status = 'PENDING'
        ORDER BY
            CASE dp.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                ELSE 4
            END,
            dp.proposed_at ASC
    """)).mappings().all()
    return [dict(row) for row in rows]


def accept_proposal(session: Session, proposal_id: str, decided_by: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'ACCEPTED', decided_at = NOW(), decided_by = :decided_by
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by}).mappings().first()
    return dict(row) if row else {}


def reject_proposal(session: Session, proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    row = session.execute(text("""
        UPDATE disruption_proposals
        SET status = 'REJECTED', decided_at = NOW(), decided_by = :decided_by,
            rejection_reason = :rejection_reason
        WHERE proposal_id = :proposal_id
        RETURNING leg_id, removed_crew_id, proposed_crew_id
    """), {"proposal_id": proposal_id, "decided_by": decided_by, "rejection_reason": rejection_reason}).mappings().first()
    return dict(row) if row else {}


def get_next_candidate(session: Session, leg_id: str, removed_crew_id: str) -> dict | None:
    """Returns the highest scored candidate not already proposed for this leg + removed crew."""
    row = session.execute(text("""
        SELECT proposed_crew_id, proposal_score
        FROM disruption_proposals
        WHERE leg_id = :leg_id
          AND removed_crew_id = :removed_crew_id
          AND status = 'REJECTED'
          AND proposed_crew_id IS NOT NULL
        ORDER BY proposal_score DESC
        LIMIT 1
    """), {"leg_id": leg_id, "removed_crew_id": removed_crew_id}).mappings().first()
    return dict(row) if row else None


def get_already_proposed_crew(session: Session, leg_id: str, removed_crew_id: str) -> set[str]:
    """Returns all crew_ids already proposed (and rejected) for this leg + removed crew."""
    rows = session.execute(text("""
        SELECT proposed_crew_id FROM disruption_proposals
        WHERE leg_id = :leg_id
          AND removed_crew_id = :removed_crew_id
          AND proposed_crew_id IS NOT NULL
    """), {"leg_id": leg_id, "removed_crew_id": removed_crew_id}).mappings().all()
    return {row["proposed_crew_id"] for row in rows}


def get_unpushed_proposals(session: Session) -> list[dict]:
    """Returns PENDING proposals not yet pushed to the controller (pushed_at IS NULL)."""
    rows = session.execute(text("""
        SELECT dp.*, fl.scheduled_departure, fl.scheduled_arrival, fl.origin_iata, fl.destination_iata, fl.flight_number
        FROM disruption_proposals dp
        JOIN flight_legs fl ON fl.leg_id = dp.leg_id
        WHERE dp.status = 'PENDING' AND dp.pushed_at IS NULL
        ORDER BY
            CASE dp.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                ELSE 4
            END
    """)).mappings().all()
    return [dict(row) for row in rows]


def mark_proposal_pushed(session: Session, proposal_id: str) -> None:
    session.execute(text("""
        UPDATE disruption_proposals SET pushed_at = NOW()
        WHERE proposal_id = :proposal_id
    """), {"proposal_id": proposal_id})


def expire_stale_proposals(session: Session) -> int:
    result = session.execute(text("""
        UPDATE disruption_proposals dp
        SET status = 'EXPIRED'
        FROM flight_legs fl
        WHERE dp.leg_id = fl.leg_id
          AND dp.status = 'PENDING'
          AND fl.scheduled_departure <= NOW()
    """))
    return result.rowcount
