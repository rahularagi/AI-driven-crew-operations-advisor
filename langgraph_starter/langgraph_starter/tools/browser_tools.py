import os
from playwright.sync_api import sync_playwright, Page

_pw = None
_browser = None
_page: Page = None


def get_page() -> Page:
    global _pw, _browser, _page
    if _page is None:
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        _page = _browser.new_page()
    return _page


def navigate(url: str) -> dict:
    try:
        get_page().goto(url, wait_until="domcontentloaded", timeout=15000)
        return {"success": True, "url": url}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click(selector: str) -> dict:
    try:
        get_page().click(selector, timeout=5000)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e), "locator_failed": True}


def fill(selector: str, value: str) -> dict:
    try:
        get_page().fill(selector, value, timeout=5000)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e), "locator_failed": True}


def take_screenshot(step_index: int) -> str:
    os.makedirs("screenshots", exist_ok=True)
    path = f"screenshots/step_{step_index:02d}.png"
    get_page().screenshot(path=path, full_page=True)
    return path


def get_dom() -> str:
    html = get_page().content()
    return html[:8000]


def close_browser():
    global _pw, _browser, _page
    if _browser:
        _browser.close()
    if _pw:
        _pw.stop()
    _browser = None
    _page = None
    _pw = None
