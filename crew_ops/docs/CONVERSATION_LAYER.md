# Conversation Layer — End to End Implementation

---

## What This Service Does

The Conversation Layer is the **only entry point for human interaction** with the system.

It translates free-text requests into structured intents, routes them to the right service, and returns human-readable responses. All four existing services (Weekly Planner, Observer, Disruption Handler, FTL Service) remain completely unaware of the human. They never change. The Conversation Layer sits in front of them as a thin translation and routing layer.

Three things it does:

1. **Classify intent** — is this a query, a simulation, or an action?
2. **Execute** — call the right pure-Python functions (legality check, candidate ranking, roster read) or write APIs
3. **Format response** — narrate the result in plain English

One thing it explicitly does NOT do: implement any business logic. Every legality check, FTL calculation, candidate score, and roster write already exists. The Conversation Layer only calls what is already built.

---

## Package Structure

The Conversation Layer lives in its own package, completely separate from the four services.

```
crew_ops/
└── conversation/
    ├── __init__.py
    ├── agent.py                  ← LangGraph graph definition, entry point
    ├── intent.py                 ← Intent dataclass + classifier prompt
    ├── tools.py                  ← All tool functions (read + write)
    ├── formatter.py              ← LLM response formatting
    ├── session.py                ← Per-session state (pending confirmations, context)
    └── router.py                 ← FastAPI router — POST /chat
```

No imports from `conversation/` into any existing service. The dependency arrow is one-way: `conversation/` imports from services, never the reverse.

---

## Architecture

```
Human (chat / UI)
      │
      ▼  POST /chat  { session_id, message }
┌─────────────────────────────────────────────────────────────┐
│  CONVERSATION LAYER  (LangGraph agent)                      │
│                                                             │
│  1. Intent Classifier  →  QUERY / SIMULATE / ACTION        │
│  2. Router             →  selects tool set for intent       │
│  3. Tool Executor      →  calls pure-Python functions       │
│  4. Response Formatter →  LLM narrates result               │
│                                                             │
│  Session state: pending confirmations, last query context   │
└──────┬──────────┬──────────┬──────────┬────────────────────┘
       │          │          │          │
       ▼          ▼          ▼          ▼
   Roster     Disruption  Planner    FTL
   (read)     (write)     (simulate) (read)
```

The LangGraph graph has four nodes:

```
classify_intent → route → execute_tools → format_response
                    │
                    └── (ACTION only) → build_confirmation → await_confirm → execute_tools
```

---

## Three Interaction Modes

### Mode 1 — QUERY (read only, no confirmation)

Examples:
- "What is the status of AI305?"
- "Who is assigned to AI101 tomorrow?"
- "Show me Capt Mehta's schedule this week"
- "How many hours does FO Sharma have left this month?"

Flow:
```
classify_intent → QUERY
      ↓
execute read-only tools
      ↓
format_response (LLM narrates)
      ↓
return response
```

No state change. No confirmation. No pending anything.

---

### Mode 2 — SIMULATE (what-if, no confirmation)

Examples:
- "If Capt Ravi is not available tomorrow, who can replace him?"
- "What happens if AI305 gets cancelled?"
- "If I swap Capt Mehta and FO Sharma on AI202, is that legal?"

Flow:
```
classify_intent → SIMULATE
      ↓
run in-memory only — no DB writes
      ↓
legality check (pure Python)
      ↓
cascade impact check (pure Python)
      ↓
rank replacement options (pure Python)
      ↓
format_response — LLM narrates outcome
      ↓
append "Want me to raise this as a disruption?" to response
      ↓
store {crew_id, leg_id, reason, severity} in session as pending_simulation
      ↓
return response
```

No DB write. Session state stores the simulation context so the next turn can act on it.

--- next turn: human says "yes, apply it" ---

```
classify_intent → detects pending_simulation in session → ACTION
      ↓
publish CrewDisruptedEvent(crew_id, leg_id, reason, severity)
      ↓
DisruptionHandler.handle_crew_disrupted() runs full pipeline:
    _find_and_rank_candidates()  — legality check + scoring for all crew
    _create_proposal()           — writes PENDING row to disruption_proposals table
      ↓
response: "Disruption raised. Proposal PROP-xxx is now pending approval in the inbox."
```

"Apply it" does not bypass the Disruption Handler. It triggers it — identical to what happens when the Observer detects a disruption automatically. The proposal lands in the disruption inbox as PENDING and goes through the normal confirm/reject approval flow from there.

---

### Mode 3 — ACTION (writes to system, requires confirmation)

Examples:
- "Mark Capt Ravi as sick for today"
- "Assign FO Deepa to AI305 instead of FO Sharma"
- "Swap Capt Mehta and Capt Nisha on tomorrow's flights"

Flow:
```
classify_intent → ACTION
      ↓
legality check (pure Python) — fail fast before showing confirmation
      ↓
cascade impact check (pure Python)
      ↓
build_confirmation_package — LLM writes the summary
      ↓
present to human: "Here is what will change. Confirm? [YES / NO]"
      ↓
human confirms
      ↓
execute service call (write to DB)
      ↓
event emitted → pipeline runs (Disruption Handler, FTL Service, Validator)
      ↓
format_response — LLM narrates what changed
      ↓
return response
```

If legality fails before confirmation, the agent returns the failure reason and stops. No confirmation shown for an illegal action.

---

## System-Initiated Decisions (Push to Human)

When the Disruption Handler creates a PENDING proposal with severity HIGH or CRITICAL, the system pushes it to the human without waiting for them to ask.

This is a separate flow from the three modes above. It is triggered by a background job that polls `disruption_proposals` for new PENDING proposals and pushes them into the active session (or a notification queue if no session is open).

```
Disruption Handler creates PENDING proposal
      ↓
severity check:
  CRITICAL → push immediately, auto-escalate after 15 min if no response
  HIGH     → push immediately, 1hr window
  MEDIUM   → push to human, 4hr window
  LOW      → auto-resolve if clean replacement found, notify only
      ↓
format_push_notification — LLM writes the alert message:
  "AI305 BOM→CCU departs in 90min. Capt Ravi called sick.
   Best replacement: Capt Vikram (reserve at BOM, FTL legal).
   Second option: FO Nair (deadhead from DEL, adds 45min to duty period).
   Confirm Capt Vikram? [YES / NO / SHOW MORE OPTIONS]"
      ↓
human responds YES / NO / SHOW MORE OPTIONS
      ↓
YES  → POST /disruptions/proposals/{id}/accept
NO   → POST /disruptions/proposals/{id}/reject  → next candidate pushed
SHOW → fetch next 2 candidates, re-format, push again
```

The push notification is formatted by the LLM using the same `formatter.py` used for regular responses. The data (proposal, leg, candidates) comes from `disruption_repository.get_pending_proposals()` — already built.

---

## What LLM Does vs Pure Python

| Task | Who |
|------|-----|
| Classify intent from free text | LLM |
| Extract entities (crew name, flight number, date) | LLM |
| Detect ambiguity ("which Sharma?") | LLM |
| Legality check (hard gates 1–11) | Pure Python — `rules/legality.py` |
| Cascade impact check | Pure Python — `rules/legality.py` + `rules/ftl_simulator.py` |
| Fatigue score calculation | Pure Python — `_fatigue_score()` in disruption handler |
| Rank replacement candidates | Pure Python — `_score_candidate()` in disruption handler |
| Write confirmation package narrative | LLM |
| Format final response | LLM |
| Apply the actual change | Pure Python — service call via `tools.py` |
| Proposal expiry / escalation timing | Pure Python — APScheduler job |

The LLM never touches numbers. It only reads structured results and writes natural language.

---

## Intent Classifier

The classifier is a single LLM call with a structured output schema. It runs first on every message.

```python
# conversation/intent.py

from pydantic import BaseModel
from typing import Literal
from crew_ops.conversation.session import SessionState


class Intent(BaseModel):
    mode:                 Literal["QUERY", "SIMULATE", "ACTION"]
    action_type:          str | None    # MARK_UNAVAILABLE / REASSIGN / SWAP / APPROVE / APPLY_SIMULATION
    entities:             dict          # crew_id, leg_id, flight_number, date — extracted from message
    raw_message:          str
    ambiguous:            bool
    clarification_needed: str | None


_SYSTEM_PROMPT = """
You are an airline operations assistant. Classify the user's message into one of three modes:

QUERY    — user wants to read information. No change to the system.
SIMULATE — user wants to explore a what-if scenario. No change to the system.
ACTION   — user wants to make a change that modifies the roster or crew state.

Extract all entities mentioned: crew names, flight numbers, dates, airports.
Resolve crew names to crew_id using the provided crew list.
If a name is ambiguous (multiple matches), set ambiguous=true and clarification_needed.

If the message is affirmative ("yes", "apply it", "do it", "go ahead") and there is a
pending_simulation in the session, set mode=ACTION and action_type=APPLY_SIMULATION.

Return JSON matching the Intent schema exactly.
"""


def classify_intent(message: str, session: SessionState, crew_list: list[dict]) -> Intent:
    from crew_ops.conversation.formatter import _get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    llm    = _get_llm().with_structured_output(Intent)
    system = _SYSTEM_PROMPT + f"\n\nCrew list:\n{crew_list}"
    if session.pending_simulation:
        system += f"\n\nPending simulation: {session.pending_simulation.model_dump()}"

    return llm.invoke([
        SystemMessage(content=system),
        HumanMessage(content=message),
    ])
```

---

## Structural Rules

Before reading the tool definitions, three rules govern where logic lives:

1. `conversation/tools.py` contains **thin wrappers only** — no business logic, no candidate ranking, no legality checks. Every tool delegates to an existing service or repository.
2. **Reject + repropose pipeline** lives in `DisruptionHandler.reject_and_repropose()` — not in tools.py. The action tool calls it in one line.
3. **In-memory simulation logic** (`_find_and_rank_candidates_in_memory`, `_check_cascade_impact`) lives in `services/simulation/simulation_service.py` — not in tools.py. The simulate tools call it in one line.

---

## Tool Definitions

All tools are pure functions in `conversation/tools.py`. They call existing clients, repositories, and services. No business logic lives here.

### Read Tools (QUERY + SIMULATE)

```python
def get_leg_status(leg_id: str) -> dict:
    """Returns current leg data including status, delay, assigned crew."""
    leg = get_flight_leg(leg_id)
    return leg.model_dump() if leg else {"error": "leg not found"}


def get_crew_schedule(crew_id: str, start: date, end: date) -> list[dict]:
    """Returns all assignments for a crew member in a date range."""
    with SessionLocal() as session:
        return roster_repository.get_future_assignments(session, start, end, crew_id=crew_id)


def get_crew_ftl(crew_id: str) -> dict:
    """Returns current FTL state for a crew member."""
    ftl = get_crew_duty_state(crew_id)
    return ftl.model_dump() if ftl else {"error": "FTL state not found"}


def get_pending_proposals() -> list[dict]:
    """Returns all PENDING disruption proposals sorted by severity."""
    with SessionLocal() as session:
        return disruption_repository.get_pending_proposals(session)


def get_roster(start: date, end: date) -> list[dict]:
    """Returns full roster for a date range."""
    with SessionLocal() as session:
        return roster_repository.get_roster_for_date_range(session, start, end)
```

### Simulate Tools (SIMULATE only — in-memory, no DB write)

All simulation logic lives in `services/simulation/simulation_service.py`. These tools are one-line delegates.

```python
def simulate_crew_removal(crew_id: str, leg_id: str) -> dict:
    """
    Simulates removing a crew member from a leg.
    Returns: removed crew, leg, top 3 ranked replacement candidates, cascade impact (future legs affected).
    No DB write. Delegates entirely to SimulationService.
    """
    return SimulationService().simulate_crew_removal(crew_id, leg_id)


def simulate_crew_swap(crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str) -> dict:
    """
    Simulates swapping two crew members across two legs.
    Runs legality check for crew_a on leg_b and crew_b on leg_a.
    Returns: per-crew legality result, swap_legal bool.
    No DB write. Delegates entirely to SimulationService.
    """
    return SimulationService().simulate_crew_swap(crew_id_a, crew_id_b, leg_id_a, leg_id_b)


def simulate_leg_cancellation(leg_id: str) -> dict:
    """
    Simulates cancelling a leg.
    Returns: released crew list, their next assignments, FTL hours freed per crew.
    No DB write. Delegates entirely to SimulationService.
    """
    return SimulationService().simulate_leg_cancellation(leg_id)
```

### Action Tools (ACTION only — writes to DB)

```python
def action_mark_crew_unavailable(crew_id: str, leg_id: str, reason: str) -> dict:
    """
    Publishes CrewDisruptedEvent for the given leg.
    DisruptionHandler.handle_crew_disrupted() runs the full pipeline:
      - finds and ranks replacement candidates
      - creates PENDING proposal in disruption_proposals
    Does NOT write to roster directly — the proposal must be approved first.
    """
    leg = get_flight_leg(leg_id)
    if not leg:
        return {"error": f"leg {leg_id} not found"}

    days_until = (leg.scheduled_departure.date() - date.today()).days
    severity   = _classify_severity(days_until)

    crew = get_crew_member(crew_id)
    crew_name = crew.full_name if crew else crew_id

    event_bus.publish(CrewDisruptedEvent(
        crew_id              = crew_id,
        crew_name            = crew_name,
        leg_id               = leg_id,
        reason               = reason,
        days_until_departure = days_until,
        severity             = severity,
        source               = "OPS_DESK",
        detected_at          = datetime.now(timezone.utc),
    ))
    return {"status": "disruption_raised", "crew_id": crew_id, "leg_id": leg_id, "severity": severity}


def action_reassign_crew(leg_id: str, old_crew_id: str, new_crew_id: str, requested_by: str) -> dict:
    """
    Human has already decided the replacement — skips DisruptionHandler candidate search.
    Steps:
      1. Legality check on new_crew for this leg — fail fast, no DB write if illegal
      2. replace_roster_crew_assignment: old crew → REPLACED, new crew → CONFIRMED
      3. Publish RosterModifiedEvent → FTL Service + DailyValidator react immediately
    """
    leg      = get_flight_leg(leg_id)
    new_crew = get_crew_member(new_crew_id)
    ftl      = get_crew_duty_state(new_crew_id)
    licenses = get_licenses_for_crew_member(new_crew_id)
    leave    = get_leave_records_for_crew(new_crew_id)

    if not leg or not new_crew or not ftl:
        return {"error": "leg or crew not found"}

    passed, fail_reason = check_legality(
        new_crew, leg, ftl, licenses, leave, leg.scheduled_departure.date()
    )
    if not passed:
        return {"error": f"legality check failed: {fail_reason}"}

    with SessionLocal() as session:
        roster_repository.replace_roster_crew_assignment(
            session, leg_id, old_crew_id, new_crew_id, requested_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = old_crew_id,
        added_crew_id   = new_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))
    return {"status": "reassigned", "leg_id": leg_id, "removed": old_crew_id, "added": new_crew_id}


def action_accept_proposal(proposal_id: str, decided_by: str) -> dict:
    """
    Accepts a PENDING disruption proposal.
    Steps:
      1. Mark proposal ACCEPTED in disruption_proposals
      2. replace_roster_crew_assignment: removed_crew → REPLACED, proposed_crew → CONFIRMED
      3. Publish RosterModifiedEvent → FTL Service updates both crew, DailyValidator re-checks
    If proposal has no proposed_crew_id (manual review case) — mark accepted, skip roster write.
    """
    with SessionLocal() as session:
        result = disruption_repository.accept_proposal(session, proposal_id, decided_by)
        if not result:
            return {"error": "proposal not found"}

        leg_id          = result["leg_id"]
        removed_crew_id = result["removed_crew_id"]
        added_crew_id   = result["proposed_crew_id"]

        if not added_crew_id:
            session.commit()
            return {"status": "accepted", "leg_id": leg_id, "added": None, "note": "no candidate — manual handling required"}

        roster_repository.replace_roster_crew_assignment(
            session, leg_id, removed_crew_id, added_crew_id, decided_by
        )
        session.commit()

    event_bus.publish(RosterModifiedEvent(
        leg_id          = leg_id,
        removed_crew_id = removed_crew_id,
        added_crew_id   = added_crew_id,
        modified_at     = datetime.now(timezone.utc),
    ))
    return {"status": "accepted", "leg_id": leg_id, "removed": removed_crew_id, "added": added_crew_id}


def action_reject_proposal(proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    """
    Rejects a PENDING disruption proposal and surfaces the next best candidate.
    All pipeline logic (reject → exclude already-proposed → re-rank → new PENDING proposal)
    lives in DisruptionHandler.reject_and_repropose(). This tool is a thin wrapper.
    """
    from crew_ops.services.disruption_handler.disruption_handler_service import DisruptionHandler
    return DisruptionHandler().reject_and_repropose(proposal_id, decided_by, rejection_reason)


def action_approve_roster_leg(leg_id: str, approved_by: str) -> dict:
    """
    Approves a DRAFT roster leg → status PUBLISHED.
    Also flips all DRAFT roster_crew_assignment rows for this leg to CONFIRMED.
    After this, crew are officially notified and the leg is live.
    """
    with SessionLocal() as session:
        roster_repository.approve_roster_leg(session, leg_id, approved_by)
        session.commit()
    return {"status": "published", "leg_id": leg_id, "approved_by": approved_by}
```

### Private helper in tools.py

```python
def _classify_severity(days_until_departure: int) -> str:
    """Same thresholds as weekly_planner_service._classify_severity."""
    if days_until_departure < 1:  return "CRITICAL"
    if days_until_departure <= 2: return "HIGH"
    if days_until_departure <= 7: return "MEDIUM"
    return "LOW"
```

---

## Session State

Each conversation session holds minimal state. No conversation history is stored in the DB — only what is needed to handle the current pending confirmation or simulation.

```python
# conversation/session.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class PendingSimulation(BaseModel):
    crew_id:  str
    leg_id:   str
    reason:   str
    severity: str


class PendingConfirmation(BaseModel):
    action_type: str    # MARK_UNAVAILABLE / REASSIGN / SWAP / ACCEPT_PROPOSAL
    action_args: dict   # exact args to pass to the action tool on confirm
    summary:     str    # human-readable summary shown before confirmation
    expires_at:  datetime


class SessionState(BaseModel):
    session_id:           str
    last_intent:          str | None = None
    last_entities:        dict = {}
    pending_confirmation: Optional[PendingConfirmation] = None
    pending_simulation:   Optional[PendingSimulation]   = None


_sessions: dict[str, SessionState] = {}


def get_session(session_id: str) -> SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = SessionState(session_id=session_id)
    return _sessions[session_id]


def save_session(session_id: str, state: SessionState) -> None:
    _sessions[session_id] = state
```

`PendingSimulation` stores the context from a SIMULATE turn so that when the human says "yes, apply it" in the next turn, the agent knows exactly which crew/leg/reason to publish the `CrewDisruptedEvent` for.

Session state is held in memory (dict keyed by session_id). For production, replace with Redis. The session is stateless between restarts — acceptable for ops desk use where sessions are short-lived.

---

## LangGraph Graph Definition

```python
# conversation/agent.py

from langgraph.graph import StateGraph, END
from crew_ops.conversation.intent import classify_intent
from crew_ops.conversation.tools import (
    get_leg_status, get_crew_schedule, get_crew_ftl, get_pending_proposals, get_roster,
    simulate_crew_removal, simulate_crew_swap, simulate_leg_cancellation,
    action_mark_crew_unavailable, action_reassign_crew, action_accept_proposal,
    action_reject_proposal, action_approve_roster_leg,
)
from crew_ops.conversation.formatter import format_response, build_confirmation_package
from crew_ops.conversation.session import get_session, save_session
from crew_ops.clients.crew_profile_client import get_all_crew_members


def build_graph():
    graph = StateGraph(dict)

    graph.add_node("classify", classify_node)
    graph.add_node("route",    route_node)
    graph.add_node("execute",  execute_node)
    graph.add_node("confirm",  confirm_node)
    graph.add_node("format",   format_node)

    graph.set_entry_point("classify")

    graph.add_edge("classify", "route")
    graph.add_conditional_edges("route", route_decision, {
        "query":    "execute",
        "simulate": "execute",
        "confirm":  "confirm",   # pending confirmation from previous turn (human said YES)
        "action":   "confirm",   # new action — build confirmation package first
        "clarify":  "format",    # ambiguous intent — ask for clarification, skip execute
    })
    graph.add_edge("execute", "format")
    graph.add_edge("confirm", "execute")  # after human confirms, execute the action
    graph.add_edge("format",  END)

    return graph.compile()


# ─── Node implementations ─────────────────────────────────────────────────────

def classify_node(state: dict) -> dict:
    crew_list = [{"crew_id": c.crew_id, "full_name": c.full_name, "role": c.role, "home_base": c.home_base}
                 for c in get_all_crew_members()]
    intent = classify_intent(state["message"], state["session"], crew_list)
    state["intent"] = intent
    return state


def route_node(state: dict) -> dict:
    # route_decision is a separate function used by add_conditional_edges
    return state


def route_decision(state: dict) -> str:
    intent  = state["intent"]
    session = state["session"]

    if intent.ambiguous:
        state["response"] = intent.clarification_needed
        state["mode"]     = "CLARIFY"
        return "clarify"

    # Human responding YES to a pending confirmation
    if session.pending_confirmation and state["message"].strip().upper() == "YES":
        return "confirm"

    # Human saying "yes, apply it" after a SIMULATE turn
    if session.pending_simulation and intent.mode == "ACTION" and intent.action_type == "APPLY_SIMULATION":
        return "action"

    if intent.mode in ("QUERY", "SIMULATE"):
        return intent.mode.lower()

    return "action"


def confirm_node(state: dict) -> dict:
    session = state["session"]
    intent  = state["intent"]
    message = state["message"].strip().upper()

    # Human said NO — cancel
    if session.pending_confirmation and message == "NO":
        session.pending_confirmation = None
        state["session"]  = session
        state["response"] = "Action cancelled."
        state["mode"]     = "CONFIRM"
        state["_skip_execute"] = True
        return state

    # Human said YES — pull args from session and pass to execute
    if session.pending_confirmation and message == "YES":
        state["_confirmed_args"] = session.pending_confirmation.action_args
        state["_confirmed_type"] = session.pending_confirmation.action_type
        session.pending_confirmation = None
        state["session"] = session
        return state

    # New ACTION — build confirmation package and store in session
    action_args    = _build_action_args(intent, state)
    legality_check = _pre_check_legality(intent, action_args)
    if not legality_check["passed"]:
        state["response"]      = f"Cannot proceed: {legality_check['reason']}"
        state["mode"]          = "ACTION"
        state["_skip_execute"] = True
        return state

    summary = build_confirmation_package(intent.action_type, action_args, legality_check)
    session.pending_confirmation = PendingConfirmation(
        action_type = intent.action_type,
        action_args = action_args,
        summary     = summary,
        expires_at  = datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    state["session"]               = session
    state["response"]              = summary
    state["mode"]                  = "ACTION"
    state["requires_confirmation"] = True
    state["_skip_execute"]         = True
    return state


def execute_node(state: dict) -> dict:
    if state.get("_skip_execute"):
        return state

    intent  = state["intent"]
    session = state["session"]
    user_id = state["user_id"]

    # Post-confirmation execution — use confirmed args
    if state.get("_confirmed_args"):
        result = _dispatch_action(state["_confirmed_type"], state["_confirmed_args"], user_id)
        state["tool_result"] = result
        state["mode"]        = "ACTION"
        return state

    # SIMULATE — run in-memory, store pending_simulation for "apply it" follow-up
    if intent.mode == "SIMULATE":
        result = _dispatch_simulate(intent)
        state["tool_result"] = result
        state["mode"]        = "SIMULATE"
        if "candidates" in result and result["candidates"]:
            session.pending_simulation = PendingSimulation(
                crew_id  = intent.entities.get("crew_id", ""),
                leg_id   = intent.entities.get("leg_id", ""),
                reason   = intent.entities.get("reason", "UNAVAILABLE"),
                severity = result.get("severity", "MEDIUM"),
            )
            state["session"] = session
        return state

    # QUERY
    result = _dispatch_query(intent)
    state["tool_result"] = result
    state["mode"]        = "QUERY"
    return state


def format_node(state: dict) -> dict:
    if state.get("response"):  # already set by confirm_node or clarify
        return state
    mode   = state.get("mode", "QUERY")
    result = state.get("tool_result", {})
    intent = state["intent"]
    response = format_response(mode, result, intent)
    if mode == "SIMULATE" and result.get("candidates"):
        response += "\n\nWant me to raise this as a disruption? [YES / NO]"
    state["response"] = response
    return state
```

The graph is compiled once at startup and reused across all requests. Each request passes its own state dict — no shared mutable state between requests.

---

## Confirmation Package

Before executing any ACTION, the agent builds a confirmation package and presents it to the human. The LLM writes the narrative. The data comes from pure-Python functions.

```python
# conversation/formatter.py

from crew_ops.config.settings import settings


def _get_llm():
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key)
    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model="claude-3-5-sonnet-20241022", api_key=settings.anthropic_api_key)
    if settings.llm_provider == "bedrock":
        from langchain_aws import ChatBedrock
        return ChatBedrock(model_id=settings.bedrock_model_id, region_name=settings.aws_region)
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def build_confirmation_package(action_type: str, action_args: dict, legality_result: dict) -> str:
    """
    LLM writes a plain-English summary of what will change.
    Called before any ACTION is executed.
    """
    prompt = f"""
The controller wants to: {action_type}
Details: {action_args}
Legality check result: {legality_result}

Write a concise confirmation message (3-5 lines) that:
1. States exactly what will change
2. Names the crew members and flight affected
3. Mentions any FTL or legality notes
4. Ends with: "Confirm? [YES / NO]"

Do not add any information not present in the details above.
"""
    return _get_llm().invoke(prompt).content


def format_response(mode: str, tool_result: dict, intent) -> str:
    """
    LLM narrates the tool result in plain English.
    Called after every QUERY and SIMULATE execution.
    """
    prompt = f"""
Mode: {mode}
Original request: {intent.raw_message}
Result data: {tool_result}

Write a concise plain-English response (2-4 lines) summarising the result.
Do not invent data not present in the result.
"""
    return _get_llm().invoke(prompt).content


def format_push_notification(proposal: dict, leg: dict, candidates: list[dict]) -> str:
    """
    LLM writes the push alert shown to the controller when a new PENDING proposal arrives.
    Called by the push polling job in main.py.
    """
    prompt = f"""
A new disruption proposal requires your attention.
Proposal: {proposal}
Flight: {leg}
Top candidates: {candidates[:2]}

Write a concise alert (3-5 lines) that:
1. States the flight and departure time
2. Names the disrupted crew member and reason
3. Names the top replacement candidate with their FTL status
4. Ends with: "Confirm? [YES / NO / SHOW MORE OPTIONS]"

Do not add any information not present above.
"""
    return _get_llm().invoke(prompt).content
```

Example `build_confirmation_package` output:

```
Capt Ravi Singh (C-003) will be removed from AI305 BOM→CCU (10:00, today).
Replacement: Capt Vikram Joshi (C-007) — currently at VABB, FTL legal, score 87.
Capt Vikram's duty period after this leg: 4.5h of 13h limit.
This will publish a RosterModifiedEvent. FTL Service and Validator will re-check both crew.
Confirm? [YES / NO]
```

---

## Ambiguity Handling

The classifier detects ambiguity when entity extraction is uncertain. The agent stops and asks for clarification before doing anything.

```
Human: "Mark Sharma as sick"
      ↓
Classifier: ambiguous=True, clarification_needed="Multiple crew named Sharma: FO Priya Sharma (C-002, VIDP) and FO Neha Patel née Sharma (C-008, VABB). Which one?"
      ↓
Agent returns clarification question, no tool called
      ↓
Human: "Priya Sharma"
      ↓
Classifier: ambiguous=False, entities={crew_id: "C-002"}
      ↓
Normal flow continues
```

The session stores `last_entities` so the human does not need to repeat the flight number or date after a clarification.

---

## API Endpoint

```python
# conversation/router.py

from fastapi import APIRouter
from pydantic import BaseModel
from conversation.agent import build_graph
from conversation.session import get_session, save_session

router = APIRouter(prefix="/chat", tags=["Conversation"])

_graph = build_graph()

class ChatRequest(BaseModel):
    session_id: str
    message:    str
    user_id:    str        # ops controller ID — used as decided_by in action tools

class ChatResponse(BaseModel):
    session_id: str
    response:   str
    mode:       str        # QUERY / SIMULATE / ACTION / CONFIRM / CLARIFY
    requires_confirmation: bool = False

@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest):
    session = get_session(req.session_id)
    result  = _graph.invoke({
        "message":    req.message,
        "user_id":    req.user_id,
        "session":    session,
    })
    save_session(req.session_id, result["session"])
    return ChatResponse(
        session_id            = req.session_id,
        response              = result["response"],
        mode                  = result["mode"],
        requires_confirmation = result.get("requires_confirmation", False),
    )
```

Registered in `api/main.py`:

```python
from crew_ops.conversation.router import router as conversation_router
app.include_router(conversation_router)
```

---

## What Needs Confirmation vs What Does Not

| Action | Confirmation | Why |
|--------|-------------|-----|
| Query current status | No | Read only |
| Simulate what-if | No | No state change |
| Mark crew unavailable | Yes | Triggers disruption pipeline |
| Assign replacement | Yes | Modifies roster |
| Swap two crew | Yes | Modifies roster for both |
| Approve weekly roster leg | Yes | Publishes to all crew |
| Accept disruption proposal | Yes | Modifies roster |
| Reject disruption proposal | Yes | Triggers next candidate search |
| Auto-resolve LOW severity | No | System handles, notifies only |

---

## Severity-Driven Push Behaviour

| Severity | Push timing | Escalation | Auto-resolve |
|----------|------------|------------|-------------|
| CRITICAL | Immediately | After 15 min if no response | Never |
| HIGH | Immediately | After 1hr | Never |
| MEDIUM | Immediately | After 4hr | Never |
| LOW | After resolution attempt | None | Yes — if clean replacement found |

LOW severity auto-resolve flow:

```
LOW proposal created
      ↓
DisruptionHandler.auto_resolve_low_severity() runs every 30 min (APScheduler)
      ↓
For each PENDING LOW proposal:
  re-run legality check on proposed_crew_id (FTL may have changed)
      ↓
  if still legal:
    disruption_repository.accept_proposal(session, proposal_id, "AUTO_RESOLVE")
    roster_repository.replace_roster_crew_assignment()
    publish RosterModifiedEvent
    notify human: "AI555 BOM→PNQ (D7): FO Tanya replaced by FO Kavya. Auto-resolved."
      ↓
  if no longer legal:
    re-run _find_and_rank_candidates()
    if new candidate found: update proposal with new proposed_crew_id
    if no candidate: escalate severity to MEDIUM, push to human
```

`auto_resolve_low_severity()` lives in `DisruptionHandler`. It uses only existing methods: `_find_and_rank_candidates()`, `_create_proposal()`, `accept_proposal()`, `replace_roster_crew_assignment()`. No new logic.

Push notification flow:

```
DisruptionHandler creates PENDING proposal
      ↓
APScheduler push job runs every 60s
      ↓
disruption_repository.get_unpushed_proposals() — WHERE pushed_at IS NULL
      ↓
for each proposal:
  formatter.format_push_notification(proposal, leg, candidates[:2])
  store in _push_queue (in-memory list in main.py)
  disruption_repository.mark_proposal_pushed(proposal_id)
      ↓
POST /chat response drains _push_queue and prepends any pending pushes
```

The `pushed_at` column is added to `disruption_proposals` (see DB Schema Changes below).

---

## Service Extensions Required

These changes are made to existing services — not to the conversation package.

### `services/disruption_handler/disruption_handler_service.py`

Add three methods to `DisruptionHandler`:

**`reject_and_repropose(proposal_id, decided_by, rejection_reason) -> dict`**

This is the pipeline currently misplaced in `action_reject_proposal` in the old doc. It lives here:

```python
def reject_and_repropose(self, proposal_id: str, decided_by: str, rejection_reason: str) -> dict:
    with SessionLocal() as session:
        result = disruption_repository.reject_proposal(session, proposal_id, decided_by, rejection_reason)
        if not result:
            return {"error": "proposal not found"}
        leg_id           = result["leg_id"]
        removed_crew_id  = result["removed_crew_id"]
        already_proposed = disruption_repository.get_already_proposed_crew(session, leg_id, removed_crew_id)
        session.commit()

    leg = get_flight_leg(leg_id)
    if not leg:
        return {"status": "rejected", "new_proposal_id": None, "reason": "leg no longer exists"}

    removed_crew = get_crew_member(removed_crew_id)
    role = removed_crew.role if removed_crew else None
    if not role:
        with SessionLocal() as session:
            assignment = roster_repository.get_assignment_for_crew(session, leg_id, removed_crew_id)
        role = assignment.get("role") if assignment else None
    if not role:
        return {"status": "rejected", "new_proposal_id": None, "reason": "cannot determine role"}

    candidates = self._find_and_rank_candidates(role, leg)
    candidates = [c for c in candidates if c["crew"].crew_id not in already_proposed]

    self._create_proposal(
        leg_id            = leg_id,
        disruption_type   = "CREW_DISRUPTED",
        disruption_reason = rejection_reason,
        removed_crew_id   = removed_crew_id,
        candidates        = candidates,
        severity          = "HIGH",
        source            = "CONTROLLER_REJECT",
    )
    next_candidate = candidates[0]["crew"].crew_id if candidates else None
    return {"status": "rejected", "leg_id": leg_id, "next_candidate": next_candidate}
```

**`auto_resolve_low_severity() -> list[str]`**

Scheduled every 30 min. For each PENDING LOW proposal:
- Re-run legality check on `proposed_crew_id` (FTL state may have changed)
- If still legal: accept, write roster, publish `RosterModifiedEvent`
- If no longer legal: re-rank candidates, update proposal or escalate to MEDIUM
- Returns list of resolved proposal IDs

**`get_proposals_for_push() -> list[dict]`**

Returns PENDING proposals where `pushed_at IS NULL`, ordered by severity. Called by the push polling job in `main.py`.

### `services/observer/observer_service.py`

Add `get_legs_for_range(start, end) -> list[FlightLeg]` to `FlightObserver`:

```python
def get_legs_for_range(self, start: date, end: date) -> list[FlightLeg]:
    all_legs = get_all_scheduled_legs()
    return [leg for leg in all_legs if start <= leg.scheduled_departure.date() <= end]
```

Used by the conversation layer for SIMULATE queries spanning multiple days.

### `services/weekly_planner/weekly_planner_service.py`

Add `simulate_build(start, end) -> dict` to `RosterPlanner`:

```python
def simulate_build(self, start: date, end: date) -> dict:
    """Dry-run build — no DB write. Returns assignments and validation failures."""
    all_crew     = get_all_crew_members()
    all_licenses = get_all_licenses()
    all_leave    = get_all_leave_records()
    crew_by_id   = {c.crew_id: c for c in all_crew if c.employment_status == "ACTIVE"}
    licenses_by_crew = defaultdict(list)
    for lic in all_licenses:
        licenses_by_crew[lic.crew_id].append(lic)
    leave_by_crew = defaultdict(list)
    for leave in all_leave:
        leave_by_crew[leave.crew_id].append(leave)
    simulated_ftl = {f.crew_id: f.model_copy(deep=True) for f in get_all_crew_duty_states()}
    legs = get_legs_for_date_range(start, end)
    assignments = _pass1_assign_crew(legs, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)
    failures    = _pass3_validate(legs, assignments, crew_by_id, simulated_ftl, licenses_by_crew, leave_by_crew)
    return {"assignments": assignments, "failures": failures}
```

Used by `SimulationService.simulate_leg_cancellation` to show what the roster looks like after a leg is removed.

---

## SimulationService (new file)

**`services/simulation/simulation_service.py`**

Owns all in-memory what-if logic. No DB writes ever happen here.

```python
# services/simulation/simulation_service.py

from collections import defaultdict
from datetime import date, timedelta
from crew_ops.clients.crew_profile_client import get_all_crew_members, get_crew_member
from crew_ops.clients.flight_schedule_client import get_flight_leg
from crew_ops.clients.ftl_client import get_all_crew_duty_states
from crew_ops.clients.license_client import get_all_licenses
from crew_ops.clients.leave_client import get_all_leave_records
from crew_ops.db.database import SessionLocal
from crew_ops.db.repositories import roster_repository
from crew_ops.rules.legality import check_legality
from crew_ops.services.disruption_handler.disruption_handler_service import _score_candidate


class SimulationService:

    def simulate_crew_removal(self, crew_id: str, leg_id: str) -> dict:
        leg  = get_flight_leg(leg_id)
        crew = get_crew_member(crew_id)
        if not leg or not crew:
            return {"error": "leg or crew not found"}
        candidates = self._find_and_rank_candidates_in_memory(crew.role, leg, exclude=[crew_id])
        cascade    = self._check_cascade_impact(crew_id, leg)
        return {
            "removed_crew":   crew.model_dump(),
            "leg":            leg.model_dump(),
            "candidates":     [{"crew_id": c["crew"].crew_id, "score": c["score"]} for c in candidates[:3]],
            "cascade_impact": cascade,
        }

    def simulate_crew_swap(self, crew_id_a: str, crew_id_b: str, leg_id_a: str, leg_id_b: str) -> dict:
        leg_a  = get_flight_leg(leg_id_a)
        leg_b  = get_flight_leg(leg_id_b)
        crew_a = get_crew_member(crew_id_a)
        crew_b = get_crew_member(crew_id_b)
        if not leg_a or not leg_b or not crew_a or not crew_b:
            return {"error": "leg or crew not found"}

        ftl_states   = {s.crew_id: s for s in get_all_crew_duty_states()}
        all_licenses = get_all_licenses()
        all_leave    = get_all_leave_records()
        lic_by_crew  = defaultdict(list)
        for lic in all_licenses:
            lic_by_crew[lic.crew_id].append(lic)
        leave_by_crew = defaultdict(list)
        for lv in all_leave:
            leave_by_crew[lv.crew_id].append(lv)

        passed_a, reason_a = check_legality(
            crew_a, leg_b, ftl_states[crew_id_a],
            lic_by_crew[crew_id_a], leave_by_crew[crew_id_a],
            leg_b.scheduled_departure.date(),
        )
        passed_b, reason_b = check_legality(
            crew_b, leg_a, ftl_states[crew_id_b],
            lic_by_crew[crew_id_b], leave_by_crew[crew_id_b],
            leg_a.scheduled_departure.date(),
        )
        return {
            "crew_a_on_leg_b": {"passed": passed_a, "reason": reason_a},
            "crew_b_on_leg_a": {"passed": passed_b, "reason": reason_b},
            "swap_legal":      passed_a and passed_b,
        }

    def simulate_leg_cancellation(self, leg_id: str) -> dict:
        leg = get_flight_leg(leg_id)
        if not leg:
            return {"error": "leg not found"}

        scan_end = leg.scheduled_departure.date() + timedelta(weeks=4)
        next_assignments: dict = {}
        ftl_impact: dict = {}
        leg_hours = (leg.scheduled_arrival - leg.scheduled_departure).total_seconds() / 3600

        with SessionLocal() as session:
            for crew_id in leg.assigned_crew:
                future = roster_repository.get_future_assignments(
                    session,
                    from_date = leg.scheduled_departure.date(),
                    to_date   = scan_end,
                    crew_id   = crew_id,
                )
                next_assignments[crew_id] = future[0] if future else None
                ftl_impact[crew_id]       = round(leg_hours, 2)

        return {
            "cancelled_leg":   leg.model_dump(),
            "released_crew":   leg.assigned_crew,
            "next_assignments": next_assignments,
            "ftl_hours_freed": ftl_impact,
        }

    # ─── Private helpers ─────────────────────────────────────────────────────

    def _find_and_rank_candidates_in_memory(
        self, role: str, leg, exclude: list[str] = []
    ) -> list[dict]:
        all_crew   = get_all_crew_members()
        ftl_states = {s.crew_id: s for s in get_all_crew_duty_states()}
        all_licenses = get_all_licenses()
        all_leave    = get_all_leave_records()
        lic_by_crew  = defaultdict(list)
        for lic in all_licenses:
            lic_by_crew[lic.crew_id].append(lic)
        leave_by_crew = defaultdict(list)
        for lv in all_leave:
            leave_by_crew[lv.crew_id].append(lv)

        dep      = leg.scheduled_departure
        leg_date = dep.date()
        results  = []
        for crew in all_crew:
            if crew.crew_id in exclude or crew.role != role or crew.employment_status != "ACTIVE":
                continue
            ftl = ftl_states.get(crew.crew_id)
            if not ftl:
                continue
            passed, _ = check_legality(
                crew, leg, ftl,
                lic_by_crew.get(crew.crew_id, []),
                leave_by_crew.get(crew.crew_id, []),
                leg_date,
            )
            if passed:
                results.append({"crew": crew, "ftl": ftl, "score": _score_candidate(crew, ftl, leg)})
        return sorted(results, key=lambda x: x["score"], reverse=True)

    def _check_cascade_impact(self, crew_id: str, leg) -> list[dict]:
        scan_end = leg.scheduled_departure.date() + timedelta(weeks=4)
        with SessionLocal() as session:
            return roster_repository.get_future_assignments(
                session,
                from_date = leg.scheduled_departure.date(),
                to_date   = scan_end,
                crew_id   = crew_id,
            )
```

---

## DB Schema Changes

One new column in `disruption_proposals` (add to `docker/init.sql`):

```sql
pushed_at TIMESTAMPTZ DEFAULT NULL
```

Two new repository functions in `db/repositories/disruption_repository.py`:

```python
def get_unpushed_proposals(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT dp.*, fl.scheduled_departure, fl.origin_iata, fl.destination_iata,
               fl.flight_number
        FROM disruption_proposals dp
        JOIN flight_legs fl ON fl.leg_id = dp.leg_id
        WHERE dp.status = 'PENDING' AND dp.pushed_at IS NULL
        ORDER BY
            CASE dp.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH'     THEN 2
                WHEN 'MEDIUM'   THEN 3
                ELSE 4
            END
    """)).mappings().all()
    return [dict(row) for row in rows]


def mark_proposal_pushed(session: Session, proposal_id: str) -> None:
    session.execute(text("""
        UPDATE disruption_proposals SET pushed_at = NOW()
        WHERE proposal_id = :proposal_id
    """), {"proposal_id": proposal_id})
```

---

## Dependencies

New dependencies required in `pyproject.toml`:

```toml
"langgraph>=0.2.0",
"langchain-openai>=0.1.0",
"langchain-anthropic>=0.1.0",
"langchain-aws>=0.1.0",
"langchain-core>=0.2.0",
```

LLM provider configured via environment variable:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

Add to `config/settings.py`:

```python
llm_provider:      str = "openai"
openai_api_key:    str = ""
anthropic_api_key: str = ""
bedrock_model_id:  str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
aws_region:        str = "us-east-1"
```

---

## Service Responsibility Boundaries

| Concern | Lives in |
|---------|----------|
| Legality check (hard gates 1–11) | `rules/legality.py` |
| FTL simulation | `rules/ftl_simulator.py` |
| Candidate scoring | `_score_candidate()` in `disruption_handler_service.py` |
| In-memory what-if simulation | `services/simulation/simulation_service.py` |
| Reject + repropose pipeline | `DisruptionHandler.reject_and_repropose()` |
| LOW severity auto-resolve | `DisruptionHandler.auto_resolve_low_severity()` |
| Push notification formatting | `conversation/formatter.py` |
| Push notification scheduling | `api/main.py` scheduled job |
| Intent classification | `conversation/intent.py` |
| Session state | `conversation/session.py` |
| Tool dispatch | `conversation/tools.py` (thin wrappers only) |
| LangGraph graph | `conversation/agent.py` |
| HTTP entry point | `conversation/router.py` |
| Detecting flight disruptions | `services/observer/observer_service.py` |
| Detecting crew legality breaches | `services/weekly_planner/weekly_planner_service.py` |
| Scheduling jobs | APScheduler in `api/main.py` |

---

## Scheduled Jobs (additions to `api/main.py`)

Three new jobs added to the existing APScheduler setup:

```python
# LOW severity auto-resolve — every 30 minutes
scheduler.add_job(
    disruption_handler.auto_resolve_low_severity,
    CronTrigger(minute="*/30"),
    id="auto_resolve_low",
)

# Push notification polling — every 60 seconds
scheduler.add_job(
    _push_pending_proposals,
    CronTrigger(second="*/60"),
    id="push_proposals",
)
```

`_push_pending_proposals()` is a module-level function in `main.py`:

```python
_push_queue: list[str] = []   # in-memory, drained on each /chat request

def _push_pending_proposals() -> None:
    from crew_ops.db.database import SessionLocal
    from crew_ops.db.repositories import disruption_repository
    from crew_ops.clients.flight_schedule_client import get_flight_leg
    from crew_ops.conversation.formatter import format_push_notification
    with SessionLocal() as session:
        proposals = disruption_repository.get_unpushed_proposals(session)
        for p in proposals:
            leg = get_flight_leg(p["leg_id"])
            msg = format_push_notification(p, leg.model_dump() if leg else {}, [])
            _push_queue.append(msg)
            disruption_repository.mark_proposal_pushed(session, p["proposal_id"])
        session.commit()
```

The `/chat` endpoint prepends any items in `_push_queue` to the response before returning.

Register the conversation router:

```python
from crew_ops.conversation.router import router as conversation_router
app.include_router(conversation_router)
```

---

## File Checklist

| File | Action | What changes |
|------|--------|--------------|
| `services/disruption_handler/disruption_handler_service.py` | Modify | Add `reject_and_repropose()`, `auto_resolve_low_severity()`, `get_proposals_for_push()` |
| `services/observer/observer_service.py` | Modify | Add `get_legs_for_range(start, end)` |
| `services/weekly_planner/weekly_planner_service.py` | Modify | Add `simulate_build(start, end)` to `RosterPlanner` |
| `services/simulation/__init__.py` | Create | Empty |
| `services/simulation/simulation_service.py` | Create | `SimulationService` with 3 public + 2 private methods |
| `db/repositories/disruption_repository.py` | Modify | Add `get_unpushed_proposals()`, `mark_proposal_pushed()` |
| `docker/init.sql` | Modify | Add `pushed_at` column to `disruption_proposals` |
| `conversation/__init__.py` | Create | Empty |
| `conversation/session.py` | Create | `PendingSimulation`, `PendingConfirmation`, `SessionState`, `get_session`, `save_session` |
| `conversation/intent.py` | Create | `Intent` model + `classify_intent()` LLM call |
| `conversation/tools.py` | Create | All read/simulate/action tools — simulate tools delegate to `SimulationService` |
| `conversation/formatter.py` | Create | `_get_llm`, `build_confirmation_package`, `format_response`, `format_push_notification` |
| `conversation/agent.py` | Create | All 5 node functions + `build_graph()` |
| `conversation/router.py` | Create | `POST /chat` endpoint |
| `api/main.py` | Modify | Register conversation router, add `auto_resolve_low` + `push_proposals` jobs |
| `config/settings.py` | Modify | Add LLM provider settings |
| `pyproject.toml` | Modify | Add langgraph + langchain deps |
| `.env.example` | Modify | Add `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `BEDROCK_MODEL_ID`, `AWS_REGION` |

---

## End to End Test

```bash
# Start server
uv run uvicorn crew_ops.api.main:app --reload --port 8000

# QUERY
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "Who is assigned to AI305 today?"}'

# SIMULATE
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "If Capt Ravi is sick today, who can cover AI305?"}'

# ACTION — step 1: agent returns confirmation package
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "Mark Capt Ravi as sick for AI305 today"}'

# ACTION — step 2: human confirms
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-001", "user_id": "ops_01", "message": "YES"}'

# Verify disruption proposal was created
curl http://localhost:8000/disruptions/proposals
```
