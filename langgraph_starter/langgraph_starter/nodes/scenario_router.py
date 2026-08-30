import json
import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = """
You are a QA planning assistant. A user has provided a list of plain English test scenarios.

Base URL: {base_url}

Scenarios:
{scenarios}

For each scenario, classify it and return a JSON array. Each item:
{{
  "description": "original scenario text",
  "scope": "single_page" | "feature" | "full_crawl",
  "target": "short name of the feature or page, or null for full_crawl"
}}

Scope rules:
- "single_page": user wants to test ONE specific page only (e.g. "test login", "test signup form")
- "feature": user wants to test a specific feature that may span a few pages (e.g. "send and read email", "checkout flow", "user profile settings")
- "full_crawl": user wants to test the entire app or all pages (e.g. "test everything", "test the complete app", "test all pages")

Only return the JSON array, nothing else.
"""

_RELEVANT_PAGES_PROMPT = """
You are a QA planning assistant.

Base URL: {base_url}
Feature to test: {target}
Scenario: {description}

List the URL paths that are likely needed to test this feature.
Return a JSON array of URL paths (e.g. ["/email", "/email/compose", "/inbox"]).
Only return the JSON array, nothing else.
"""


def route_scenarios(state: QAState) -> dict:
    scenarios = state.get("scenarios") or []
    base_url = state["base_url"]

    # Classify all scenarios at once
    raw = invoke_with_system(
        "You are a QA planning assistant.",
        _CLASSIFY_PROMPT.format(
            base_url=base_url,
            scenarios="\n".join(f"- {s}" for s in scenarios),
        ),
    )
    logger.info("[scenario_router] classification raw: %s...", raw[:800])
    raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        classified = json.loads(raw)
    except Exception:
        classified = [{"description": s, "scope": "full_crawl", "target": None} for s in scenarios]
        logger.warning("[scenario_router] JSON parse failed, defaulted all scenarios to full_crawl")

    logger.info("[scenario_router] classified: %s", json.dumps(classified, indent=2))

    # For feature-scoped scenarios, ask LLM which pages to visit
    for item in classified:
        if item["scope"] == "feature" and item.get("target"):
            pages_raw = invoke_with_system(
                "You are a QA planning assistant.",
                _RELEVANT_PAGES_PROMPT.format(
                    base_url=base_url,
                    target=item["target"],
                    description=item["description"],
                ),
            )
            pages_raw = pages_raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            logger.info("[scenario_router] feature-scoped scenarios item : %s response: %s",item,pages_raw)
            try:
                paths = json.loads(pages_raw)
                item["relevant_pages"] = [
                    base_url.rstrip("/") + p if p.startswith("/") else p
                    for p in paths
                ]
            except Exception:
                item["relevant_pages"] = []
        else:
            item["relevant_pages"] = []


    # Pop first scenario and set it as active
    first = classified[0]
    remaining = classified[1:]
    logger.info("[scenario_router] routing to first scenario: %s, remaining: %s", first, remaining)
    return {
        "scenario_queue": remaining,
        "active_scenario": first,
        "scope": first["scope"],
        "relevant_pages": first.get("relevant_pages", []),
        "current_page_url": "",
        "visited_pages": [],
        "pages_to_visit": [],
        "test_intents": [],
        "current_intent_index": 0,
        "discovered_routes": [],
    }
