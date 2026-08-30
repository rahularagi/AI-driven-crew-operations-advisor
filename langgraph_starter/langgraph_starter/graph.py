from langgraph.graph import StateGraph, END
from langgraph_starter.state import QAState
from langgraph_starter.nodes.scenario_router import route_scenarios
from langgraph_starter.nodes.crawler import crawl
from langgraph_starter.nodes.intent_generator import generate_intents
from langgraph_starter.nodes.orchestrator import load_next_intent, collect_report, load_next_page, load_next_scenario
from langgraph_starter.nodes.planner import plan_steps
from langgraph_starter.nodes.executor import execute_step
from langgraph_starter.nodes.verifier import verify_step
from langgraph_starter.nodes.healer import heal_locator
from langgraph_starter.nodes.reporter import build_report


def _route_after_executor(state: QAState) -> str:
    result = state.get("_current_result") or {}
    if result.get("status") == "locator_failed":
        if (state.get("heal_attempts") or 0) < 2:
            return "healer"
        return "reporter"
    return "verifier"


def _route_after_verifier(state: QAState) -> str:
    if state["current_step_index"] >= len(state["steps"]):
        return "reporter"
    return "executor"


def _route_after_healer(state: QAState) -> str:
    result = state.get("_current_result") or {}
    if result.get("healed"):
        return "verifier"
    return "reporter"


def _route_after_intent_generator(state: QAState) -> str:
    if state.get("test_intents"):
        return "load_next_intent"
    if state.get("pages_to_visit"):
        return "load_next_page"
    if state.get("scenario_queue"):
        return "load_next_scenario"
    return END


def _route_after_collect(state: QAState) -> str:
    # More intents on this page → keep going
    if state["current_intent_index"] < len(state["test_intents"]):
        return "load_next_intent"
    # More pages for this scenario → crawl next page
    if state.get("pages_to_visit"):
        return "load_next_page"
    # This scenario is done — more scenarios queued → next scenario
    if state.get("scenario_queue"):
        return "load_next_scenario"
    return END


builder = StateGraph(QAState)

# Scenario routing (entry point)
builder.add_node("scenario_router", route_scenarios)

# Discovery
builder.add_node("crawler", crawl)
builder.add_node("intent_generator", generate_intents)

# Orchestrator
builder.add_node("load_next_intent", load_next_intent)
builder.add_node("collect_report", collect_report)
builder.add_node("load_next_page", load_next_page)
builder.add_node("load_next_scenario", load_next_scenario)

# Per-intent execution
builder.add_node("planner", plan_steps)
builder.add_node("executor", execute_step)
builder.add_node("verifier", verify_step)
builder.add_node("healer", heal_locator)
builder.add_node("reporter", build_report)

# Edges
builder.set_entry_point("scenario_router")
builder.add_edge("scenario_router", "crawler")
builder.add_edge("crawler", "intent_generator")
builder.add_conditional_edges("intent_generator", _route_after_intent_generator, {
    "load_next_intent": "load_next_intent",
    "load_next_page": "load_next_page",
    "load_next_scenario": "load_next_scenario",
    END: END,
})
builder.add_edge("load_next_intent", "planner")
builder.add_edge("planner", "executor")
builder.add_conditional_edges("executor", _route_after_executor,
    {"verifier": "verifier", "healer": "healer", "reporter": "reporter"})
builder.add_conditional_edges("verifier", _route_after_verifier,
    {"executor": "executor", "reporter": "reporter"})
builder.add_conditional_edges("healer", _route_after_healer,
    {"verifier": "verifier", "reporter": "reporter"})
builder.add_edge("reporter", "collect_report")
builder.add_conditional_edges("collect_report", _route_after_collect, {
    "load_next_intent": "load_next_intent",
    "load_next_page": "load_next_page",
    "load_next_scenario": "load_next_scenario",
    END: END,
})
builder.add_edge("load_next_page", "crawler")
builder.add_edge("load_next_scenario", "crawler")

graph = builder.compile()
