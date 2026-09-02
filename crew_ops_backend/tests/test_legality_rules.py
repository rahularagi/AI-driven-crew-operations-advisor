"""Tests for rules/legality.py — all 11 gates"""
from datetime import date, datetime, timezone, timedelta

import pytest

from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.models.crew_license import CrewLicense
from crew_ops_backend.models.crew_leave import CrewLeaveRecord
from crew_ops_backend.rules.legality import check_legality


_TODAY = date.today()
_DEP   = datetime.combine(_TODAY, datetime.min.time()).replace(tzinfo=timezone.utc).replace(hour=10)
_ARR   = _DEP + timedelta(hours=2)


def _crew(role="PILOT", status="ACTIVE") -> CrewMember:
    return CrewMember(
        crew_id="C-001", employee_id="E-001", full_name="Test Crew",
        designation="Captain", role=role, home_base="VABB",
        date_of_joining="2020-01-01", seniority_number=1,
        employment_status=status,
    )


def _leg(aircraft_type="B737") -> FlightLeg:
    return FlightLeg(
        leg_id="L-001", flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao="VIDP",
        scheduled_departure=_DEP, scheduled_arrival=_ARR,
        aircraft_type=aircraft_type, aircraft_registration="VT-001",
    )


def _ftl(status="AVAILABLE", **kwargs) -> CrewFlightTimeLimitsState:
    defaults = dict(
        crew_id="C-001", role="PILOT", status=status,
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )
    defaults.update(kwargs)
    return CrewFlightTimeLimitsState(**defaults)


def _license(aircraft_type="B737", expiry_offset=365, medical_offset=365) -> CrewLicense:
    return CrewLicense(
        crew_id="C-001", aircraft_type=aircraft_type,
        expiry_date=_TODAY + timedelta(days=expiry_offset),
        medical_expiry=_TODAY + timedelta(days=medical_offset),
    )


def _leave(start_offset=10, end_offset=20) -> CrewLeaveRecord:
    return CrewLeaveRecord(
        crew_id="C-001", leave_type="ANNUAL",
        start_date=_TODAY + timedelta(days=start_offset),
        end_date=_TODAY + timedelta(days=end_offset),
    )


# ─── 118 — Gate 1 ─────────────────────────────────────────────────────────────

def test_inactive_crew_fails():
    passed, reason = check_legality(_crew(status="INACTIVE"), _leg(), _ftl(), [_license()], [], _TODAY)
    assert not passed
    assert reason == "INACTIVE_CREW"


# ─── 119 — Gate 3 ─────────────────────────────────────────────────────────────

def test_pilot_no_type_rating_fails():
    passed, reason = check_legality(_crew(), _leg(aircraft_type="B787"), _ftl(), [_license("B737")], [], _TODAY)
    assert not passed
    assert reason == "NO_TYPE_RATING"


# ─── 120 — Gate 4 ─────────────────────────────────────────────────────────────

def test_pilot_license_expired_fails():
    expired_lic = _license(expiry_offset=-1)
    passed, reason = check_legality(_crew(), _leg(), _ftl(), [expired_lic], [], _TODAY)
    assert not passed
    assert reason == "LICENSE_EXPIRED"


# ─── 121 — Gate 5 ─────────────────────────────────────────────────────────────

def test_pilot_medical_expired_fails():
    lic = CrewLicense(
        crew_id="C-001", aircraft_type="B737",
        expiry_date=_TODAY + timedelta(days=365),
        medical_expiry=_TODAY - timedelta(days=1),
    )
    passed, reason = check_legality(_crew(), _leg(), _ftl(), [lic], [], _TODAY)
    assert not passed
    assert reason == "MEDICAL_EXPIRED"


# ─── 122 — Gates 3-5 skipped for cabin ───────────────────────────────────────

def test_cabin_crew_skips_type_rating_check():
    # cabin crew with no licenses at all — should still pass gates 3-5
    passed, reason = check_legality(_crew(role="CABIN"), _leg(), _ftl(), [], [], _TODAY)
    assert passed
    assert reason is None


# ─── 123 — Gate 6 ─────────────────────────────────────────────────────────────

def test_on_leave_fails():
    leave = CrewLeaveRecord(
        crew_id="C-001", leave_type="ANNUAL",
        start_date=_TODAY, end_date=_TODAY + timedelta(days=5),
    )
    passed, reason = check_legality(_crew(), _leg(), _ftl(), [_license()], [leave], _TODAY)
    assert not passed
    assert reason == "ON_LEAVE"


# ─── 124 — Gate 7a ────────────────────────────────────────────────────────────

def test_ftl_unavailable_fails():
    passed, reason = check_legality(_crew(), _leg(), _ftl(status="UNAVAILABLE"), [_license()], [], _TODAY)
    assert not passed
    assert reason == "FTL_UNAVAILABLE"


# ─── 125 — Gate 7b ────────────────────────────────────────────────────────────

def test_in_rest_period_fails():
    checkout = _DEP + timedelta(hours=2)  # checkout is after departure
    ftl = _ftl(status="RESTING", earliest_checkout=checkout)
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "IN_REST_PERIOD"


# ─── 126 — Gate 7b passes after checkout ─────────────────────────────────────

def test_in_rest_period_passes_after_checkout():
    checkout = _DEP - timedelta(hours=1)  # checkout is before departure
    ftl = _ftl(status="RESTING", earliest_checkout=checkout)
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert passed
    assert reason is None


# ─── 127 — Gate 8 ─────────────────────────────────────────────────────────────

def test_duty_period_breach_fails():
    # leg is 2h, current duty already at 12h — morning window limit is 13h for 1 sector
    ftl = _ftl(flight_hours_current_duty=12.0)
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "DUTY_PERIOD_BREACH"


# ─── 128 — Gate 9 ─────────────────────────────────────────────────────────────

def test_7_day_cap_breach_fails():
    ftl = _ftl(duty_hours_7_day=59.0)  # 59 + 2h leg = 61 > 60
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "7_DAY_CAP_BREACH"


# ─── 129 — Gate 10 ────────────────────────────────────────────────────────────

def test_28_day_cap_breach_fails():
    ftl = _ftl(flight_hours_28_day=99.0)  # 99 + 2h = 101 > 100
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "28_DAY_CAP_BREACH"


# ─── 130 — Gate 11 ────────────────────────────────────────────────────────────

def test_consecutive_days_cap_fails():
    ftl = _ftl(consecutive_duty_days=6)
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "CONSECUTIVE_DAYS_CAP"


# ─── 131 — All gates pass ─────────────────────────────────────────────────────

def test_all_gates_pass_returns_true():
    passed, reason = check_legality(_crew(), _leg(), _ftl(), [_license()], [], _TODAY)
    assert passed
    assert reason is None


# ─── 132 — Gate 7b: RESTING with no checkout time ────────────────────────────

def test_resting_with_no_checkout_fails():
    """RESTING + earliest_checkout=None must return IN_REST_PERIOD (no TypeError)."""
    ftl = _ftl(status="RESTING", earliest_checkout=None)
    passed, reason = check_legality(_crew(), _leg(), ftl, [_license()], [], _TODAY)
    assert not passed
    assert reason == "IN_REST_PERIOD"
