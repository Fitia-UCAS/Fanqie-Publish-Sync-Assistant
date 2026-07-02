from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.syncing.apply import apply_local_to_remote, apply_remote_to_local, record_diff_snapshot
from backend.syncing.editor import create_sync_remote_chapter_editor
from backend.syncing.local_source import Chapter, get_local_chapter
from backend.syncing.plan import SyncPlan, SyncedChapter
from backend.syncing.content_check import confirm_same_content_if_needed
from backend.fanqie_web.browser_session import save_debug
from backend.fanqie_web.form_fields import get_remote_chapter
from backend.fanqie_web.open_chapter import ChapterEditorNotFound, open_chapter_editor
from backend.novel.text_cleaning import normalize_novel_body, same_text


def run_single_chapter_sync(
    page,
    novel_file: Path,
    chapter_no: int,
    options: SyncPlan,
    log: Callable[[str], None] = print,
    local_chapter: Chapter | None = None,
    editor_url_cache: dict[int, str] | None = None,
    created_chapter_numbers: set[int] | None = None,
) -> SyncedChapter:
    local = local_chapter or get_local_chapter(novel_file, chapter_no)
    local_title = local.subtitle
    local_body_norm = normalize_novel_body(local.content)
    log(f"本地：第 {chapter_no} 章《{local_title}》")

    cached_editor_url = editor_url_cache.get(chapter_no) if editor_url_cache else None
    created_chapter = False
    created_new_page = False
    chapter_no_loc = None

    try:
        open_chapter_editor(page, options.chapter_manage_url, chapter_no, local_title, log=log, cached_editor_url=cached_editor_url)
        save_debug(page, "before_read")
        remote_title, remote_body, title_loc, body_loc = get_remote_chapter(page)
        log(f"番茄：标题《{remote_title}》")
    except ChapterEditorNotFound as exc:
        if not _can_create_missing(options):
            raise RuntimeError(f"未找到番茄后台第 {chapter_no} 章。当前操作不会新建章节。") from exc
        created = create_sync_remote_chapter_editor(
            page,
            chapter_manage_url=options.chapter_manage_url,
            chapter_no=chapter_no,
            local_title=local_title,
            created_chapter_numbers=created_chapter_numbers,
            log=log,
        )
        page = created.page
        chapter_no_loc = created.chapter_no_loc
        title_loc = created.title_loc
        body_loc = created.body_loc
        remote_title = ""
        remote_body = ""
        created_chapter = True
        created_new_page = created.opened_new_page
        save_debug(page, "after_create_before_fill")
        log(f"番茄：第 {chapter_no} 章不存在，已打开新建章节编辑页。")

    title_same = same_text(local_title, remote_title) or same_text(local.full_title, remote_title)
    body_same = same_text(local_body_norm, remote_body)
    if title_same and body_same:
        result = confirm_same_content_if_needed(page, chapter_no=chapter_no, options=options, local=local, log=log)
        if result:
            return result
        msg = "经检测，本地版本与番茄版本一致，无需替换。"
        log(msg)
        return SyncedChapter(ok=True, changed=False, published=False, message=msg)

    log("经检测，本地版本与番茄版本有差异。")
    diff_path, git_repo, trace_dir = record_diff_snapshot(
        chapter_no=chapter_no,
        local_title=local_title,
        local_body=local.content,
        remote_title=remote_title,
        remote_body=remote_body,
        direction=options.direction,
        git_tracking=options.git_tracking,
        log=log,
    )

    if options.check_only:
        msg = "仅检查：已记录差异和 Git追踪，未替换。" if options.git_tracking else "仅检查：已检测到差异，未替换。"
        log(msg)
        return SyncedChapter(ok=True, changed=True, published=False, message=msg, diff_path=diff_path, git_repo=git_repo, trace_dir=trace_dir)

    if options.direction == "remote_to_local":
        return apply_remote_to_local(
            novel_file=novel_file,
            chapter_no=chapter_no,
            remote_title=remote_title,
            remote_body=remote_body,
            diff_path=diff_path,
            git_repo=git_repo,
            trace_dir=trace_dir,
            log=log,
        )

    result = apply_local_to_remote(
        page,
        chapter_no=chapter_no,
        local=local,
        local_title=local_title,
        title_loc=title_loc,
        body_loc=body_loc,
        chapter_no_loc=chapter_no_loc,
        created_chapter=created_chapter,
        options=options,
        diff_path=diff_path,
        git_repo=git_repo,
        trace_dir=trace_dir,
        log=log,
    )
    if created_chapter and result.ok and created_chapter_numbers is not None:
        created_chapter_numbers.add(chapter_no)
        log(f"顺序新建记录：本次已新建第 {chapter_no} 章，后续可继续新建第 {chapter_no + 1} 章。")
    if created_new_page:
        try:
            page.close()
            log("已关闭新建章节时打开的临时编辑标签页。")
        except Exception:
            pass
    return result


def _can_create_missing(options: SyncPlan) -> bool:
    return options.direction == "local_to_remote" and not options.check_only
