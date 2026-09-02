"""Tests for conversation/agent.py"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from crew_ops.conversation.agent import (
    route_decision, confirm_node, execute_node, format_node,
    _build_action_args, _pre_check_legality,
)
from crew_ops.conversation.tools import _classify_severity
from crew_ops.conversation.session import (
    SessionState, PendingConfirmation, PendingSimulation, _sessions
)
from crew_ops.conversation.intent import Intent


def setup_function():
    _sessions.clear()


def _make_intent(mode="QUERY", action_type=None, entities=None, ambiguous=False, clarification=None, raw="test"):
    return Intent(
        mode=mode,
        action_type=action_type,
        entities=entities or {},
        raw_message=raw,
        ambiguous=ambiguous,
        clarification_needed=clarification,
    )


def _make_state(message="test", mode="QUERY", intent=None, session=None):
    return {
        "message":  message,
        "user_id":  "ops_01",
        "session":  session or SessionState(session_id="test"),
        "intent":   intent or _make_intent(),
    }


# ─── route_decision ───────────────────────────────────────────────────────────

def test_route_ambiguous_returns_clarify():
    intent = _make_intent(ambiguous=True, clarification="Which Sharma?")
    state  = _make_state(intent=intent)
    result = route_decision(state)
    assert result == "clarify"
    # response is NOT set by route_decision — it's set by format_node
    assert "response" not in state or state.get("response") is None

def test_route_query():
    state = _make_state(intent=_make_intent(mode="QUERY"))
    assert route_decision(state) == "query"

def test_route_simulate():
    state = _make_state(intent=_make_intent(mode="SIMULATE"))
    assert route_decision(state) == "simulate"

def test_route_action():
    state = _make_state(intent=_make_intent(mode="ACTION", action_type="MARK_UNAVAILABLE"))
    assert route_decision(state) == "action"

def test_route_yes_with_pending_confirmation():
    session = SessionState(session_id="s1")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state = _make_state(message="YES", session=session, intent=_make_intent(mode="ACTION"))
    assert route_decision(state) == "confirm"

def test_route_no_with_pending_confirmation():
    session = SessionState(session_id="s1")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state = _make_state(message="NO", session=session, intent=_make_intent(mode="ACTION"))
    assert route_decision(state) == "confirm"

def test_route_apply_simulation():
    session = SessionState(session_id="s1")
    session.pending_simulation = PendingSimulation(
        crew_id="C-001", leg_id="L-001", reason="SICK_CALL", severity="HIGH"
    )
    intent = _make_intent(mode="ACTION", action_type="APPLY_SIMULATION")
    state  = _make_state(message="yes apply it", session=session, intent=intent)
    assert route_decision(state) == "action"


def test_route_unrecognised_message_with_pending_confirmation_returns_clarify():
    """Any message that is not YES/NO while a confirmation is pending must route to clarify."""
    session = SessionState(session_id="s1")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state = _make_state(message="maybe", session=session, intent=_make_intent(mode="ACTION"))
    assert route_decision(state) == "clarify"


# ─── confirm_node ─────────────────────────────────────────────────────────────

def test_confirm_node_no_cancels():
    session = SessionState(session_id="s1")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={"crew_id": "C-001"},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state = _make_state(message="NO", session=session, intent=_make_intent(mode="ACTION"))
    result = confirm_node(state)
    assert result["response"] == "Action cancelled."
    assert result["session"].pending_confirmation is None
    assert result.get("_skip_execute") is True

def test_confirm_node_yes_sets_confirmed_args():
    session = SessionState(session_id="s1")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={"crew_id": "C-001", "leg_id": "L-001", "reason": "SICK_CALL"},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    state = _make_state(message="YES", session=session, intent=_make_intent(mode="ACTION"))
    result = confirm_node(state)
    assert result["_confirmed_args"]["crew_id"] == "C-001"
    assert result["_confirmed_type"] == "MARK_UNAVAILABLE"
    assert result["session"].pending_confirmation is None

def test_confirm_node_apply_simulation_builds_confirmation():
    session = SessionState(session_id="s1")
    session.pending_simulation = PendingSimulation(
        crew_id="C-001", leg_id="L-001", reason="SICK_CALL", severity="HIGH"
    )
    intent = _make_intent(mode="ACTION", action_type="APPLY_SIMULATION")
    state  = _make_state(message="yes", session=session, intent=intent)
    with patch("crew_ops.conversation.agent.build_confirmation_package", return_value="Confirm?"):
        result = confirm_node(state)
    assert result["requires_confirmation"] is True
    assert result["session"].pending_confirmation is not None
    assert result["session"].pending_simulation is None
    assert result.get("_skip_execute") is True

def test_confirm_node_new_action_legality_fail():
    intent = _make_intent(mode="ACTION", action_type="REASSIGN",
                          entities={"leg_id": "L-001", "old_crew_id": "C-001", "new_crew_id": "C-002"})
    state  = _make_state(message="assign C-002", intent=intent)
    with patch("crew_ops.conversation.agent._pre_check_legality",
               return_value={"passed": False, "reason": "NO_TYPE_RATING"}):
        result = confirm_node(state)
    assert "NO_TYPE_RATING" in result["response"]
    assert result.get("_skip_execute") is True

def test_confirm_node_new_action_builds_package():
    intent = _make_intent(mode="ACTION", action_type="MARK_UNAVAILABLE",
                          entities={"crew_id": "C-001", "leg_id": "L-001"})
    state  = _make_state(message="mark sick", intent=intent)
    with patch("crew_ops.conversation.agent._pre_check_legality", return_value={"passed": True, "reason": None}), \
         patch("crew_ops.conversation.agent.build_confirmation_package", return_value="Confirm? [YES / NO]"):
        result = confirm_node(state)
    assert result["requires_confirmation"] is True
    assert "Confirm?" in result["response"]
    assert result["session"].pending_confirmation is not None


# ─── execute_node ─────────────────────────────────────────────────────────────

def test_execute_node_skips_when_flagged():
    state = _make_state()
    state["_skip_execute"] = True
    result = execute_node(state)
    assert "tool_result" not in result

def test_execute_node_dispatches_confirmed_action():
    state = _make_state(intent=_make_intent(mode="ACTION", action_type="MARK_UNAVAILABLE"))
    state["_confirmed_args"] = {"crew_id": "C-001", "leg_id": "L-001", "reason": "SICK_CALL"}
    state["_confirmed_type"] = "MARK_UNAVAILABLE"
    with patch("crew_ops.conversation.agent._dispatch_action",
               return_value={"status": "disruption_raised"}) as mock_dispatch:
        result = execute_node(state)
    mock_dispatch.assert_called_once_with("MARK_UNAVAILABLE", state["_confirmed_args"], "ops_01")
    assert result["tool_result"]["status"] == "disruption_raised"
    assert result["mode"] == "ACTION"

def test_execute_node_simulate_stores_pending():
    session = SessionState(session_id="s1")
    intent  = _make_intent(mode="SIMULATE", entities={"crew_id": "C-001", "leg_id": "L-001"})
    state   = _make_state(intent=intent, session=session)
    sim_result = {"candidates": [{"crew_id": "C-002", "score": 80}], "cascade_impact": []}
    with patch("crew_ops.conversation.agent._dispatch_simulate", return_value=sim_result):
        result = execute_node(state)
    assert result["mode"] == "SIMULATE"
    assert result["session"].pending_simulation is not None
    assert result["session"].pending_simulation.crew_id == "C-001"

def test_execute_node_simulate_no_pending_if_no_candidates():
    session = SessionState(session_id="s1")
    intent  = _make_intent(mode="SIMULATE", entities={"crew_id": "C-001", "leg_id": "L-001"})
    state   = _make_state(intent=intent, session=session)
    with patch("crew_ops.conversation.agent._dispatch_simulate", return_value={"candidates": []}):
        result = execute_node(state)
    assert result["session"].pending_simulation is None

def test_execute_node_query():
    intent = _make_intent(mode="QUERY", entities={"leg_id": "L-001"})
    state  = _make_state(intent=intent)
    with patch("crew_ops.conversation.agent._dispatch_query", return_value={"leg_id": "L-001"}):
        result = execute_node(state)
    assert result["mode"] == "QUERY"
    assert result["tool_result"]["leg_id"] == "L-001"


# ─── format_node ──────────────────────────────────────────────────────────────

def test_format_node_skips_if_response_set():
    state = _make_state()
    state["response"] = "Already set"
    result = format_node(state)
    assert result["response"] == "Already set"

def test_format_node_calls_formatter():
    intent = _make_intent(raw="Who is on AI305?")
    state  = _make_state(intent=intent)
    state["mode"]        = "QUERY"
    state["tool_result"] = {"leg_id": "L-001"}
    with patch("crew_ops.conversation.agent.format_response", return_value="AI305 has 4 crew."):
        result = format_node(state)
    assert result["response"] == "AI305 has 4 crew."

def test_format_node_appends_simulate_prompt():
    intent = _make_intent(mode="SIMULATE", raw="Who can replace Ravi?")
    state  = _make_state(intent=intent)
    state["mode"]        = "SIMULATE"
    state["tool_result"] = {"candidates": [{"crew_id": "C-002", "score": 80}]}
    with patch("crew_ops.conversation.agent.format_response", return_value="Top candidate: C-002."):
        result = format_node(state)
    assert "Want me to raise this as a disruption?" in result["response"]

def test_format_node_no_simulate_prompt_when_no_candidates():
    intent = _make_intent(mode="SIMULATE", raw="Who can replace Ravi?")
    state  = _make_state(intent=intent)
    state["mode"]        = "SIMULATE"
    state["tool_result"] = {"candidates": []}
    with patch("crew_ops.conversation.agent.format_response", return_value="No candidates found."):
        result = format_node(state)
    assert "Want me to raise" not in result["response"]


# ─── _build_action_args ───────────────────────────────────────────────────────

def test_build_action_args_mark_unavailable():
    intent = _make_intent(action_type="MARK_UNAVAILABLE",
                          entities={"crew_id": "C-001", "leg_id": "L-001", "reason": "SICK_CALL"})
    args = _build_action_args(intent, {})
    assert args == {"crew_id": "C-001", "leg_id": "L-001", "reason": "SICK_CALL"}

def test_build_action_args_reassign():
    intent = _make_intent(action_type="REASSIGN",
                          entities={"leg_id": "L-001", "old_crew_id": "C-001", "new_crew_id": "C-002"})
    args = _build_action_args(intent, {})
    assert args["old_crew_id"] == "C-001"
    assert args["new_crew_id"] == "C-002"

def test_build_action_args_accept_proposal():
    intent = _make_intent(action_type="ACCEPT_PROPOSAL", entities={"proposal_id": "PROP-001"})
    args = _build_action_args(intent, {})
    assert args["proposal_id"] == "PROP-001"


# ─── _pre_check_legality ──────────────────────────────────────────────────────

def test_pre_check_legality_non_reassign_always_passes():
    for action_type in ("MARK_UNAVAILABLE", "ACCEPT_PROPOSAL", "REJECT_PROPOSAL", "APPROVE_LEG"):
        intent = _make_intent(action_type=action_type)
        result = _pre_check_legality(intent, {})
        assert result["passed"] is True

def test_pre_check_legality_reassign_missing_leg():
    intent = _make_intent(action_type="REASSIGN",
                          entities={"leg_id": "MISSING", "new_crew_id": "C-002"})
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=None):
        result = _pre_check_legality(intent, {"leg_id": "MISSING", "new_crew_id": "C-002"})
    assert result["passed"] is False

def test_pre_check_legality_reassign_passes():
    from datetime import date, datetime, timezone
    intent   = _make_intent(action_type="REASSIGN",
                            entities={"leg_id": "L-001", "new_crew_id": "C-002"})
    mock_leg = MagicMock()
    mock_leg.scheduled_departure = datetime.now(timezone.utc)
    mock_crew = MagicMock()
    mock_ftl  = MagicMock()
    with patch("crew_ops.clients.flight_schedule_client.get_flight_leg", return_value=mock_leg), \
         patch("crew_ops.clients.crew_profile_client.get_crew_member", return_value=mock_crew), \
         patch("crew_ops.clients.ftl_client.get_crew_duty_state", return_value=mock_ftl), \
         patch("crew_ops.clients.license_client.get_licenses_for_crew_member", return_value=[]), \
         patch("crew_ops.clients.leave_client.get_leave_records_for_crew", return_value=[]), \
         patch("crew_ops.rules.legality.check_legality", return_value=(True, None)):
        result = _pre_check_legality(intent, {"leg_id": "L-001", "new_crew_id": "C-002"})
    assert result["passed"] is True


# ─── _dispatch_query — insufficient context ───────────────────────────────────

def test_dispatch_query_insufficient_context_returns_error():
    """No leg_id, no crew_id, no keyword — must return error dict."""
    from crew_ops.conversation.agent import _dispatch_query
    intent = _make_intent(mode="QUERY", entities={}, raw="hello")
    result = _dispatch_query(intent)
    assert "error" in result


# ─── _dispatch_simulate — insufficient entities ───────────────────────────────

def test_dispatch_simulate_insufficient_entities_returns_error():
    """No crew_id or leg_id — must return error dict."""
    from crew_ops.conversation.agent import _dispatch_simulate
    intent = _make_intent(mode="SIMULATE", entities={}, raw="what if something happens")
    result = _dispatch_simulate(intent)
    assert "error" in result


# ─── _dispatch_action — unknown action_type ───────────────────────────────────

def test_dispatch_action_unknown_type_returns_error():
    """Unrecognised action_type must return error dict, not raise."""
    from crew_ops.conversation.agent import _dispatch_action
    result = _dispatch_action("UNKNOWN_ACTION", {}, "ops_01")
    assert "error" in result
    assert "unknown" in result["error"].lower()


# ─── format_node — pending confirmation + no tool_result → clarify ────────────

def test_format_node_pending_confirmation_no_tool_result_asks_yes_no():
    """When a confirmation is pending and no tool_result is set, format_node
    must ask the user to reply YES or NO (clarify branch)."""
    from crew_ops.conversation.session import PendingConfirmation
    from datetime import datetime, timezone, timedelta
    session = SessionState(session_id="s-fmt")
    session.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    intent = _make_intent(mode="ACTION")
    state  = _make_state(intent=intent, session=session)
    # no tool_result set
    result = format_node(state)
    assert result["mode"] == "CLARIFY"
    assert "YES" in result["response"] or "yes" in result["response"].lower()
