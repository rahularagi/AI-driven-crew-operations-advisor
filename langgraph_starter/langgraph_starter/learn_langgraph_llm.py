"""
LANGGRAPH LEARNING — Where LLM Adds Intelligence
=================================================

This file upgrades learn_langgraph.py by replacing hardcoded mock logic
with real LLM calls — showing EXACTLY where and why the LLM is used.

Same food order scenario. Same graph structure. Same state.
Only difference: nodes now use LLM instead of hardcoded if/else.

Run this file:
  python -m langgraph_starter.learn_langgraph_llm

KEY QUESTION ANSWERED:
  "Where does the LLM add intelligence?"

  Answer: Inside nodes — specifically when the task requires:
    1. Understanding free text (parsing)
    2. Making a judgment call (reasoning)
    3. Writing a human-friendly response (generation)

  The LLM does NOT:
    - decide which node runs next  (that is the router's job)
    - update state directly        (that is the node's job)
    - know about the graph         (it just sees a prompt)
"""

import json
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph_starter.connection import invoke_with_system

# =============================================================================
# STATE — same as before, one new field: raw_order (free text from customer)
# =============================================================================

class OrderState(TypedDict):
    raw_order: str             # free text from customer: "I want something cheesy and spicy"
    item_requested: str        # LLM extracts this from raw_order
    is_available: bool         # LLM decides this based on menu context
    unavailability_reason: str # LLM explains WHY it's not available
    alternative: str           # LLM suggests this (not hardcoded)
    final_response: str        # LLM writes this in a friendly tone


# =============================================================================
# WHERE LLM IS USED — 3 places, each for a different reason
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# NODE 1 — parse_order
# LLM USE: UNDERSTANDING FREE TEXT (parsing / intent extraction)
# ─────────────────────────────────────────────────────────────────────────────
#
# WITHOUT LLM: customer must type exact item name "pizza"
# WITH LLM:    customer can type "something cheesy and spicy" → LLM figures out "pizza"
#
# This is the first place LLM adds value — turning messy human input
# into a clean structured value the rest of the graph can work with.

def parse_order(state: OrderState) -> dict:
    print(f"\n[Node: parse_order] Raw input: '{state['raw_order']}'")
    print("[Node: parse_order] Asking LLM to extract the item...")

    # The LLM receives:
    #   - a system prompt telling it what to do
    #   - the raw customer input
    # It returns a clean item name

    system = """You are a food order parser.
Given a customer's free-text order, extract the single food item they want.
Our menu has: pizza, burger, pasta, sushi, tacos, ramen, burrito.
Reply with ONLY a JSON object: {"item": "<item name>"}
If the request is unclear, pick the closest match from the menu."""

    user = f"Customer said: {state['raw_order']}"

    # invoke_with_system sends system + user prompt to LLM, returns cleaned string
    raw = invoke_with_system(system, user)
    parsed = json.loads(raw)
    item = parsed["item"]

    print(f"[Node: parse_order] LLM extracted item: '{item}'")

    # LLM turned "something cheesy and spicy" → "pizza"
    # Now the rest of the graph has a clean value to work with
    return {"item_requested": item}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 2 — check_availability
# LLM USE: REASONING / JUDGMENT (not just a lookup)
# ─────────────────────────────────────────────────────────────────────────────
#
# WITHOUT LLM: hardcoded list check — "pizza" in ["pizza", "burger", "pasta"]
# WITH LLM:    LLM reasons about availability based on context
#              e.g. "sushi is unavailable on Mondays due to fish delivery schedule"
#              e.g. "burger is unavailable because the grill is broken today"
#
# This is the second place LLM adds value — making judgment calls
# that depend on context, not just a fixed lookup table.

def check_availability(state: OrderState) -> dict:
    print(f"\n[Node: check_availability] Checking availability of '{state['item_requested']}'...")
    print("[Node: check_availability] Asking LLM to reason about availability...")

    system = """You are a restaurant inventory manager.
Today's situation:
- Pizza: available
- Burger: available
- Pasta: available
- Sushi: NOT available (fish delivery delayed)
- Tacos: NOT available (chef called sick)
- Ramen: available
- Burrito: available

Given an item, decide if it is available today and explain why if not.
Reply with ONLY a JSON object:
{"is_available": true/false, "reason": "<reason if not available, else empty string>"}"""

    user = f"Is {state['item_requested']} available today?"

    raw = invoke_with_system(system, user)
    parsed = json.loads(raw)

    print(f"[Node: check_availability] LLM decision: available={parsed['is_available']}, reason='{parsed['reason']}'")

    # LLM didn't just check a list — it reasoned about WHY
    # That "why" is stored in state and used later in the response
    return {
        "is_available": parsed["is_available"],
        "unavailability_reason": parsed.get("reason", "")
    }


# ─────────────────────────────────────────────────────────────────────────────
# ROUTER — route_after_availability
# NO LLM HERE — pure Python logic reading state
# ─────────────────────────────────────────────────────────────────────────────
#
# The router does NOT use LLM.
# It just reads a boolean from state and returns a string.
# This is intentional — routing decisions should be deterministic.
# If you let LLM decide routing, you lose control of the graph flow.

def route_after_availability(state: OrderState) -> str:
    print(f"\n[Router] is_available = {state['is_available']}")
    if state["is_available"]:
        print("[Router] → confirm_order")
        return "confirm_order"
    else:
        print("[Router] → suggest_alternative")
        return "suggest_alternative"


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3a — confirm_order
# LLM USE: GENERATION (writing a friendly human response)
# ─────────────────────────────────────────────────────────────────────────────
#
# WITHOUT LLM: f"Your {item} is confirmed. Delivery in 30 mins."
# WITH LLM:    warm, personalized message that matches the customer's original tone
#
# This is the third place LLM adds value — generating natural language
# that feels human, not robotic.

def confirm_order(state: OrderState) -> dict:
    print(f"\n[Node: confirm_order] Generating confirmation for '{state['item_requested']}'...")
    print("[Node: confirm_order] Asking LLM to write a friendly confirmation...")

    system = """You are a friendly restaurant assistant.
Write a warm, enthusiastic order confirmation message.
Keep it under 2 sentences. Be specific about the item."""

    user = f"""Customer originally asked for: "{state['raw_order']}"
We identified they want: {state['item_requested']}
Write a confirmation message."""

    # Notice: LLM receives BOTH the raw order AND the extracted item
    # This lets it write "Your cheesy spicy pizza is on its way!"
    # instead of just "Your pizza is confirmed."
    # The LLM uses context from multiple state fields

    response = invoke_with_system(system, user)

    print(f"[Node: confirm_order] LLM wrote: '{response}'")

    return {"final_response": response}


# ─────────────────────────────────────────────────────────────────────────────
# NODE 3b — suggest_alternative
# LLM USE: REASONING + GENERATION (smart suggestion + friendly message)
# ─────────────────────────────────────────────────────────────────────────────
#
# WITHOUT LLM: hardcoded dict {"sushi": "ramen", "tacos": "burrito"}
# WITH LLM:    suggests based on WHY the item is unavailable + what customer originally wanted
#
# e.g. customer wanted "sushi" (fish-based) → sushi unavailable due to fish delivery
#      LLM reasons: "fish delivery delayed, so suggest something non-fish → ramen"
#      LLM also knows customer wanted something light/Japanese → ramen fits better than burger

def suggest_alternative(state: OrderState) -> dict:
    print(f"\n[Node: suggest_alternative] '{state['item_requested']}' unavailable...")
    print("[Node: suggest_alternative] Asking LLM to suggest a smart alternative...")

    system = """You are a helpful restaurant assistant.
An item is unavailable. Suggest the best alternative from our available menu.
Available today: pizza, burger, pasta, ramen, burrito.
Consider WHY the item is unavailable and what the customer originally wanted.
Reply with ONLY a JSON object: {"alternative": "<item>", "message": "<friendly message to customer>"}"""

    user = f"""Customer originally asked for: "{state['raw_order']}"
They wanted: {state['item_requested']}
Reason unavailable: {state['unavailability_reason']}
Suggest the best alternative and write a friendly message."""

    # LLM receives 3 pieces of context from state:
    #   1. raw_order — what customer actually said
    #   2. item_requested — what we extracted
    #   3. unavailability_reason — WHY it's not available
    # This lets LLM make a smarter suggestion than a hardcoded dict ever could

    raw = invoke_with_system(system, user)
    parsed = json.loads(raw)

    print(f"[Node: suggest_alternative] LLM suggests: '{parsed['alternative']}'")
    print(f"[Node: suggest_alternative] LLM message: '{parsed['message']}'")

    return {
        "alternative": parsed["alternative"],
        "final_response": parsed["message"]
    }


# =============================================================================
# GRAPH — same structure as learn_langgraph.py, nodes now use LLM inside
# =============================================================================

builder = StateGraph(OrderState)

builder.add_node("parse_order", parse_order)
builder.add_node("check_availability", check_availability)
builder.add_node("confirm_order", confirm_order)
builder.add_node("suggest_alternative", suggest_alternative)

builder.set_entry_point("parse_order")

# Fixed edge: parse always goes to check
builder.add_edge("parse_order", "check_availability")

# Conditional edge: check goes to confirm OR suggest based on is_available
builder.add_conditional_edges(
    "check_availability",
    route_after_availability,
    {
        "confirm_order": "confirm_order",
        "suggest_alternative": "suggest_alternative"
    }
)

builder.add_edge("confirm_order", END)
builder.add_edge("suggest_alternative", END)

graph = builder.compile()


# =============================================================================
# SUMMARY — WHERE LLM IS USED AND WHY
# =============================================================================
#
#  Node              | LLM used? | Why
#  ──────────────────┼───────────┼──────────────────────────────────────────
#  parse_order       | YES       | Free text → structured value (parsing)
#  check_availability| YES       | Context-aware judgment (reasoning)
#  route_after_avail | NO        | Pure boolean check — must be deterministic
#  confirm_order     | YES       | Warm personalized message (generation)
#  suggest_alternative| YES      | Smart suggestion + friendly message (reasoning + generation)
#
#  RULE OF THUMB:
#  Use LLM when the task needs: understanding, judgment, or natural language
#  Do NOT use LLM for: routing decisions, math, database lookups, boolean checks
#
#  WHY NOT USE LLM FOR ROUTING?
#  If LLM decides which node runs next, the graph becomes unpredictable.
#  LLM might say "go to confirm" when it should say "go to suggest".
#  Routing must be deterministic — based on hard values in state, not LLM opinion.


def run(raw_order: str):
    print(f"\n{'='*60}")
    print(f"CUSTOMER SAYS: \"{raw_order}\"")
    print('='*60)

    initial_state: OrderState = {
        "raw_order": raw_order,
        "item_requested": None,
        "is_available": None,
        "unavailability_reason": None,
        "alternative": None,
        "final_response": None,
    }

    result = graph.invoke(initial_state)

    print(f"\n--- FINAL STATE ---")
    print(f"raw_order:             {result['raw_order']}")
    print(f"item_requested:        {result['item_requested']}")
    print(f"is_available:          {result['is_available']}")
    print(f"unavailability_reason: {result['unavailability_reason']}")
    print(f"alternative:           {result['alternative']}")
    print(f"\n>>> Customer sees: {result['final_response']}")


if __name__ == "__main__":
    # LLM parses free text, confirms with warm message
    run("I want something cheesy and spicy")

    # LLM parses, finds unavailable, reasons about alternative
    run("I'm in the mood for Japanese food")

    # LLM handles ambiguous input
    run("give me something light and healthy")
