import logging
from langgraph_starter.connection import ask_with_image
from langgraph_starter.state import QAState
from langgraph_starter.tools.visual_tools import check_visual_design

logger = logging.getLogger(__name__)

_VERIFY_PROMPT = """
I just executed a browser step. Expected outcome: "{expected}"

Here is a screenshot of the current page state.

Judge flexibly — if the expected outcome says "expect an error message indicating X",
check if ANY error message related to X is visible, not an exact string match.
If the expected outcome says "expect redirect" or "expect success", check if the page
looks like a success state or a different page.

Did the step succeed? Answer with exactly one word: PASS or FAIL.
"""


def verify_step(state: QAState) -> dict:
    idx = state["current_step_index"]
    step = state["steps"][idx]
    result = dict(state.get("_current_result") or {})
    expected = step["expected_outcome"]

    logger.info("[verifier] ▶ Verifying step %d | expected: '%s'", idx, expected)

    screenshot_path = result.get("screenshot_path", "")

    if screenshot_path:
        verdict = ask_with_image(
            _VERIFY_PROMPT.format(expected=expected),
            screenshot_path,
        ).strip().upper()
        logger.info("[verifier] Step %d verdict: %s", idx, verdict)

        if "FAIL" in verdict:
            result["status"] = "fail"
            logger.warning("[verifier] Step %d FAILED — expected: '%s'", idx, expected)

        design_issues = check_visual_design(screenshot_path)
        result["design_issues"] = design_issues
        if design_issues:
            logger.info("[verifier] %d design issue(s) found on step %d", len(design_issues), idx)
    else:
        logger.warning("[verifier] No screenshot available for step %d — skipping visual check", idx)

    step_results = list(state.get("step_results") or [])
    step_results.append(result)

    return {
        "step_results": step_results,
        "current_step_index": idx + 1,
        "heal_attempts": 0,
        "_current_result": {},
    }
