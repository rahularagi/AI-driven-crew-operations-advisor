"""Tests for services/observer/observer_service.py"""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from crew_ops.services.observer.observer_service import FlightObserver
from crew_ops.models.flight_leg import FlightLeg
from crew_ops.models.events import FlightDisruptedEvent, LegCompletedEvent


_TODAY = date.today()


def _now():
    return datetime.now(timezone.utc)


def _make_leg(leg_id="L-001", dep_date=None, assigned_crew=None) -> FlightLeg:
    d = dep_date or _TODAY
    dep = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc).replace(hour=10)
    return FlightLeg(
        leg_id=leg_id, flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao="VIDP",
        scheduled_departure=dep,
        scheduled_arrival=dep + timedelta(hours=2),
        aircraft_type="B737", aircraft_registration="VT-001",
        assigned_crew=assigned_crew or ["C-001"],
    )


def _poll_result(status="active", delay=0, actual_arrival=None):
    return {
        "flight_status": status,
        "departure": {"delay": delay, "actual": None},
        "arrival":   {"delay": delay, "actual": actual_arrival, "iata": "DEL"},
    }


# ─── 47 ───────────────────────────────────────────────────────────────────────

def test_get_legs_by_target_date():
    obs = FlightObserver()
    today_leg     = _make_leg("L-001", dep_date=_TODAY)
    tomorrow_leg  = _make_leg("L-002", dep_date=_TODAY + timedelta(days=1))
    with patch("crew_ops.services.observer.observer_service.get_all_scheduled_legs",
               return_value=[today_leg, tomorrow_leg]):
        result = obs.get_legs(target_date=_TODAY)
    assert len(result) == 1
    assert result[0].leg_id == "L-001"


# ─── 48 ───────────────────────────────────────────────────────────────────────

def test_get_legs_by_offset():
    obs = FlightObserver()
    tomorrow_leg = _make_leg("L-002", dep_date=_TODAY + timedelta(days=1))
    today_leg    = _make_leg("L-001", dep_date=_TODAY)
    with patch("crew_ops.services.observer.observer_service.get_all_scheduled_legs",
               return_value=[today_leg, tomorrow_leg]):
        result = obs.get_legs(offset=1)
    assert len(result) == 1
    assert result[0].leg_id == "L-002"


# ─── 49 ───────────────────────────────────────────────────────────────────────

def test_get_legs_both_args_raises():
    obs = FlightObserver()
    with pytest.raises(ValueError, match="not both"):
        obs.get_legs(target_date=_TODAY, offset=1)


# ─── 50 ───────────────────────────────────────────────────────────────────────

def test_get_legs_neither_arg_raises():
    obs = FlightObserver()
    with pytest.raises(ValueError):
        obs.get_legs()


# ─── 51 ───────────────────────────────────────────────────────────────────────

def test_get_legs_assigned_crew_only_filters():
    obs = FlightObserver()
    with_crew    = _make_leg("L-001", assigned_crew=["C-001"])
    # Build a leg with empty assigned_crew by overriding the field directly
    without_crew = with_crew.model_copy(update={"leg_id": "L-002", "assigned_crew": []})
    with patch("crew_ops.services.observer.observer_service.get_all_scheduled_legs",
               return_value=[with_crew, without_crew]):
        result = obs.get_legs(target_date=_TODAY, assigned_crew_only=True)
    assert len(result) == 1
    assert result[0].leg_id == "L-001"


# ─── 52 ───────────────────────────────────────────────────────────────────────

def test_get_legs_for_range_returns_correct_window():
    obs = FlightObserver()
    start = _TODAY
    end   = _TODAY + timedelta(days=2)
    in_range  = _make_leg("L-001", dep_date=_TODAY + timedelta(days=1))
    out_range = _make_leg("L-002", dep_date=_TODAY + timedelta(days=5))
    with patch("crew_ops.services.observer.observer_service.get_all_scheduled_legs",
               return_value=[in_range, out_range]):
        result = obs.get_legs_for_range(start, end)
    assert len(result) == 1
    assert result[0].leg_id == "L-001"


# ─── 53 ───────────────────────────────────────────────────────────────────────

def test_poll_landed_publishes_leg_completed_event():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="landed", actual_arrival="2026-01-01T12:00:00+00:00")), \
         patch("crew_ops.services.observer.observer_service.reset_poll_index_for_leg"), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert len(published) == 1
    assert isinstance(published[0], LegCompletedEvent)
    assert published[0].leg_id == "L-001"


# ─── 54 ───────────────────────────────────────────────────────────────────────

def test_poll_landed_resets_poll_index():
    obs = FlightObserver()
    leg = _make_leg()
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="landed")), \
         patch("crew_ops.services.observer.observer_service.reset_poll_index_for_leg") as mock_reset, \
         patch("crew_ops.services.observer.observer_service.event_bus"):
        obs.poll(leg)
    mock_reset.assert_called_once_with("L-001")


# ─── 55 ───────────────────────────────────────────────────────────────────────

def test_poll_landed_uses_actual_arrival_when_present():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="landed", actual_arrival="2026-06-01T14:30:00+00:00")), \
         patch("crew_ops.services.observer.observer_service.reset_poll_index_for_leg"), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert published[0].actual_arrival.year == 2026


# ─── 56 ───────────────────────────────────────────────────────────────────────

def test_poll_landed_falls_back_to_now_when_no_actual():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="landed", actual_arrival=None)), \
         patch("crew_ops.services.observer.observer_service.reset_poll_index_for_leg"), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert published[0].actual_arrival is not None


# ─── 57 ───────────────────────────────────────────────────────────────────────

def test_poll_cancelled_publishes_flight_disrupted_cancellation():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="cancelled")), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert isinstance(published[0], FlightDisruptedEvent)
    assert published[0].disruption_type == "CANCELLATION"
    assert published[0].severity == "CRITICAL"


# ─── 58 ───────────────────────────────────────────────────────────────────────

def test_poll_delay_240min_publishes_high_severity():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="active", delay=240)), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert published[0].severity == "HIGH"
    assert published[0].disruption_type == "DELAY"


# ─── 59 ───────────────────────────────────────────────────────────────────────

def test_poll_delay_120min_publishes_medium_severity():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="active", delay=120)), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert published[0].severity == "MEDIUM"


# ─── 60 ───────────────────────────────────────────────────────────────────────

def test_poll_delay_30min_publishes_low_severity():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="active", delay=30)), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert published[0].severity == "LOW"


# ─── 61 ───────────────────────────────────────────────────────────────────────

def test_poll_delay_below_threshold_no_event():
    obs = FlightObserver()
    leg = _make_leg()
    published = []
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=_poll_result(status="active", delay=10)), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        obs.poll(leg)
    assert len(published) == 0


# ─── 62 ───────────────────────────────────────────────────────────────────────

def test_poll_no_result_returns_early():
    obs = FlightObserver()
    leg = _make_leg()
    with patch("crew_ops.services.observer.observer_service.get_next_live_status_poll",
               return_value=None), \
         patch("crew_ops.services.observer.observer_service.event_bus") as mock_bus:
        obs.poll(leg)
    mock_bus.publish.assert_not_called()


# ─── 63 ───────────────────────────────────────────────────────────────────────

def test_poll_all_today_calls_poll_for_each_leg():
    obs = FlightObserver()
    legs = [_make_leg("L-001"), _make_leg("L-002"), _make_leg("L-003")]
    with patch.object(obs, "get_todays_active_legs", return_value=legs), \
         patch.object(obs, "poll") as mock_poll:
        obs.poll_all_today()
    assert mock_poll.call_count == 3


# ─── 64 ───────────────────────────────────────────────────────────────────────

def test_poll_all_today_empty_legs_no_calls():
    obs = FlightObserver()
    with patch.object(obs, "get_todays_active_legs", return_value=[]), \
         patch.object(obs, "poll") as mock_poll:
        obs.poll_all_today()
    mock_poll.assert_not_called()


# ─── 65 ───────────────────────────────────────────────────────────────────────

def test_delay_severity_thresholds_exact_boundaries():
    obs = FlightObserver()
    assert obs._delay_severity(240) == "HIGH"
    assert obs._delay_severity(120) == "MEDIUM"
    assert obs._delay_severity(30)  == "LOW"
    assert obs._delay_severity(29)  is None
    assert obs._delay_severity(0)   is None


# ─── 66 — _build_disruption_event fields ─────────────────────────────────────

def test_build_disruption_event_fields():
    obs = FlightObserver()
    leg = _make_leg(assigned_crew=["C-001", "C-002"])
    poll = {
        "flight_status": "active",
        "departure": {"delay": 240, "actual": "2026-06-01T10:30:00+00:00"},
        "arrival":   {"delay": 0,   "actual": None, "iata": "DEL"},
    }
    event = obs._build_disruption_event(leg, poll, "DELAY", "HIGH")
    assert event.leg_id == "L-001"
    assert event.flight_number == "AI305"
    assert event.origin == "BOM"
    assert event.destination == "DEL"
    assert event.disruption_type == "DELAY"
    assert event.severity == "HIGH"
    assert event.delay_minutes == 240
    assert event.assigned_crew == ["C-001", "C-002"]
    assert event.actual_departure is not None


# ─── 67 — _build_disruption_event with no actual departure ───────────────────

def test_build_disruption_event_no_actual_departure():
    obs = FlightObserver()
    leg = _make_leg()
    poll = {
        "flight_status": "cancelled",
        "departure": {"delay": None, "actual": None},
        "arrival":   {"delay": 0,   "actual": None, "iata": "DEL"},
    }
    event = obs._build_disruption_event(leg, poll, "CANCELLATION", "CRITICAL")
    assert event.actual_departure is None
    assert event.disruption_type == "CANCELLATION"
    assert event.severity == "CRITICAL"


# ─── 68 — get_todays_active_legs delegates to get_legs ───────────────────────

def test_get_todays_active_legs_returns_only_assigned():
    obs = FlightObserver()
    with_crew    = _make_leg("L-001", assigned_crew=["C-001"])
    without_crew = with_crew.model_copy(update={"leg_id": "L-002", "assigned_crew": []})
    with patch("crew_ops.services.observer.observer_service.get_all_scheduled_legs",
               return_value=[with_crew, without_crew]):
        result = obs.get_todays_active_legs()
    assert len(result) == 1
    assert result[0].leg_id == "L-001"
