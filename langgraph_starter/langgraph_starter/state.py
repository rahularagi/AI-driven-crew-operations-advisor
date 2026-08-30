from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages


class Step(TypedDict):
    action: str               # "navigate" | "click" | "fill" | "assert"
    target_description: str   # plain English: "the Login button"
    value: str                # for fill/navigate: what to type or URL
    expected_outcome: str     # "page shows dashboard"


class StepResult(TypedDict):
    step_index: int
    status: str               # "pass" | "fail" | "healed" | "error"
    error: str
    healed: bool
    old_locator: str
    new_locator: str
    design_issues: list
    screenshot_path: str


class QAState(TypedDict):
    # --- Input (from API request + agents.yaml) ---
    agent: str
    agent_prompt: str
    base_url: str
    credentials: dict           # {"email": "...", "password": "..."}
    scenarios: list[str]        # list of plain English test descriptions

    # --- Scenario routing (set by scenario_router) ---
    scenario_queue: list[dict]  # [{description, scope, target}] remaining scenarios
    active_scenario: dict       # current scenario being executed
    scope: str                  # "single_page" | "feature" | "full_crawl"
    relevant_pages: list[str]   # for feature scope: LLM-decided pages to visit

    # --- Page queue (drives page-by-page crawl loop) ---
    pages_to_visit: list[str]       # queue of URLs to crawl next
    current_page_url: str           # page currently being tested
    visited_pages: list[str]        # already tested, avoid revisit

    # --- Crawler output (per page) ---
    discovered_routes: list[dict]   # [{url, description, forms: [{id, fields}], links: [str]}]

    # --- Intent generator output (per page) ---
    test_intents: list[str]         # all test cases for current page
    current_intent_index: int

    # --- Per-scenario execution (reset each intent) ---
    test_intent: str
    steps: list
    current_step_index: int
    screenshots: list[str]
    dom_snapshots: list[str]
    step_results: list
    heal_attempts: int
    _current_result: dict

    # --- Aggregated output ---
    all_reports: list[dict]         # one report per test case across all pages
    report: dict

    messages: Annotated[list, add_messages]


def initial_state(agent: str, agent_prompt: str, base_url: str, credentials: dict, scenarios: list[str]) -> QAState:
    return QAState(
        agent=agent,
        agent_prompt=agent_prompt,
        base_url=base_url,
        credentials=credentials,
        scenarios=scenarios,
        scenario_queue=[],
        active_scenario={},
        scope="full_crawl",
        relevant_pages=[],
        pages_to_visit=[],
        current_page_url="",
        visited_pages=[],
        discovered_routes=[],
        test_intents=[],
        current_intent_index=0,
        test_intent="",
        steps=[],
        current_step_index=0,
        step_results=[],
        screenshots=[],
        dom_snapshots=[],
        heal_attempts=0,
        _current_result={},
        all_reports=[],
        report={},
        messages=[],
    )
