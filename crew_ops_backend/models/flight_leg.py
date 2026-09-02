from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class FlightLeg(BaseModel):
    leg_id: str
    flight_number: str
    origin_iata: str
    origin_icao: str
    destination_iata: str
    destination_icao: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    estimated_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    aircraft_type: str
    aircraft_registration: str
    status: str = "SCHEDULED"
    delay_status: str = "ON_TIME"
    delay_minutes: int = 0
    assigned_crew: List[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
