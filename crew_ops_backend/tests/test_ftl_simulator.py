"""Tests for rules/ftl_simulator.py"""
from datetime import datetime, timezone, timedelta, date

from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.rules.ftl_simulator import simulate_leg_assigned, simulate_rest_after_leg


_TODAY = date.today()
_DEP   = datetime.combine(_TODAY, datetime.min.time()).replace(tzinfo=timezone.utc).replace(hour=10)
_ARR   = _DEP + timedelta(hours=3)


def _leg(dep=None, arr=None, dest="VIDP") -> FlightLeg:
    d = dep or _DEP
    a = arr or _ARR
    return FlightLeg(
        leg_id="L-001", flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao=dest,
        scheduled_departure=d, scheduled_arrival=a,
        aircraft_type="B737", aircraft_registration="VT-001",
    )


def _ftl(**kwargs) -> CrewFlightTimeLimitsState:
    defaults = dict(
        crew_id="C-001", role="PILOT", status="AVAILABLE",
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )
    defaults.update(kwargs)
    return CrewFlightTimeLimitsState(**defaults)


# ─── 132 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_increments_flight_hours():
    result = simulate_leg_assigned(_ftl(), _leg())
    assert abs(result.flight_hours_current_duty - 3.0) < 0.01
    assert abs(result.flight_hours_28_day - 3.0) < 0.01


# ─── 133 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_increments_sectors():
    result = simulate_leg_assigned(_ftl(sectors_current_duty=1), _leg())
    assert result.sectors_current_duty == 2


# ─── 134 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_updates_current_airport():
    result = simulate_leg_assigned(_ftl(), _leg(dest="VIDP"))
    assert result.current_airport == "VIDP"


# ─── 135 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_increments_consecutive_days_new_day():
    yesterday_dep = _DEP - timedelta(days=1)
    ftl = _ftl(duty_start_time=yesterday_dep, consecutive_duty_days=1)
    result = simulate_leg_assigned(ftl, _leg())
    assert result.consecutive_duty_days == 2


# ─── 136 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_no_consecutive_day_same_day():
    ftl = _ftl(duty_start_time=_DEP - timedelta(hours=1), consecutive_duty_days=1)
    result = simulate_leg_assigned(ftl, _leg())
    assert result.consecutive_duty_days == 1


# ─── 137 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_sets_projected_duty_end():
    result = simulate_leg_assigned(_ftl(), _leg())
    assert result.projected_duty_period_end is not None
    assert result.projected_duty_period_end > _DEP


# ─── 138 ──────────────────────────────────────────────────────────────────────

def test_simulate_leg_assigned_does_not_mutate_original():
    original = _ftl()
    original_hours = original.flight_hours_current_duty
    simulate_leg_assigned(original, _leg())
    assert original.flight_hours_current_duty == original_hours


# ─── 139 ──────────────────────────────────────────────────────────────────────

def test_simulate_rest_after_leg_resets_duty_counters():
    ftl = _ftl(
        duty_start_time=_DEP - timedelta(hours=5),
        flight_hours_current_duty=5.0,
        sectors_current_duty=2,
    )
    result = simulate_rest_after_leg(ftl, _leg())
    assert result.flight_hours_current_duty == 0.0
    assert result.sectors_current_duty == 0


# ─── 140 ──────────────────────────────────────────────────────────────────────

def test_simulate_rest_after_leg_sets_available_status():
    ftl = _ftl(duty_start_time=_DEP - timedelta(hours=5))
    result = simulate_rest_after_leg(ftl, _leg())
    assert result.status == "AVAILABLE"


# ─── 141 ──────────────────────────────────────────────────────────────────────

def test_simulate_rest_after_leg_minimum_rest_11h():
    # duty duration = 3h (less than 11h) → min_rest must be 11h
    ftl = _ftl(duty_start_time=_DEP)
    result = simulate_rest_after_leg(ftl, _leg())
    rest_hours = (result.earliest_checkout - result.rest_start_time).total_seconds() / 3600
    assert abs(rest_hours - 11.0) < 0.01


# ─── 142 ──────────────────────────────────────────────────────────────────────

def test_simulate_rest_after_leg_rest_equals_duty_when_longer():
    # duty duration = 14h (more than 11h) → min_rest = 14h
    # leg arrives at _ARR; duty started 14h before _ARR so duty_duration = 14h
    long_dep = _ARR - timedelta(hours=14)
    ftl = _ftl(duty_start_time=long_dep)
    result = simulate_rest_after_leg(ftl, _leg())
    rest_hours = (result.earliest_checkout - result.rest_start_time).total_seconds() / 3600
    assert abs(rest_hours - 14.0) < 0.1
