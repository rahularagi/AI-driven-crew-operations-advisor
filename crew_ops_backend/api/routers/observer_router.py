from fastapi import APIRouter, HTTPException, Query
from datetime import date
from crew_ops_backend.services.observer.observer_service import FlightObserver
from crew_ops_backend.models.flight_leg import FlightLeg

router = APIRouter(prefix="/observer", tags=["Observer"])

_observer = FlightObserver()


@router.get("/legs/today", response_model=list[FlightLeg])
def get_todays_legs():
    """
    Returns today's active legs that have crew assigned.
    This is what the automated polling loop watches.
    """
    return _observer.get_todays_active_legs()


@router.get("/legs", response_model=list[FlightLeg])
def get_legs_for_date(
    target_date: date | None = Query(default=None),
    offset: int | None = Query(default=None),
):
    """
    Manager view — returns scheduled legs for a given date. Read-only, no polling.

    Use target_date OR offset, not both.
      ?target_date=2024-03-05   → specific date
      ?offset=1                 → tomorrow
      ?offset=2                 → day after tomorrow
      ?offset=7                 → one week from today
    """
    try:
        return _observer.get_legs(target_date=target_date, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
