"""Tests for rules/duty_period_limits.py — all 4 windows, sector capping, boundaries."""
import pytest
from crew_ops_backend.rules.duty_period_limits import max_duty_hours, _duty_start_window


# ─── Window classification ────────────────────────────────────────────────────

def test_window_night_boundary_start():
    assert _duty_start_window(0) == "night"

def test_window_night_boundary_end():
    assert _duty_start_window(5) == "night"

def test_window_morning_boundary_start():
    assert _duty_start_window(6) == "morning"

def test_window_morning_boundary_end():
    assert _duty_start_window(13) == "morning"

def test_window_afternoon_boundary_start():
    assert _duty_start_window(14) == "afternoon"

def test_window_afternoon_boundary_end():
    assert _duty_start_window(17) == "afternoon"

def test_window_evening_boundary_start():
    assert _duty_start_window(18) == "evening"

def test_window_evening_boundary_end():
    assert _duty_start_window(23) == "evening"


# ─── max_duty_hours — night window ───────────────────────────────────────────

def test_night_1_sector():
    assert max_duty_hours(2, 1) == 11.0

def test_night_2_sectors():
    assert max_duty_hours(2, 2) == 10.5

def test_night_3_sectors():
    assert max_duty_hours(2, 3) == 10.0

def test_night_4_sectors():
    assert max_duty_hours(2, 4) == 9.5


# ─── max_duty_hours — morning window ─────────────────────────────────────────

def test_morning_1_sector():
    assert max_duty_hours(8, 1) == 13.0

def test_morning_2_sectors():
    assert max_duty_hours(8, 2) == 12.5

def test_morning_3_sectors():
    assert max_duty_hours(8, 3) == 12.0

def test_morning_4_sectors():
    assert max_duty_hours(8, 4) == 11.5


# ─── max_duty_hours — afternoon window ───────────────────────────────────────

def test_afternoon_1_sector():
    assert max_duty_hours(15, 1) == 12.0

def test_afternoon_2_sectors():
    assert max_duty_hours(15, 2) == 11.5

def test_afternoon_3_sectors():
    assert max_duty_hours(15, 3) == 11.0

def test_afternoon_4_sectors():
    assert max_duty_hours(15, 4) == 10.5


# ─── max_duty_hours — evening window ─────────────────────────────────────────

def test_evening_1_sector():
    assert max_duty_hours(20, 1) == 11.5

def test_evening_2_sectors():
    assert max_duty_hours(20, 2) == 11.0

def test_evening_3_sectors():
    assert max_duty_hours(20, 3) == 10.5

def test_evening_4_sectors():
    assert max_duty_hours(20, 4) == 10.0


# ─── Sector capping ───────────────────────────────────────────────────────────

def test_sectors_below_1_capped_to_1():
    """sectors=0 must behave identically to sectors=1."""
    assert max_duty_hours(8, 0) == max_duty_hours(8, 1)

def test_sectors_above_4_capped_to_4():
    """sectors=10 must behave identically to sectors=4."""
    assert max_duty_hours(8, 10) == max_duty_hours(8, 4)

def test_sectors_exactly_4_not_capped():
    assert max_duty_hours(8, 4) == 11.5

def test_sectors_exactly_1_not_capped():
    assert max_duty_hours(8, 1) == 13.0
