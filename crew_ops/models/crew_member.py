from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CrewMember(BaseModel):
    crew_id: str
    employee_id: str
    full_name: str
    designation: str
    role: str                       # PILOT or CABIN
    home_base: str                  # ICAO code
    date_of_joining: str
    seniority_number: int
    employment_status: str = "ACTIVE"
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
