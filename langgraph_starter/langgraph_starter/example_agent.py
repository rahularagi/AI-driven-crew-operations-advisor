"""
A complete, minimal LangGraph agent that calls tools in a loop (ReAct pattern).

Concepts demonstrated, in order:
  1. State      - the data that flows through the graph (here: a running message list)
  2. Tools      - plain Python functions the LLM can decide to call
  3. Nodes      - functions that read/update state ("agent" and "tools" below)
  4. Edges      - fixed transitions between nodes
  5. Conditional edges - branching logic based on current state
  6. Compiling & running the graph

Flow:
  START -> agent -> (LLM decides) -> tools -> agent -> ... -> END
                  \-> (no tool call) -----------------------> END

Run this file directly:
    python -m langgraph_starter.example_agent
"""

from langgraph.graph import END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

from langgraph_starter.connection import get_llm


# --- 1. Tools -----------------------------------------------------------
# Each @tool becomes something the LLM can choose to call. The docstring
# is sent to the LLM as the tool description, so it must clearly state
# what the tool does and what its arguments mean.

@tool
def get_order_status(order_id: str) -> str:
    """Look up the current status of an order by its ID."""
    fake_db = {
        "123": "shipped, arriving in 2 days",
        "456": "processing, not yet shipped",
    }
    return fake_db.get(order_id, f"No order found with id {order_id}")


@tool
def cancel_order(order_id: str) -> str:
    """Cancel an order by its ID. Only works if the order has not shipped yet."""
    return f"Order {order_id} has been cancelled."


TOOLS = [get_order_status, cancel_order]


# --- 2. State ------------------------------------------------------------
# MessagesState is a prebuilt state schema: {"messages": [...]}.
# Every node receives the current state dict and returns a partial update
# to merge into it. For messages specifically, LangGraph appends new
# messages to the list rather than overwriting it.

# (No custom class needed here since MessagesState already fits this agent.
#  For a custom state, you'd define: class MyState(TypedDict): foo: str)


# --- 3. Nodes ------------------------------------------------------------

llm = get_llm()
llm_with_tools = llm.bind_tools(TOOLS)


def call_model(state: MessagesState) -> dict:
    """The 'agent' node: ask the LLM what to do next given the conversation so far."""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


tool_node = ToolNode(TOOLS)  # prebuilt node: executes whichever tool(s) the LLM requested


# --- 4. Conditional edge --------------------------------------------------

def route_after_agent(state: MessagesState) -> str:
    """Decide what happens after the agent node runs.

    If the LLM's last message contains tool calls, go execute them.
    Otherwise the LLM has given a final answer, so we stop.
    """
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


# --- 5. Build and compile the graph --------------------------------------

builder = StateGraph(MessagesState)

builder.add_node("agent", call_model)
builder.add_node("tools", tool_node)

builder.set_entry_point("agent")
builder.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")  # after running tools, go back to the agent to react to results

graph = builder.compile()


# --- 6. Run it ------------------------------------------------------------

if __name__ == "__main__":
    result = graph.invoke(
        {"messages": [("user", "What's the status of order 123, and cancel it if it hasn't shipped?")]}
    )

    print("\n--- Full message trace ---")
    for msg in result["messages"]:
        msg.pretty_print()

    print("\n--- Final answer ---")
    print(result["messages"][-1].content)
