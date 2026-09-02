from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class CrewReserveSchedule(BaseModel):
    reserve_id: str
    crew_id: str
    date: date
    standby_start: datetime
    standby_end: datetime
    base_airport: str
    callable_within: int = 120          # minutes
    status: str = "SCHEDULED"           # SCHEDULED / ACTIVATED / RELEASED
    activated_for: Optional[str] = None # leg_id if activated
    created_at: Optional[datetime] = None
