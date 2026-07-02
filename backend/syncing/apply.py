from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from backend.syncing.local_source import Chapter, replace_local_chapter
from backend.syncing.plan import SyncPlan, SyncedChapter
from backend.fanqie_web.submission import complete_sync_submission
from backend.fanqie_web.list_counts import verify_single_chapter_count
from backend.fanqie_web.browser_session import save_debug, save_failure_debug
from backend.fanqie_web.diff_report import make_git_diff, save_history
from backend.fanqie_web.snapshots import track_snapshot
from backend.fanqie_web.draft_save import click_save_draft
from backend.fanqie_web.form_fields import editor_body_counter_confirms, element_text_or_value, reported_body_word_count
from backend.fanqie_web.text_entry import fill_locator
from backend.novel.text_cleaning import normalize_novel_body


def record_diff_snapshot(
    *,
    chapter_no: int,
    local_title: str,
    local_body: str,
    remote_title: str,
    remote_body: str,
    direction: str,
    git_tracking: bool,
    log: Callable[[str], None],
) -> tuple[Path | None, Optional[Path], Optional[Path]]:
    if not git_tracking:
        return None, None, None
    trace_dir = save_history(
        chapter_no=chapter_no,
        local_title=local_title,
        local_body=local_body,
        remote_title=remote_title,
        remote_body=remote_body,
    )
    diff_path = make_git_diff(
        chapter_no=chapter_no,
        local_title=local_title,
        local_body=local_body,
        remote_title=remote_title,
        remote_body=remote_body,
        direction=direction,
    )
    log(f"Diff：{diff_path}")
    _committed, git_repo, commit_id = track_snapshot(
        chapter_no=chapter_no,
        local_title=local_title,
        local_body=local_body,
        remote_title=remote_title,
        remote_body=remote_body,
    )
    log(f"Git：已记录差异提交 {commit_id}" if commit_id else "Git：未检测到 Git 或无需新增提交")
    log(f"Git追踪目录：{trace_dir}")
    return diff_path, git_repo, trace_dir


def apply_remote_to_local(
    *,
    novel_file: Path,
    chapter_no: int,
    remote_title: str,
    remote_body: str,
    diff_path: Path | None,
    git_repo: Optional[Path],
    trace_dir: Optional[Path],
    log: Callable[[str], None],
) -> SyncedChapter:
    log("正在把番茄版本完整覆盖写入本地 txt...")
    backup_path = replace_local_chapter(
        novel_file=novel_file,
        no=chapter_no,
        title=remote_title,
        content=remote_body,
    )
    msg = f"完成：已将番茄版本完整覆盖写入本地 txt，并已格式化当前章节；章节备份：{backup_path}"
    log(msg)
    return SyncedChapter(ok=True, changed=True, published=False, message=msg, diff_path=diff_path, git_repo=git_repo, trace_dir=trace_dir)


def apply_local_to_remote(
    page,
    *,
    chapter_no: int,
    local: Chapter,
    local_title: str,
    title_loc,
    body_loc,
    chapter_no_loc=None,
    created_chapter: bool = False,
    options: SyncPlan,
    diff_path: Path | None,
    git_repo: Optional[Path],
    trace_dir: Optional[Path],
    log: Callable[[str], None],
) -> SyncedChapter:
    log("正在用本地正文完整覆盖番茄正文...")
    if created_chapter and chapter_no_loc is not None:
        log("正在填写章节序号...")
        fill_locator(page, chapter_no_loc, str(chapter_no))
    log("正在覆盖标题和完整正文...")
    fill_locator(page, title_loc, local_title)
    fill_locator(page, body_loc, local.content)
    written_body = normalize_novel_body(element_text_or_value(body_loc))
    expected_body = normalize_novel_body(local.content)
    if expected_body and len(written_body) < max(200, int(len(expected_body) * 0.65)) and not editor_body_counter_confirms(page, local.content):
        log("正文写入未刷新，正在重试写入正文...")
        fill_locator(page, body_loc, local.content)
        written_body = normalize_novel_body(element_text_or_value(body_loc))
    if expected_body and len(written_body) < max(200, int(len(expected_body) * 0.65)):
        if editor_body_counter_confirms(page, local.content):
            count = reported_body_word_count(page)
            log(f"正文编辑器字数统计已刷新：{count}，继续保存和同步。")
        else:
            save_failure_debug(page, "body_fill_failed")
            raise RuntimeError("正文写入失败：番茄编辑器仍显示正文为空或字数过少。")
    save_debug(page, "after_fill_before_save")
    log("正在保存草稿，等待番茄显示已保存...")
    click_save_draft(page, log=log)
    save_debug(page, "after_save")

    log("正在进入同步提交流程：点击右上角“下一步”，并处理错别字/AI 设置/确认弹窗...")
    complete_sync_submission(page, use_ai=options.use_ai, log=log, scheduled_slot=options.schedule_for(chapter_no))
    save_debug(page, "after_sync_submit")
    if options.verify_after_publish:
        verify_single_chapter_count(
            page,
            chapter_no=chapter_no,
            chapter_manage_url=options.chapter_manage_url,
            local=local,
            action_name="同步",
            log=log,
        )
    msg = "完成：已自动新建、写入、保存并同步确认。" if created_chapter else "完成：已自动替换、保存并同步确认。"
    log(msg)
    return SyncedChapter(
        ok=True,
        changed=True,
        published=True,
        message=msg,
        diff_path=diff_path,
        git_repo=git_repo,
        trace_dir=trace_dir,
    )
