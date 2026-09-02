"""Tests for conversation/session.py"""
from datetime import datetime, timezone, timedelta
from crew_ops.conversation.session import (
    SessionState, PendingConfirmation, PendingSimulation,
    get_session, save_session, _sessions,
)


def setup_function():
    _sessions.clear()


def test_get_session_creates_new():
    s = get_session("s1")
    assert s.session_id == "s1"
    assert s.pending_confirmation is None
    assert s.pending_simulation is None
    assert s.last_entities == {}


def test_get_session_returns_existing():
    s1 = get_session("s2")
    s1.last_intent = "QUERY"
    save_session("s2", s1)
    s2 = get_session("s2")
    assert s2.last_intent == "QUERY"


def test_save_and_retrieve_pending_confirmation():
    s = get_session("s3")
    s.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={"crew_id": "C-001", "leg_id": "L-001", "reason": "SICK_CALL"},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    save_session("s3", s)
    loaded = get_session("s3")
    assert loaded.pending_confirmation.action_type == "MARK_UNAVAILABLE"
    assert loaded.pending_confirmation.action_args["crew_id"] == "C-001"


def test_save_and_retrieve_pending_simulation():
    s = get_session("s4")
    s.pending_simulation = PendingSimulation(
        crew_id="C-003", leg_id="L-005", reason="SICK_CALL", severity="HIGH"
    )
    save_session("s4", s)
    loaded = get_session("s4")
    assert loaded.pending_simulation.crew_id == "C-003"
    assert loaded.pending_simulation.severity == "HIGH"


def test_sessions_are_isolated():
    s_a = get_session("a")
    s_b = get_session("b")
    s_a.last_intent = "ACTION"
    save_session("a", s_a)
    assert get_session("b").last_intent is None


def test_expired_pending_confirmation_is_cleared():
    """get_session must auto-clear a PendingConfirmation whose expires_at is in the past."""
    from datetime import timedelta
    s = get_session("s-exp")
    s.pending_confirmation = PendingConfirmation(
        action_type="MARK_UNAVAILABLE",
        action_args={"crew_id": "C-001"},
        summary="Confirm?",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
    )
    save_session("s-exp", s)
    loaded = get_session("s-exp")
    assert loaded.pending_confirmation is None
