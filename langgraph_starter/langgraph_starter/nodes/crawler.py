import json
import logging
from langgraph_starter.connection import invoke_with_system
from langgraph_starter.state import QAState
from langgraph_starter.tools.browser_tools import navigate, get_dom, get_page, click, fill

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """
You are analyzing the HTML of a web page to discover its structure.

Current URL: {url}
Page HTML (first 8000 chars):
{dom}

Extract and return a JSON object with:
{{
  "url": "current page URL",
  "description": "what this page does",
  "forms": [
    {{
      "id": "form id or name or description",
      "fields": ["field name or placeholder or label"]
    }}
  ],
  "links": ["full URL or path of internal links found"]
}}

Only return the JSON object, nothing else.
"""

_LOGIN_PROMPT = """
You are given the HTML of a login page and credentials to use.

Page HTML (first 8000 chars):
{dom}

Credentials:
- username/email: {username}
- password: {password}

Return a JSON array of steps to log in. Each step:
{{"action": "fill" | "click", "selector": "CSS selector", "value": "text to type or empty"}}

Only return the JSON array, nothing else.
"""


def _do_login(dom: str, credentials: dict) -> bool:
    raw = invoke_with_system(
        "You are a browser automation assistant.",
        _LOGIN_PROMPT.format(
            dom=dom,
            username=credentials.get("email") or credentials.get("username", ""),
            password=credentials.get("password", ""),
        ),
    )
    logger.debug("[crawler] login steps raw: %s...", raw[:200])
    try:
        steps = json.loads(raw)
    except Exception:
        return False

    for step in steps:
        if step["action"] == "fill":
            r = fill(step["selector"], step["value"])
        elif step["action"] == "click":
            r = click(step["selector"])
        else:
            continue
        if not r.get("success"):
            return False

    try:
        get_page().wait_for_load_state("domcontentloaded", timeout=10000)
    except Exception:
        pass
    return True


def _extract_page_info(url: str) -> dict:
    dom = get_dom()
    raw = invoke_with_system(
        "You are a web page structure analyzer.",
        _EXTRACT_PROMPT.format(url=url, dom=dom),
    )
    logger.debug("[crawler] page_info raw: %s...", raw[:200])
    try:
        return json.loads(raw)
    except Exception:
        return {"url": url, "description": "", "forms": [], "links": []}


def crawl(state: QAState) -> dict:
    base_url = state["base_url"]
    credentials = state.get("credentials") or {}
    visited = list(state.get("visited_pages") or [])

    current_url = state.get("current_page_url") or base_url
    scope = state.get("scope", "full_crawl")
    relevant_pages = state.get("relevant_pages") or []
    existing_queue = list(state.get("pages_to_visit") or [])

    logger.info("[crawler] ▶ Crawling page: %s (scope=%s)", current_url, scope)
    logger.info("[crawler] Already visited %d page(s): %s", len(visited), visited)
    logger.info("[crawler] Pages still in queue: %s", existing_queue)
    if relevant_pages:
        logger.info("[crawler] Feature-scoped — will only follow these pages: %s", relevant_pages)

    navigate(current_url)

    # If credentials provided and on first page, login before crawling
    # Skip login for single_page scope — we want to test the page itself (e.g. login form)
    if credentials and current_url == base_url and scope != "single_page":
        logger.info("[crawler] Logging in as '%s' before crawling...", credentials.get("email") or credentials.get("username"))
        dom_before_login = get_dom()
        _do_login(dom_before_login, credentials)
        current_url = get_page().url
        logger.info("[crawler] Login complete. Redirected to: %s", current_url)

    page_info = _extract_page_info(current_url)
    visited.append(current_url)
    logger.info("[crawler] Page analysed — description: '%s', forms found: %d, links found: %d",
                page_info.get("description", ""), len(page_info.get("forms", [])), len(page_info.get("links", [])))

    if scope == "single_page":
        pages_to_visit = existing_queue  # never follow any links
        logger.info("[crawler] Scope is single_page — not following any links")
    else:
        new_links = [
            l if l.startswith("http") else base_url.rstrip("/") + l
            for l in page_info.get("links", [])
            if l and (l.startswith("/") or l.startswith(base_url))
        ]
        if scope == "feature":
            new_links = [l for l in new_links if l in relevant_pages]
        pages_to_visit = existing_queue + [l for l in new_links if l not in visited and l not in existing_queue]

    logger.info("[crawler] Done. Total visited: %d, Pages remaining in queue: %d — %s",
                len(visited), len(pages_to_visit), pages_to_visit)

    return {
        "current_page_url": current_url,
        "discovered_routes": [page_info],
        "visited_pages": visited,
        "pages_to_visit": pages_to_visit,
    }
