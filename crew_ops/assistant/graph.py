# graph.py
# This is the brain of the assistant.
# It wires together the LLM, the tools, and the synthesizer
# into a LangGraph state machine that processes every user question.

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from crew_ops.assistant.state import AssistantState
from crew_ops.assistant.prompts import SYSTEM_PROMPT, SYNTHESIZER_PROMPT

# Import all crew tools — these query crew member data
from crew_ops.assistant.tools.crew_tools import (
    get_available_crew,
    get_crew_by_role,
    get_crew_qualifications,
    get_crew_by_base,
    get_crew_contact,
)

# Import all flight tools — these query flight schedule data
from crew_ops.assistant.tools.flight_tools import (
    get_flights_by_date,
    get_flight_by_number,
    get_unassigned_flights,
    get_flights_by_route,
)

# Import all FTL tools — these query flight time limits and rest compliance
from crew_ops.assistant.tools.ftl_tools import (
    get_ftl_status,
    get_crew_rest_compliance,
    get_crew_hours_last_28_days,
    get_crew_approaching_limit,
)

# Import all roster tools — these query roster assignments and conflicts
from crew_ops.assistant.tools.roster_tools import (
    get_roster_by_date,
    get_crew_roster,
    get_open_positions,
    get_roster_conflicts,
)

# Settings holds the API keys and DB URL from the .env file
from crew_ops.config.settings import settings


# ── LLM Setup ────────────────────────────────────────────────────────────────
# We use Gemini 2.0 Flash via Google Generative AI
# temperature=0 means deterministic — no creative guessing, just facts

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    google_api_key=settings.google_api_key,
    temperature=0,
)


# ── Tool Registry ─────────────────────────────────────────────────────────────
# ALL_TOOLS is the complete list of functions the LLM is allowed to call.
# The LLM sees their names and docstrings and decides which ones to use.

ALL_TOOLS = [
    # Crew tools
    get_available_crew,
    get_crew_by_role,
    get_crew_qualifications,
    get_crew_by_base,
    get_crew_contact,
    # Flight tools
    get_flights_by_date,
    get_flight_by_number,
    get_unassigned_flights,
    get_flights_by_route,
    # FTL tools
    get_ftl_status,
    get_crew_rest_compliance,
    get_crew_hours_last_28_days,
    get_crew_approaching_limit,
    # Roster tools
    get_roster_by_date,
    get_crew_roster,
    get_open_positions,
    get_roster_conflicts,
]

# Bind tools to the LLM so it knows what functions it can call
llm_with_tools = llm.bind_tools(ALL_TOOLS)


# ── Node 1: Agent ─────────────────────────────────────────────────────────────
# The agent node is the LLM's decision point.
# It reads the conversation history and either:
#   a) calls one or more tools to get data, OR
#   b) writes a direct answer if no tools are needed

def agent_node(state: AssistantState) -> dict:
    """LLM decides what tools to call or writes a direct answer."""
    # Prepend the system prompt so the LLM knows its role and rules
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    # Add the LLM response to the message history
    return {"messages": [response]}


# ── Node 2: Synthesizer ───────────────────────────────────────────────────────
# The synthesizer node runs AFTER tools have returned results.
# It collects all tool outputs and asks the LLM to write a clean,
# plain-English summary for the OCC manager.

def synthesizer_node(state: AssistantState) -> dict:
    """Summarizes tool results into a plain-English answer."""
    # Collect every tool message from the conversation history
    tool_outputs = []
    for msg in state["messages"]:
        # Tool messages have a 'name' attribute with the tool's function name
        if hasattr(msg, "name") and msg.name:
            tool_outputs.append(f"{msg.name}: {msg.content}")

    if not tool_outputs:
        # No tools were called — the agent answered directly, use that answer
        last = state["messages"][-1]
        return {"final_answer": last.content}

    # Join all tool outputs into one block of text for the synthesizer
    combined = "\n\n".join(tool_outputs)
    prompt = f"{SYNTHESIZER_PROMPT}\n\nTool Results:\n{combined}"

    # Ask the LLM to summarize the tool results into a clean answer
    response = llm.invoke([HumanMessage(content=prompt)])
    return {"final_answer": response.content}


# ── Routing Function ──────────────────────────────────────────────────────────
# After the agent node runs, this function decides what happens next:
#   - If the LLM made tool calls → go to the tools node to execute them
#   - If the LLM gave a direct answer → go to synthesizer to finalize it

def should_continue(state: AssistantState) -> str:
    """Route to tools if the LLM made tool calls, else synthesize."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "synthesizer"


# ── Graph Assembly ────────────────────────────────────────────────────────────
# ToolNode is a LangGraph built-in that automatically executes
# whatever tool calls the LLM requested and adds results to messages.

tool_node = ToolNode(ALL_TOOLS)

# Create the state graph using our AssistantState schema
graph_builder = StateGraph(AssistantState)

# Register all three nodes
graph_builder.add_node("agent", agent_node)
graph_builder.add_node("tools", tool_node)
graph_builder.add_node("synthesizer", synthesizer_node)

# Every conversation starts at the agent node
graph_builder.set_entry_point("agent")

# After agent runs, route to tools or synthesizer based on should_continue
graph_builder.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "synthesizer": "synthesizer"},
)

# After tools run, go back to agent so it can process the results
graph_builder.add_edge("tools", "agent")

# After synthesizer runs, we're done
graph_builder.add_edge("synthesizer", END)

# Compile the graph into a runnable object
# This is what the API router will call for every user question
assistant_graph = graph_builder.compile()