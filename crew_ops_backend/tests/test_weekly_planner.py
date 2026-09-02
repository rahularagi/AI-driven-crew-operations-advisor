"""Tests for services/weekly_planner/weekly_planner_service.py — RosterPlanner + helpers"""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from crew_ops.services.weekly_planner.weekly_planner_service import (
    RosterPlanner, _pass1_assign_crew, _pass2_fill_reserve,
    _pass3_validate, _score_candidate, _fatigue_score,
)
from crew_ops.models.crew_member import CrewMember
from crew_ops.models.flight_leg import FlightLeg
from crew_ops.models.crew_flight_time_limits_state import CrewFlightTimeLimitsState
from crew_ops.models.crew_license import CrewLicense

_MODULE = "crew_ops.services.weekly_planner.weekly_planner_service"
_TODAY  = date.today()


def _dep(offset_days=1, hour=10):
    d = _TODAY + timedelta(days=offset_days)
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc).replace(hour=hour)


def _make_leg(leg_id="L-001", aircraft_type="B737", offset_days=1):
    dep = _dep(offset_days)
    return FlightLeg(
        leg_id=leg_id, flight_number="AI305",
        origin_iata="BOM", origin_icao="VABB",
        destination_iata="DEL", destination_icao="VIDP",
        scheduled_departure=dep,
        scheduled_arrival=dep + timedelta(hours=2),
        aircraft_type=aircraft_type, aircraft_registration="VT-001",
    )


def _make_crew(crew_id="C-001", role="PILOT", status="ACTIVE", home_base="VABB"):
    return CrewMember(
        crew_id=crew_id, employee_id=f"E-{crew_id}", full_name=f"Crew {crew_id}",
        designation="Captain", role=role, home_base=home_base,
        date_of_joining="2020-01-01", seniority_number=1,
        employment_status=status,
    )


def _make_ftl(crew_id="C-001", status="AVAILABLE", airport="VABB", **kwargs):
    defaults = dict(
        crew_id=crew_id, role="PILOT", status=status,
        home_base="VABB", current_airport=airport,
        flight_hours_current_duty=0.0, sectors_current_duty=0,
        flight_hours_28_day=0.0, duty_hours_7_day=0.0,
        duty_hours_28_day=0.0, consecutive_duty_days=0,
    )
    defaults.update(kwargs)
    return CrewFlightTimeLimitsState(**defaults)


def _mock_session_ctx():
    ctx = MagicMock()
    mock_sl = MagicMock()
    mock_sl.return_value.__enter__ = lambda s: ctx
    mock_sl.return_value.__exit__ = MagicMock(return_value=False)
    return mock_sl, ctx


# ── RosterPlanner.build ───────────────────────────────────────────────────────

def test_build_no_args_uses_today_and_settings_horizon():
    planner = RosterPlanner()
    with patch.object(planner, "_run_build") as mock_run:
        planner.build()
    args = mock_run.call_args[1]
    assert args["start"] == _TODAY


def test_build_requested_by_only_uses_same_window():
    planner = RosterPlanner()
    with patch.object(planner, "_run_build") as mock_run:
        planner.build(requested_by="manager_01")
    args = mock_run.call_args[1]
    assert args["start"] == _TODAY
    assert args["triggered_by"] == "manager_01"


def test_build_explicit_start_end():
    planner = RosterPlanner()
    s = _TODAY + timedelta(days=1)
    e = _TODAY + timedelta(days=7)
    with patch.object(planner, "_run_build") as mock_run:
        planner.build(start=s, end=e, requested_by="mgr")
    args = mock_run.call_args[1]
    assert args["start"] == s
    assert args["end"] == e


def test_build_end_before_start_raises():
    planner = RosterPlanner()
    with pytest.raises(ValueError):
        planner.build(start=_TODAY + timedelta(days=5), end=_TODAY)


def test_build_empty_legs_skips_week():
    planner = RosterPlanner()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo:
        planner.build(start=_TODAY, end=_TODAY + timedelta(days=6))
    mock_repo.upsert_roster_leg.assert_not_called()


def test_build_writes_roster_to_db():
    planner = RosterPlanner()
    leg = _make_leg()
    pilot = _make_crew("C-001", role="PILOT")
    ftl   = _make_ftl("C-001")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[pilot]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[leg]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", return_value=ftl), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.reserve_repository"):
        planner.build(start=_TODAY, end=_TODAY + timedelta(days=6))
    mock_repo.upsert_roster_leg.assert_called()
    mock_repo.upsert_roster_crew_assignment.assert_called()


def test_build_advances_simulated_ftl_across_weeks():
    planner = RosterPlanner()
    leg_w1 = _make_leg("L-001", offset_days=1)
    leg_w2 = _make_leg("L-002", offset_days=8)
    pilot  = _make_crew("C-001", role="PILOT")
    ftl    = _make_ftl("C-001")
    mock_sl, ctx = _mock_session_ctx()
    simulate_calls = []
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[pilot]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_legs_for_date_range", side_effect=[[leg_w1], [leg_w2]]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned",
               side_effect=lambda f, l: (simulate_calls.append(l), f)[1]), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository"), \
         patch(f"{_MODULE}.reserve_repository"):
        planner.build(start=_TODAY, end=_TODAY + timedelta(days=13))
    assert len(simulate_calls) >= 1


def test_build_inactive_crew_excluded():
    planner = RosterPlanner()
    leg     = _make_leg()
    inactive = _make_crew("C-INACTIVE", status="INACTIVE")
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[inactive]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[leg]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", return_value=_make_ftl()), \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository") as mock_repo, \
         patch(f"{_MODULE}.reserve_repository"):
        planner.build(start=_TODAY, end=_TODAY + timedelta(days=6))
    for c in mock_repo.upsert_roster_crew_assignment.call_args_list:
        assert c[0][1]["crew_id"] != "C-INACTIVE"


def test_build_multi_week_range():
    planner = RosterPlanner()
    mock_sl, ctx = _mock_session_ctx()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[]) as mock_legs, \
         patch(f"{_MODULE}.SessionLocal", mock_sl), \
         patch(f"{_MODULE}.roster_repository"), \
         patch(f"{_MODULE}.reserve_repository"):
        planner.build(start=_TODAY, end=_TODAY + timedelta(days=13))
    assert mock_legs.call_count == 2


# ── simulate_build ────────────────────────────────────────────────────────────

def test_simulate_build_returns_assignments_and_failures():
    planner = RosterPlanner()
    leg   = _make_leg()
    pilot = _make_crew("C-001", role="PILOT")
    ftl   = _make_ftl("C-001")
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[pilot]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[leg]), \
         patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", return_value=ftl):
        result = planner.simulate_build(_TODAY, _TODAY + timedelta(days=6))
    assert "assignments" in result
    assert "failures" in result


def test_simulate_build_no_db_write():
    planner = RosterPlanner()
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[]), \
         patch(f"{_MODULE}.SessionLocal") as mock_sl:
        planner.simulate_build(_TODAY, _TODAY + timedelta(days=6))
    mock_sl.assert_not_called()


def test_simulate_build_failures_populated_when_legality_fails():
    planner = RosterPlanner()
    leg   = _make_leg()
    pilot = _make_crew("C-001", role="PILOT")
    ftl   = _make_ftl("C-001")
    # first call (pass1) passes, second call (pass3) fails
    with patch(f"{_MODULE}.get_all_crew_members", return_value=[pilot]), \
         patch(f"{_MODULE}.get_all_licenses", return_value=[]), \
         patch(f"{_MODULE}.get_all_leave_records", return_value=[]), \
         patch(f"{_MODULE}.get_all_crew_duty_states", return_value=[ftl]), \
         patch(f"{_MODULE}.get_legs_for_date_range", return_value=[leg]), \
         patch(f"{_MODULE}.check_legality",
               side_effect=[(True, None), (False, "DUTY_PERIOD_BREACH")]), \
         patch(f"{_MODULE}.simulate_leg_assigned", return_value=ftl):
        result = planner.simulate_build(_TODAY, _TODAY + timedelta(days=6))
    assert len(result["failures"]) > 0


# ── _pass1_assign_crew ────────────────────────────────────────────────────────

def _crew_pool_b737():
    """2 pilots + 3 cabin — exactly fills a B737."""
    pilots = [_make_crew(f"P-{i}", role="PILOT") for i in range(1, 3)]
    cabin  = [_make_crew(f"CA-{i}", role="CABIN") for i in range(1, 4)]
    return pilots + cabin


def _ftl_pool(crew_list):
    return {c.crew_id: _make_ftl(c.crew_id) for c in crew_list}


def test_pass1_assigns_correct_pilot_count():
    leg  = _make_leg(aircraft_type="B737")
    crew = _crew_pool_b737()
    ftls = _ftl_pool(crew)
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], {c.crew_id: c for c in crew}, ftls, {}, {})
    pilots = [c for c in result["L-001"] if c.startswith("P-")]
    assert len(pilots) == 2


def test_pass1_assigns_correct_cabin_count():
    leg  = _make_leg(aircraft_type="B737")
    crew = _crew_pool_b737()
    ftls = _ftl_pool(crew)
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], {c.crew_id: c for c in crew}, ftls, {}, {})
    cabin = [c for c in result["L-001"] if c.startswith("CA-")]
    assert len(cabin) == 3


def test_pass1_picks_highest_scored_candidates():
    leg    = _make_leg()
    p_high = _make_crew("P-HIGH", role="PILOT")
    p_low  = _make_crew("P-LOW",  role="PILOT")
    ftl_high = _make_ftl("P-HIGH", airport="VABB")   # at origin → +40
    ftl_low  = _make_ftl("P-LOW",  airport="VIDP")   # not at origin
    crew_map = {"P-HIGH": p_high, "P-LOW": p_low}
    ftl_map  = {"P-HIGH": ftl_high, "P-LOW": ftl_low}
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], crew_map, ftl_map, {}, {})
    # B737 needs 2 pilots but we only have 2 — both assigned; high score first
    assert result["L-001"][0] == "P-HIGH"


def test_pass1_skips_crew_with_no_ftl():
    leg  = _make_leg()
    crew = _make_crew("C-001", role="PILOT")
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], {"C-001": crew}, {}, {}, {})
    assert "C-001" not in result.get("L-001", [])


def test_pass1_skips_illegal_crew():
    leg  = _make_leg()
    crew = _make_crew("C-001", role="PILOT")
    ftl  = _make_ftl("C-001")
    with patch(f"{_MODULE}.check_legality", return_value=(False, "FTL_UNAVAILABLE")), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert "C-001" not in result.get("L-001", [])


def test_pass1_updates_ftl_after_assignment():
    leg  = _make_leg()
    crew = _make_crew("C-001", role="PILOT")
    ftl  = _make_ftl("C-001")
    sim_calls = []
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned",
               side_effect=lambda f, l: (sim_calls.append(l), f)[1]):
        _pass1_assign_crew([leg], {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert len(sim_calls) == 1


def test_pass1_legs_sorted_by_departure():
    leg_late  = _make_leg("L-LATE",  offset_days=2)
    leg_early = _make_leg("L-EARLY", offset_days=1)
    crew = _make_crew("C-001", role="PILOT")
    ftl  = _make_ftl("C-001")
    processed = []
    def fake_legality(c, leg, f, lic, lv, d):
        processed.append(leg.leg_id)
        return True, None
    with patch(f"{_MODULE}.check_legality", side_effect=fake_legality), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        _pass1_assign_crew([leg_late, leg_early], {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert processed[0] == "L-EARLY"


def test_pass1_partial_fill_when_not_enough_crew():
    leg  = _make_leg(aircraft_type="B737")  # needs 2 pilots
    crew = _make_crew("C-001", role="PILOT")  # only 1 pilot
    ftl  = _make_ftl("C-001")
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)), \
         patch(f"{_MODULE}.simulate_leg_assigned", side_effect=lambda f, l: f):
        result = _pass1_assign_crew([leg], {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert "C-001" in result["L-001"]
    assert len(result["L-001"]) == 1


# ── _pass2_fill_reserve ───────────────────────────────────────────────────────

def test_pass2_creates_reserve_slots_for_unassigned_crew():
    leg  = _make_leg(offset_days=1)
    crew = _make_crew("C-001", role="PILOT", home_base="VABB")
    ftl  = _make_ftl("C-001")
    # crew not assigned to any leg
    slots = _pass2_fill_reserve([leg], {}, {"C-001": crew}, {"C-001": ftl},
                                 _TODAY, _TODAY)
    assert any(s["crew_id"] == "C-001" for s in slots)


def test_pass2_excludes_crew_already_on_duty():
    leg  = _make_leg(offset_days=0)
    crew = _make_crew("C-001", role="PILOT", home_base="VABB")
    ftl  = _make_ftl("C-001")
    assignments = {"L-001": ["C-001"]}
    slots = _pass2_fill_reserve([leg], assignments, {"C-001": crew}, {"C-001": ftl},
                                 _TODAY, _TODAY)
    assert not any(s["crew_id"] == "C-001" for s in slots)


def test_pass2_excludes_unavailable_ftl_crew():
    leg  = _make_leg(offset_days=0)
    crew = _make_crew("C-001", role="PILOT", home_base="VABB")
    ftl  = _make_ftl("C-001", status="UNAVAILABLE")
    slots = _pass2_fill_reserve([leg], {}, {"C-001": crew}, {"C-001": ftl},
                                 _TODAY, _TODAY)
    assert not any(s["crew_id"] == "C-001" for s in slots)


def test_pass2_reserve_slot_fields():
    leg  = _make_leg(offset_days=0)
    crew = _make_crew("C-001", role="PILOT", home_base="VABB")
    ftl  = _make_ftl("C-001")
    slots = _pass2_fill_reserve([leg], {}, {"C-001": crew}, {"C-001": ftl},
                                 _TODAY, _TODAY)
    slot = next(s for s in slots if s["crew_id"] == "C-001")
    assert slot["standby_start"].hour == 6
    assert slot["standby_end"].hour == 22
    assert slot["callable_within"] == 120
    assert slot["status"] == "SCHEDULED"


def test_pass2_covers_all_dates_in_range():
    crew = _make_crew("C-001", role="PILOT", home_base="VABB")
    ftl  = _make_ftl("C-001")
    start = _TODAY
    end   = _TODAY + timedelta(days=2)
    slots = _pass2_fill_reserve([], {}, {"C-001": crew}, {"C-001": ftl}, start, end)
    dates = {s["date"] for s in slots if s["crew_id"] == "C-001"}
    assert len(dates) == 3


# ── _pass3_validate ───────────────────────────────────────────────────────────

def test_pass3_returns_empty_when_all_legal():
    leg  = _make_leg()
    crew = _make_crew("C-001")
    ftl  = _make_ftl("C-001")
    with patch(f"{_MODULE}.check_legality", return_value=(True, None)):
        result = _pass3_validate([leg], {"L-001": ["C-001"]},
                                  {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert result == []


def test_pass3_returns_failure_for_illegal_assignment():
    leg  = _make_leg()
    crew = _make_crew("C-001")
    ftl  = _make_ftl("C-001")
    with patch(f"{_MODULE}.check_legality", return_value=(False, "DUTY_PERIOD_BREACH")):
        result = _pass3_validate([leg], {"L-001": ["C-001"]},
                                  {"C-001": crew}, {"C-001": ftl}, {}, {})
    assert len(result) == 1
    assert result[0]["crew_id"] == "C-001"
    assert result[0]["reason"] == "DUTY_PERIOD_BREACH"


def test_pass3_skips_missing_crew_or_ftl():
    leg = _make_leg()
    with patch(f"{_MODULE}.check_legality", return_value=(False, "X")):
        # crew_by_id and ftl_by_id both empty — should not crash
        result = _pass3_validate([leg], {"L-001": ["C-001"]}, {}, {}, {}, {})
    assert result == []


# ── _score_candidate / _fatigue_score ─────────────────────────────────────────

def test_score_at_origin_airport_adds_40():
    leg  = _make_leg()
    crew = _make_crew("C-001", home_base="VIDP")
    ftl  = _make_ftl("C-001", airport="VABB")   # at origin
    score = _score_candidate(crew, ftl, leg)
    assert score >= 40.0


def test_score_at_home_base_adds_20():
    leg  = _make_leg()
    crew = _make_crew("C-001", home_base="VABB")
    ftl  = _make_ftl("C-001", airport="VABB")   # at home base
    score = _score_candidate(crew, ftl, leg)
    assert score >= 20.0


def test_score_destination_is_home_adds_10():
    leg  = _make_leg()   # destination_icao = VIDP
    crew = _make_crew("C-001", home_base="VIDP")
    ftl  = _make_ftl("C-001", airport="VABB")
    score = _score_candidate(crew, ftl, leg)
    assert score >= 10.0


def test_score_away_from_home_both_ends_subtracts_10():
    leg  = _make_leg()   # origin=VABB, dest=VIDP
    crew = _make_crew("C-001", home_base="OMDB")  # neither end is home
    # ftl at OMDB (not at origin VABB) and zero fatigue → score = 30*(1-0) - 10 = 20
    # The -10 penalty applies; verify it is lower than a crew at origin
    ftl_away   = _make_ftl("C-001", airport="OMDB")
    ftl_origin = _make_ftl("C-001", airport="VABB")
    score_away   = _score_candidate(crew, ftl_away, leg)
    score_origin = _score_candidate(_make_crew("C-001", home_base="OMDB"), ftl_origin, leg)
    assert score_away < score_origin


def test_fatigue_score_caps_at_100():
    ftl = _make_ftl(
        flight_hours_current_duty=20.0,
        consecutive_duty_days=10,
        flight_hours_28_day=200.0,
    )
    assert _fatigue_score(ftl) == 100.0


def test_fatigue_score_zero_for_fresh_crew():
    ftl = _make_ftl(
        flight_hours_current_duty=0.0,
        consecutive_duty_days=0,
        flight_hours_28_day=0.0,
    )
    assert _fatigue_score(ftl) == 0.0


# ── _classify_severity ────────────────────────────────────────────────────────

from crew_ops.services.weekly_planner.weekly_planner_service import _classify_severity


def test_classify_severity_critical_today():
    assert _classify_severity(0) == "CRITICAL"

def test_classify_severity_critical_past():
    assert _classify_severity(-1) == "CRITICAL"

def test_classify_severity_high_1_day():
    assert _classify_severity(1) == "HIGH"

def test_classify_severity_high_2_days():
    assert _classify_severity(2) == "HIGH"

def test_classify_severity_medium_3_days():
    assert _classify_severity(3) == "MEDIUM"

def test_classify_severity_medium_7_days():
    assert _classify_severity(7) == "MEDIUM"

def test_classify_severity_low_8_days():
    assert _classify_severity(8) == "LOW"

def test_classify_severity_low_far_future():
    assert _classify_severity(30) == "LOW"
