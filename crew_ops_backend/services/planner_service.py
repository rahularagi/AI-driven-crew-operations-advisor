from datetime import date, datetime, timezone

from crew_ops_backend.db.database import SessionLocal
from crew_ops_backend.db.repositories import roster_repository
from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
from crew_ops_backend.clients.ftl_client import get_crew_duty_state
from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.clients.license_client import get_licenses_for_crew_member
from crew_ops_backend.clients.leave_client import get_leave_records_for_crew
from crew_ops_backend.rules.legality import check_legality
from crew_ops_backend.models.events import RosterModifiedEvent
from crew_ops_backend.services.event_bus import event_bus
from crew_ops_backend.services.weekly_planner.weekly_planner_service import RosterPlanner, DailyValidator

_planner   = RosterPlanner()
_validator = DailyValidator()


def build_roster(requested_by: str, start: date = None, end: date = None) -> dict:
    _planner.build(start=start, end=end, requested_by=requested_by)
    return {"status": "build started", "start": start, "end": end, "requested_by": requested_by}


def validate_roster(requested_by: str) -> dict:
    _validator.validate(requested_by=requested_by)
    return {"status": "validation started", "requested_by": requested_by}


def get_roster(start: date, end: date) -> list:
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)


def approve_leg(leg_id: str, approved_by: str) -> dict:
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "approved", "leg_id": leg_id, "approved_by": approved_by}


def reassign_crew(leg_id: str, crew_id: str, replaced_by: str, requested_by: str) -> dict:
    leg = get_flight_leg(leg_id)
    if not leg:
        return {"error": "leg_not_found"}

    new_crew = get_crew_member(replaced_by)
    if not new_crew:
        return {"error": "crew_not_found"}

    ftl = get_crew_duty_state(replaced_by)
    if not ftl:
        return {"error": "ftl_not_found"}

    licenses      = get_licenses_for_crew_member(replaced_by)
    leave_records = get_leave_records_for_crew(replaced_by)
    passed, fail_reason = check_legality(new_crew, leg, ftl, licenses, leave_records, leg.scheduled_departure.date())

    if not passed:
        return {"error": "legality_failed", "reason": fail_reason}

    with SessionLocal() as session:
        roster_repository.replace_roster_crew_assignment(session, leg_id, crew_id, replaced_by, requested_by)
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = crew_id,
        added_crew_id   = replaced_by,
        modified_at     = datetime.now(timezone.utc),
    ))

    return {"status": "reassigned", "leg_id": leg_id, "removed": crew_id, "added": replaced_by}
