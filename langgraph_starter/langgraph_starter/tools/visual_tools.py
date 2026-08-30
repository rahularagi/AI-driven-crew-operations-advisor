import json
from langgraph_starter.connection import ask_with_image

_DESIGN_PROMPT = """
You are a UI quality reviewer. Look at this screenshot and identify any of these issues:
- Overlapping or clipped elements
- Text cut off or overflowing its container
- Buttons or links that appear unclickable (covered, off-screen, zero-size)
- Low contrast text (hard to read)
- Broken layout (columns misaligned, elements stacked incorrectly)
- Missing images (broken image icons)

Reply with a JSON array of issues found.
Each issue: {"type": "...", "description": "...", "severity": "low|medium|high"}
If no issues, reply with: []
Only reply with the JSON array, nothing else.
"""


def check_visual_design(screenshot_path: str) -> list:
    try:
        raw = ask_with_image(_DESIGN_PROMPT, screenshot_path)
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean)
    except Exception:
        return []
