# graph.py
# Flow: agent → [tools?] → synthesizer → END
# Max 2 LLM calls per request. No loops.

import itertools
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from crew_ops.assistant.state import AssistantState
from crew_ops.assistant.prompts import SYSTEM_PROMPT, SYNTHESIZER_PROMPT

from crew_ops.assistant.tools.crew_tools import (
    get_available_crew, get_crew_by_role, get_crew_by_base,
    get_crew_contact, get_crew_licenses, get_crew_leave, get_crew_unavailability,
)
from crew_ops.assistant.tools.flight_tools import (
    get_flights_today, get_flight_by_number, get_delayed_flights, get_flight_crew,
)
from crew_ops.assistant.tools.ftl_tools import (
    get_crew_ftl_state, get_crew_near_ftl_limit, get_reserve_crew,
)
from crew_ops.assistant.tools.roster_tools import (
    get_crew_roster, get_unassigned_legs, get_roster_plan_status,
)

from crew_ops.config.settings import settings


# ── Groq Round-Robin Key Pool ─────────────────────────────────────────────────
# Reads GROQ_API_KEY from .env as comma-separated keys.
# Example: GROQ_API_KEY=gsk_key1,gsk_key2,gsk_key3

def _load_groq_keys() -> list[str]:
    raw = settings.groq_api_key
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise ValueError("GROQ_API_KEY not set in .env — add comma-separated Groq keys.")
    return keys


_key_cycle = itertools.cycle(_load_groq_keys())  # infinite round-robin


def _next_llm(tools: list | None = None) -> ChatGroq:
    """Returns a ChatGroq instance on the next key in rotation."""
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=next(_key_cycle),
        temperature=0,
    )
    return llm.bind_tools(tools) if tools else llm


# ── Tool Registry ─────────────────────────────────────────────────────────────

ALL_TOOLS = [
    get_available_crew, get_crew_by_role, get_crew_by_base,
    get_crew_contact, get_crew_licenses, get_crew_leave, get_crew_unavailability,
    get_flights_today, get_flight_by_number, get_delayed_flights, get_flight_crew,
    get_crew_ftl_state, get_crew_near_ftl_limit, get_reserve_crew,
    get_crew_roster, get_unassigned_legs, get_roster_plan_status,
]


# ── Node 1: Agent ─────────────────────────────────────────────────────────────

def agent_node(state: AssistantState) -> dict:
    """LLM reads the question and decides which tools to call."""
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = _next_llm(tools=ALL_TOOLS).invoke(messages)
    return {"messages": [response]}


# ── Node 2: Synthesizer ───────────────────────────────────────────────────────

def synthesizer_node(state: AssistantState) -> dict:
    """Reads tool results from state and writes a plain-English answer."""
    tool_outputs = []
    for msg in state["messages"]:
        if hasattr(msg, "name") and msg.name:
            tool_outputs.append(f"{msg.name}: {msg.content}")

    if not tool_outputs:
        # Agent answered directly without tools
        last = state["messages"][-1]
        return {"final_answer": last.content}

    combined = "\n\n".join(tool_outputs)
    prompt = f"{SYNTHESIZER_PROMPT}\n\nTool Results:\n{combined}"
    response = _next_llm().invoke([HumanMessage(content=prompt)])
    return {"final_answer": response.content}


# ── Routing ───────────────────────────────────────────────────────────────────

def should_continue(state: AssistantState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "synthesizer"


# ── Graph Assembly ────────────────────────────────────────────────────────────

tool_node = ToolNode(ALL_TOOLS)

graph_builder = StateGraph(AssistantState)
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)
graph_builder.add_node("synthesizer", synthesizer_node)

graph_builder.set_entry_point("agent")
graph_builder.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "synthesizer": "synthesizer"},
)
graph_builder.add_edge("tools", "synthesizer")  # no loop
graph_builder.add_edge("synthesizer", END)

assistant_graph = graph_builder.compile()