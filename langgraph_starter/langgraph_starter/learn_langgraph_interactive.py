"""
Interactive Food Ordering — Human-in-the-Loop

New concepts covered (beyond learn_langgraph.py):
  1. list fields in State (order_history)
  2. interrupt_before  — graph pauses and waits for user input
  3. MemorySaver       — checkpointer that persists state between pauses
  4. thread_id         — ties multiple invoke() calls into one conversation
  5. graph.update_state() — inject user input into paused graph
  6. Querying order history — first item, nth item, total count

Run:
  python -m langgraph_starter.learn_langgraph_interactive
"""

from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver


# =============================================================================
# STATE
# =============================================================================
#
# New fields vs learn_langgraph.py:
#   current_item   — the single item being processed right now
#   order_history  — list of every order attempt with its outcome
#   final_response — what the customer sees after each node

class OrderState(TypedDict):
    current_item: str                  # item being checked right now
    is_available: Optional[bool]       # set by check_availability
    order_history: list[dict]          # accumulated across the whole conversation
    final_response: str                # shown to user after each step


# =============================================================================
# NODES
# =============================================================================

AVAILABLE_ITEMS = ["pizza", "burger", "pasta"]
ALTERNATIVES    = {"sushi": "ramen", "tacos": "burrito", "steak": "chicken"}


def check_availability(state: OrderState) -> dict:
    item = state["current_item"].strip().lower()
    is_available = item in AVAILABLE_ITEMS
    print(f"\n[check_availability] '{item}' → {'AVAILABLE' if is_available else 'NOT AVAILABLE'}")
    return {"is_available": is_available, "current_item": item}


def confirm_order(state: OrderState) -> dict:
    item = state["current_item"]
    entry = {"item": item, "status": "confirmed", "alternative": None}
    history = state.get("order_history", []) + [entry]
    message = f"✅ '{item}' confirmed! Anything else? (type item name or 'done')"
    print(f"[confirm_order] {message}")
    return {"order_history": history, "final_response": message}


def suggest_alternative(state: OrderState) -> dict:
    item = state["current_item"]
    alt = ALTERNATIVES.get(item, "a house special")
    entry = {"item": item, "status": "unavailable", "alternative": alt}
    history = state.get("order_history", []) + [entry]
    message = f"❌ '{item}' unavailable. How about '{alt}'? Or type another item / 'done'."
    print(f"[suggest_alternative] {message}")
    return {"order_history": history, "final_response": message}


# This node exists ONLY to be interrupted before it runs.
# When the graph resumes, update_state() injects current_item,
# then this node is skipped and execution continues from check_availability.
def wait_for_next_item(state: OrderState) -> dict:
    # Never actually executes — graph is interrupted before this node
    return {}


# =============================================================================
# ROUTERS
# =============================================================================

def route_after_availability(state: OrderState) -> str:
    return "confirm_order" if state["is_available"] else "suggest_alternative"


def route_next_or_end(state: OrderState) -> str:
    # After confirm or suggest, always pause and ask for next item
    return "wait_for_next_item"


# =============================================================================
# GRAPH
# =============================================================================

builder = StateGraph(OrderState)

builder.add_node("check_availability", check_availability)
builder.add_node("confirm_order", confirm_order)
builder.add_node("suggest_alternative", suggest_alternative)
builder.add_node("wait_for_next_item", wait_for_next_item)

builder.set_entry_point("check_availability")

builder.add_conditional_edges(
    "check_availability",
    route_after_availability,
    {"confirm_order": "confirm_order", "suggest_alternative": "suggest_alternative"}
)

# After confirm or suggest → go to wait node (which will be interrupted)
builder.add_edge("confirm_order", "wait_for_next_item")
builder.add_edge("suggest_alternative", "wait_for_next_item")
builder.add_edge("wait_for_next_item", "check_availability")  # resumes here after interrupt

# MemorySaver persists state between pauses so conversation history is preserved
memory = MemorySaver()

graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["wait_for_next_item"]  # pause BEFORE wait node every time
)


# =============================================================================
# QUERY HELPERS
# =============================================================================

def show_order_summary(history: list[dict]):
    print(f"\n{'─'*45}")
    print(f"  Total items ordered: {len(history)}")
    for i, entry in enumerate(history, 1):
        status = "✅" if entry["status"] == "confirmed" else "❌"
        alt = f" → suggested '{entry['alternative']}'" if entry["alternative"] else ""
        print(f"  {i}. {status} {entry['item']}{alt}")
    print(f"{'─'*45}\n")


def answer_query(query: str, history: list[dict]):
    query = query.lower()
    if not history:
        print("No orders yet.")
        return

    if "total" in query or "how many" in query:
        print(f"Total items: {len(history)}")

    elif "first" in query:
        print(f"First item: {history[0]['item']} ({history[0]['status']})")

    elif "last" in query:
        print(f"Last item: {history[-1]['item']} ({history[-1]['status']})")

    elif any(word.isdigit() for word in query.split()):
        n = int(next(w for w in query.split() if w.isdigit()))
        if 1 <= n <= len(history):
            e = history[n - 1]
            print(f"Item {n}: {e['item']} ({e['status']})")
        else:
            print(f"No item at position {n}. You have {len(history)} items.")

    else:
        show_order_summary(history)


# =============================================================================
# MAIN LOOP
# =============================================================================

if __name__ == "__main__":
    # thread_id ties all invoke() calls into one conversation
    config = {"configurable": {"thread_id": "order-session-1"}}

    print("=== Interactive Food Ordering ===")
    print(f"Available: {AVAILABLE_ITEMS}")
    print(f"Alternatives known: {list(ALTERNATIVES.keys())}")
    print("Commands: type item name | 'done' | 'summary' | 'query: <question>'\n")

    first_item = input("What would you like to order? ").strip()

    # First invoke — starts the graph with the initial item
    result = graph.invoke(
        {"current_item": first_item, "order_history": [], "final_response": ""},
        config=config
    )
    print(f"\n→ {result['final_response']}")

    # Conversation loop — graph is paused at wait_for_next_item each iteration
    while True:
        user_input = input("\nYou: ").strip()

        if not user_input:
            continue

        if user_input.lower() == "done":
            # Get final state from checkpointer
            snapshot = graph.get_state(config)
            show_order_summary(snapshot.values.get("order_history", []))
            break

        if user_input.lower() == "summary":
            snapshot = graph.get_state(config)
            show_order_summary(snapshot.values.get("order_history", []))
            continue

        if user_input.lower().startswith("query:"):
            query = user_input[6:].strip()
            snapshot = graph.get_state(config)
            answer_query(query, snapshot.values.get("order_history", []))
            continue

        # Inject the new item into the paused graph state, then resume
        # update_state() writes current_item into state at the interrupted node
        graph.update_state(config, {"current_item": user_input}, as_node="wait_for_next_item")

        # Resume — graph continues from wait_for_next_item → check_availability
        result = graph.invoke(None, config=config)
        print(f"\n→ {result['final_response']}")
