from datetime import date, datetime

from langchain_core.tools import tool

from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
from crew_ops_backend.clients.ftl_client import get_crew_duty_state
from crew_ops_backend.clients.license_client import get_licenses_for_crew_member
from crew_ops_backend.clients.leave_client import get_leave_records_for_crew
from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.db.repositories import disruption_repository, roster_repository
from crew_ops_backend.models.events import CrewDisruptedEvent, RosterModifiedEvent
from crew_ops_backend.rules.legality import check_legality
from crew_ops_backend.services.event_bus import event_bus
from crew_ops_backend.services.simulation.simulation_service import SimulationService


# ─── Read tools ───────────────────────────────────────────────────────────────

@tool
def get_leg_status(leg_id: str) -> dict:
    """Get the current status and details of a flight leg by its leg ID (e.g. L42).
    Use when the user asks about a specific flight leg status, departure time, delay, or leg details."""
    leg = get_flight_leg(leg_id)
    return leg.model_dump() if leg else {"error": "leg not found"}


@tool
def get_crew_schedule(crew_id: str, start: date, end: date) -> list:
    """Get the roster assignments for a crew member between start and end date.
    Use when the user asks about a crew member's schedule, assignments, or flights for a date range."""
    with SessionLocal() as session:
        return roster_repository.get_future_assignments(session, from_date=start, to_date=end, crew_id=crew_id)


@tool
def get_crew_ftl(crew_id: str) -> dict:
    """Get the current Flight Time Limitations (FTL) and duty hours state for a crew member.
    Use when the user asks about FTL, duty hours, rest time, or flight hour limits for a crew member."""
    ftl = get_crew_duty_state(crew_id)
    return ftl.model_dump() if ftl else {"error": "FTL state not found"}


@tool
def get_pending_proposals() -> list:
    """Get all pending disruption proposals waiting for ops controller decision.
    Use when the user asks about pending proposals, inbox, disruption proposals, or proposals to review."""
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


@tool
def get_roster(start: date, end: date) -> list:
    """Get the full crew roster and flight legs for a date range.
    Use when the user asks about the roster, crew assignments, who is flying, delayed flights, today's flights, or flight activity for a given period.
    For 'today' use today's date for both start and end."""
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)


# ─── Simulate tools ───────────────────────────────────────────────────────────

@tool
def simulate_crew_removal(crew_id: str, leg_id: str) -> dict:
    """Simulate the impact of removing a crew member from a flight leg without making any real changes.
    Use when the user wants to explore what happens if a crew member is removed or becomes unavailable for a leg."""
    return SimulationService().simulate_crew_removal(crew_id, leg_id)


@tool
def simulate_crew_swap(crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str) -> dict:
    """Simulate swapping two crew members between two flight legs without making any real changes.
    Use when the user wants to explore swapping crew assignments between legs."""
    return SimulationService().simulate_crew_swap(crew_id_a, crew_id_b, leg_id_a, leg_id_b)


@tool
def simulate_leg_cancellation(leg_id: str) -> dict:
    """Simulate the impact of cancelling a flight leg without making any real changes.
    Use when the user wants to explore what happens if a flight leg is cancelled."""
    return SimulationService().simulate_leg_cancellation(leg_id)


# ─── Action tools ─────────────────────────────────────────────────────────────

@tool
def action_mark_crew_unavailable(crew_id: str, reason: str, start_date: date, end_date: date) -> dict:
    """Mark a crew member as unavailable for a date range. This raises a disruption event.
    Use when the user wants to mark a crew member sick, unavailable, or on leave.
    Requires confirmation before executing.
    reason must be one of: SICK_CALL, PERSONAL, TRAINING, OTHER.
    start_date and end_date must be in ISO format (YYYY-MM-DD)."""
    from datetime import datetime, timezone
    crew       = get_crew_member(crew_id)
    if not crew:
        return {"error": f"crew {crew_id} not found"}

    days_until = (start_date - datetime.now(timezone.utc).date()).days
    severity   = _classify_severity(days_until)

    event_bus.publish(CrewDisruptedEvent(
        crew_id              = crew_id,
        crew_name            = crew.full_name if crew else crew_id,
        leg_id               = "",
        reason               = reason,
        days_until_departure = days_until,
        severity             = severity,
        source               = "OPS_DESK",
        detected_at          = datetime.now(timezone.utc),
        start_date           = str(start_date),
        end_date             = str(end_date),
    ))
    return {"status": "disruption_raised", "crew_id": crew_id, "reason": reason,
            "start_date": str(start_date), "end_date": str(end_date), "severity": severity}


@tool
def action_reassign_crew(leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> dict:
    """Reassign a flight leg from one crew member to another. Runs a legality check before reassigning.
    Use when the user wants to directly assign a specific replacement crew member to a leg."""
    leg      = get_flight_leg(leg_id)
    new_crew = get_crew_member(new_crew_id)
    ftl      = get_crew_duty_state(new_crew_id)
    licenses = get_licenses_for_crew_member(new_crew_id)
    leave    = get_leave_records_for_crew(new_crew_id)

    if not leg or not new_crew or not ftl:
        return {"error": "leg or crew not found"}

    passed, fail_reason = check_legality(
        new_crew, leg, ftl, licenses, leave, leg.scheduled_departure.date()
    )
    if not passed:
        return {"error": f"legality check failed: {fail_reason}"}

    with SessionLocal() as session:
        roster_repository.replace_roster_crew_assignment(
            session, leg_id, old_crew_id, new_crew_id, requested_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = old_crew_id,
        added_crew_id   = new_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))
    return {"status": "reassigned", "leg_id": leg_id, "removed": old_crew_id, "added": new_crew_id}


@tool
def action_accept_proposal(proposal_id: str, decided_by: str) -> dict:
    """Accept a pending disruption proposal and apply the proposed crew replacement to the roster.
    Use when the user wants to accept a disruption proposal."""
    with SessionLocal() as session:
        result = disruption_repository.accept_proposal(session, proposal_id, decided_by)
        if not result or "leg_id" not in result:
            return {"error": "proposal not found"}

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        added_crew_id   = result["proposed_crew_id"]

        if not added_crew_id:
            session.commit()
            return {"status": "accepted", "leg_id": leg_id, "added": None,
                    "note": "no candidate — manual handling required"}

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


@tool
def action_reject_proposal(proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    """Reject a pending disruption proposal and trigger re-proposal with the next best candidate.
    Use when the user wants to reject a disruption proposal."""
    from crew_ops_backend.services.disruption_handler.disruption_handler_service import DisruptionHandler
    return DisruptionHandler().reject_and_repropose(proposal_id, decided_by, rejection_reason)


@tool
def action_approve_roster_leg(leg_id: str, approved_by: str) -> dict:
    """Approve a DRAFT roster leg and publish it to PUBLISHED status.
    Use when the user wants to approve or publish a roster leg."""
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "published", "leg_id": leg_id, "approved_by": approved_by}


# ─── All tools list (used by agent_llm to bind to LLM) ───────────────────────

ALL_QUERY_TOOLS    = [get_leg_status, get_crew_schedule, get_crew_ftl, get_pending_proposals, get_roster]
ALL_SIMULATE_TOOLS = [simulate_crew_removal, simulate_crew_swap, simulate_leg_cancellation]
ALL_ACTION_TOOLS   = [action_mark_crew_unavailable, action_reassign_crew, action_accept_proposal, action_reject_proposal, action_approve_roster_leg]
ALL_TOOLS          = ALL_QUERY_TOOLS + ALL_SIMULATE_TOOLS + ALL_ACTION_TOOLS


# ─── Private helper ───────────────────────────────────────────────────────────

def _classify_severity(days_until_departure: int) -> str:
    if days_until_departure < 1:  return "CRITICAL"
    if days_until_departure <= 2: return "HIGH"
    if days_until_departure <= 7: return "MEDIUM"
    return "LOW"
