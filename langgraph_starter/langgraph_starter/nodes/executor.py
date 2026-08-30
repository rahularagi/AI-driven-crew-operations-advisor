import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState
from langgraph_starter.tools.browser_tools import navigate, click, fill, take_screenshot, get_dom

logger = logging.getLogger(__name__)

_RESOLVE_LOCATOR_PROMPT = """
I need to find an element on this page described as: "{description}"

Here is the current page DOM (first 8000 chars):
{dom}

Return a single CSS selector that best matches this element.
Only return the CSS selector string, nothing else.
"""


def _resolve_locator(description: str, dom: str, agent_prompt: str) -> str:
    return invoke_with_system(
        agent_prompt,
        _RESOLVE_LOCATOR_PROMPT.format(description=description, dom=dom),
    ).strip('"').strip("'")


def execute_step(state: QAState) -> dict:
    idx = state["current_step_index"]
    step = state["steps"][idx]
    action = step["action"]
    description = step.get("target_description", "")
    value = step.get("value", "")

    logger.info("[executor] ▶ Step %d: action='%s' target='%s' value='%s'", idx, action, description, value)

    dom = get_dom()
    result = {
        "step_index": idx, "status": "pass", "error": "",
        "healed": False, "old_locator": "", "new_locator": "",
        "design_issues": [], "screenshot_path": "",
    }

    if action == "navigate":
        r = navigate(value or description)
        if not r["success"]:
            result["status"] = "error"
            result["error"] = r.get("error", "")
            logger.warning("[executor] Navigate failed: %s", result["error"])
        else:
            logger.info("[executor] Navigated to: %s", value or description)
    elif action in ("click", "fill", "assert"):
        selector = _resolve_locator(description, dom, state.get("agent_prompt", ""))
        result["old_locator"] = selector
        logger.info("[executor] Resolved selector for '%s': %s", description, selector)

        if action == "click":
            r = click(selector)
        elif action == "fill":
            r = fill(selector, value)
        else:
            r = {"success": True}

        if not r.get("success"):
            result["status"] = "locator_failed"
            result["error"] = r.get("error", "")
            logger.warning("[executor] Step %d FAILED — action='%s' selector='%s' error='%s'", idx, action, selector, result["error"])
        else:
            logger.info("[executor] Step %d PASSED — action='%s' on '%s'", idx, action, selector)

    screenshot_path = ""
    if result["status"] != "error":
        try:
            screenshot_path = take_screenshot(idx)
            logger.info("[executor] Screenshot saved: %s", screenshot_path)
        except Exception as e:
            logger.warning("[executor] Screenshot failed: %s", e)
    else:
        logger.info("[executor] Skipping screenshot — step errored")
    result["screenshot_path"] = screenshot_path

    screenshots = list(state.get("screenshots") or [])
    screenshots.append(screenshot_path)
    dom_snapshots = list(state.get("dom_snapshots") or [])
    dom_snapshots.append(dom)

    return {
        "screenshots": screenshots,
        "dom_snapshots": dom_snapshots,
        "_current_result": result,
    }
