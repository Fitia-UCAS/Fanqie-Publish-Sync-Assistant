from __future__ import annotations

from typing import Callable

from playwright.sync_api import Page

from backend.fanqie_web.form_fields import pick_chapter_no_title_and_editor
from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.ui_actions import dismiss_popups, ensure_logged_in, goto_chapter_manage, wait_briefly_for_page_ready
from backend.fanqie_web.edit_dialogs import click_continue_edit_if_present
from backend.fanqie_web.remote_editor import RemoteChapterEditor
from backend.fanqie_web.open_editor import (
    _click_new_chapter,
    collect_all_remote_chapter_numbers,
    _ensure_create_allowed,
    dismiss_editor_guides,
)


def create_sync_remote_chapter_editor(
    page: Page,
    *,
    chapter_manage_url: str,
    chapter_no: int,
    local_title: str,
    created_chapter_numbers: set[int] | None = None,
    log: Callable[[str], None] = print,
    verify_sequence: bool = True,
) -> RemoteChapterEditor:


    log(f"准备自动新建番茄后台第 {chapter_no} 章《{local_title}》...")
    goto_chapter_manage(page, chapter_manage_url)
    ensure_logged_in(page, chapter_manage_url, log=log)
    dismiss_popups(page)
    save_debug(page, f"chapter_{chapter_no:03d}_manage_before_new")

    if verify_sequence:
        existing_numbers = collect_all_remote_chapter_numbers(page, chapter_manage_url=chapter_manage_url, log=log)
        _ensure_create_allowed(
            chapter_no,
            existing_numbers,
            created_chapter_numbers=created_chapter_numbers,
        )
        log("未找到目标章节，顺序校准通过，正在点击“新建章节”...")
    else:
        log("直接新建流程：跳过平台章节查找/对比，直接点击“新建章节”。")

    editor_page, opened_new_page = _click_new_chapter(page, log=log)
    wait_briefly_for_page_ready(editor_page)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_editor_opened")
    click_continue_edit_if_present(editor_page, log=log, timeout_ms=1200)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_continue_edit_check")
    dismiss_editor_guides(editor_page, log=log)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_editor_guides")
    chapter_no_loc, title_loc, body_loc = pick_chapter_no_title_and_editor(editor_page)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_editor_inputs_picked")
    return RemoteChapterEditor(
        page=editor_page,
        chapter_no_loc=chapter_no_loc,
        title_loc=title_loc,
        body_loc=body_loc,
        opened_new_page=opened_new_page,
    )
