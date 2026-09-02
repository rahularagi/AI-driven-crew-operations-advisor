from fastapi import APIRouter
from crew_ops_backend.services.flight_time_limits.flight_time_limits_service import FlightTimeLimitsService

router = APIRouter(prefix="/ftl", tags=["Flight Time Limits"])

_ftl_service = FlightTimeLimitsService()


@router.post("/scan")
def trigger_alert_scan():
    """
    Manually trigger the proactive FTL alert scan across all crew.
    Normally runs automatically every 15 minutes via the scheduler.
    """
    _ftl_service.run_proactive_alert_scan()
    return {"status": "alert scan completed"}


@router.post("/recalculate")
def trigger_midnight_recalculation():
    """
    Manually trigger the rolling counter recalculation for all crew.
    Normally runs automatically every midnight via the scheduler.
    """
    _ftl_service.run_midnight_recalculation()
    return {"status": "recalculation completed"}
