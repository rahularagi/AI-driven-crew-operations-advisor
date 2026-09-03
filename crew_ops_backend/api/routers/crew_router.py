from fastapi import APIRouter, HTTPException, Body

from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.services import crew_service

router = APIRouter(prefix="/crew", tags=["Crew"])


@router.get("/{crew_id}/ftl", response_model=CrewFlightTimeLimitsState)
def get_crew_ftl_state(crew_id: str):
    ftl = crew_service.get_crew_ftl(crew_id)
    if not ftl:
        raise HTTPException(status_code=404, detail=f"FTL state for {crew_id} not found")
    return ftl


@router.post("/{crew_id}/unavailable")
def mark_crew_unavailable(
    crew_id: str,
    reason: str = Body(...),
    start_date: str = Body(...),
    end_date: str = Body(...),
):
    result = crew_service.mark_unavailable(crew_id, reason, start_date, end_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Crew member {crew_id} not found")
    return result
