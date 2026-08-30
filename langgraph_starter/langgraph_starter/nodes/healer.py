import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState
from langgraph_starter.tools.browser_tools import click, fill

logger = logging.getLogger(__name__)

_HEAL_PROMPT = """
A browser automation step failed because the element could not be found.

Element description: "{description}"
Failed selector: "{old_selector}"

Current page DOM (first 8000 chars):
{dom}

The element may have been renamed or restructured. Find the new CSS selector.
Return only the CSS selector string, nothing else.
"""


def heal_locator(state: QAState) -> dict:
    idx = state["current_step_index"]
    step = state["steps"][idx]
    result = dict(state.get("_current_result") or {})
    dom = (state.get("dom_snapshots") or [""])[-1]
    old_selector = result.get("old_locator", "unknown")
    description = step.get("target_description", "")

    logger.info("[healer] ▶ Attempting to heal step %d | element: '%s' | failed selector: '%s'", idx, description, old_selector)

    new_selector = invoke_with_system(
        state.get("agent_prompt", ""),
        _HEAL_PROMPT.format(
            description=description,
            old_selector=old_selector,
            dom=dom,
        ),
    ).strip('"').strip("'")

    logger.info("[healer] New selector candidate: '%s'", new_selector)

    action = step["action"]
    if action == "click":
        r = click(new_selector)
    elif action == "fill":
        r = fill(new_selector, step.get("value", ""))
    else:
        r = {"success": True}

    healed = r.get("success", False)
    result["healed"] = healed
    result["new_locator"] = new_selector if healed else ""
    result["status"] = "healed" if healed else "error"

    if healed:
        logger.info("[healer] ✅ Healed successfully: '%s' → '%s'", old_selector, new_selector)
    else:
        logger.warning("[healer] ❌ Healing failed for '%s' — new selector '%s' also did not work", description, new_selector)

    return {
        "_current_result": result,
        "heal_attempts": (state.get("heal_attempts") or 0) + 1,
    }
