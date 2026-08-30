import json
import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState

logger = logging.getLogger(__name__)

_PLANNER_PROMPT = """
Break the following test intent into a sequence of browser steps.

Test intent: {intent}

Return a JSON array of steps. Each step must have:
- "action": one of "navigate" | "click" | "fill" | "assert"
- "target_description": plain English description of the element or URL
- "value": for fill/navigate actions, the text to type or URL; empty string otherwise
- "expected_outcome": what should be visible/true after this step succeeds

Only return the JSON array, nothing else.
"""


def plan_steps(state: QAState) -> dict:
    agent_prompt = state.get("agent_prompt", "You are a QA test planner.")
    intent = state["test_intent"]
    logger.info("[planner] ▶ Planning steps for intent: '%s'", intent)

    raw = invoke_with_system(agent_prompt, _PLANNER_PROMPT.format(intent=intent))

    try:
        steps = json.loads(raw)
    except Exception as e:
        logger.warning("[planner] JSON parse failed: %s | raw: %s", e, raw[:200])
        steps = []

    logger.info("[planner] Generated %d step(s): %s", len(steps), [{s['action'], s['target_description']} for s in steps])

    return {
        "steps": steps,
        "current_step_index": 0,
        "step_results": [],
        "screenshots": [],
        "dom_snapshots": [],
        "heal_attempts": 0,
        "_current_result": {},
    }
