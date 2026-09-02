from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class CrewFlightTimeLimitsState(BaseModel):
    crew_id: str
    role: str
    status: str = "AVAILABLE"           # AVAILABLE / RESTING / UNAVAILABLE

    # ─── Current duty window ──────────────────────────────────────────────────
    duty_start_time: Optional[datetime] = None
    duty_end_time: Optional[datetime] = None
    projected_duty_period_end: Optional[datetime] = None
    flight_hours_current_duty: float = 0.0
    sectors_current_duty: int = 0

    # ─── Rest state ───────────────────────────────────────────────────────────
    rest_start_time: Optional[datetime] = None
    last_rest_end_time: Optional[datetime] = None
    rest_hours_available: float = 0.0

    # ─── Rolling counters (never reset, carry history forward) ───────────────
    flight_hours_28_day: float = 0.0
    duty_hours_7_day: float = 0.0
    duty_hours_28_day: float = 0.0
    consecutive_duty_days: int = 0
    last_weekly_rest_end: Optional[datetime] = None

    # ─── Per duty fields (reset when duty ends) ───────────────────────────────
    max_duty_period_hours: float = 13.0
    circadian_low_window_encroachment: bool = False
    duty_period_reduction_hours: float = 0.0
    duty_period_extended: bool = False
    duty_period_extension_hours: float = 0.0

    # ─── Location ─────────────────────────────────────────────────────────────
    home_base: str
    current_airport: str
    at_home_base: bool = True
    rest_type: Optional[str] = None     # HOME_REST / HOTEL_REST
    earliest_checkout: Optional[datetime] = None

    last_updated: Optional[datetime] = None
