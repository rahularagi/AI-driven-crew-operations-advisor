from fastapi import APIRouter, HTTPException, Body
from datetime import datetime, timezone
from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.clients.ftl_client import get_crew_duty_state
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.models.events import CrewDisruptedEvent
from crew_ops_backend.services.event_bus import event_bus

router = APIRouter(prefix="/crew", tags=["Crew"])


@router.get("/{crew_id}/ftl", response_model=CrewFlightTimeLimitsState)
def get_crew_ftl_state(crew_id: str):
    """Current flight time limits state for a crew member."""
    ftl = get_crew_duty_state(crew_id)
    if not ftl:
        raise HTTPException(status_code=404, detail=f"FTL state for {crew_id} not found")
    return ftl


@router.post("/{crew_id}/unavailable")
def mark_crew_unavailable(
    crew_id: str,
    reason: str = Body(...),
    affected_leg_id: str = Body(...),
    days_until_departure: int = Body(...),
):
    """
    Ops desk marks a crew member as unavailable for a specific leg.
    Publishes CrewDisruptedEvent → triggers the disruption pipeline.

    reason: SICK_CALL / NO_SHOW / MEDICAL_GROUNDING / EMERGENCY_LEAVE / URGENT_TRAINING
    """
    crew = get_crew_member(crew_id)
    if not crew:
        raise HTTPException(status_code=404, detail=f"Crew member {crew_id} not found")

    severity = _compute_severity(days_until_departure)

    event_bus.publish(CrewDisruptedEvent(
        crew_id=crew_id,
        crew_name=crew.full_name,
        leg_id=affected_leg_id,
        reason=reason,
        days_until_departure=days_until_departure,
        severity=severity,
        source="OPS_DESK",
        detected_at=datetime.now(timezone.utc),
    ))

    return {
        "status": "disruption event published",
        "crew_id": crew_id,
        "leg_id": affected_leg_id,
        "severity": severity,
        "reason": reason,
    }


def _compute_severity(days_until_departure: int) -> str:
    if days_until_departure < 1:  return "CRITICAL"
    if days_until_departure <= 2: return "HIGH"
    if days_until_departure <= 7: return "MEDIUM"
    return "LOW"
