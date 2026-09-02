from datetime import date, datetime, timezone

from crew_ops.clients.crew_profile_client import get_crew_member
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.ftl_client import get_crew_duty_state
from crew_ops.clients.license_client import get_licenses_for_crew_member
from crew_ops.clients.leave_client import get_leave_records_for_crew
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import disruption_repository, roster_repository
from crew_ops.models.events import CrewDisruptedEvent, RosterModifiedEvent
from crew_ops.rules.legality import check_legality
from crew_ops.services.event_bus import event_bus
from crew_ops.services.simulation.simulation_service import SimulationService


# ─── Read tools ───────────────────────────────────────────────────────────────

def get_leg_status(leg_id: str) -> dict:
    leg = get_flight_leg(leg_id)
    return leg.model_dump() if leg else {"error": "leg not found"}


def get_crew_schedule(crew_id: str, start: date, end: date) -> list[dict]:
    with SessionLocal() as session:
        return roster_repository.get_future_assignments(session, from_date=start, to_date=end, crew_id=crew_id)


def get_crew_ftl(crew_id: str) -> dict:
    ftl = get_crew_duty_state(crew_id)
    return ftl.model_dump() if ftl else {"error": "FTL state not found"}


def get_pending_proposals() -> list[dict]:
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


def get_roster(start: date, end: date) -> list[dict]:
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)


# ─── Simulate tools ───────────────────────────────────────────────────────────

def simulate_crew_removal(crew_id: str, leg_id: str) -> dict:
    return SimulationService().simulate_crew_removal(crew_id, leg_id)


def simulate_crew_swap(crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str) -> dict:
    return SimulationService().simulate_crew_swap(crew_id_a, crew_id_b, leg_id_a, leg_id_b)


def simulate_leg_cancellation(leg_id: str) -> dict:
    return SimulationService().simulate_leg_cancellation(leg_id)


# ─── Action tools ─────────────────────────────────────────────────────────────

def action_mark_crew_unavailable(crew_id: str, leg_id: str, reason: str) -> dict:
    leg = get_flight_leg(leg_id)
    if not leg:
        return {"error": f"leg {leg_id} not found"}

    days_until = (leg.scheduled_departure.astimezone(timezone.utc).date() - datetime.now(timezone.utc).date()).days
    severity   = _classify_severity(days_until)
    crew       = get_crew_member(crew_id)
    crew_name  = crew.full_name if crew else crew_id

    event_bus.publish(CrewDisruptedEvent(
        crew_id              = crew_id,
        crew_name            = crew_name,
        leg_id               = leg_id,
        reason               = reason,
        days_until_departure = days_until,
        severity             = severity,
        source               = "OPS_DESK",
        detected_at          = datetime.now(timezone.utc),
    ))
    return {"status": "disruption_raised", "crew_id": crew_id, "leg_id": leg_id, "severity": severity}


def action_reassign_crew(leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> dict:
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


def action_accept_proposal(proposal_id: str, decided_by: str) -> dict:
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


def action_reject_proposal(proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    from crew_ops.services.disruption_handler.disruption_handler_service import DisruptionHandler
    return DisruptionHandler().reject_and_repropose(proposal_id, decided_by, rejection_reason)


def action_approve_roster_leg(leg_id: str, approved_by: str) -> dict:
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "published", "leg_id": leg_id, "approved_by": approved_by}


# ─── Private helper ───────────────────────────────────────────────────────────

def _classify_severity(days_until_departure: int) -> str:
    if days_until_departure < 1:  return "CRITICAL"
    if days_until_departure <= 2: return "HIGH"
    if days_until_departure <= 7: return "MEDIUM"
    return "LOW"
