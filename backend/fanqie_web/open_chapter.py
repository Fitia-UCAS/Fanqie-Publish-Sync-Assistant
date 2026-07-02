from __future__ import annotations

from typing import Optional

from playwright.sync_api import Page

from backend.fanqie_web.edit_dialogs import click_continue_edit_if_present
from backend.fanqie_web.pagination import click_next_page, click_page_number, get_visible_page_numbers
from backend.fanqie_web.ui_actions import dismiss_popups, ensure_logged_in, goto_chapter_manage, wait_briefly_for_page_ready


class ChapterEditorNotFound(RuntimeError):
    def __init__(self, chapter_no: int) -> None:
        super().__init__(f"未能在番茄章节管理列表中定位到第 {chapter_no} 章。")
        self.chapter_no = chapter_no


def click_edit_near_chapter_by_js(page: Page, targets: list[str]) -> bool:
    script = r"""
    (targets) => {
        function visible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none';
        }
        function includesTarget(text) {
            if (!text) return false;
            const compact = text.replace(/\s+/g, '');
            return targets.some(t => {
                const tt = String(t || '').replace(/\s+/g, '');
                return tt && compact.includes(tt);
            });
        }
        const rows = Array.from(document.querySelectorAll('tr, .arco-table-tr')).filter(visible);
        for (const row of rows) {
            const text = row.innerText || row.textContent || '';
            if (!includesTarget(text)) continue;
            const link = row.querySelector('a[href*="/publish/"][href*="modifychapter"]')
                      || row.querySelector('a[href*="/publish/"]')
                      || row.querySelector('a.link');
            if (link) {
                link.scrollIntoView({block: 'center', inline: 'center'});
                window.location.href = link.href;
                return {ok: true, href: link.href};
            }
            const icon = row.querySelector('.icon-edit, .tomato-edit, [class*="edit"]');
            if (icon) {
                const a = icon.closest('a');
                if (a && a.href) {
                    a.scrollIntoView({block: 'center', inline: 'center'});
                    window.location.href = a.href;
                    return {ok: true, href: a.href};
                }
                icon.click();
                return {ok: true};
            }
        }
        return {ok: false};
    }
    """
    try:
        result = page.evaluate(script, targets)
        return bool(isinstance(result, dict) and result.get("ok"))
    except Exception:
        return False


def open_chapter_editor(
    page: Page,
    chapter_manage_url: str,
    chapter_no: int,
    local_title: str,
    log=print,
    cached_editor_url: Optional[str] = None,
    manual_fallback: bool = False,
) -> None:
    log(f"正在定位番茄后台第 {chapter_no} 章...")
    if cached_editor_url:
        try:
            log("使用已缓存的章节入口，直接进入编辑页...")
            page.goto(cached_editor_url, wait_until="domcontentloaded", timeout=60000)
            wait_briefly_for_page_ready(page)
            click_continue_edit_if_present(page, log=log, timeout_ms=1500)
            return
        except Exception:
            log("缓存入口打开失败，改用常规定位方式...")
    goto_chapter_manage(page, chapter_manage_url)
    ensure_logged_in(page, chapter_manage_url, log=log)
    dismiss_popups(page)


    targets = [
        f"第{chapter_no}章 {local_title}",
        f"第 {chapter_no} 章 {local_title}",
        f"第{chapter_no}章",
        f"第 {chapter_no} 章",
        local_title,
    ]
    def try_current_page() -> bool:
        for _ in range(2):
            if click_edit_near_chapter_by_js(page, targets):
                page.wait_for_timeout(1500)
                click_continue_edit_if_present(page, log=log, timeout_ms=2000)
                return True
            page.wait_for_timeout(700)
        return False

    if try_current_page():
        return

    visited_pages: set[int] = set()
    for _ in range(40):
        progressed = False
        page_numbers = sorted(get_visible_page_numbers(page))
        for page_no in page_numbers:
            if page_no in visited_pages:
                continue
            visited_pages.add(page_no)
            if click_page_number(page, page_no):
                progressed = True
                dismiss_popups(page)
                if try_current_page():
                    return
        if click_next_page(page):
            progressed = True
            dismiss_popups(page)
            if try_current_page():
                return
        if not progressed:
            break

    goto_chapter_manage(page, chapter_manage_url)
    page.wait_for_timeout(1500)
    visited_pages.clear()
    for _ in range(40):
        progressed = False
        page_numbers = sorted(get_visible_page_numbers(page))
        for page_no in page_numbers:
            if page_no in visited_pages:
                continue
            visited_pages.add(page_no)
            if click_page_number(page, page_no):
                progressed = True
                if try_current_page():
                    return
        if click_next_page(page):
            progressed = True
            if try_current_page():
                return
        if not progressed:
            break
    if manual_fallback:
        log("自动定位章节失败，请手动点进目标章节编辑页。")
        input("看到标题框、正文编辑器、保存按钮后按 Enter：")
        page.wait_for_timeout(1000)
        click_continue_edit_if_present(page, log=log, timeout_ms=1500)
        return
    raise ChapterEditorNotFound(chapter_no)
