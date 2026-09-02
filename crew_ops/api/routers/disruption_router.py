from fastapi import APIRouter, Body, HTTPException
from datetime import datetime, timezone
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository, disruption_repository
from crew_ops.models.events import RosterModifiedEvent
from crew_ops.services.event_bus import event_bus
from crew_ops.services.weekly_planner.weekly_planner_service import DailyValidator
from crew_ops.services.disruption_handler.disruption_handler_service import DisruptionHandler
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.crew_profile_client import get_crew_member
from crew_ops.rules.legality import check_legality
from crew_ops.clients.ftl_client import get_crew_duty_state
from crew_ops.clients.license_client import get_licenses_for_crew_member
from crew_ops.clients.leave_client import get_leave_records_for_crew

router = APIRouter(prefix="/disruptions", tags=["Disruptions"])

_validator = DailyValidator()
_handler   = DisruptionHandler()


@router.get("/proposals")
def get_proposals():
    """Returns all PENDING proposals sorted by severity then age."""
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


@router.post("/proposals/{proposal_id}/accept")
def accept_proposal(proposal_id: str, decided_by: str = Body(...)):
    """
    Controller accepts a proposal.
    1. Marks proposal ACCEPTED
    2. Updates roster_crew_assignment — old crew REPLACED, new crew CONFIRMED
    3. Publishes RosterModifiedEvent
    4. Daily Validator re-validates both crew members' future legs immediately
    """
    with SessionLocal() as session:
        result = disruption_repository.accept_proposal(session, proposal_id, decided_by)
        if not result:
            raise HTTPException(status_code=404, detail="Proposal not found")

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        added_crew_id   = result["proposed_crew_id"]

        if not added_crew_id:
            # Proposal had no candidate — controller accepted a manual-review proposal
            # Nothing to write to roster, just mark accepted
            session.commit()
            return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": None}

        # Write roster change — old crew REPLACED, new crew CONFIRMED
        roster_repository.replace_roster_crew_assignment(
            session, leg_id, removed_crew_id, added_crew_id, decided_by
        )
        session.commit()

    # Publish RosterModifiedEvent — Daily Validator re-validates both crew immediately
    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = removed_crew_id,
        added_crew_id   = added_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))

    return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": added_crew_id}


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    decided_by: str = Body(...),
    rejection_reason: str = Body(...),
):
    """
    Controller rejects a proposal.
    1. Marks proposal REJECTED
    2. Finds next best candidate not already proposed for this leg + removed crew
    3. Creates new PENDING proposal with next candidate
    4. If no more candidates — creates proposal with proposed_crew_id = None (manual handling)
    """
    with SessionLocal() as session:
        result = disruption_repository.reject_proposal(session, proposal_id, decided_by, rejection_reason)
        if not result:
            raise HTTPException(status_code=404, detail="Proposal not found")

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]

        # Get all crew already proposed for this leg + removed crew to exclude them
        already_proposed = disruption_repository.get_already_proposed_crew(session, leg_id, removed_crew_id)
        session.commit()

    # Find next candidate — exclude all previously proposed crew
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

    # Re-run candidate search excluding already proposed crew
    candidates = _handler._find_and_rank_candidates(role, leg)
    candidates = [c for c in candidates if c["crew"].crew_id not in already_proposed]

    # Create new proposal with next best candidate (or None if exhausted)
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
