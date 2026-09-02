from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState


def get_all_ftl_states(session: Session) -> list[CrewFlightTimeLimitsState]:
    rows = session.execute(text("SELECT * FROM crew_ftl_states")).mappings().all()
    return [CrewFlightTimeLimitsState(**dict(row)) for row in rows]


def get_ftl_state_by_crew_id(session: Session, crew_id: str) -> Optional[CrewFlightTimeLimitsState]:
    row = session.execute(
        text("SELECT * FROM crew_ftl_states WHERE crew_id = :crew_id"),
        {"crew_id": crew_id}
    ).mappings().first()
    return CrewFlightTimeLimitsState(**dict(row)) if row else None


def upsert_ftl_state(session: Session, state: CrewFlightTimeLimitsState) -> None:
    session.execute(text("""
        INSERT INTO crew_ftl_states (
            crew_id, role, status, duty_start_time, duty_end_time,
            projected_duty_period_end, flight_hours_current_duty, sectors_current_duty,
            rest_start_time, last_rest_end_time, rest_hours_available,
            flight_hours_28_day, duty_hours_7_day, duty_hours_28_day,
            consecutive_duty_days, last_weekly_rest_end, max_duty_period_hours,
            circadian_low_window_encroachment, duty_period_reduction_hours,
            duty_period_extended, duty_period_extension_hours,
            home_base, current_airport, at_home_base,
            rest_type, earliest_checkout, last_updated
        ) VALUES (
            :crew_id, :role, :status, :duty_start_time, :duty_end_time,
            :projected_duty_period_end, :flight_hours_current_duty, :sectors_current_duty,
            :rest_start_time, :last_rest_end_time, :rest_hours_available,
            :flight_hours_28_day, :duty_hours_7_day, :duty_hours_28_day,
            :consecutive_duty_days, :last_weekly_rest_end, :max_duty_period_hours,
            :circadian_low_window_encroachment, :duty_period_reduction_hours,
            :duty_period_extended, :duty_period_extension_hours,
            :home_base, :current_airport, :at_home_base,
            :rest_type, :earliest_checkout, NOW()
        )
        ON CONFLICT (crew_id) DO UPDATE SET
            status                             = EXCLUDED.status,
            duty_start_time                    = EXCLUDED.duty_start_time,
            duty_end_time                      = EXCLUDED.duty_end_time,
            projected_duty_period_end          = EXCLUDED.projected_duty_period_end,
            flight_hours_current_duty          = EXCLUDED.flight_hours_current_duty,
            sectors_current_duty               = EXCLUDED.sectors_current_duty,
            rest_start_time                    = EXCLUDED.rest_start_time,
            last_rest_end_time                 = EXCLUDED.last_rest_end_time,
            rest_hours_available               = EXCLUDED.rest_hours_available,
            flight_hours_28_day                = EXCLUDED.flight_hours_28_day,
            duty_hours_7_day                   = EXCLUDED.duty_hours_7_day,
            duty_hours_28_day                  = EXCLUDED.duty_hours_28_day,
            consecutive_duty_days              = EXCLUDED.consecutive_duty_days,
            last_weekly_rest_end               = EXCLUDED.last_weekly_rest_end,
            max_duty_period_hours              = EXCLUDED.max_duty_period_hours,
            circadian_low_window_encroachment  = EXCLUDED.circadian_low_window_encroachment,
            duty_period_reduction_hours        = EXCLUDED.duty_period_reduction_hours,
            duty_period_extended               = EXCLUDED.duty_period_extended,
            duty_period_extension_hours        = EXCLUDED.duty_period_extension_hours,
            current_airport                    = EXCLUDED.current_airport,
            at_home_base                       = EXCLUDED.at_home_base,
            rest_type                          = EXCLUDED.rest_type,
            earliest_checkout                  = EXCLUDED.earliest_checkout,
            last_updated                       = NOW()
    """), state.model_dump(exclude={"last_updated"}))
    session.commit()
