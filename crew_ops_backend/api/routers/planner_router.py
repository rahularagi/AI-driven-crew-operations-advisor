from fastapi import APIRouter, Body, HTTPException
from datetime import date

from crew_ops_backend.services import planner_service

router = APIRouter(prefix="/planner", tags=["Planner"])


@router.post("/build")
def trigger_build(
    requested_by: str = Body(...),
    start: date | None = Body(default=None),
    end: date | None = Body(default=None),
):
    try:
        return planner_service.build_roster(requested_by, start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate")
def trigger_validation(requested_by: str = Body(...)):
    return planner_service.validate_roster(requested_by)


@router.get("/roster")
def get_roster(start: date, end: date):
    return planner_service.get_roster(start, end)


@router.post("/roster/{leg_id}/approve")
def approve_leg(leg_id: str, approved_by: str = Body(...)):
    return planner_service.approve_leg(leg_id, approved_by)


@router.post("/roster/{leg_id}/reassign")
def reassign_crew(
    leg_id: str,
    crew_id: str = Body(...),
    replaced_by: str = Body(...),
    reason: str = Body(...),
    requested_by: str = Body(...),
):
    result = planner_service.reassign_crew(leg_id, crew_id, replaced_by, requested_by)
    if result.get("error") == "leg_not_found":
        raise HTTPException(status_code=404, detail="Leg not found")
    if result.get("error") == "crew_not_found":
        raise HTTPException(status_code=404, detail="Replacement crew member not found")
    if result.get("error") == "ftl_not_found":
        raise HTTPException(status_code=400, detail="No FTL state found for replacement crew")
    if result.get("error") == "legality_failed":
        raise HTTPException(status_code=400, detail=f"Legality check failed: {result.get('reason')}")
    return result
