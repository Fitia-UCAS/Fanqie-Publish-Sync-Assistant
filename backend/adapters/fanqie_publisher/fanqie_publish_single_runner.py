from __future__ import annotations

from typing import Callable

from backend.adapters.fanqie_publisher.fanqie_publish_creator import create_remote_chapter_editor
from backend.adapters.fanqie_publisher.fanqie_publish_submitter import publish_after_save
from backend.adapters.fanqie_publisher.fanqie_publish_tracker import track_publish_chapter
from backend.adapters.fanqie_publisher.fanqie_publish_local_file import Chapter
from backend.adapters.fanqie_publisher.fanqie_publish_models import ChapterPublishResult
from backend.adapters.fanqie_publisher.fanqie_publish_options import ChapterPublishOptions
from backend.adapters.fanqie_publisher.fanqie_publish_verifier import verify_single_list_count
from backend.adapters.fanqie_web.browser.browser_session import save_debug, save_failure_debug
from backend.adapters.fanqie_web.pages.chapter_editor_page import (
    click_save_draft,
    editor_body_counter_confirms,
    element_text_or_value,
    fill_locator,
    reported_body_word_count,
)
from backend.services.novel_text.text_normalizer import normalize_novel_body


def run_single_chapter_publish(
    *,
    page,
    chapter_no: int,
    local: Chapter,
    options: ChapterPublishOptions,
    log: Callable[[str], None],
) -> ChapterPublishResult:

    local_title = local.subtitle
    log(f"本地：第 {chapter_no} 章《{local_title}》")
    trace_dir = track_publish_chapter(chapter_no, local, enabled=options.git_tracking, log=log)

    created = create_remote_chapter_editor(
        page,
        chapter_manage_url=options.chapter_manage_url,
        chapter_no=chapter_no,
        local_title=local_title,
        log=log,
        verify_sequence=False,
    )
    editor_page = created.page

    log("正在填写章节序号...")
    save_debug(editor_page, f"chapter_{chapter_no:03d}_before_fill_chapter_no")
    fill_locator(editor_page, created.chapter_no_loc, str(chapter_no))
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_fill_chapter_no")

    log("正在覆盖标题和完整正文...")
    save_debug(editor_page, f"chapter_{chapter_no:03d}_before_fill_title")
    fill_locator(editor_page, created.title_loc, local_title)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_fill_title")

    save_debug(editor_page, f"chapter_{chapter_no:03d}_before_fill_body")
    fill_locator(editor_page, created.body_loc, local.content)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_fill_body")
    _ensure_body_written(editor_page, created.body_loc, local, log=log)

    log("正在保存草稿，等待番茄显示已保存...")
    click_save_draft(editor_page, log=log)
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_save")

    log("正在进入发布流程：点击右上角“下一步”，并处理错别字/AI 设置/确认发布弹窗...")
    publish_after_save(editor_page, use_ai=options.use_ai, log=log, scheduled_slot=options.schedule_for(chapter_no))
    save_debug(editor_page, f"chapter_{chapter_no:03d}_after_publish")
    if options.verify_after_publish:
        verify_single_list_count(editor_page, chapter_no=chapter_no, chapter_manage_url=options.chapter_manage_url, local=local, log=log)
        save_debug(editor_page, f"chapter_{chapter_no:03d}_after_list_verify")
    msg = "完成：已自动新建、写入、保存并确认发布。"
    log(msg)
    return ChapterPublishResult(ok=True, chapter_no=chapter_no, published=True, message=msg, trace_dir=trace_dir)


def _ensure_body_written(page, body_loc, local: Chapter, *, log: Callable[[str], None]) -> None:
    expected_body = normalize_novel_body(local.content)
    written_body = normalize_novel_body(element_text_or_value(body_loc))
    if expected_body and len(written_body) >= max(200, int(len(expected_body) * 0.65)):
        return
    if editor_body_counter_confirms(page, local.content):
        count = reported_body_word_count(page)
        log(f"正文编辑器字数统计已刷新：{count}，继续保存和发布。")
        return

    if expected_body:
        log("正文写入状态读取不稳定，正在重试写入正文...")
        save_debug(page, "body_fill_retry_before")
        fill_locator(page, body_loc, local.content)
        save_debug(page, "body_fill_retry_after")
        written_body = normalize_novel_body(element_text_or_value(body_loc))

    if expected_body and len(written_body) < max(200, int(len(expected_body) * 0.65)):
        if editor_body_counter_confirms(page, local.content):
            count = reported_body_word_count(page)
            log(f"正文编辑器字数统计已刷新：{count}，继续保存和发布。")
            return
        save_failure_debug(page, "body_fill_failed_after_retry")
        raise RuntimeError("正文写入失败：番茄编辑器仍显示正文为空或字数过少。")
