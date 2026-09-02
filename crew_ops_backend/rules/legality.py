from datetime import date
from crew_ops.models.crew_member import CrewMember
from crew_ops.models.flight_leg import FlightLeg
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops.models.crew_license import CrewLicense
from crew_ops.models.crew_leave import CrewLeaveRecord
from crew_ops.rules.duty_period_limits import max_duty_hours


def check_legality(
    crew: CrewMember,
    leg: FlightLeg,
    ftl: CrewFlightTimeLimitsState,
    licenses: list[CrewLicense],
    leave_records: list[CrewLeaveRecord],
    leg_date: date,
) -> tuple[bool, str | None]:

    # Gate 1 — Employment status
    if crew.employment_status != "ACTIVE":
        return False, "INACTIVE_CREW"

    # Gate 2 — Role match (checked via pool separation in Pass 1; explicit check for Job B)
    # No check here — enforced by caller

    # Gates 3-5 — Type rating, license expiry, medical — pilots only
    # Cabin crew have no aircraft type ratings; these checks do not apply
    if crew.role == "PILOT":
        if not any(lic.aircraft_type == leg.aircraft_type for lic in licenses):
            return False, "NO_TYPE_RATING"

        rated_licenses = [lic for lic in licenses if lic.aircraft_type == leg.aircraft_type]
        if not any(lic.expiry_date >= leg_date for lic in rated_licenses):
            return False, "LICENSE_EXPIRED"

        if not any(
            lic.medical_expiry is not None and lic.medical_expiry >= leg_date
            for lic in rated_licenses
        ):
            return False, "MEDICAL_EXPIRED"

    # Gate 6 — Not on leave
    for leave in leave_records:
        if leave.start_date <= leg_date <= leave.end_date:
            return False, "ON_LEAVE"

    # Gate 7 — FTL status allows duty
    if ftl.status == "UNAVAILABLE":
        return False, "FTL_UNAVAILABLE"
    if ftl.status == "RESTING":
        if ftl.earliest_checkout is None or leg.scheduled_departure < ftl.earliest_checkout:
            return False, "IN_REST_PERIOD"

    leg_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600

    # Gate 8 — Duty period will not be breached
    report_hour = leg.scheduled_departure.hour
    limit = max_duty_hours(report_hour, sectors=ftl.sectors_current_duty + 1)
    if ftl.flight_hours_current_duty + leg_hours > limit:
        return False, "DUTY_PERIOD_BREACH"

    # Gate 9 — 7-day duty hours cap
    if ftl.duty_hours_7_day + leg_hours > 60:
        return False, "7_DAY_CAP_BREACH"

    # Gate 10 — 28-day flight hours cap
    if ftl.flight_hours_28_day + leg_hours > 100:
        return False, "28_DAY_CAP_BREACH"

    # Gate 11 — Consecutive duty days cap
    if ftl.consecutive_duty_days >= 6:
        return False, "CONSECUTIVE_DAYS_CAP"

    return True, None
