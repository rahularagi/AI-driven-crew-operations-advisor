from pydantic import BaseModel
from typing import Literal, Optional
from crew_ops.conversation.session import SessionState


class Intent(BaseModel):
    mode:                 Literal["QUERY", "SIMULATE", "ACTION"]
    action_type:          Optional[str] = None  # MARK_UNAVAILABLE / REASSIGN / ACCEPT_PROPOSAL / REJECT_PROPOSAL / APPROVE_LEG / APPLY_SIMULATION
    entities:             dict = {}             # crew_id, leg_id, flight_number, date
    raw_message:          str
    ambiguous:            bool = False
    clarification_needed: Optional[str] = None


_SYSTEM_PROMPT = """\
You are an airline operations assistant. Classify the user message into one of three modes:

QUERY    — user wants to read information. No change to the system.
SIMULATE — user wants to explore a what-if scenario. No change to the system.
ACTION   — user wants to make a change that modifies the roster or crew state.

Extract all entities: crew names, flight numbers, dates, airports.
Resolve crew names to crew_id using the provided crew list.
If a name matches multiple crew members, set ambiguous=true and clarification_needed.

ACTION types:
  MARK_UNAVAILABLE   — mark a crew member sick / unavailable for a leg
  REASSIGN           — directly assign a specific replacement (human already decided)
  ACCEPT_PROPOSAL    — accept a pending disruption proposal
  REJECT_PROPOSAL    — reject a pending disruption proposal
  APPROVE_LEG        — approve a DRAFT roster leg to PUBLISHED

If the message is affirmative ("yes", "apply it", "do it", "go ahead", "confirm") AND
there is a pending_simulation in the session context, set mode=ACTION and action_type=APPLY_SIMULATION.

Return JSON matching the Intent schema exactly. Do not add extra fields.
"""


def classify_intent(message: str, session: SessionState, crew_list: list[dict]) -> Intent:
    from crew_ops.conversation.formatter import _get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = _get_llm().with_structured_output(Intent)

    system = _SYSTEM_PROMPT + f"\n\nCrew list:\n{crew_list}"
    if session.pending_simulation:
        system += f"\n\nPending simulation context: {session.pending_simulation.model_dump()}"
    if session.last_entities:
        system += f"\n\nLast known entities (reuse if not re-specified): {session.last_entities}"

    return llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=message),
    ])
