from datetime import date, datetime, timedelta, timezone
from typing import Any

from langgraph.graph import StateGraph, END

from crew_ops_backend.clients.crew_profile_client import get_all_crew_members
from crew_ops_backend.conversation.session import (
    PendingConfirmation, PendingSimulation, SessionState,
)
from crew_ops_backend.conversation.tools import (
    action_accept_proposal,
    action_approve_roster_leg,
    action_mark_crew_unavailable,
    action_reassign_crew,
    action_reject_proposal,
    get_crew_ftl,
    get_crew_schedule,
    get_leg_status,
    get_pending_proposals,
    get_roster,
    simulate_crew_removal,
    simulate_crew_swap,
    simulate_leg_cancellation,
)


# ─── Keywords ─────────────────────────────────────────────────────────────────

_QUERY_KEYWORDS    = {"schedule", "ftl", "duty", "hours", "status", "roster", "proposal", "proposals", "inbox", "leg", "show", "get", "list", "check", "available", "availability", "who", "crew", "now", "today", "current", "free", "on", "duty"}
_SIMULATE_KEYWORDS = {"simulate", "simulation", "what if", "whatif", "impact", "swap", "cancel"}
_ACTION_KEYWORDS   = {"mark", "unavailable", "reassign", "assign", "accept", "reject", "approve"}
_CONFIRM_YES       = {"yes", "y", "confirm"}
_CONFIRM_NO        = {"no", "n", "cancel"}

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
        "query":    "execute",
        "simulate": "execute",
        "confirm":  "confirm",
        "action":   "confirm",
        "clarify":  "format",
    })
    graph.add_edge("execute", "format")
    graph.add_edge("confirm", "execute")
    graph.add_edge("format",  END)

    return graph.compile()


# ─── Nodes ────────────────────────────────────────────────────────────────────

def gateway_node(state: dict) -> dict:
    msg    = state["message"].lower()
    tokens = set(msg.split())
    state["_relevant"] = bool(
        tokens & _QUERY_KEYWORDS or
        tokens & _SIMULATE_KEYWORDS or
        tokens & _ACTION_KEYWORDS or
        tokens & _CONFIRM_YES or
        tokens & _CONFIRM_NO or
        any(k in msg for k in ("crew", "leg", "flight", "roster", "proposal", "ftl"))
    )
    return state


def gateway_decision(state: dict) -> str:
    return "relevant" if state.get("_relevant") else "irrelevant"


def classify_node(state: dict) -> dict:
    msg     = state["message"].lower()
    tokens  = set(msg.split())
    session: SessionState = state["session"]

    # Determine mode
    if tokens & _SIMULATE_KEYWORDS:
        mode = "SIMULATE"
    elif tokens & _ACTION_KEYWORDS:
        mode = "ACTION"
    else:
        mode = "QUERY"

    # Extract entities
    entities   = {}
    crew_list  = get_all_crew_members()
    crew_by_id = {c.crew_id.lower(): c.crew_id for c in crew_list}

    for word in msg.split():
        w = word.strip(".,?!")
        if w in crew_by_id:
            if "crew_id_a" in entities:
                entities["crew_id_b"] = crew_by_id[w]
            elif "crew_id" in entities:
                entities["crew_id_a"] = entities.pop("crew_id")
                entities["crew_id_b"] = crew_by_id[w]
            else:
                entities["crew_id"] = crew_by_id[w]
        elif w.startswith("l") and w[1:].isdigit():
            if "leg_id_a" in entities:
                entities["leg_id_b"] = w.upper()
            elif "leg_id" in entities:
                entities["leg_id_a"] = entities.pop("leg_id")
                entities["leg_id_b"] = w.upper()
            else:
                entities["leg_id"] = w.upper()
        elif w.startswith("p") and w[1:].isdigit():
            entities["proposal_id"] = w.upper()

    # Determine action_type
    action_type = None
    if mode == "ACTION":
        if "mark" in tokens or "unavailable" in tokens or "sick" in tokens:
            action_type = "MARK_UNAVAILABLE"
        elif "reassign" in tokens or "assign" in tokens:
            action_type = "REASSIGN"
        elif "accept" in tokens:
            action_type = "ACCEPT_PROPOSAL"
        elif "reject" in tokens:
            action_type = "REJECT_PROPOSAL"
        elif "approve" in tokens:
            action_type = "APPROVE_LEG"

    if mode == "ACTION" and session.pending_simulation and tokens & _CONFIRM_YES:
        action_type = "APPLY_SIMULATION"

    # Merge entities into session
    merged = {**session.last_entities, **entities}
    session.last_entities = merged
    session.last_intent   = mode
    state["session"]      = session

    state["intent"] = {
        "mode":                 mode,
        "action_type":          action_type,
        "entities":             merged,
        "raw_message":          state["message"],
        "ambiguous":            False,
        "clarification_needed": None,
    }
    return state


def route_node(state: dict) -> dict:
    return state


def route_decision(state: dict) -> str:
    intent:  dict         = state["intent"]
    session: SessionState = state["session"]
    message: str          = state["message"].strip().lower()

    if session.pending_confirmation:
        if session.pending_confirmation.expires_at < datetime.now(timezone.utc):
            session.pending_confirmation  = None
            state["session"]              = session
            state["_confirmation_expired"] = True
            return "clarify"
        if message in _CONFIRM_YES:
            return "confirm"
        if message in _CONFIRM_NO:
            return "confirm"
        return "clarify"

    if session.pending_simulation and intent["action_type"] == "APPLY_SIMULATION":
        return "action"

    if intent["mode"] == "QUERY":
        return "query"
    if intent["mode"] == "SIMULATE":
        return "simulate"
    return "action"


def confirm_node(state: dict) -> dict:
    session: SessionState = state["session"]
    message: str          = state["message"].strip().lower()
    intent:  dict         = state["intent"]

    if session.pending_confirmation and message in _CONFIRM_NO:
        session.pending_confirmation = None
        state["session"]       = session
        state["response"]      = "Action cancelled."
        state["mode"]          = "CONFIRM"
        state["_skip_execute"] = True
        return state

    if session.pending_confirmation and message in _CONFIRM_YES:
        state["_confirmed_args"] = session.pending_confirmation.action_args
        state["_confirmed_type"] = session.pending_confirmation.action_type
        session.pending_confirmation = None
        state["session"] = session
        return state

    if session.pending_simulation and intent["action_type"] == "APPLY_SIMULATION":
        sim         = session.pending_simulation
        action_args = {"crew_id": sim.crew_id, "leg_id": sim.leg_id, "reason": sim.reason}
        summary     = (
            f"Confirm marking {sim.crew_id} unavailable for leg {sim.leg_id} "
            f"(reason: {sim.reason}, severity: {sim.severity})?\n\nConfirm? [YES / NO]"
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

    action_args    = _build_action_args(intent)
    legality_check = _pre_check_legality(intent, action_args)

    if not legality_check["passed"]:
        state["response"]      = f"Cannot proceed: {legality_check['reason']}"
        state["mode"]          = "ACTION"
        state["_skip_execute"] = True
        return state

    summary = (
        f"Confirm: {intent['action_type']} — {action_args}\n\nConfirm? [YES / NO]"
    )
    session.pending_confirmation = PendingConfirmation(
        action_type = intent["action_type"] or "ACTION",
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

    intent:  dict         = state["intent"]
    session: SessionState = state["session"]
    user_id: str          = state["user_id"]

    if state.get("_confirmed_args"):
        result = _dispatch_action(state["_confirmed_type"], state["_confirmed_args"], user_id)
        state["tool_result"] = result
        state["mode"]        = "ACTION"
        return state

    if intent["mode"] == "SIMULATE":
        result     = _dispatch_simulate(intent)
        candidates = result.get("candidates", [])
        crew_id    = intent["entities"].get("crew_id", "")
        leg_id     = intent["entities"].get("leg_id", "")
        if candidates and crew_id and leg_id:
            session.pending_simulation = PendingSimulation(
                crew_id  = crew_id,
                leg_id   = leg_id,
                reason   = intent["entities"].get("reason", "UNAVAILABLE"),
                severity = "MEDIUM",
            )
            state["session"] = session
        state["tool_result"] = result
        state["mode"]        = "SIMULATE"
        return state

    result = _dispatch_query(intent)
    state["tool_result"] = result
    state["mode"]        = "QUERY"
    return state


def format_node(state: dict) -> dict:
    if state.get("response"):
        return state

    if not state.get("_relevant"):
        state["response"] = _HELP_MESSAGE
        state["mode"]     = "IRRELEVANT"
        return state

    intent: dict = state["intent"]
    mode:   str  = state.get("mode", "QUERY")
    result       = state.get("tool_result", {})

    if state.get("_confirmation_expired"):
        state["response"] = "Your confirmation timed out. Please repeat your request."
        state["mode"]     = "CLARIFY"
        return state

    if intent["ambiguous"]:
        state["response"] = intent["clarification_needed"] or "Could you clarify your request?"
        state["mode"]     = "CLARIFY"
        return state

    session: SessionState = state["session"]
    if session.pending_confirmation and not result:
        state["response"] = "Please reply YES to confirm or NO to cancel."
        state["mode"]     = "CLARIFY"
        return state

    if isinstance(result, dict) and "error" in result:
        state["response"] = f"Sorry, I couldn't process that: {result['error']}"
        state["mode"]     = mode
        return state

    response = _format_result(mode, result)

    if mode == "SIMULATE" and result.get("candidates"):
        response += "\n\nWant me to raise this as a disruption? [YES / NO]"

    state["response"] = response
    return state


# ─── Dispatch helpers ─────────────────────────────────────────────────────────

def _dispatch_query(intent: dict) -> Any:
    e   = intent["entities"]
    msg = intent["raw_message"].lower()

    if "leg_id" in e and not intent["action_type"]:
        return get_leg_status(e["leg_id"])
    if "crew_id" in e and ("schedule" in msg or "assignment" in msg):
        start = _parse_date(e.get("start_date") or date.today().isoformat())
        end   = _parse_date(e.get("end_date")   or date.today().isoformat())
        return get_crew_schedule(e["crew_id"], start, end)
    if "crew_id" in e and ("ftl" in msg or "hours" in msg or "duty" in msg):
        return get_crew_ftl(e["crew_id"])
    if "proposal" in msg or "inbox" in msg:
        return get_pending_proposals()
    if "roster" in msg:
        start = _parse_date(e.get("start_date") or date.today().isoformat())
        end   = _parse_date(e.get("end_date")   or date.today().isoformat())
        return get_roster(start, end)
    if "leg_id" in e:
        return get_leg_status(e["leg_id"])
    if "crew_id" in e:
        return get_crew_ftl(e["crew_id"])
    return {"error": "insufficient context to answer query"}


def _dispatch_simulate(intent: dict) -> dict:
    e   = intent["entities"]
    msg = intent["raw_message"].lower()

    if "swap" in msg and "crew_id_a" in e and "crew_id_b" in e:
        return simulate_crew_swap(
            e["crew_id_a"], e["crew_id_b"],
            e.get("leg_id_a", e.get("leg_id", "")),
            e.get("leg_id_b", e.get("leg_id", "")),
        )
    if ("cancel" in msg or "cancell" in msg) and "leg_id" in e:
        return simulate_leg_cancellation(e["leg_id"])
    if "crew_id" in e and "leg_id" in e:
        return simulate_crew_removal(e["crew_id"], e["leg_id"])
    return {"error": "insufficient entities for simulation"}


def _dispatch_action(action_type: str, action_args: dict, user_id: str) -> dict:
    if action_type == "MARK_UNAVAILABLE":
        return action_mark_crew_unavailable(
            action_args["crew_id"], action_args["leg_id"], action_args.get("reason", "SICK_CALL")
        )
    if action_type == "REASSIGN":
        return action_reassign_crew(
            action_args["leg_id"], action_args["old_crew_id"],
            action_args["new_crew_id"], user_id
        )
    if action_type == "ACCEPT_PROPOSAL":
        return action_accept_proposal(action_args["proposal_id"], user_id)
    if action_type == "REJECT_PROPOSAL":
        return action_reject_proposal(
            action_args["proposal_id"], user_id, action_args.get("rejection_reason", "")
        )
    if action_type == "APPROVE_LEG":
        return action_approve_roster_leg(action_args["leg_id"], user_id)
    return {"error": f"unknown action_type: {action_type}"}


def _build_action_args(intent: dict) -> dict:
    e = intent["entities"]
    t = intent["action_type"] or ""
    if t == "MARK_UNAVAILABLE":
        return {"crew_id": e.get("crew_id", ""), "leg_id": e.get("leg_id", ""), "reason": e.get("reason", "SICK_CALL")}
    if t == "REASSIGN":
        return {"leg_id": e.get("leg_id", ""), "old_crew_id": e.get("old_crew_id", ""), "new_crew_id": e.get("new_crew_id", "")}
    if t == "ACCEPT_PROPOSAL":
        return {"proposal_id": e.get("proposal_id", "")}
    if t == "REJECT_PROPOSAL":
        return {"proposal_id": e.get("proposal_id", ""), "rejection_reason": e.get("rejection_reason", "")}
    if t == "APPROVE_LEG":
        return {"leg_id": e.get("leg_id", "")}
    return dict(e)


def _pre_check_legality(intent: dict, action_args: dict) -> dict:
    if intent["action_type"] == "REASSIGN":
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


def _format_result(mode: str, result: Any) -> str:
    if isinstance(result, list):
        if not result:
            return "No records found."
        lines = []
        for item in result[:10]:
            if isinstance(item, dict):
                lines.append("  " + ", ".join(f"{k}: {v}" for k, v in item.items()))
            else:
                lines.append(f"  {item}")
        return f"Found {len(result)} record(s):\n" + "\n".join(lines)
    if isinstance(result, dict):
        return "\n".join(f"{k}: {v}" for k, v in result.items())
    return str(result)


def _parse_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
