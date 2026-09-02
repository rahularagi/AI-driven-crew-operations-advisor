from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class CrewLicense(BaseModel):
    crew_id: str
    aircraft_type: str              # A320, B737, B787 etc.
    expiry_date: date
    medical_expiry: Optional[date] = None
    simulator_check_due: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
