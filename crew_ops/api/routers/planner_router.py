from fastapi import APIRouter, Body, HTTPException
from datetime import date
from crew_ops.services.weekly_planner.weekly_planner_service import RosterPlanner, DailyValidator

router = APIRouter(prefix="/planner", tags=["Planner"])

_planner   = RosterPlanner()
_validator = DailyValidator()


@router.post("/build")
def trigger_build(
    requested_by: str = Body(...),
    start: date | None = Body(default=None),
    end: date | None = Body(default=None),
):
    """
    Manual roster build trigger.

    No start/end  → builds today + configured weeks (same as Sunday scheduler)
    start + end   → builds only that specific date window
    """
    try:
        _planner.build(start=start, end=end, requested_by=requested_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "build started", "start": start, "end": end, "requested_by": requested_by}


@router.post("/validate")
def trigger_validation(requested_by: str = Body(...)):
    """
    Manual validation trigger.
    Same as the 3AM daily scheduler — re-checks all future planned weeks against current reality.
    """
    _validator.validate(requested_by=requested_by)
    return {"status": "validation started", "requested_by": requested_by}
