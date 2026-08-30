from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class CrewLeaveRecord(BaseModel):
    crew_id: str
    leave_type: str                 # ANNUAL / SICK / TRAINING
    start_date: date
    end_date: date
    created_at: Optional[datetime] = None
