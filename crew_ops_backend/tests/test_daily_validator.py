"""Tests for services/weekly_planner/weekly_planner_service.py — DailyValidator"""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

from crew_ops_backend.services.weekly_planner.weekly_planner_service import DailyValidator
from crew_ops_backend.models.crew_member import CrewMember
from crew_ops_backend.models.flight_leg import FlightLeg
from crew_ops_backend.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops_backend.models.events import CrewDisruptedEvent, RosterModifiedEvent

_MODULE = "crew_ops_backend.services.weekly_planner.weekly_planner_service"
_TODAY  = date.today()


def _dep(offset_days=1):
    d = _TODAY + timedelta(days=offset_days)
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc).replace(hour=10)


def _make_leg(leg_id="L-001", offset_days=1):
    dep = _dep(offset_days)
    return FlightLeg(
        leg_id=leg_id, flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao="VIDP",
        scheduled_departure=dep,
        scheduled_arrival=dep + timedelta(hours=2),
        aircraft_type="B737", aircraft_registration="VT-001",
    )


def _make_crew(crew_id="C-001"):
    return CrewMember(
        crew_id=crew_id, employee_id="E-001", full_name="Test Crew",
        designation="Captain", role="PILOT", home_base="VABB",
        date_of_joining="2020-01-01", seniority_number=1,
        employment_status="ACTIVE",
    )


def _make_ftl(crew_id="C-001"):
    return CrewFlightTimeLimitsState(
        crew_id=crew_id, role="PILOT", status="AVAILABLE",
        home_base="VABB", current_airport="VABB",
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )


def _mock_session_ctx():
    ctx = MagicMock()
    mock_sl = MagicMock()
    mock_sl.return_value.__enter__ = lambda s: ctx
    mock_sl.return_value.__exit__ = MagicMock(return_value=False)
    return mock_sl, ctx


def _base_patches(mock_sl, leg, crew, ftl, legality=(True, None), assignments=None):
    if assignments is None:
        assignments = [{"leg_id": leg.leg_id, "crew_id": crew.crew_id}]
    return {
        f"{_MODULE}.get_all_crew_members":   [crew],
        f"{_MODULE}.get_all_crew_duty_states": [ftl],
        f"{_MODULE}.get_all_licenses":       [],
        f"{_MODULE}.get_all_leave_records":  [],
        f"{_MODULE}.get_flight_leg":         leg,
        f"{_MODULE}.check_legality":         legality,
        f"{_MODULE}.SessionLocal":           mock_sl,
    }


# ── validate ──────────────────────────────────────────────────────────────────

def test_validate_publishes_crew_disrupted_for_illegal_assignment():
    validator = DailyValidator()
    leg  = _make_leg(offset_days=1)
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        mock_bus.publish.side_effect = lambda e: published.append(e)
        validator.validate()
    assert any(isinstance(e, CrewDisruptedEvent) for e in published)


def test_validate_no_event_when_all_legal():
    validator = DailyValidator()
    leg  = _make_leg()
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        validator.validate()
    mock_bus.publish.assert_not_called()


def test_validate_skips_missing_leg():
    validator = DailyValidator()
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=None), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-MISSING", "crew_id": "C-001"}
        ]
        validator.validate()
    mock_bus.publish.assert_not_called()


def test_validate_skips_missing_crew():
    validator = DailyValidator()
    leg = _make_leg()
    ftl = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-MISSING"}
        ]
        validator.validate()
    mock_bus.publish.assert_not_called()


def test_validate_skips_missing_ftl():
    validator = DailyValidator()
    leg  = _make_leg()
    crew = _make_crew()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        validator.validate()
    mock_bus.publish.assert_not_called()


def test_validate_severity_critical_for_today():
    validator = DailyValidator()
    leg  = _make_leg(offset_days=0)   # today
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        mock_bus.publish.side_effect = lambda e: published.append(e)
        validator.validate()
    event = next(e for e in published if isinstance(e, CrewDisruptedEvent))
    assert event.severity == "CRITICAL"


def test_validate_severity_low_for_far_future():
    validator = DailyValidator()
    leg  = _make_leg(offset_days=30)
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        mock_bus.publish.side_effect = lambda e: published.append(e)
        validator.validate()
    event = next(e for e in published if isinstance(e, CrewDisruptedEvent))
    assert event.severity == "LOW"


def test_validate_source_is_weekly_planner_validator():
    validator = DailyValidator()
    leg  = _make_leg()
    crew = _make_crew()
    ftl  = _make_ftl()
    mock_sl, ctx = _mock_session_ctx()
    published = []
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[crew]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_flight_leg", return_value=leg), \
         patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.event_bus") as mock_bus:
        mock_repo.get_future_assignments.return_value = [
            {"leg_id": "L-001", "crew_id": "C-001"}
        ]
        mock_bus.publish.side_effect = lambda e: published.append(e)
        validator.validate()
    event = next(e for e in published if isinstance(e, CrewDisruptedEvent))
    assert event.source == "WEEKLY_PLANNER_VALIDATOR"


# ── on_roster_modified ────────────────────────────────────────────────────────

def test_on_roster_modified_triggers_validation_for_added_crew():
    validator = DailyValidator()
    event = RosterModifiedEvent(
        leg_id="L-001", added_crew_id="C-002",
        removed_crew_id=None, modified_at=datetime.now(timezone.utc),
    )
    with patch.object(validator, "_run_validation") as mock_run:
        validator.on_roster_modified(event)
    mock_run.assert_called_once_with(triggered_by="ROSTER_MODIFIED", crew_id="C-002")


def test_on_roster_modified_triggers_validation_for_removed_crew():
    validator = DailyValidator()
    event = RosterModifiedEvent(
        leg_id="L-001", removed_crew_id="C-001",
        added_crew_id=None, modified_at=datetime.now(timezone.utc),
    )
    with patch.object(validator, "_run_validation") as mock_run:
        validator.on_roster_modified(event)
    mock_run.assert_called_once_with(triggered_by="ROSTER_MODIFIED", crew_id="C-001")


def test_on_roster_modified_both_crew_ids():
    validator = DailyValidator()
    event = RosterModifiedEvent(
        leg_id="L-001", removed_crew_id="C-001",
        added_crew_id="C-002", modified_at=datetime.now(timezone.utc),
    )
    with patch.object(validator, "_run_validation") as mock_run:
        validator.on_roster_modified(event)
    assert mock_run.call_count == 2


def test_on_roster_modified_none_crew_ids_no_call():
    validator = DailyValidator()
    event = RosterModifiedEvent(
        leg_id="L-001", removed_crew_id=None,
        added_crew_id=None, modified_at=datetime.now(timezone.utc),
    )
    with patch.object(validator, "_run_validation") as mock_run:
        validator.on_roster_modified(event)
    mock_run.assert_not_called()
