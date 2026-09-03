from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class FlightDisruptedEvent(BaseModel):
    event: str = "FlightDisrupted"
    leg_id: str
    flight_number: str
    origin: str
    destination: str
    disruption_type: str            # DELAY / CANCELLATION / DIVERSION
    severity: str                   # LOW / MEDIUM / HIGH / CRITICAL
    scheduled_departure: datetime
    actual_departure: Optional[datetime] = None
    delay_minutes: Optional[int] = None
    assigned_crew: List[str] = []
    detected_at: datetime


class LegCompletedEvent(BaseModel):
    event: str = "LegCompleted"
    leg_id: str
    actual_arrival: datetime
    destination: str
    crew: List[str] = []
    delay_minutes: int = 0


class CrewDisruptedEvent(BaseModel):
    event: str = "CrewDisrupted"
    crew_id: str
    crew_name: str
    leg_id: str
    reason: str
    days_until_departure: int
    severity: str                   # LOW / MEDIUM / HIGH / CRITICAL
    source: str                     # OPS_DESK / WEEKLY_PLANNER_VALIDATOR
    detected_at: datetime
    start_date: Optional[str] = None   # leave period start (YYYY-MM-DD)
    end_date: Optional[str] = None     # leave period end (YYYY-MM-DD)


class RosterModifiedEvent(BaseModel):
    event: str = "RosterModified"
    leg_id: str
    removed_crew_id: Optional[str] = None
    added_crew_id: Optional[str] = None
    modified_at: datetime


class FlightTimeLimitsAlertEvent(BaseModel):
    event: str = "FlightTimeLimitsAlert"
    crew_id: str
    alert_type: str                 # DUTY_PERIOD_APPROACHING / REST_VIOLATION / WEEKLY_REST_OVERDUE
    message: str
    detected_at: datetime
