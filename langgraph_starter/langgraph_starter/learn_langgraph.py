"""
LANGGRAPH LEARNING — State, Nodes, Conditional Edges
=====================================================

This file teaches LangGraph concepts using a simple food order example.
No airline stuff. No complexity. Just one concept at a time.

Scenario:
  A customer places a food order.
  The system checks if the item is available.
  If available  → confirm the order → END
  If unavailable → suggest alternative → END

Run this file:
  python -m langgraph_starter.learn_langgraph

Concepts covered:
  1. What is State
  2. What is a Node
  3. How State flows between nodes
  4. What is a conditional edge
  5. How the graph decides which path to take
"""

from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph_starter.connection import get_llm

llm = get_llm()


# =============================================================================
# CONCEPT 1 — STATE
# =============================================================================
#
# State is a TypedDict — a plain Python dictionary with fixed keys.
# Think of it as a SHARED NOTEBOOK that every node can read and write to.
#
# Every node receives the FULL current state.
# Every node returns ONLY the fields it changed (partial update).
# LangGraph merges the partial update into the full state automatically.
#
# In this example, the state tracks everything about one food order:

class OrderState(TypedDict):
    item_requested: str        # what the customer wants — set at the start, never changes
    is_available: bool         # set by check_availability node
    alternative: str           # set by suggest_alternative node (only if unavailable)
    confirmation_message: str  # set by confirm_order node (only if available)
    final_response: str        # set by the last node — what customer sees


# =============================================================================
# CONCEPT 2 — NODES
# =============================================================================
#
# A node is just a plain Python function.
# It receives the full state dict as input.
# It returns a dict with ONLY the fields it wants to update.
#
# IMPORTANT: returning a field overwrites it in state.
#            NOT returning a field leaves it unchanged.
#
# Think of each node as one employee doing one specific job.


# NODE 1 — Check if item is available
# ------------------------------------
# Job: look at what the customer ordered, decide if we have it
# Reads:   state["item_requested"]
# Writes:  state["is_available"]

def check_availability(state: OrderState) -> dict:
    print(f"\n[Node: check_availability] Checking if '{state['item_requested']}' is available...")

    # In real system: query a database
    # Here: simple mock
    available_items = ["pizza", "burger", "pasta"]
    is_available = state["item_requested"].lower() in available_items

    print(f"[Node: check_availability] Result: {'AVAILABLE' if is_available else 'NOT AVAILABLE'}")

    # Returns ONLY the field this node is responsible for
    # State before this node:  { item_requested: "pizza", is_available: None, ... }
    # State after this node:   { item_requested: "pizza", is_available: True, ... }
    return {"is_available": is_available}


# NODE 2 — Confirm the order (only runs if item IS available)
# -----------------------------------------------------------
# Job: generate a confirmation message for the customer
# Reads:   state["item_requested"]
# Writes:  state["confirmation_message"], state["final_response"]

def confirm_order(state: OrderState) -> dict:
    print(f"\n[Node: confirm_order] Confirming order for '{state['item_requested']}'...")

    message = f"Great news! Your {state['item_requested']} is confirmed. Estimated delivery: 30 mins."

    print(f"[Node: confirm_order] Message: {message}")

    # State before: { item_requested: "pizza", is_available: True, confirmation_message: None, ... }
    # State after:  { item_requested: "pizza", is_available: True, confirmation_message: "...", final_response: "..." }
    return {
        "confirmation_message": message,
        "final_response": message
    }


# NODE 3 — Suggest alternative (only runs if item is NOT available)
# -----------------------------------------------------------------
# Job: tell the customer the item is unavailable and suggest something else
# Reads:   state["item_requested"]
# Writes:  state["alternative"], state["final_response"]

def suggest_alternative(state: OrderState) -> dict:
    print(f"\n[Node: suggest_alternative] '{state['item_requested']}' unavailable, finding alternative...")

    # In real system: LLM suggests based on menu
    # Here: simple mock
    alternatives = {"sushi": "ramen", "tacos": "burrito", "steak": "chicken"}
    alt = alternatives.get(state["item_requested"].lower(), "a house special")

    message = f"Sorry, {state['item_requested']} is unavailable today. How about {alt} instead?"

    print(f"[Node: suggest_alternative] Suggestion: {message}")

    # State before: { item_requested: "sushi", is_available: False, alternative: None, ... }
    # State after:  { item_requested: "sushi", is_available: False, alternative: "ramen", final_response: "..." }
    return {
        "alternative": alt,
        "final_response": message
    }


# =============================================================================
# CONCEPT 3 — CONDITIONAL EDGE
# =============================================================================
#
# A conditional edge is a function that looks at the current state
# and returns a STRING telling LangGraph which node to go to next.
#
# It is NOT a node — it does NOT update state.
# It is a ROUTER — it just reads state and returns a direction.
#
# Think of it as a traffic signal:
#   - reads the situation (state)
#   - returns "go left" or "go right"
#   - does not move the car itself
#
# This function runs AFTER check_availability node completes.
# It reads is_available from state and decides the next node.

def route_after_availability(state: OrderState) -> str:
    print(f"\n[Router: route_after_availability] is_available = {state['is_available']}")

    if state["is_available"]:
        print("[Router] → going to confirm_order")
        return "confirm_order"       # this string must match a node name in the graph
    else:
        print("[Router] → going to suggest_alternative")
        return "suggest_alternative" # this string must match a node name in the graph


# =============================================================================
# CONCEPT 4 — BUILDING THE GRAPH
# =============================================================================
#
# The graph wires everything together:
#   - which nodes exist
#   - where to start
#   - which edges connect which nodes
#   - which edges are conditional (use a router function)

builder = StateGraph(OrderState)

# Register all nodes
# First argument = name you give this node (used in edges)
# Second argument = the function that runs when this node is reached
builder.add_node("check_availability", check_availability)
builder.add_node("confirm_order", confirm_order)
builder.add_node("suggest_alternative", suggest_alternative)

# Set entry point — which node runs first
builder.set_entry_point("check_availability")

# Add a CONDITIONAL edge from check_availability
# After check_availability runs, call route_after_availability(state)
# The return value of that function determines the next node
# The dict maps possible return values → node names
builder.add_conditional_edges(
    "check_availability",           # from this node
    route_after_availability,       # call this router function
    {
        "confirm_order": "confirm_order",           # if router returns "confirm_order" → go here
        "suggest_alternative": "suggest_alternative" # if router returns "suggest_alternative" → go here
    }
)

# Add fixed edges — these always go to the same place, no condition
builder.add_edge("confirm_order", END)       # after confirm → done
builder.add_edge("suggest_alternative", END) # after suggest → done

graph = builder.compile()


# =============================================================================
# CONCEPT 5 — WHAT HAPPENS WHEN YOU RUN IT
# =============================================================================
#
# graph.invoke() takes the INITIAL state and runs the graph.
# You only need to set the fields that are known at the start.
# All other fields start as None and get filled in by nodes.
#
# State evolution for "pizza" (available):
#
#   START
#   state = { item_requested: "pizza", is_available: None, alternative: None,
#             confirmation_message: None, final_response: None }
#
#   → check_availability runs
#   state = { item_requested: "pizza", is_available: True, alternative: None,
#             confirmation_message: None, final_response: None }
#
#   → router reads is_available=True → returns "confirm_order"
#
#   → confirm_order runs
#   state = { item_requested: "pizza", is_available: True, alternative: None,
#             confirmation_message: "Great news! ...", final_response: "Great news! ..." }
#
#   → fixed edge → END
#
# ─────────────────────────────────────────────────────────────────────────────
#
# State evolution for "sushi" (unavailable):
#
#   START
#   state = { item_requested: "sushi", is_available: None, ... }
#
#   → check_availability runs
#   state = { item_requested: "sushi", is_available: False, ... }
#
#   → router reads is_available=False → returns "suggest_alternative"
#
#   → suggest_alternative runs
#   state = { item_requested: "sushi", is_available: False,
#             alternative: "ramen", final_response: "Sorry, sushi is unavailable..." }
#
#   → fixed edge → END


def run(item: str):
    print(f"\n{'='*60}")
    print(f"ORDER: {item}")
    print('='*60)

    # Initial state — only set what you know at the start
    # Everything else is None until a node fills it in
    initial_state: OrderState = {
        "item_requested": item,
        "is_available": None,
        "alternative": None,
        "confirmation_message": None,
        "final_response": None,
    }

    result = graph.invoke(initial_state)

    print(f"\n--- FINAL STATE ---")
    print(f"item_requested:       {result['item_requested']}")
    print(f"is_available:         {result['is_available']}")
    print(f"alternative:          {result['alternative']}")
    print(f"confirmation_message: {result['confirmation_message']}")
    print(f"final_response:       {result['final_response']}")
    print(f"\n>>> Customer sees: {result['final_response']}")


if __name__ == "__main__":
    run("pizza")   # available   → goes to confirm_order
    run("sushi")   # unavailable → goes to suggest_alternative
    run("burger")  # available   → goes to confirm_order
    run("tacos")   # unavailable → goes to suggest_alternative
