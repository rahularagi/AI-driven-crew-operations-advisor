"""Integration tests for POST /chat endpoint."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from crew_ops.api.main import app
from crew_ops.conversation.session import _sessions
from crew_ops.conversation.push_queue import _push_queue

client = TestClient(app)


def setup_function():
    _sessions.clear()
    _push_queue.clear()


def _chat(session_id: str, message: str, user_id: str = "ops_01") -> dict:
    resp = client.post("/chat", json={
        "session_id": session_id,
        "message":    message,
        "user_id":    user_id,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


# ─── QUERY flow ───────────────────────────────────────────────────────────────

def test_chat_query_returns_response():
    mock_intent = MagicMock()
    mock_intent.mode        = "QUERY"
    mock_intent.action_type = None
    mock_intent.entities    = {"leg_id": "L-001"}
    mock_intent.raw_message = "What is the status of AI305?"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._dispatch_query", return_value={"leg_id": "L-001", "status": "SCHEDULED"}), \
         patch("crew_ops.conversation.agent.format_response", return_value="AI305 is scheduled."):
        data = _chat("sess-q1", "What is the status of AI305?")

    assert data["mode"] == "QUERY"
    assert "AI305" in data["response"]
    assert data["requires_confirmation"] is False


# ─── CLARIFY flow ─────────────────────────────────────────────────────────────

def test_chat_clarify_returns_question():
    mock_intent = MagicMock()
    mock_intent.mode        = "QUERY"
    mock_intent.action_type = None
    mock_intent.entities    = {}
    mock_intent.raw_message = "Mark Sharma as sick"
    mock_intent.ambiguous   = True
    mock_intent.clarification_needed = "Multiple crew named Sharma. Which one?"

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent):
        data = _chat("sess-c1", "Mark Sharma as sick")

    assert data["mode"] == "CLARIFY"
    assert "Sharma" in data["response"]
    assert data["requires_confirmation"] is False


# ─── SIMULATE flow ────────────────────────────────────────────────────────────

def test_chat_simulate_returns_candidates_and_prompt():
    mock_intent = MagicMock()
    mock_intent.mode        = "SIMULATE"
    mock_intent.action_type = None
    mock_intent.entities    = {"crew_id": "C-003", "leg_id": "L-005"}
    mock_intent.raw_message = "If Capt Ravi is sick, who covers AI305?"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    sim_result = {
        "removed_crew": {"crew_id": "C-003"},
        "candidates":   [{"crew_id": "C-007", "score": 87}],
        "cascade_impact": [],
    }

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._dispatch_simulate", return_value=sim_result), \
         patch("crew_ops.conversation.agent.format_response", return_value="Top candidate: C-007."):
        data = _chat("sess-s1", "If Capt Ravi is sick, who covers AI305?")

    assert data["mode"] == "SIMULATE"
    assert "Want me to raise this as a disruption?" in data["response"]
    assert data["requires_confirmation"] is False

    # Session should have pending_simulation stored
    from crew_ops.conversation.session import get_session
    session = get_session("sess-s1")
    assert session.pending_simulation is not None
    assert session.pending_simulation.crew_id == "C-003"


# ─── ACTION → confirm → execute flow ─────────────────────────────────────────

def test_chat_action_requires_confirmation():
    mock_intent = MagicMock()
    mock_intent.mode        = "ACTION"
    mock_intent.action_type = "MARK_UNAVAILABLE"
    mock_intent.entities    = {"crew_id": "C-003", "leg_id": "L-005", "reason": "SICK_CALL"}
    mock_intent.raw_message = "Mark Capt Ravi as sick for AI305"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._pre_check_legality", return_value={"passed": True, "reason": None}), \
         patch("crew_ops.conversation.agent.build_confirmation_package",
               return_value="Capt Ravi will be marked unavailable. Confirm? [YES / NO]"):
        data = _chat("sess-a1", "Mark Capt Ravi as sick for AI305")

    assert data["mode"] == "ACTION"
    assert data["requires_confirmation"] is True
    assert "Confirm?" in data["response"]


def test_chat_action_yes_executes():
    from crew_ops.conversation.session import get_session, save_session, SessionState, PendingConfirmation

    # Pre-seed session with pending confirmation
    session = get_session("sess-a2")
    session.pending_confirmation = PendingConfirmation(
        action_type = "MARK_UNAVAILABLE",
        action_args = {"crew_id": "C-003", "leg_id": "L-005", "reason": "SICK_CALL"},
        summary     = "Confirm?",
        expires_at  = datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    save_session("sess-a2", session)

    mock_intent = MagicMock()
    mock_intent.mode        = "ACTION"
    mock_intent.action_type = "MARK_UNAVAILABLE"
    mock_intent.entities    = {}
    mock_intent.raw_message = "YES"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    action_result = {"status": "disruption_raised", "crew_id": "C-003", "leg_id": "L-005", "severity": "CRITICAL"}

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._dispatch_action", return_value=action_result), \
         patch("crew_ops.conversation.agent.format_response", return_value="Disruption raised. Proposal pending."):
        data = _chat("sess-a2", "YES")

    assert data["mode"] == "ACTION"
    assert "Disruption" in data["response"]
    # Pending confirmation should be cleared
    assert get_session("sess-a2").pending_confirmation is None


def test_chat_action_no_cancels():
    from crew_ops.conversation.session import get_session, save_session, PendingConfirmation

    session = get_session("sess-a3")
    session.pending_confirmation = PendingConfirmation(
        action_type = "MARK_UNAVAILABLE",
        action_args = {"crew_id": "C-003", "leg_id": "L-005", "reason": "SICK_CALL"},
        summary     = "Confirm?",
        expires_at  = datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    save_session("sess-a3", session)

    mock_intent = MagicMock()
    mock_intent.mode        = "ACTION"
    mock_intent.action_type = None
    mock_intent.entities    = {}
    mock_intent.raw_message = "NO"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent):
        data = _chat("sess-a3", "NO")

    assert data["response"] == "Action cancelled."
    assert get_session("sess-a3").pending_confirmation is None


# ─── SIMULATE → apply it flow ─────────────────────────────────────────────────

def test_chat_simulate_then_apply():
    from crew_ops.conversation.session import get_session, save_session, PendingSimulation

    # Step 1: simulate
    session = get_session("sess-sim1")
    session.pending_simulation = PendingSimulation(
        crew_id="C-003", leg_id="L-005", reason="SICK_CALL", severity="HIGH"
    )
    save_session("sess-sim1", session)

    mock_intent = MagicMock()
    mock_intent.mode        = "ACTION"
    mock_intent.action_type = "APPLY_SIMULATION"
    mock_intent.entities    = {}
    mock_intent.raw_message = "yes apply it"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent.build_confirmation_package",
               return_value="Capt Ravi will be marked unavailable. Confirm? [YES / NO]"):
        data = _chat("sess-sim1", "yes apply it")

    assert data["requires_confirmation"] is True
    assert "Confirm?" in data["response"]
    # pending_simulation cleared, pending_confirmation set
    s = get_session("sess-sim1")
    assert s.pending_simulation is None
    assert s.pending_confirmation is not None
    assert s.pending_confirmation.action_type == "MARK_UNAVAILABLE"


# ─── Push queue drain ─────────────────────────────────────────────────────────

def test_chat_drains_push_queue():
    _push_queue.append("ALERT: AI305 disruption — Capt Ravi sick. Confirm Vikram?")

    mock_intent = MagicMock()
    mock_intent.mode        = "QUERY"
    mock_intent.action_type = None
    mock_intent.entities    = {}
    mock_intent.raw_message = "show roster"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._dispatch_query", return_value=[]), \
         patch("crew_ops.conversation.agent.format_response", return_value="Roster is empty."):
        data = _chat("sess-push1", "show roster")

    assert "[ALERT]" in data["response"]
    assert "AI305" in data["response"]
    assert len(_push_queue) == 0  # queue drained


# ─── Legality fail before confirmation ────────────────────────────────────────

def test_chat_action_legality_fail_no_confirmation():
    mock_intent = MagicMock()
    mock_intent.mode        = "ACTION"
    mock_intent.action_type = "REASSIGN"
    mock_intent.entities    = {"leg_id": "L-001", "old_crew_id": "C-001", "new_crew_id": "C-002"}
    mock_intent.raw_message = "Assign C-002 instead of C-001 on L-001"
    mock_intent.ambiguous   = False
    mock_intent.clarification_needed = None

    with patch("crew_ops.conversation.agent.classify_intent", return_value=mock_intent), \
         patch("crew_ops.conversation.agent._pre_check_legality",
               return_value={"passed": False, "reason": "NO_TYPE_RATING"}):
        data = _chat("sess-legal1", "Assign C-002 instead of C-001 on L-001")

    assert data["requires_confirmation"] is False
    assert "NO_TYPE_RATING" in data["response"]
