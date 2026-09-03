import json
import re
from datetime import datetime, timedelta, timezone

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from crew_ops_backend.clients.crew_profile_client import get_all_crew_members
from crew_ops_backend.conversation.formatter import _get_llm, build_confirmation_package, format_response
from crew_ops_backend.conversation.intent import Intent, classify_intent
from crew_ops_backend.conversation.session import (
    PendingConfirmation, PendingSimulation, SessionState,
)
from crew_ops_backend.conversation.tools import (
    ALL_TOOLS, ALL_ACTION_TOOLS,
    action_accept_proposal,
    action_approve_roster_leg,
    action_mark_crew_unavailable,
    action_reassign_crew,
    action_reject_proposal,
)


# ─── Tool registry — name → callable ─────────────────────────────────────────

_TOOL_MAP = {t.name: t for t in ALL_TOOLS}

# Action tool names — these require confirmation before execution
_ACTION_TOOL_NAMES = {t.name for t in ALL_ACTION_TOOLS}


# ─── Gateway prompt ───────────────────────────────────────────────────────────

_GATEWAY_PROMPT = """\
You are a gateway for a crew operations system. Decide if the user message is relevant
to airline crew operations or not.

The system can handle:
- Crew schedule queries         e.g. "show me C001 schedule"
- FTL / duty hour queries       e.g. "check FTL state for crew C002"
- Flight leg status             e.g. "what is the status of leg L42"
- Roster queries                e.g. "show roster for this week"
- Pending proposals             e.g. "show pending proposals"
- Simulate crew removal         e.g. "simulate removing C001 from L42"
- Simulate crew swap            e.g. "simulate swapping C001 and C002"
- Simulate leg cancellation     e.g. "simulate cancelling leg L42"
- Mark crew unavailable         e.g. "mark C001 unavailable for leg L42"
- Reassign crew                 e.g. "reassign C002 to leg L42"
- Accept / reject proposals     e.g. "accept proposal P01"
- Approve roster leg            e.g. "approve leg L42"
- Confirmation replies          e.g. "yes", "no", "confirm", "cancel"

Return JSON: {"relevant": true} or {"relevant": false}
"""

_HELP_MESSAGE = (
    "I'm your crew operations assistant. Here's what I can help you with:\n\n"
    "  Queries      — crew schedule, FTL state, leg status, roster, proposals\n"
    "  Simulations  — crew removal, crew swap, leg cancellation\n"
    "  Actions      — mark unavailable, reassign crew, accept/reject proposal, approve leg\n\n"
    "Example requests:\n"
    "  \"Show me schedule for C001\"\n"
    "  \"Simulate removing C001 from leg L42\"\n"
    "  \"Mark C002 unavailable for leg L10\"\n"
    "  \"Show pending proposals\""
)

_TOOL_SELECTION_PROMPT = """\
You are a crew operations assistant. Based on the user message, select the most appropriate tool and provide its arguments.

Today's date: {today}

Available crew members:
{crew_list}

{session_context}

Select exactly one tool that best answers the user's request.
For date arguments use ISO format (YYYY-MM-DD).
For crew_id and leg_id use the exact IDs from the crew list or message.
"""


# ─── Graph builder ────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(dict)

    graph.add_node("gateway",  gateway_node)
    graph.add_node("classify", classify_node)
    graph.add_node("route",    route_node)
    graph.add_node("execute",  execute_node)
    graph.add_node("confirm",  confirm_node)
    graph.add_node("format",   format_node)

    graph.set_entry_point("gateway")

    graph.add_conditional_edges("gateway", gateway_decision, {
        "relevant":   "classify",
        "irrelevant": "format",
    })
    graph.add_edge("classify", "route")
    graph.add_conditional_edges("route", route_decision, {
        "execute": "execute",
        "confirm": "confirm",
        "clarify": "format",
    })
    graph.add_edge("execute", "format")
    graph.add_edge("confirm", "execute")
    graph.add_edge("format",  END)

    return graph.compile()


# ─── Nodes ────────────────────────────────────────────────────────────────────

def gateway_node(state: dict) -> dict:
    llm      = _get_llm()
    response = llm.invoke([
        SystemMessage(content=_GATEWAY_PROMPT),
        HumanMessage(content=state["message"]),
    ])
    try:
        text = re.sub(r"```[a-z]*\n?", "", response.content).strip()
        result = json.loads(text)
        state["_relevant"] = result.get("relevant", False)
    except Exception:
        state["_relevant"] = "true" in response.content.lower()
    return state


def gateway_decision(state: dict) -> str:
    return "relevant" if state.get("_relevant") else "irrelevant"


def classify_node(state: dict) -> dict:
    from datetime import date

    session: SessionState = state["session"]
    message_upper = state["message"].strip().upper()

    # Short-circuit: confirmation reply — no need to classify
    if session.pending_confirmation and message_upper in ("YES", "Y", "CONFIRM", "NO", "N", "CANCEL"):
        state["intent"]      = Intent(mode="ACTION", raw_message=state["message"])
        state["_tool_calls"] = []
        return state

    crew_list = [
        {"crew_id": c.crew_id, "full_name": c.full_name, "role": c.role, "home_base": c.home_base}
        for c in get_all_crew_members()
    ]

    # Build session context for tool selection prompt
    session_context = ""
    if session.pending_simulation:
        session_context += f"Pending simulation: {session.pending_simulation.model_dump()}\n"
    if session.last_entities:
        session_context += f"Last known entities (reuse if not re-specified): {session.last_entities}\n"

    prompt = _TOOL_SELECTION_PROMPT.format(
        today        = date.today().isoformat(),
        crew_list    = crew_list,
        session_context = session_context,
    )

    # Bind all tools to LLM — LLM selects which tool and what args
    llm_with_tools = _get_llm().bind_tools(ALL_TOOLS)
    response = llm_with_tools.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=state["message"]),
    ])

    # Also classify intent for routing (confirm/simulate flow still needs it)
    intent = classify_intent(state["message"], session, crew_list)
    state["intent"] = intent

    # Store tool call selected by LLM
    tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []
    state["_tool_calls"] = tool_calls

    # Persist entities from intent into session
    if intent.entities:
        session.last_entities = {**session.last_entities, **intent.entities}
        session.last_intent   = intent.mode
        state["session"]      = session

    return state


def route_node(state: dict) -> dict:
    intent:  Intent       = state["intent"]
    session: SessionState = state["session"]
    message: str          = state["message"].strip().upper()

    if intent.ambiguous:
        state["_clarify_message"] = intent.clarification_needed or "Could you clarify your request?"
        return state

    if session.pending_confirmation:
        if session.pending_confirmation.expires_at < datetime.now(timezone.utc):
            session.pending_confirmation   = None
            state["session"]               = session
            state["_confirmation_expired"] = True
        elif message not in ("YES", "Y", "CONFIRM", "NO", "N", "CANCEL"):
            state["_clarify_message"] = "Please reply YES to confirm or NO to cancel."
        return state

    tool_calls = state.get("_tool_calls", [])
    if tool_calls and tool_calls[0]["name"] == "action_mark_crew_unavailable":
        args    = tool_calls[0].get("args", {})
        missing = []
        if not args.get("crew_id"):    missing.append("crew ID (e.g. C-020)")
        if not args.get("reason"):     missing.append("reason (SICK_CALL / PERSONAL / TRAINING / OTHER)")
        if not args.get("start_date"): missing.append("leave start date (YYYY-MM-DD)")
        if not args.get("end_date"):   missing.append("leave end date (YYYY-MM-DD)")
        if missing:
            state["_clarify_message"] = (
                f"To mark a crew member unavailable I need: {', '.join(missing)}.\n"
                f"Example: 'Mark C-020 unavailable, reason SICK_CALL, from 2025-07-10 to 2025-07-15'"
            )
        return state

    if not tool_calls and intent.mode == "ACTION":
        action_type = intent.action_type or ""
        if action_type == "MARK_UNAVAILABLE":
            entities = intent.entities or {}
            missing  = []
            if not entities.get("crew_id"):    missing.append("crew ID (e.g. C-020)")
            if not entities.get("reason"):     missing.append("reason (SICK_CALL / PERSONAL / TRAINING / OTHER)")
            if not entities.get("start_date"): missing.append("leave start date (YYYY-MM-DD)")
            if not entities.get("end_date"):   missing.append("leave end date (YYYY-MM-DD)")
            if missing:
                state["_clarify_message"] = (
                    f"To mark a crew member unavailable I need: {', '.join(missing)}.\n"
                    f"Example: 'Mark C-020 unavailable, reason SICK_CALL, from 2025-07-10 to 2025-07-15'"
                )
            else:
                # All entities present — synthesize tool call so route_decision sends to confirm
                state["_tool_calls"] = [{
                    "name": "action_mark_crew_unavailable",
                    "args": {
                        "crew_id":    entities["crew_id"],
                        "reason":     entities["reason"],
                        "start_date": entities["start_date"],
                        "end_date":   entities["end_date"],
                    },
                }]
        else:
            state["_clarify_message"] = (
                intent.clarification_needed or "Please provide more details."
            )

    # Swap simulation — needs leg IDs
    tool_calls = state.get("_tool_calls", [])
    if not tool_calls and intent.mode == "SIMULATE":
        entities = intent.entities or {}
        if not entities.get("leg_id") and not entities.get("leg_id_a"):
            state["_clarify_message"] = (
                "To simulate a crew swap I need the flight legs for each crew member.\n"
                "Example: 'Simulate swapping C-019 on leg AI202-DEL-BOM-20260904 "
                "with C-018 on leg AI305-BOM-CCU-20260904'"
            )

    return state


def route_decision(state: dict) -> str:
    intent:  Intent       = state["intent"]
    session: SessionState = state["session"]
    message: str          = state["message"].strip().upper()

    if state.get("_clarify_message") or state.get("_confirmation_expired"):
        return "clarify"

    if session.pending_confirmation:
        if message in ("YES", "Y", "CONFIRM", "NO", "N", "CANCEL"):
            return "confirm"
        return "clarify"

    if session.pending_simulation and intent.action_type == "APPLY_SIMULATION":
        return "confirm"

    tool_calls = state.get("_tool_calls", [])
    if tool_calls and tool_calls[0]["name"] in _ACTION_TOOL_NAMES:
        return "confirm"

    if intent.mode == "ACTION":
        return "clarify"

    return "execute"


def confirm_node(state: dict) -> dict:
    session: SessionState = state["session"]
    message: str          = state["message"].strip().upper()
    intent:  Intent       = state["intent"]

    # Human said NO
    if session.pending_confirmation and message in ("NO", "N", "CANCEL"):
        session.pending_confirmation = None
        state["session"]       = session
        state["response"]      = "Action cancelled."
        state["mode"]          = "CONFIRM"
        state["_skip_execute"] = True
        return state

    # Human said YES — execute confirmed action
    if session.pending_confirmation and message in ("YES", "Y", "CONFIRM"):
        state["_confirmed_args"] = session.pending_confirmation.action_args
        state["_confirmed_type"] = session.pending_confirmation.action_type
        session.pending_confirmation = None
        state["session"] = session
        return state

    # APPLY_SIMULATION — convert to MARK_UNAVAILABLE confirmation
    if session.pending_simulation and intent.action_type == "APPLY_SIMULATION":
        sim         = session.pending_simulation
        action_args = {"crew_id": sim.crew_id, "leg_id": sim.leg_id, "reason": sim.reason}
        summary     = build_confirmation_package(
            "MARK_UNAVAILABLE", action_args,
            {"passed": True, "note": f"severity={sim.severity}"}
        )
        session.pending_confirmation = PendingConfirmation(
            action_type = "MARK_UNAVAILABLE",
            action_args = action_args,
            summary     = summary,
            expires_at  = datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.pending_simulation     = None
        state["session"]               = session
        state["response"]              = summary
        state["mode"]                  = "ACTION"
        state["requires_confirmation"] = True
        state["_skip_execute"]         = True
        return state

    # New action tool selected by LLM — build confirmation package
    tool_calls = state.get("_tool_calls", [])
    if not tool_calls:
        state["response"]      = "I couldn't determine what action to take. Please rephrase."
        state["mode"]          = "CLARIFY"
        state["_skip_execute"] = True
        return state

    tool_call   = tool_calls[0]
    action_type = tool_call["name"]
    action_args = tool_call["args"]

    # Legality pre-check for reassign
    legality_check = _pre_check_legality_for_tool(action_type, action_args)
    if not legality_check["passed"]:
        state["response"]      = f"Cannot proceed: {legality_check['reason']}"
        state["mode"]          = "ACTION"
        state["_skip_execute"] = True
        return state

    summary = build_confirmation_package(action_type, action_args, legality_check)
    session.pending_confirmation = PendingConfirmation(
        action_type = action_type,
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

    intent:  Intent       = state["intent"]
    session: SessionState = state["session"]
    user_id: str          = state["user_id"]

    # Post-confirmation action execution
    if state.get("_confirmed_args"):
        from datetime import date as date_type
        tool = _TOOL_MAP.get(state["_confirmed_type"])
        raw  = {**state["_confirmed_args"], "requested_by": user_id, "decided_by": user_id, "approved_by": user_id}
        # Coerce date strings back to date objects for tools that expect date type
        for k, v in raw.items():
            if isinstance(v, str) and k in ("start_date", "end_date"):
                try:
                    raw[k] = date_type.fromisoformat(v)
                except ValueError:
                    pass
        args   = {k: v for k, v in raw.items() if k in tool.args}
        result = tool.invoke(args)
        state["tool_result"] = result
        state["mode"]        = "ACTION"
        # Immediately flush any new proposals created by this action into the push queue
        if result and not result.get("error"):
            _flush_new_proposals()
        return state

    # Execute tool selected by LLM
    tool_calls = state.get("_tool_calls", [])
    if not tool_calls:
        state["tool_result"] = {"error": "I couldn't find relevant information for that request. Try being more specific, e.g. 'show roster for today' or 'status of leg L42'."}
        state["mode"]        = "QUERY"
        return state

    tool_call = tool_calls[0]
    tool      = _TOOL_MAP.get(tool_call["name"])
    if not tool:
        state["tool_result"] = {"error": f"unknown tool: {tool_call['name']}"}
        state["mode"]        = "QUERY"
        return state

    result = tool.invoke(tool_call["args"])
    mode   = "SIMULATE" if "simulate" in tool_call["name"] else "QUERY"

    # Store pending simulation if candidates found
    if mode == "SIMULATE":
        candidates = result.get("candidates", []) if isinstance(result, dict) else []
        crew_id    = tool_call["args"].get("crew_id", "")
        leg_id     = tool_call["args"].get("leg_id", "")
        if candidates and crew_id and leg_id:
            session.pending_simulation = PendingSimulation(
                crew_id  = crew_id,
                leg_id   = leg_id,
                reason   = tool_call["args"].get("reason", "UNAVAILABLE"),
                severity = "MEDIUM",
            )
            state["session"] = session

    state["tool_result"] = result
    state["mode"]        = mode
    return state


def format_node(state: dict) -> dict:
    if state.get("response"):
        return state

    if not state.get("_relevant"):
        state["response"] = _HELP_MESSAGE
        state["mode"]     = "IRRELEVANT"
        return state

    # Clarify path — must check before calling format_response to avoid hallucination
    if state.get("_clarify_message"):
        state["response"] = state["_clarify_message"]
        state["mode"]     = "CLARIFY"
        return state

    if state.get("_confirmation_expired"):
        state["response"] = "Your confirmation timed out. Please repeat your request."
        state["mode"]     = "CLARIFY"
        return state

    intent: Intent = state["intent"]
    mode:   str    = state.get("mode", "QUERY")
    result         = state.get("tool_result", {})

    if intent.ambiguous:
        state["response"] = intent.clarification_needed or "Could you clarify your request?"
        state["mode"]     = "CLARIFY"
        return state

    session: SessionState = state["session"]
    if session.pending_confirmation and not result:
        state["response"] = "Please reply YES to confirm or NO to cancel."
        state["mode"]     = "CLARIFY"
        return state

    response = format_response(mode, result, intent.raw_message)

    if mode == "SIMULATE" and isinstance(result, dict) and result.get("candidates"):
        response += "\n\nWant me to raise this as a disruption? [YES / NO]"

    state["response"] = response
    return state


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pre_check_legality_for_tool(tool_name: str, action_args: dict) -> dict:
    if tool_name == "action_reassign_crew":
        from crew_ops_backend.clients.crew_profile_client import get_crew_member
        from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
        from crew_ops_backend.clients.ftl_client import get_crew_duty_state
        from crew_ops_backend.clients.license_client import get_licenses_for_crew_member
        from crew_ops_backend.clients.leave_client import get_leave_records_for_crew
        from crew_ops_backend.rules.legality import check_legality

        leg_id      = action_args.get("leg_id", "")
        new_crew_id = action_args.get("new_crew_id", "")
        leg         = get_flight_leg(leg_id)
        new_crew    = get_crew_member(new_crew_id)
        ftl         = get_crew_duty_state(new_crew_id)
        if not leg or not new_crew or not ftl:
            return {"passed": False, "reason": "leg or crew not found"}
        licenses = get_licenses_for_crew_member(new_crew_id)
        leave    = get_leave_records_for_crew(new_crew_id)
        passed, reason = check_legality(new_crew, leg, ftl, licenses, leave, leg.scheduled_departure.date())
        return {"passed": passed, "reason": reason}
    return {"passed": True, "reason": None}


def _flush_new_proposals() -> None:
    """Immediately push any unpushed proposals into the push queue.
    Called right after an action executes so the alert appears in the same response."""
    from crew_ops_backend.db.database import SessionLocal
    from crew_ops_backend.db.repositories import disruption_repository
    from crew_ops_backend.clients.flight_schedule_client import get_flight_leg
    from crew_ops_backend.clients.crew_profile_client import get_crew_member
    from crew_ops_backend.conversation.formatter import format_push_notification
    from crew_ops_backend.conversation.push_queue import _push_queue
    with SessionLocal() as session:
        proposals = disruption_repository.get_unpushed_proposals(session)
        for p in proposals:
            leg = get_flight_leg(p["leg_id"])
            candidates = []
            if p.get("proposed_crew_id"):
                crew = get_crew_member(p["proposed_crew_id"])
                if crew:
                    candidates = [{"crew_id": crew.crew_id, "full_name": crew.full_name, "role": crew.role}]
            msg = format_push_notification(p, leg.model_dump() if leg else {}, candidates)
            _push_queue.append(msg)
            disruption_repository.mark_proposal_pushed(session, p["proposal_id"])
        session.commit()
