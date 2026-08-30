import logging
from langgraph_starter.state import QAState

logger = logging.getLogger(__name__)


def load_next_intent(state: QAState) -> dict:
    idx = state["current_intent_index"]
    intent = state["test_intents"][idx]
    logger.info("[orchestrator] ▶ Loading intent %d/%d: '%s'", idx + 1, len(state["test_intents"]), intent)
    return {
        "test_intent": intent,
        "steps": [],
        "current_step_index": 0,
        "step_results": [],
        "screenshots": [],
        "dom_snapshots": [],
        "heal_attempts": 0,
        "_current_result": {},
        "report": {},
    }


def collect_report(state: QAState) -> dict:
    all_reports = list(state.get("all_reports") or [])
    all_reports.append({
        **state["report"],
        "page": state.get("current_page_url", ""),
        "scenario": (state.get("active_scenario") or {}).get("description", ""),
        "scope": state.get("scope", ""),
    })
    next_idx = state["current_intent_index"] + 1
    remaining = len(state["test_intents"]) - next_idx
    logger.info("[orchestrator] Report collected. Total reports so far: %d. Intents remaining on this page: %d", len(all_reports), remaining)
    return {
        "all_reports": all_reports,
        "current_intent_index": next_idx,
    }


def load_next_page(state: QAState) -> dict:
    pages_to_visit = list(state.get("pages_to_visit") or [])
    next_page = pages_to_visit.pop(0)
    logger.info("[orchestrator] ▶ Moving to next page: %s (%d page(s) still queued)", next_page, len(pages_to_visit))
    return {
        "current_page_url": next_page,
        "pages_to_visit": pages_to_visit,
        "test_intents": [],
        "current_intent_index": 0,
        "discovered_routes": [],
    }


def load_next_scenario(state: QAState) -> dict:
    scenario_queue = list(state.get("scenario_queue") or [])
    next_scenario = scenario_queue.pop(0)
    logger.info("[orchestrator] ▶ Moving to next scenario: '%s' (scope=%s, %d scenario(s) remaining)",
                next_scenario.get("description", ""), next_scenario.get("scope", ""), len(scenario_queue))
    return {
        "scenario_queue": scenario_queue,
        "active_scenario": next_scenario,
        "scope": next_scenario["scope"],
        "relevant_pages": next_scenario.get("relevant_pages", []),
        "current_page_url": "",
        "visited_pages": [],
        "pages_to_visit": [],
        "test_intents": [],
        "current_intent_index": 0,
        "discovered_routes": [],
    }
