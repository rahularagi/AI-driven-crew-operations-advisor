from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional


class PendingSimulation(BaseModel):
    crew_id:  str
    leg_id:   str
    reason:   str
    severity: str


class PendingConfirmation(BaseModel):
    action_type: str   # MARK_UNAVAILABLE / REASSIGN / ACCEPT_PROPOSAL / REJECT_PROPOSAL / APPROVE_LEG
    action_args: dict  # exact args passed to the action tool on confirm
    summary:     str   # human-readable summary shown before confirmation
    expires_at:  datetime


class SessionState(BaseModel):
    session_id:           str
    last_intent:          Optional[str] = None
    last_entities:        dict = {}
    pending_confirmation: Optional[PendingConfirmation] = None
    pending_simulation:   Optional[PendingSimulation]   = None


_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id=session_id)
    session = _sessions[session_id]
    # Expire stale pending confirmations so they are never silently acted on
    if session.pending_confirmation and session.pending_confirmation.expires_at < datetime.now(timezone.utc):
        session.pending_confirmation = None
        _sessions[session_id] = session
    return session


def save_session(session_id: str, state: SessionState) -> None:
    _sessions[session_id] = state
