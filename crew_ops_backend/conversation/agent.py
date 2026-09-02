from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.graph import StateGraph, END

from crew_ops.clients.crew_profile_client import get_all_crew_members
from crew_ops.conversation.formatter import build_confirmation_package, format_response
from crew_ops.conversation.intent import Intent, classify_intent
from crew_ops.conversation.session import (
    PendingConfirmation, PendingSimulation, SessionState, get_session, save_session
)
from crew_ops.conversation.tools import (
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


# ─── Graph builder ────────────────────────────────────────────────────────────

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
        "query":   "execute",
        "simulate":"execute",
        "confirm": "confirm",
        "action":  "confirm",
        "clarify": "format",
    })
    graph.add_edge("execute", "format")
    graph.add_edge("confirm", "execute")
    graph.add_edge("format",  END)

    return graph.compile()


# ─── Nodes ────────────────────────────────────────────────────────────────────

def classify_node(state: dict) -> dict:
    crew_list = [
        {"crew_id": c.crew_id, "full_name": c.full_name, "role": c.role, "home_base": c.home_base}
        for c in get_all_crew_members()
    ]
    intent = classify_intent(state["message"], state["session"], crew_list)
    state["intent"] = intent
    # persist entities for follow-up turns
    if intent.entities:
        session: SessionState = state["session"]
        session.last_entities = {**session.last_entities, **intent.entities}
        session.last_intent   = intent.mode
        state["session"]      = session
    return state


def route_node(state: dict) -> dict:
    return state


def route_decision(state: dict) -> str:
    intent:  Intent       = state["intent"]
    session: SessionState = state["session"]
    message: str          = state["message"].strip().upper()

    # Ambiguous — ask for clarification (response set in format_node)
    if intent.ambiguous:
        return "clarify"

    # Human responding to a pending confirmation
    if session.pending_confirmation:
        if message in ("YES", "Y", "CONFIRM"):
            return "confirm"
        if message in ("NO", "N", "CANCEL"):
            return "confirm"   # confirm_node handles the NO branch
        # Any other message while confirmation is pending — ask for clarification
        return "clarify"

    # Human applying a pending simulation
    if session.pending_simulation and intent.action_type == "APPLY_SIMULATION":
        return "action"

    if intent.mode == "QUERY":
        return "query"
    if intent.mode == "SIMULATE":
        return "simulate"
    return "action"


def confirm_node(state: dict) -> dict:
    session: SessionState = state["session"]
    message: str          = state["message"].strip().upper()
    intent:  Intent       = state["intent"]

    # ── Human said NO to a pending confirmation ──
    if session.pending_confirmation and message in ("NO", "N", "CANCEL"):
        session.pending_confirmation = None
        state["session"]       = session
        state["response"]      = "Action cancelled."
        state["mode"]          = "CONFIRM"
        state["_skip_execute"] = True
        return state

    # ── Human said YES to a pending confirmation ──
    if session.pending_confirmation and message in ("YES", "Y", "CONFIRM"):
        state["_confirmed_args"] = session.pending_confirmation.action_args
        state["_confirmed_type"] = session.pending_confirmation.action_type
        session.pending_confirmation = None
        state["session"] = session
        return state

    # ── APPLY_SIMULATION: convert pending simulation into an action ──
    if session.pending_simulation and intent.action_type == "APPLY_SIMULATION":
        sim = session.pending_simulation
        action_args = {
            "crew_id":  sim.crew_id,
            "leg_id":   sim.leg_id,
            "reason":   sim.reason,
        }
        summary = build_confirmation_package(
            "MARK_UNAVAILABLE", action_args,
            {"passed": True, "note": f"severity={sim.severity}"}
        )
        session.pending_confirmation = PendingConfirmation(
            action_type = "MARK_UNAVAILABLE",
            action_args = action_args,
            summary     = summary,
            expires_at  = datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.pending_simulation = None
        state["session"]               = session
        state["response"]              = summary
        state["mode"]                  = "ACTION"
        state["requires_confirmation"] = True
        state["_skip_execute"]         = True
        return state

    # ── New ACTION: build confirmation package ──
    action_args    = _build_action_args(intent, state)
    legality_check = _pre_check_legality(intent, action_args)

    if not legality_check["passed"]:
        state["response"]      = f"Cannot proceed: {legality_check['reason']}"
        state["mode"]          = "ACTION"
        state["_skip_execute"] = True
        return state

    summary = build_confirmation_package(intent.action_type or "ACTION", action_args, legality_check)
    session.pending_confirmation = PendingConfirmation(
        action_type = intent.action_type or "ACTION",
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

    # ── Post-confirmation: execute the confirmed action ──
    if state.get("_confirmed_args"):
        result = _dispatch_action(state["_confirmed_type"], state["_confirmed_args"], user_id)
        state["tool_result"] = result
        state["mode"]        = "ACTION"
        return state

    # ── SIMULATE ──
    if intent.mode == "SIMULATE":
        result = _dispatch_simulate(intent)
        state["tool_result"] = result
        state["mode"]        = "SIMULATE"
        # store pending simulation if candidates were found
        candidates = result.get("candidates", [])
        crew_id    = intent.entities.get("crew_id", "")
        leg_id     = intent.entities.get("leg_id", "")
        if candidates and crew_id and leg_id:
            session.pending_simulation = PendingSimulation(
                crew_id  = crew_id,
                leg_id   = leg_id,
                reason   = intent.entities.get("reason", "UNAVAILABLE"),
                severity = "MEDIUM",
            )
            state["session"] = session
        return state

    # ── QUERY ──
    result = _dispatch_query(intent)
    state["tool_result"] = result
    state["mode"]        = "QUERY"
    return state


def format_node(state: dict) -> dict:
    # Already set by confirm_node (confirmation package or cancel)
    if state.get("response"):
        return state

    intent: Intent = state["intent"]
    mode:   str    = state.get("mode", "QUERY")
    result         = state.get("tool_result", {})

    # Clarify branch — no LLM call needed
    if intent.ambiguous or state.get("mode") == "CLARIFY":
        state["response"] = intent.clarification_needed or "Could you clarify your request?"
        state["mode"]     = "CLARIFY"
        return state

    # Pending confirmation — unrecognised response
    session: SessionState = state["session"]
    if session.pending_confirmation and not state.get("tool_result"):
        state["response"] = "Please reply YES to confirm or NO to cancel."
        state["mode"]     = "CLARIFY"
        return state

    response = format_response(mode, result, intent.raw_message)

    if mode == "SIMULATE" and result.get("candidates"):
        response += "\n\nWant me to raise this as a disruption? [YES / NO]"

    state["response"] = response
    return state


# ─── Dispatch helpers ─────────────────────────────────────────────────────────

def _dispatch_query(intent: Intent) -> Any:
    e = intent.entities
    action = intent.action_type or ""

    if "leg_id" in e and not action:
        return get_leg_status(e["leg_id"])
    if "crew_id" in e and ("schedule" in intent.raw_message.lower() or "assignment" in intent.raw_message.lower()):
        from datetime import date
        start = e.get("start_date") or date.today().isoformat()
        end   = e.get("end_date")   or date.today().isoformat()
        return get_crew_schedule(e["crew_id"], _parse_date(start), _parse_date(end))
    if "crew_id" in e and ("ftl" in intent.raw_message.lower() or "hours" in intent.raw_message.lower() or "duty" in intent.raw_message.lower()):
        return get_crew_ftl(e["crew_id"])
    if "proposal" in intent.raw_message.lower() or "inbox" in intent.raw_message.lower():
        return get_pending_proposals()
    if "roster" in intent.raw_message.lower():
        from datetime import date
        start = e.get("start_date") or date.today().isoformat()
        end   = e.get("end_date")   or date.today().isoformat()
        return get_roster(_parse_date(start), _parse_date(end))
    if "leg_id" in e:
        return get_leg_status(e["leg_id"])
    if "crew_id" in e:
        return get_crew_ftl(e["crew_id"])
    if "proposal" in intent.raw_message.lower() or "inbox" in intent.raw_message.lower():
        return get_pending_proposals()
    return {"error": "insufficient context to answer query"}


def _dispatch_simulate(intent: Intent) -> dict:
    e = intent.entities
    msg = intent.raw_message.lower()

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


def _build_action_args(intent: Intent, state: dict) -> dict:
    e = intent.entities
    t = intent.action_type or ""
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


def _pre_check_legality(intent: Intent, action_args: dict) -> dict:
    """
    Fast pre-check before showing confirmation. Only runs for REASSIGN
    (legality check on the new crew member). All other actions are safe to confirm
    without a pre-check — the action tool itself will fail-fast if illegal.
    """
    if intent.action_type == "REASSIGN":
        from crew_ops.clients.crew_profile_client import get_crew_member
        from crew_ops.clients.flight_schedule_client import get_flight_leg
        from crew_ops.clients.ftl_client import get_crew_duty_state
        from crew_ops.clients.license_client import get_licenses_for_crew_member
        from crew_ops.clients.leave_client import get_leave_records_for_crew
        from crew_ops.rules.legality import check_legality

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


def _parse_date(value: str):
    from datetime import date
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
