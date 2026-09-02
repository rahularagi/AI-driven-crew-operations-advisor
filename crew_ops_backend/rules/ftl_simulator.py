from datetime import timedelta
from crew_ops.models.flight_leg import FlightLeg
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops.rules.duty_period_limits import max_duty_hours


def simulate_leg_assigned(
    ftl: CrewFlightTimeLimitsState,
    leg: FlightLeg,
) -> CrewFlightTimeLimitsState:
    leg_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600

    new = ftl.model_copy(deep=True)
    new.flight_hours_current_duty += leg_hours
    new.sectors_current_duty      += 1
    new.flight_hours_28_day       += leg_hours
    new.duty_hours_7_day          += leg_hours
    new.duty_hours_28_day         += leg_hours
    new.current_airport            = leg.destination_icao

    leg_day = leg.scheduled_departure.date()
    last_duty_day = ftl.duty_start_time.date() if ftl.duty_start_time else None
    if last_duty_day is None or leg_day > last_duty_day:
        new.consecutive_duty_days += 1

    report_hour = leg.scheduled_departure.hour
    limit = max_duty_hours(report_hour, new.sectors_current_duty)
    if new.duty_start_time is None:
        new.duty_start_time = leg.scheduled_departure
    new.projected_duty_period_end = new.duty_start_time + timedelta(hours=limit)

    return new


def simulate_rest_after_leg(
    ftl: CrewFlightTimeLimitsState,
    leg: FlightLeg,
) -> CrewFlightTimeLimitsState:
    duty_duration = (
        (leg.scheduled_arrival - ftl.duty_start_time).total_seconds() / 3600
        if ftl.duty_start_time else 0.0
    )
    min_rest = max(duty_duration, 11.0)

    new = ftl.model_copy(deep=True)
    new.flight_hours_current_duty = 0.0
    new.sectors_current_duty      = 0
    new.duty_start_time           = None
    new.projected_duty_period_end = None
    new.status                    = "AVAILABLE"
    new.rest_start_time           = leg.scheduled_arrival + timedelta(minutes=30)
    new.earliest_checkout         = new.rest_start_time + timedelta(hours=min_rest)
    new.last_rest_end_time        = new.earliest_checkout
    return new
