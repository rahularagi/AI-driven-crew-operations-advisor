import json
import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState

logger = logging.getLogger(__name__)

_EXPAND_PROMPT = """
Current page: {url}
Page structure:
{page_info}

Credentials available: {credentials}

User's test scenario: {scenario_description}

Based on your role, generate the appropriate test cases for this page.
Rules:
- Each test case must be a single self-contained intent string
- Each intent must include: exact URL, exact field names from the page structure, test data, and the ACCURATE expected outcome for that specific input combination
- For expected outcomes on login forms use these rules:
  * empty username → expect any error message containing "username" or "invalid"
  * valid username + wrong/empty password → expect any error message containing "password" or "invalid"
  * both wrong → expect any error message (username or password invalid)
  * valid credentials → expect successful redirect or success message
  * Do NOT hardcode the exact error string — use "expect an error message indicating X" instead
- Use the real credentials provided for any positive/login cases
- If your role includes a positive/success case, it must come LAST (it navigates to the next page)
{strict_rule}

Return a JSON array of intent strings.
Only return the JSON array, nothing else.
"""


def generate_intents(state: QAState) -> dict:
    page_info = state["discovered_routes"][0] if state["discovered_routes"] else {}
    current_url = state.get("current_page_url", state["base_url"])
    credentials = state.get("credentials") or {}
    active_scenario = state.get("active_scenario") or {}
    scope = state.get("scope", "full_crawl")

    scenario_description = active_scenario.get("description", "test this page thoroughly")

    strict_rule = (
        f"- IMPORTANT: Generate test cases ONLY for this specific scenario: '{scenario_description}'. Do not test anything outside this scope."
        if scope in ("single_page", "feature")
        else "- Cover all meaningful test cases for this page based on your role."
    )

    user_prompt = _EXPAND_PROMPT.format(
        url=current_url,
        page_info=json.dumps(page_info, indent=2),
        credentials=json.dumps(credentials),
        scenario_description=scenario_description,
        strict_rule=strict_rule,
    )

    logger.info("[intent_generator] ▶ Generating intents for: %s (scope=%s, scenario='%s')", current_url, scope, scenario_description)
    logger.info("[intent_generator] Page has %d form(s) and %d link(s)", len(page_info.get("forms", [])), len(page_info.get("links", [])))

    if not page_info:
        logger.warning("[intent_generator] discovered_routes is empty — no page info available, falling back to scenario text")

    raw = invoke_with_system(
        state.get("agent_prompt", "You are a QA engineer. Generate all meaningful test cases."),
        user_prompt,
    )

    logger.info("[intent_generator] LLM raw response: %s...", raw[:300])

    try:
        test_intents = json.loads(raw)
    except Exception as e:
        logger.warning("[intent_generator] JSON parse failed: %s, falling back to scenario", e)
        test_intents = [scenario_description]

    logger.info("[intent_generator] Generated %d intent(s): %s", len(test_intents), test_intents)

    return {
        "test_intents": test_intents,
        "current_intent_index": 0,
        "all_reports": list(state.get("all_reports") or []),
    }
