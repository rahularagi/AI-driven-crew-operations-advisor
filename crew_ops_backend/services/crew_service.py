from datetime import datetime, timezone

from crew_ops_backend.clients.crew_profile_client import get_crew_member
from crew_ops_backend.clients.ftl_client import get_crew_duty_state
from crew_ops_backend.models.events import CrewDisruptedEvent
from crew_ops_backend.services.event_bus import event_bus


def get_crew_ftl(crew_id: str):
    return get_crew_duty_state(crew_id)


def mark_unavailable(crew_id: str, reason: str, start_date: str, end_date: str) -> dict:
    from datetime import date
    crew = get_crew_member(crew_id)
    if not crew:
        return None

    days_until = (date.fromisoformat(start_date) - datetime.now(timezone.utc).date()).days
    severity   = _compute_severity(days_until)

    event_bus.publish(CrewDisruptedEvent(
        crew_id              = crew_id,
        crew_name            = crew.full_name,
        leg_id               = "",
        reason               = reason,
        days_until_departure = days_until,
        severity             = severity,
        source               = "OPS_DESK",
        detected_at          = datetime.now(timezone.utc),
        start_date           = start_date,
        end_date             = end_date,
    ))

    return {
        "status":     "disruption event published",
        "crew_id":    crew_id,
        "reason":     reason,
        "start_date": start_date,
        "end_date":   end_date,
        "severity":   severity,
    }


def _compute_severity(days_until_departure: int) -> str:
    if days_until_departure < 1:  return "CRITICAL"
    if days_until_departure <= 2: return "HIGH"
    if days_until_departure <= 7: return "MEDIUM"
    return "LOW"
