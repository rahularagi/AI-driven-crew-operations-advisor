from fastapi import APIRouter, Body, HTTPException
from datetime import date, datetime, timezone
from crew_ops.services.weekly_planner.weekly_planner_service import RosterPlanner, DailyValidator
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.ftl_client import get_crew_duty_state
from crew_ops.clients.crew_profile_client import get_crew_member
from crew_ops.clients.license_client import get_licenses_for_crew_member
from crew_ops.clients.leave_client import get_leave_records_for_crew
from crew_ops.rules.legality import check_legality
from crew_ops.models.events import RosterModifiedEvent
from crew_ops.services.event_bus import event_bus

router = APIRouter(prefix="/planner", tags=["Planner"])

_planner   = RosterPlanner()
_validator = DailyValidator()


@router.post("/build")
def trigger_build(
    requested_by: str = Body(...),
    start: date | None = Body(default=None),
    end: date | None = Body(default=None),
):
    try:
        _planner.build(start=start, end=end, requested_by=requested_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "build started", "start": start, "end": end, "requested_by": requested_by}


@router.post("/validate")
def trigger_validation(requested_by: str = Body(...)):
    _validator.validate(requested_by=requested_by)
    return {"status": "validation started", "requested_by": requested_by}


@router.get("/roster")
def get_roster(start: date, end: date):
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)


@router.post("/roster/{leg_id}/approve")
def approve_leg(leg_id: str, approved_by: str = Body(...)):
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "approved", "leg_id": leg_id, "approved_by": approved_by}


@router.post("/roster/{leg_id}/reassign")
def reassign_crew(
    leg_id: str,
    crew_id: str = Body(...),
    replaced_by: str = Body(...),
    reason: str = Body(...),
    requested_by: str = Body(...),
):
    leg  = get_flight_leg(leg_id)
    if not leg:
        raise HTTPException(status_code=404, detail="Leg not found")

    new_crew = get_crew_member(replaced_by)
    if not new_crew:
        raise HTTPException(status_code=404, detail="Replacement crew member not found")

    ftl = get_crew_duty_state(replaced_by)
    if not ftl:
        raise HTTPException(status_code=400, detail="No FTL state found for replacement crew")

    licenses     = get_licenses_for_crew_member(replaced_by)
    leave_records = get_leave_records_for_crew(replaced_by)
    leg_date     = leg.scheduled_departure.date()

    passed, fail_reason = check_legality(new_crew, leg, ftl, licenses, leave_records, leg_date)
    if not passed:
        raise HTTPException(status_code=400, detail=f"Legality check failed: {fail_reason}")

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
