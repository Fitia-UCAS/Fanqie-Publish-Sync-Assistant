from __future__ import annotations

import re

from playwright.sync_api import Page

from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.ui_actions import locator_count_safe


def wait_for_editor_saved(page: Page, *, timeout_ms: int = 15000) -> bool:
    end_rounds = max(1, timeout_ms // 500)
    saw_saving = False
    saw_any_state = False
    for _ in range(end_rounds):
        try:
            body = page.locator("body").inner_text(timeout=800)
        except Exception:
            body = ""
        compact = re.sub(r"\s+", "", body or "")
        if "保存中" in compact:
            saw_saving = True
            saw_any_state = True
            page.wait_for_timeout(500)
            continue
        if "已保存" in compact or "保存成功" in compact:
            return True
        if "保存失败" in compact:
            return False
        page.wait_for_timeout(500)

    return not saw_any_state or not saw_saving


def click_save_draft(page: Page, log=print) -> None:
    save_debug(page, "save_draft_before")
    save_words = ["保存草稿", "保存", "存草稿", "确认保存"]
    for word in save_words:
        loc = page.get_by_text(word, exact=False)
        count = locator_count_safe(loc)
        for i in range(count):
            item = loc.nth(i)
            try:
                if item.is_visible() and item.is_enabled():
                    item.scroll_into_view_if_needed()
                    text = (item.inner_text(timeout=1000) or "").strip()
                    if "发布" in text:
                        continue
                    item.click(timeout=10000)
                    save_debug(page, "save_draft_clicked")
                    page.wait_for_timeout(800)
                    if not wait_for_editor_saved(page, timeout_ms=15000):
                        save_debug(page, "save_draft_state_failed", force=True)
                        raise RuntimeError("保存草稿后未等到“已保存”状态。")
                    save_debug(page, "save_draft_after")
                    return
            except Exception:
                continue
    save_debug(page, "save_draft_button_not_found", force=True)
    raise RuntimeError("未找到保存草稿/保存按钮。")
