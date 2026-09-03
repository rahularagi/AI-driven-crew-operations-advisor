from datetime import datetime, timezone

from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.db.repositories import roster_repository, disruption_repository
from crew_ops_backend.models.events import RosterModifiedEvent
from crew_ops_backend.services.event_bus import event_bus
from crew_ops_backend.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
from crew_ops_backend.clients.crew_profile_client import get_crew_member


_handler = DisruptionHandler()


def get_pending_proposals():
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


def accept_proposal(proposal_id: str, decided_by: str) -> dict:
    with SessionLocal() as session:
        result = disruption_repository.accept_proposal(session, proposal_id, decided_by)
        if not result:
            return None

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        added_crew_id   = result["proposed_crew_id"]

        if not added_crew_id:
            session.commit()
            return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": None}

        roster_repository.replace_roster_crew_assignment(
            session, leg_id, removed_crew_id, added_crew_id, decided_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = removed_crew_id,
        added_crew_id   = added_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))

    return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": added_crew_id}


def reject_proposal(proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    with SessionLocal() as session:
        result = disruption_repository.reject_proposal(session, proposal_id, decided_by, rejection_reason)
        if not result:
            return None

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        already_proposed = disruption_repository.get_already_proposed_crew(session, leg_id, removed_crew_id)
        session.commit()

    leg = get_flight_leg(leg_id)
    if not leg:
        return {"status": "rejected", "new_proposal_id": None, "reason": "leg no longer exists"}

    removed_crew = get_crew_member(removed_crew_id)
    if removed_crew:
        role = removed_crew.role
    else:
        with SessionLocal() as session:
            assignment = roster_repository.get_assignment_for_crew(session, leg_id, removed_crew_id)
        role = assignment.get("role") if assignment else None

    if not role:
        return {"status": "rejected", "new_proposal_id": None, "reason": "cannot determine role"}

    candidates = _handler._find_and_rank_candidates(role, leg)
    candidates = [c for c in candidates if c["crew"].crew_id not in already_proposed]

    proposed_crew_id = candidates[0]["crew"].crew_id if candidates else None
    proposal_score   = candidates[0]["score"] if candidates else 0.0
    new_proposal_id  = f"PROP-{leg_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    with SessionLocal() as session:
        disruption_repository.insert_proposal(session, {
            "proposal_id":       new_proposal_id,
            "leg_id":            leg_id,
            "disruption_type":   "CREW_DISRUPTED",
            "disruption_reason": rejection_reason,
            "removed_crew_id":   removed_crew_id,
            "proposed_crew_id":  proposed_crew_id,
            "proposal_score":    proposal_score,
            "status":            "PENDING",
            "severity":          "HIGH",
            "source":            "CONTROLLER_REJECT",
        })
        session.commit()

    return {
        "status":          "rejected",
        "new_proposal_id": new_proposal_id,
        "next_candidate":  proposed_crew_id,
    }
