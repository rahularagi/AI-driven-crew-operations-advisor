"""Tests for conversation/tools.py"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from crew_ops_backend.conversation.tools import (
    _classify_severity,
    get_leg_status,
    get_crew_ftl,
    get_pending_proposals,
    simulate_crew_removal,
    simulate_crew_swap,
    simulate_leg_cancellation,
    action_mark_crew_unavailable,
    action_reassign_crew,
    action_accept_proposal,
    action_approve_roster_leg,
)


# ─── _classify_severity ───────────────────────────────────────────────────────

def test_severity_critical():
    assert _classify_severity(0)  == "CRITICAL"
    assert _classify_severity(-1) == "CRITICAL"

def test_severity_high():
    assert _classify_severity(1) == "HIGH"
    assert _classify_severity(2) == "HIGH"

def test_severity_medium():
    assert _classify_severity(3) == "MEDIUM"
    assert _classify_severity(7) == "MEDIUM"

def test_severity_low():
    assert _classify_severity(8)  == "LOW"
    assert _classify_severity(30) == "LOW"


# ─── get_leg_status ───────────────────────────────────────────────────────────

def test_get_leg_status_found():
    mock_leg = MagicMock()
    mock_leg.model_dump.return_value = {"leg_id": "L-001", "status": "SCHEDULED"}
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=mock_leg):
        result = get_leg_status("L-001")
    assert result["leg_id"] == "L-001"

def test_get_leg_status_not_found():
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=None):
        result = get_leg_status("MISSING")
    assert "error" in result


# ─── get_crew_ftl ─────────────────────────────────────────────────────────────

def test_get_crew_ftl_found():
    mock_ftl = MagicMock()
    mock_ftl.model_dump.return_value = {"crew_id": "C-001", "status": "AVAILABLE"}
    with patch("crew_ops_backend.conversation.tools.get_crew_duty_state", return_value=mock_ftl):
        result = get_crew_ftl("C-001")
    assert result["status"] == "AVAILABLE"

def test_get_crew_ftl_not_found():
    with patch("crew_ops_backend.conversation.tools.get_crew_duty_state", return_value=None):
        result = get_crew_ftl("MISSING")
    assert "error" in result


# ─── simulate_crew_removal ────────────────────────────────────────────────────

def test_simulate_crew_removal_delegates():
    expected = {"removed_crew": {}, "candidates": [], "cascade_impact": []}
    with patch("crew_ops_backend.conversation.tools.SimulationService") as MockSvc:
        MockSvc.return_value.simulate_crew_removal.return_value = expected
        result = simulate_crew_removal("C-001", "L-001")
    assert result == expected
    MockSvc.return_value.simulate_crew_removal.assert_called_once_with("C-001", "L-001")


def test_simulate_crew_swap_delegates():
    expected = {"swap_legal": True}
    with patch("crew_ops_backend.conversation.tools.SimulationService") as MockSvc:
        MockSvc.return_value.simulate_crew_swap.return_value = expected
        result = simulate_crew_swap("C-001", "C-002", "L-001", "L-002")
    assert result["swap_legal"] is True


def test_simulate_leg_cancellation_delegates():
    expected = {"released_crew": ["C-001"]}
    with patch("crew_ops_backend.conversation.tools.SimulationService") as MockSvc:
        MockSvc.return_value.simulate_leg_cancellation.return_value = expected
        result = simulate_leg_cancellation("L-001")
    assert result["released_crew"] == ["C-001"]


# ─── action_mark_crew_unavailable ─────────────────────────────────────────────

def test_action_mark_crew_unavailable_leg_not_found():
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=None):
        result = action_mark_crew_unavailable("C-001", "MISSING", "SICK_CALL")
    assert "error" in result

def test_action_mark_crew_unavailable_publishes_event():
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = datetime.now(timezone.utc)
    mock_crew = MagicMock()
    mock_crew.full_name = "Capt Test"
    published = []
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops_backend.conversation.tools.get_crew_member", return_value=mock_crew), \
         patch("crew_ops_backend.conversation.tools.event_bus") as mock_bus:
        mock_bus.publish.side_effect = lambda e: published.append(e)
        result = action_mark_crew_unavailable("C-001", "L-001", "SICK_CALL")
    assert result["status"] == "disruption_raised"
    assert len(published) == 1
    assert published[0].crew_id == "C-001"
    assert published[0].reason == "SICK_CALL"


# ─── action_reassign_crew ─────────────────────────────────────────────────────

def test_action_reassign_crew_legality_fail():
    mock_leg  = MagicMock()
    mock_crew = MagicMock()
    mock_ftl  = MagicMock()
    mock_leg.scheduled_departure = datetime.now(timezone.utc)
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops_backend.conversation.tools.get_crew_member", return_value=mock_crew), \
         patch("crew_ops_backend.conversation.tools.get_crew_duty_state", return_value=mock_ftl), \
         patch("crew_ops_backend.conversation.tools.get_licenses_for_crew_member", return_value=[]), \
         patch("crew_ops_backend.conversation.tools.get_leave_records_for_crew", return_value=[]), \
         patch("crew_ops_backend.conversation.tools.check_legality", return_value=(False, "FTL_UNAVAILABLE")):
        result = action_reassign_crew("L-001", "C-001", "C-002", "ops_01")
    assert "error" in result
    assert "FTL_UNAVAILABLE" in result["error"]

def test_action_reassign_crew_success():
    mock_leg  = MagicMock()
    mock_crew = MagicMock()
    mock_ftl  = MagicMock()
    mock_leg.scheduled_departure = datetime.now(timezone.utc)
    with patch("crew_ops_backend.conversation.tools.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops_backend.conversation.tools.get_crew_member", return_value=mock_crew), \
         patch("crew_ops_backend.conversation.tools.get_crew_duty_state", return_value=mock_ftl), \
         patch("crew_ops_backend.conversation.tools.get_licenses_for_crew_member", return_value=[]), \
         patch("crew_ops_backend.conversation.tools.get_leave_records_for_crew", return_value=[]), \
         patch("crew_ops_backend.conversation.tools.check_legality", return_value=(True, None)), \
         patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.roster_repository") as mock_repo, \
         patch("crew_ops_backend.conversation.tools.event_bus"):
        mock_sl.return_value.__enter__ = lambda s: MagicMock()
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        result = action_reassign_crew("L-001", "C-001", "C-002", "ops_01")
    assert result["status"] == "reassigned"
    assert result["removed"] == "C-001"
    assert result["added"] == "C-002"


# ─── action_accept_proposal ───────────────────────────────────────────────────

def test_action_accept_proposal_not_found():
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.disruption_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.accept_proposal.return_value = {}
        result = action_accept_proposal("PROP-MISSING", "ops_01")
    assert "error" in result

def test_action_accept_proposal_no_candidate():
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.disruption_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.accept_proposal.return_value = {
            "leg_id": "L-001", "removed_crew_id": "C-001", "proposed_crew_id": None
        }
        result = action_accept_proposal("PROP-001", "ops_01")
    assert result["status"] == "accepted"
    assert result["added"] is None
    assert "manual" in result["note"]


# ─── action_approve_roster_leg ────────────────────────────────────────────────

def test_action_approve_roster_leg():
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.roster_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        result = action_approve_roster_leg("L-001", "ops_01")
    assert result["status"] == "published"
    assert result["leg_id"] == "L-001"
    assert result["approved_by"] == "ops_01"


# ─── get_pending_proposals ────────────────────────────────────────────────────

def test_get_pending_proposals_delegates_to_repository():
    expected = [{"proposal_id": "PROP-001", "status": "PENDING"}]
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.disruption_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_pending_proposals.return_value = expected
        result = get_pending_proposals()
    assert result == expected
    mock_repo.get_pending_proposals.assert_called_once_with(ctx)


# ─── get_crew_schedule ────────────────────────────────────────────────────────

def test_get_crew_schedule_delegates_to_repository():
    from crew_ops_backend.conversation.tools import get_crew_schedule
    expected = [{"leg_id": "L-001", "crew_id": "C-001"}]
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.roster_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_future_assignments.return_value = expected
        result = get_crew_schedule("C-001", date(2026, 1, 1), date(2026, 1, 7))
    assert result == expected


# ─── get_roster ───────────────────────────────────────────────────────────────

def test_get_roster_delegates_to_repository():
    from crew_ops_backend.conversation.tools import get_roster
    expected = [{"leg_id": "L-001"}]
    with patch("crew_ops_backend.conversation.tools.SessionLocal") as mock_sl, \
         patch("crew_ops_backend.conversation.tools.roster_repository") as mock_repo:
        ctx = MagicMock()
        mock_sl.return_value.__enter__ = lambda s: ctx
        mock_sl.return_value.__exit__ = MagicMock(return_value=False)
        mock_repo.get_roster_for_date_range.return_value = expected
        result = get_roster(date(2026, 1, 1), date(2026, 1, 7))
    assert result == expected


# ─── action_reject_proposal ───────────────────────────────────────────────────

def test_action_reject_proposal_delegates_to_disruption_handler():
    from crew_ops_backend.conversation.tools import action_reject_proposal
    expected = {"status": "rejected", "next_candidate": "C-002"}
    with patch("crew_ops_backend.services.disruption_handler.disruption_handler_service.DisruptionHandler") as MockDH:
        MockDH.return_value.reject_and_repropose.return_value = expected
        result = action_reject_proposal("PROP-001", "ops_01", "wrong candidate")
    assert result == expected
    MockDH.return_value.reject_and_repropose.assert_called_once_with(
        "PROP-001", "ops_01", "wrong candidate"
    )
