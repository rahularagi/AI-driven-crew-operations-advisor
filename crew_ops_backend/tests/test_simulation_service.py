"""Tests for services/simulation/simulation_service.py"""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from crew_ops_backend.services.simulation.simulation_service import SimulationService


def _make_leg(leg_id="L-001", aircraft_type="B737", assigned_crew=None):
    leg = MagicMock()
    leg.leg_id = leg_id
    leg.aircraft_type = aircraft_type
    leg.assigned_crew = assigned_crew or ["C-001", "C-002"]
    dep = datetime.now(timezone.utc) + timedelta(hours=3)
    leg.scheduled_departure = dep
    leg.scheduled_arrival   = dep + timedelta(hours=2)
    leg.origin_icao         = "VABB"
    leg.destination_icao    = "VIDP"
    leg.model_dump.return_value = {"leg_id": leg_id}
    return leg


def _make_crew(crew_id="C-001", role="PILOT", home_base="VABB", status="ACTIVE"):
    crew = MagicMock()
    crew.crew_id           = crew_id
    crew.role              = role
    crew.home_base         = home_base
    crew.employment_status = status
    crew.model_dump.return_value = {"crew_id": crew_id}
    return crew


def _make_ftl(crew_id="C-001", airport="VABB", status="AVAILABLE"):
    ftl = MagicMock()
    ftl.crew_id                  = crew_id
    ftl.status                   = status
    ftl.current_airport          = airport
    ftl.flight_hours_current_duty = 0.0
    ftl.consecutive_duty_days    = 0
    ftl.flight_hours_28_day      = 0.0
    ftl.earliest_checkout        = None
    return ftl


# ─── simulate_crew_removal ────────────────────────────────────────────────────

def test_simulate_crew_removal_leg_not_found():
    svc = SimulationService()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=None), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=_make_crew()):
        result = svc.simulate_crew_removal("C-001", "MISSING")
    assert "error" in result

def test_simulate_crew_removal_crew_not_found():
    svc = SimulationService()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=_make_leg()), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=None):
        result = svc.simulate_crew_removal("MISSING", "L-001")
    assert "error" in result

def test_simulate_crew_removal_returns_structure():
    svc  = SimulationService()
    leg  = _make_leg()
    crew = _make_crew()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=leg), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=crew), \
         patch.object(svc, "_find_and_rank_candidates_in_memory", return_value=[
             {"crew": _make_crew("C-002"), "score": 80.0},
             {"crew": _make_crew("C-003"), "score": 60.0},
         ]), \
         patch.object(svc, "_check_cascade_impact", return_value=[]):
        result = svc.simulate_crew_removal("C-001", "L-001")
    assert "removed_crew" in result
    assert "candidates" in result
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["score"] == 80.0

def test_simulate_crew_removal_excludes_removed_crew():
    """The removed crew must not appear in their own replacement candidates."""
    svc  = SimulationService()
    leg  = _make_leg()
    crew = _make_crew("C-001", role="PILOT")
    # Two candidates: C-001 (should be excluded) and C-002
    all_crew = [_make_crew("C-001"), _make_crew("C-002")]
    ftl_c001 = _make_ftl("C-001")
    ftl_c002 = _make_ftl("C-002")
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=leg), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=crew), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_members", return_value=all_crew), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[ftl_c001, ftl_c002]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_leave_records", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.check_legality", return_value=(True, None)), \
         patch("crew_ops_backend.services.simulation.simulation_service._score_candidate", return_value=50.0), \
         patch.object(svc, "_check_cascade_impact", return_value=[]):
        result = svc.simulate_crew_removal("C-001", "L-001")
    candidate_ids = [c["crew_id"] for c in result["candidates"]]
    assert "C-001" not in candidate_ids


# ─── simulate_crew_swap ───────────────────────────────────────────────────────

def test_simulate_crew_swap_missing_leg():
    svc = SimulationService()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=None), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=_make_crew()):
        result = svc.simulate_crew_swap("C-001", "C-002", "L-001", "L-002")
    assert "error" in result

def test_simulate_crew_swap_missing_ftl():
    svc   = SimulationService()
    leg_a = _make_leg("L-001")
    leg_b = _make_leg("L-002")
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", side_effect=[leg_a, leg_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", return_value=_make_crew()), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[]):
        result = svc.simulate_crew_swap("C-001", "C-002", "L-001", "L-002")
    assert "error" in result

def test_simulate_crew_swap_both_legal():
    svc   = SimulationService()
    leg_a = _make_leg("L-001")
    leg_b = _make_leg("L-002")
    crew_a = _make_crew("C-001")
    crew_b = _make_crew("C-002")
    ftl_a  = _make_ftl("C-001")
    ftl_b  = _make_ftl("C-002")
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", side_effect=[leg_a, leg_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", side_effect=[crew_a, crew_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[ftl_a, ftl_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_leave_records", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.check_legality", return_value=(True, None)):
        result = svc.simulate_crew_swap("C-001", "C-002", "L-001", "L-002")
    assert result["swap_legal"] is True
    assert result["crew_a_on_leg_b"]["passed"] is True
    assert result["crew_b_on_leg_a"]["passed"] is True

def test_simulate_crew_swap_one_illegal():
    svc   = SimulationService()
    leg_a = _make_leg("L-001")
    leg_b = _make_leg("L-002")
    crew_a = _make_crew("C-001")
    crew_b = _make_crew("C-002")
    ftl_a  = _make_ftl("C-001")
    ftl_b  = _make_ftl("C-002")
    # crew_a legal on leg_b, crew_b illegal on leg_a
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", side_effect=[leg_a, leg_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_crew_member", side_effect=[crew_a, crew_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[ftl_a, ftl_b]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_leave_records", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.check_legality", side_effect=[(True, None), (False, "NO_TYPE_RATING")]):
        result = svc.simulate_crew_swap("C-001", "C-002", "L-001", "L-002")
    assert result["swap_legal"] is False
    assert result["crew_b_on_leg_a"]["reason"] == "NO_TYPE_RATING"


# ─── simulate_leg_cancellation ────────────────────────────────────────────────

def test_simulate_leg_cancellation_not_found():
    svc = SimulationService()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=None):
        result = svc.simulate_leg_cancellation("MISSING")
    assert "error" in result

def test_simulate_leg_cancellation_returns_structure():
    svc = SimulationService()
    leg = _make_leg(assigned_crew=["C-001", "C-002"])
    mock_session = MagicMock()
    mock_repo    = MagicMock()
    mock_repo.get_future_assignments.return_value = []
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=leg), \
         patch("crew_ops_backend.services.simulation.simulation_service.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.services.simulation.simulation_service.roster_repository", mock_repo):
        mock_sl.return_value.__enter__ = lambda s: mock_session
        mock_sl.return_value.__exit__  = MagicMock(return_value=False)
        result = svc.simulate_leg_cancellation("L-001")
    assert result["released_crew"] == ["C-001", "C-002"]
    assert "next_assignments" in result
    assert "ftl_hours_freed" in result
    assert result["next_assignments"]["C-001"] is None

def test_simulate_leg_cancellation_excludes_self():
    """The cancelled leg itself must not appear in next_assignments."""
    svc = SimulationService()
    leg = _make_leg("L-001", assigned_crew=["C-001"])
    future_assignments = [{"leg_id": "L-001", "crew_id": "C-001"}, {"leg_id": "L-002", "crew_id": "C-001"}]
    mock_repo = MagicMock()
    mock_repo.get_future_assignments.return_value = future_assignments
    with patch("crew_ops_backend.services.simulation.simulation_service.get_flight_leg", return_value=leg), \
         patch("crew_ops_backend.services.simulation.simulation_service.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.services.simulation.simulation_service.roster_repository", mock_repo):
        mock_sl.return_value.__enter__ = lambda s: MagicMock()
        mock_sl.return_value.__exit__  = MagicMock(return_value=False)
        result = svc.simulate_leg_cancellation("L-001")
    # next assignment should be L-002, not L-001
    assert result["next_assignments"]["C-001"]["leg_id"] == "L-002"


# ─── _find_and_rank_candidates_in_memory ─────────────────────────────────────

def test_find_candidates_excludes_inactive():
    svc  = SimulationService()
    leg  = _make_leg()
    inactive = _make_crew("C-INACTIVE", status="INACTIVE")
    active   = _make_crew("C-ACTIVE",   status="ACTIVE")
    ftl      = _make_ftl("C-ACTIVE")
    with patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_members", return_value=[inactive, active]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[ftl]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_leave_records", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.check_legality", return_value=(True, None)), \
         patch("crew_ops_backend.services.simulation.simulation_service._score_candidate", return_value=50.0):
        results = svc._find_and_rank_candidates_in_memory("PILOT", leg)
    ids = [r["crew"].crew_id for r in results]
    assert "C-INACTIVE" not in ids
    assert "C-ACTIVE" in ids

def test_find_candidates_no_mutable_default():
    """Ensure exclude=None default doesn't share state across calls."""
    svc = SimulationService()
    leg = _make_leg()
    with patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_members", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_crew_duty_states", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_licenses", return_value=[]), \
         patch("crew_ops_backend.services.simulation.simulation_service.get_all_leave_records", return_value=[]):
        r1 = svc._find_and_rank_candidates_in_memory("PILOT", leg)
        r2 = svc._find_and_rank_candidates_in_memory("PILOT", leg)
    assert r1 == r2 == []
