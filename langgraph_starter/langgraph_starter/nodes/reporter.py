import logging
from langgraph_starter.state import QAState

logger = logging.getLogger(__name__)


def build_report(state: QAState) -> dict:
    results = state.get("step_results") or []

    passed = [r for r in results if r.get("status") in ("pass", "healed")]
    failed = [r for r in results if r.get("status") in ("fail", "error")]
    healed = [r for r in results if r.get("healed")]
    design_issues = [issue for r in results for issue in (r.get("design_issues") or [])]

    report = {
        "test_intent": state.get("test_intent", ""),
        "total_steps": len(results),
        "passed": len(passed),
        "failed": len(failed),
        "healed": len(healed),
        "overall": "PASS" if not failed else "FAIL",
        "healing_events": [
            {"step": r["step_index"], "old": r.get("old_locator", ""), "new": r.get("new_locator", "")}
            for r in healed
        ],
        "design_issues": design_issues,
        "step_details": results,
    }

    logger.info("[reporter] " + "=" * 50)
    logger.info("[reporter] RESULT: %s | intent: '%s'", report["overall"], report["test_intent"])
    logger.info("[reporter] Steps: %d  Passed: %d  Failed: %d  Healed: %d",
                report["total_steps"], report["passed"], report["failed"], report["healed"])
    if healed:
        for h in report["healing_events"]:
            logger.info("[reporter] Healed step %d: '%s' → '%s'", h["step"], h["old"], h["new"])
    if design_issues:
        logger.info("[reporter] %d design issue(s) found", len(design_issues))
        for issue in design_issues:
            logger.info("[reporter]   [%s] %s: %s", issue.get("severity", "?").upper(), issue.get("type", ""), issue.get("description", ""))
    logger.info("[reporter] " + "=" * 50)

    return {"report": report}
