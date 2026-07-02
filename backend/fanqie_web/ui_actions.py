from __future__ import annotations

from typing import Optional

from playwright.sync_api import Locator, Page

from backend.novel.text_cleaning import chinese_to_int
from backend.fanqie_web.browser_session import save_debug

def locator_count_safe(locator: Locator) -> int:
    try:
        return locator.count()
    except Exception:
        return 0

def first_visible(locator: Locator) -> Optional[Locator]:
    count = locator_count_safe(locator)
    for i in range(count):
        item = locator.nth(i)
        try:
            if item.is_visible():
                return item
        except Exception:
            continue
    return None

def wait_briefly_for_page_ready(page: Page, timeout_ms: int = 4000) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 2500))
    except Exception:

        pass

def goto_chapter_manage(page: Page, chapter_manage_url: str) -> None:
    page.goto(chapter_manage_url, wait_until="domcontentloaded", timeout=60000)
    wait_briefly_for_page_ready(page)

def page_text(page: Page, limit: int = 4000) -> str:
    try:
        text = page.locator("body").inner_text(timeout=5000)
        return text[:limit]
    except Exception:
        return ""

def ensure_logged_in(page: Page, chapter_manage_url: str, log: Callable[[str], None] = print) -> None:
    text = page_text(page)
    url = page.url.lower()
    maybe_login = (
        "passport" in url
        or "login" in url
        or ("登录" in text and "章节" not in text and "作品" not in text)
    )
    if maybe_login:
        log("检测到未登录，请在浏览器里登录番茄后台。")
        input("登录完成后按 Enter：")
        page.wait_for_timeout(1500)
        goto_chapter_manage(page, chapter_manage_url)

def dismiss_popups(page: Page) -> None:
    for word in ["我知道了", "知道了", "取消"]:
        try:
            loc = page.get_by_text(word, exact=True)
            count = locator_count_safe(loc)
            for i in range(count):
                item = loc.nth(i)
                if item.is_visible():
                    save_debug(page, f"popup_before_click_{word}")
                    item.click(timeout=1500)
                    save_debug(page, f"popup_after_click_{word}")
                    page.wait_for_timeout(500)
                    return
        except Exception:
            pass

def normalize_chapter_no(raw: str) -> Optional[int]:
    from backend.novel.text_cleaning import chinese_to_int

    value = chinese_to_int(str(raw or "").strip())
    return value if value and value > 0 else None
