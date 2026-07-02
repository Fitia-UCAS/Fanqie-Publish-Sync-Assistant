from __future__ import annotations

from typing import Callable

from playwright.sync_api import Page

from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.chapter_list import (
    collect_chapter_rows_on_current_page_deep,
    collect_editor_links_on_current_page_deep,
)
from backend.fanqie_web.pagination import click_next_page, click_page_number, get_visible_page_numbers
from backend.fanqie_web.ui_actions import dismiss_popups, ensure_logged_in, goto_chapter_manage, locator_count_safe


def collect_all_remote_chapter_numbers(
    page: Page,
    *,
    chapter_manage_url: str,
    log: Callable[[str], None] = print,
) -> list[int]:
    goto_chapter_manage(page, chapter_manage_url)
    ensure_logged_in(page, chapter_manage_url, log=log)
    dismiss_popups(page)

    found: set[int] = set()
    visited_pages: set[int] = set()
    stagnant_rounds = 0

    def collect() -> int:
        before = len(found)
        found.update(collect_chapter_rows_on_current_page_deep(page).keys())
        found.update(collect_editor_links_on_current_page_deep(page).keys())
        return len(found) - before

    collect()
    for _ in range(40):
        progressed = False
        for page_no in sorted(get_visible_page_numbers(page)):
            if page_no in visited_pages:
                continue
            visited_pages.add(page_no)
            if click_page_number(page, page_no):
                dismiss_popups(page)
                added = collect()
                progressed = True
                if added:
                    stagnant_rounds = 0
        before = len(found)
        if click_next_page(page):
            dismiss_popups(page)
            collect()
            progressed = True
            if len(found) > before:
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1
        elif not progressed:
            stagnant_rounds += 1
        if stagnant_rounds >= 3:
            break

    numbers = sorted(found)
    if numbers:
        log(f"新建前校验：平台当前已识别章节 {len(numbers)} 章，最后一章约为第 {numbers[-1]} 章。")
    else:
        log("新建前校验：平台列表暂未识别到已有章节，将按空书处理。")
    return numbers


def _ensure_create_allowed(
    chapter_no: int,
    existing_numbers: list[int],
    *,
    created_chapter_numbers: set[int] | None = None,
) -> None:
    existing = {int(no) for no in existing_numbers if int(no) > 0}
    already_created = {int(no) for no in (created_chapter_numbers or set()) if int(no) > 0}
    numbers = sorted(existing | already_created)

    if chapter_no in existing:
        raise RuntimeError(f"安全校验失败：平台列表里已经存在第 {chapter_no} 章，不能重复新建。")
    if chapter_no in already_created:
        raise RuntimeError(f"安全校验失败：本次批量任务中已经新建过第 {chapter_no} 章，不能重复新建。")

    expected = (numbers[-1] + 1) if numbers else 1
    if chapter_no != expected:
        raise RuntimeError(
            f"安全策略阻止自动新建：平台最后一章是第 {max(existing) if existing else 0} 章，"
            f"本次批量已连续补到第 {max(already_created) if already_created else (max(existing) if existing else 0)} 章，"
            f"系统只允许按顺序继续新建第 {expected} 章；但本次目标是第 {chapter_no} 章。"
            "请先确认本地范围是否从平台最后一章的下一章开始，避免章节错位。"
        )


def _click_new_chapter(page: Page, *, log: Callable[[str], None]) -> tuple[Page, bool]:
    save_debug(page, "before_click_new_chapter")
    context = page.context
    old_pages = list(context.pages)
    try:
        page.evaluate(
            """() => {
                for (const el of [document.scrollingElement, document.documentElement, document.body]) {
                    if (el) el.scrollTop = 0;
                }
            }"""
        )
    except Exception:
        pass

    if not _click_new_button_once(page):
        dismiss_popups(page)
        page.wait_for_timeout(800)
        if not _click_new_button_once(page):
            raise RuntimeError('未找到\u201c新建章节\u201d按钮。请确认当前 URL 是番茄章节管理页。')

    page.wait_for_timeout(2200)
    save_debug(page, "after_click_new_chapter")
    if len(context.pages) > len(old_pages):
        editor_page = context.pages[-1]
        try:
            editor_page.bring_to_front()
        except Exception:
            pass
        log("番茄已打开新的章节编辑标签页，已自动切换过去。")
        save_debug(editor_page, "new_chapter_new_tab_front")
        return editor_page, True
    return page, False


def _click_new_button_once(page: Page) -> bool:
    button_candidates = [
        page.get_by_role("button", name="新建章节"),
        page.get_by_text("新建章节", exact=True),
        page.get_by_text("新建", exact=False),
    ]
    for loc in button_candidates:
        count = locator_count_safe(loc)
        for i in range(count):
            item = loc.nth(i)
            try:
                if item.is_visible() and item.is_enabled():
                    item.scroll_into_view_if_needed()
                    item.click(force=True, timeout=10000)
                    return True
            except Exception:
                continue

    script = r"""
    () => {
        function visible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none' &&
                   rect.bottom >= 0 && rect.right >= 0 &&
                   rect.top <= window.innerHeight && rect.left <= window.innerWidth;
        }
        function text(el) { return ((el.innerText || el.textContent || '') + '').replace(/\s+/g, '').trim(); }
        const nodes = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .filter(visible)
            .map(el => ({ el, clickable: el.closest('button, [role="button"], a') || el, text: text(el) }))
            .filter(x => x.text.includes('新建章节') || x.text === '新建');
        for (const item of nodes) {
            try {
                item.clickable.scrollIntoView({block: 'center', inline: 'center'});
                item.clickable.click();
                return true;
            } catch (e) {
                try { item.el.click(); return true; } catch (e2) {}
            }
        }
        return false;
    }
    """
    try:
        return bool(page.evaluate(script))
    except Exception:
        return False


def dismiss_editor_guides(page: Page, *, log: Callable[[str], None] = print) -> None:
    for _ in range(3):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(180)
        except Exception:
            pass

    for _ in range(8):
        clicked = False
        for text in ("我知道了", "知道了", "跳过", "完成"):
            if _click_visible_text_button(page, text, only_floating=False):
                save_debug(page, f"editor_guide_clicked_{text}")
                clicked = True
                page.wait_for_timeout(450)

        if _click_visible_text_button(page, "下一步", only_floating=True):
            save_debug(page, "editor_guide_clicked_next")
            clicked = True
            page.wait_for_timeout(450)
        if not clicked:
            break
    log("编辑页遮罩清理完成。")


def _click_visible_text_button(page: Page, text: str, *, only_floating: bool) -> bool:
    script = r"""
    ([target, onlyFloating]) => {
        function visible(el) {
            if (!el) return false;
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
                   style.visibility !== 'hidden' && style.display !== 'none' &&
                   rect.bottom >= 0 && rect.right >= 0 &&
                   rect.top <= window.innerHeight && rect.left <= window.innerWidth;
        }
        function compact(el) { return ((el.innerText || el.textContent || '') + '').replace(/\s+/g, '').trim(); }
        const nodes = Array.from(document.querySelectorAll('button, [role="button"], a, span, div'))
            .filter(visible)
            .map(el => {
                const clickable = el.closest('button, [role="button"], a') || el;
                const rect = clickable.getBoundingClientRect();
                return {el, clickable, rect, text: compact(el)};
            })
            .filter(x => x.text === target || compact(x.clickable) === target)
            .filter(x => !onlyFloating || x.rect.top > 100)
            .sort((a, b) => b.rect.top - a.rect.top);
        for (const item of nodes) {
            try {
                item.clickable.click();
                return true;
            } catch (e) {
                try { item.el.click(); return true; } catch (e2) {}
            }
        }
        return false;
    }
    """
    try:
        return bool(page.evaluate(script, [text, only_floating]))
    except Exception:
        return False


__all__ = [
    "collect_all_remote_chapter_numbers",
    "_ensure_create_allowed",
    "_click_new_chapter",
    "_click_new_button_once",
    "dismiss_editor_guides",
    "_click_visible_text_button",
]

