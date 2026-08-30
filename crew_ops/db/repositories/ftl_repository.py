from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from crew_ops.models.crew_ftl_state import CrewFTLState


def get_all_ftl_states(session: Session) -> list[CrewFTLState]:
    rows = session.execute(text("SELECT * FROM crew_ftl_states")).mappings().all()
    return [CrewFTLState(**dict(row)) for row in rows]


def get_ftl_state_by_crew_id(session: Session, crew_id: str) -> Optional[CrewFTLState]:
    row = session.execute(
        text("SELECT * FROM crew_ftl_states WHERE crew_id = :crew_id"),
        {"crew_id": crew_id}
    ).mappings().first()
    return CrewFTLState(**dict(row)) if row else None


def upsert_ftl_state(session: Session, ftl_state: CrewFTLState) -> None:
    data = ftl_state.model_dump(exclude={"last_updated"})
    data["last_updated"] = "NOW()"
    session.execute(text("""
        INSERT INTO crew_ftl_states (
            crew_id, role, status, duty_start_time, duty_end_time,
            projected_fdp_end, flight_time_current_duty, sectors_current_duty,
            rest_start_time, last_rest_end_time, rest_hours_available,
            flight_hours_28_day, duty_hours_7_day, duty_hours_28_day,
            consecutive_duty_days, last_weekly_rest_end, max_fdp_allowed,
            wocl_encroachment, fdp_reduction_applied, fdp_extension_used,
            extension_hours, home_base, current_airport, at_home_base,
            rest_type, earliest_checkout, last_updated
        ) VALUES (
            :crew_id, :role, :status, :duty_start_time, :duty_end_time,
            :projected_fdp_end, :flight_time_current_duty, :sectors_current_duty,
            :rest_start_time, :last_rest_end_time, :rest_hours_available,
            :flight_hours_28_day, :duty_hours_7_day, :duty_hours_28_day,
            :consecutive_duty_days, :last_weekly_rest_end, :max_fdp_allowed,
            :wocl_encroachment, :fdp_reduction_applied, :fdp_extension_used,
            :extension_hours, :home_base, :current_airport, :at_home_base,
            :rest_type, :earliest_checkout, NOW()
        )
        ON CONFLICT (crew_id) DO UPDATE SET
            status                      = EXCLUDED.status,
            duty_start_time             = EXCLUDED.duty_start_time,
            duty_end_time               = EXCLUDED.duty_end_time,
            projected_fdp_end           = EXCLUDED.projected_fdp_end,
            flight_time_current_duty    = EXCLUDED.flight_time_current_duty,
            sectors_current_duty        = EXCLUDED.sectors_current_duty,
            rest_start_time             = EXCLUDED.rest_start_time,
            last_rest_end_time          = EXCLUDED.last_rest_end_time,
            rest_hours_available        = EXCLUDED.rest_hours_available,
            flight_hours_28_day         = EXCLUDED.flight_hours_28_day,
            duty_hours_7_day            = EXCLUDED.duty_hours_7_day,
            duty_hours_28_day           = EXCLUDED.duty_hours_28_day,
            consecutive_duty_days       = EXCLUDED.consecutive_duty_days,
            last_weekly_rest_end        = EXCLUDED.last_weekly_rest_end,
            max_fdp_allowed             = EXCLUDED.max_fdp_allowed,
            wocl_encroachment           = EXCLUDED.wocl_encroachment,
            fdp_reduction_applied       = EXCLUDED.fdp_reduction_applied,
            fdp_extension_used          = EXCLUDED.fdp_extension_used,
            extension_hours             = EXCLUDED.extension_hours,
            current_airport             = EXCLUDED.current_airport,
            at_home_base                = EXCLUDED.at_home_base,
            rest_type                   = EXCLUDED.rest_type,
            earliest_checkout           = EXCLUDED.earliest_checkout,
            last_updated                = NOW()
    """), ftl_state.model_dump(exclude={"last_updated"}))
    session.commit()
