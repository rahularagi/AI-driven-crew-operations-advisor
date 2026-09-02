"""Tests for services/flight_time_limits/flight_time_limits_service.py"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from crew_ops.services.flight_time_limits.flight_time_limits_service import FlightTimeLimitsService
from crew_ops.models.events import LegCompletedEvent, RosterModifiedEvent
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState


def _now():
    return datetime.now(timezone.utc)


def _ftl(crew_id="C-001", status="AVAILABLE", **kwargs) -> CrewFlightTimeLimitsState:
    defaults = dict(
        crew_id=crew_id, role="PILOT", status=status,
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )
    defaults.update(kwargs)
    return CrewFlightTimeLimitsState(**defaults)


def _leg_completed_event(crew=None, dest="VIDP"):
    return LegCompletedEvent(
        leg_id="L-001", actual_arrival=_now(),
        destination=dest, crew=crew or ["C-001"], delay_minutes=0,
    )


def _roster_modified_event(removed=None, added=None):
    return RosterModifiedEvent(
        leg_id="L-001", removed_crew_id=removed,
        added_crew_id=added, modified_at=_now(),
    )


# ─── on_leg_completed ─────────────────────────────────────────────────────────

def test_on_leg_completed_increments_flight_hours():
    svc = FlightTimeLimitsService()
    ftl = _ftl()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event())
    assert updated[0].flight_hours_current_duty > 0
    assert updated[0].flight_hours_28_day > 0


def test_on_leg_completed_increments_sectors():
    svc = FlightTimeLimitsService()
    ftl = _ftl(sectors_current_duty=1)
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event())
    assert updated[0].sectors_current_duty == 2


def test_on_leg_completed_updates_current_airport():
    svc = FlightTimeLimitsService()
    ftl = _ftl()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event(dest="VIDP"))
    assert updated[0].current_airport == "VIDP"


def test_on_leg_completed_sets_resting_status():
    svc = FlightTimeLimitsService()
    ftl = _ftl()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event())
    assert updated[0].status == "RESTING"


def test_on_leg_completed_home_rest_when_at_home_base():
    svc = FlightTimeLimitsService()
    ftl = _ftl()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event(dest="VABB"))
    assert updated[0].rest_type == "HOME_REST"
    assert updated[0].earliest_checkout is None


def test_on_leg_completed_hotel_rest_when_away():
    svc = FlightTimeLimitsService()
    ftl = _ftl()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event(dest="VIDP"))
    assert updated[0].rest_type == "HOTEL_REST"
    assert updated[0].earliest_checkout is not None


def test_on_leg_completed_skips_crew_with_no_ftl():
    svc = FlightTimeLimitsService()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=None), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state") as mock_update:
        svc.on_leg_completed(_leg_completed_event())
    mock_update.assert_not_called()


def test_on_leg_completed_calls_update_for_each_crew():
    svc = FlightTimeLimitsService()
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = _now() - timedelta(hours=2)
    mock_leg.scheduled_arrival   = _now()
    mock_crew = MagicMock()
    mock_crew.home_base = "VABB"
    ftl_a = _ftl("C-001")
    ftl_b = _ftl("C-002")
    ftl_c = _ftl("C-003")
    updated = []
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state",
               side_effect=[ftl_a, ftl_b, ftl_c]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_leg_completed(_leg_completed_event(crew=["C-001", "C-002", "C-003"]))
    assert len(updated) == 3


# ─── on_roster_modified ───────────────────────────────────────────────────────

def test_on_roster_modified_removed_crew_set_unavailable():
    svc = FlightTimeLimitsService()
    ftl = _ftl("C-001", status="AVAILABLE")
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_roster_modified(_roster_modified_event(removed="C-001"))
    assert updated[0].status == "UNAVAILABLE"


def test_on_roster_modified_added_crew_set_available():
    svc = FlightTimeLimitsService()
    ftl = _ftl("C-002", status="UNAVAILABLE")
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_roster_modified(_roster_modified_event(added="C-002"))
    assert updated[0].status == "AVAILABLE"
    assert updated[0].duty_start_time is not None


def test_on_roster_modified_none_removed_no_update_for_removed():
    svc = FlightTimeLimitsService()
    ftl = _ftl("C-002")
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_roster_modified(_roster_modified_event(added="C-002"))
    # only one update — for added crew
    assert len(updated) == 1
    assert updated[0].status == "AVAILABLE"


def test_on_roster_modified_none_added_no_update_for_added():
    svc = FlightTimeLimitsService()
    ftl = _ftl("C-001")
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=ftl), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.on_roster_modified(_roster_modified_event(removed="C-001"))
    assert len(updated) == 1
    assert updated[0].status == "UNAVAILABLE"


def test_on_roster_modified_skips_missing_ftl():
    svc = FlightTimeLimitsService()
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_crew_duty_state", return_value=None), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state") as mock_update:
        svc.on_roster_modified(_roster_modified_event(removed="C-001", added="C-002"))
    mock_update.assert_not_called()


# ─── run_proactive_alert_scan ─────────────────────────────────────────────────

def test_proactive_scan_duty_period_approaching_alert():
    svc = FlightTimeLimitsService()
    ftl = _ftl(status="AVAILABLE",
               projected_duty_period_end=_now() + timedelta(hours=1))
    published = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        svc.run_proactive_alert_scan()
    assert any(e.alert_type == "DUTY_PERIOD_APPROACHING" for e in published)


def test_proactive_scan_no_alert_when_duty_period_far():
    svc = FlightTimeLimitsService()
    ftl = _ftl(status="AVAILABLE",
               projected_duty_period_end=_now() + timedelta(hours=5))
    published = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        svc.run_proactive_alert_scan()
    assert not any(e.alert_type == "DUTY_PERIOD_APPROACHING" for e in published)


def test_proactive_scan_cumulative_hours_warning():
    svc = FlightTimeLimitsService()
    ftl = _ftl(flight_hours_28_day=95.0)
    published = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        svc.run_proactive_alert_scan()
    assert any(e.alert_type == "CUMULATIVE_HOURS_WARNING" for e in published)


def test_proactive_scan_weekly_rest_overdue():
    svc = FlightTimeLimitsService()
    ftl = _ftl(last_weekly_rest_end=_now() - timedelta(days=7))
    published = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        svc.run_proactive_alert_scan()
    assert any(e.alert_type == "WEEKLY_REST_OVERDUE" for e in published)


def test_proactive_scan_no_alert_for_unavailable_crew():
    svc = FlightTimeLimitsService()
    ftl = _ftl(status="UNAVAILABLE",
               projected_duty_period_end=_now() + timedelta(hours=1))
    published = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        svc.run_proactive_alert_scan()
    assert not any(e.alert_type == "DUTY_PERIOD_APPROACHING" for e in published)


# ─── run_midnight_recalculation ───────────────────────────────────────────────

def test_midnight_recalc_resets_crew_after_rest():
    svc = FlightTimeLimitsService()
    ftl = _ftl(
        status="RESTING",
        earliest_checkout=_now() - timedelta(hours=1),
        flight_hours_current_duty=5.0,
        sectors_current_duty=3,
    )
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.run_midnight_recalculation()
    assert updated[0].status == "AVAILABLE"
    assert updated[0].flight_hours_current_duty == 0.0
    assert updated[0].sectors_current_duty == 0


def test_midnight_recalc_skips_crew_not_resting():
    svc = FlightTimeLimitsService()
    ftl = _ftl(status="AVAILABLE", earliest_checkout=_now() - timedelta(hours=1))
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state") as mock_update:
        svc.run_midnight_recalculation()
    mock_update.assert_not_called()


def test_midnight_recalc_skips_crew_with_no_checkout():
    svc = FlightTimeLimitsService()
    ftl = _ftl(status="RESTING", earliest_checkout=None)
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[ftl]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state") as mock_update:
        svc.run_midnight_recalculation()
    mock_update.assert_not_called()


def test_midnight_recalc_calls_update_for_each_eligible_crew():
    svc = FlightTimeLimitsService()
    eligible   = _ftl("C-001", status="RESTING", earliest_checkout=_now() - timedelta(hours=1))
    ineligible = _ftl("C-002", status="AVAILABLE")
    updated = []
    with patch("crew_ops.services.flight_time_limits.flight_time_limits_service.get_all_crew_duty_states",
               return_value=[eligible, ineligible]), \
         patch("crew_ops.services.flight_time_limits.flight_time_limits_service.update_crew_duty_state",
               side_effect=lambda f: updated.append(f)):
        svc.run_midnight_recalculation()
    assert len(updated) == 1
    assert updated[0].crew_id == "C-001"
