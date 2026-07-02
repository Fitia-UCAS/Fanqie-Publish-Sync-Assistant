from __future__ import annotations

from typing import Callable

from backend.defaults import DEFAULT_CHAPTER_MANAGE_URL
from backend.fanqie_web.browser_session import close_context, make_context
from backend.fanqie_web.chapter_list import collect_editor_links_on_current_page_deep
from backend.fanqie_web.ui_actions import dismiss_popups, ensure_logged_in, goto_chapter_manage
from backend.fanqie_web.pagination import click_next_page, click_page_number, get_visible_page_numbers


def collect_remote_chapter_numbers(
    chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
    log: Callable[[str], None] = print,
) -> list[int]:
    p, context, page = make_context(headless=False)
    try:
        goto_chapter_manage(page, chapter_manage_url)
        ensure_logged_in(page, chapter_manage_url, log=log)
        dismiss_popups(page)
        found: set[int] = set()
        visited_pages: set[int] = set()

        def collect() -> int:
            before = len(found)
            found.update(collect_editor_links_on_current_page_deep(page).keys())
            return len(found) - before

        collect()
        stagnant_rounds = 0
        for _ in range(40):
            progressed = False
            for page_no in sorted(get_visible_page_numbers(page)):
                if page_no in visited_pages:
                    continue
                visited_pages.add(page_no)
                if click_page_number(page, page_no):
                    dismiss_popups(page)
                    progressed = True or collect() > 0
            if click_next_page(page):
                dismiss_popups(page)
                progressed = True or collect() > 0
            if progressed:
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1
                if stagnant_rounds >= 2:
                    break
        return sorted(found)
    finally:
        close_context(p, context)
