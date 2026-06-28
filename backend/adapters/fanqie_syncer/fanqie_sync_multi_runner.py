from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Callable

from backend.adapters.fanqie_syncer.fanqie_sync_local_file import Chapter, parse_chapters
from backend.shared.app.app_errors import ErrorStage
from backend.adapters.fanqie_syncer.fanqie_sync_models import ChapterSyncOptions, ChapterSyncResult
from backend.adapters.fanqie_syncer.fanqie_sync_options import make_chapter_sync_options
from backend.adapters.fanqie_syncer.fanqie_sync_single_runner import run_single_chapter_sync
from backend.adapters.fanqie_syncer.fanqie_sync_preflight import wait_for_chapter_list_word_counts
from backend.adapters.fanqie_web.browser.browser_session import close_context, make_context, save_failure_debug
from backend.adapters.fanqie_web.page_actions.chapter_page_interactions import dismiss_popups, goto_chapter_manage
from backend.adapters.fanqie_web.pages.chapter_list_page import build_chapter_editor_index
from backend.adapters.fanqie_web.models import build_schedule_slots, describe_schedule_slots
from backend.services.novel_text.chapter_parser import chapters_by_number
from backend.shared.app.app_paths import CHAPTER_SYNC_COMPARE_DIR, CHAPTER_SYNC_DEBUG_DIR, CHAPTER_SYNC_HISTORY_DIR
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


def run_multi_chapter_sync(
    novel_file: Path,
    chapters: list[int],
    chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
    use_ai: bool = False,
    check_only: bool = False,
    direction: str = "local_to_remote",
    log: Callable[[str], None] = print,
    verify_after_publish: bool = True,
    debug_screenshots: bool = True,
    failure_screenshots: bool = True,
    git_tracking: bool = True,
    clean_before_run: bool = True,
    headless: bool = False,
    auth_state_path: str = "",
    manual_schedule_enabled: bool = False,
    schedule_start_date: str = "",
    schedule_morning_time: str = "10:00",
    schedule_morning_count: int = 1,
    schedule_afternoon_time: str = "18:00",
    schedule_afternoon_count: int = 0,
    stop_requested: Callable[[], bool] | None = None,
    pause_requested: Callable[[], bool] | None = None,
) -> list[ChapterSyncResult]:
    options = make_chapter_sync_options(
        chapter_manage_url=chapter_manage_url,
        use_ai=use_ai,
        check_only=check_only,
        direction=direction,
        verify_after_publish=verify_after_publish,
        debug_screenshots=debug_screenshots,
        failure_screenshots=failure_screenshots,
        git_tracking=git_tracking,
        clean_before_run=clean_before_run,
        headless=headless,
        auth_state_path=auth_state_path,
        schedule_slots=build_schedule_slots(
            chapters,
            enabled=manual_schedule_enabled and direction == "local_to_remote" and not check_only,
            start_date=schedule_start_date,
            morning_time=schedule_morning_time,
            morning_count=schedule_morning_count,
            afternoon_time=schedule_afternoon_time,
            afternoon_count=schedule_afternoon_count,
        ),
    )
    if options.clean_before_run:
        _clean_previous_sync_artifacts(log=log)
    else:
        log("启动清理旧番茄同步数据已关闭。")
    if options.debug_screenshots:
        log(f"番茄同步调试截图已开启：{CHAPTER_SYNC_DEBUG_DIR}")
    else:
        log("番茄同步调试截图已关闭。")
    if options.git_tracking:
        log(f"番茄同步 Git追踪已开启：{CHAPTER_SYNC_HISTORY_DIR}")
    else:
        log("番茄同步 Git追踪已关闭。")
    schedule_desc = describe_schedule_slots(options.schedule_slots)
    if schedule_desc:
        log(schedule_desc)

    p, context, page = make_context(headless=options.headless, debug_category="chapter_sync", debug_enabled=options.debug_screenshots, failure_debug_enabled=options.failure_screenshots, auth_state_path=options.auth_state_path)
    state = MultiChapterSyncState(chapters=list(chapters), results=[], result_chapter_numbers=[])
    try:
        local_chapters = _local_chapters_by_number(novel_file, chapters)
        if options.direction == "local_to_remote":
            log("正文校准已启用：会进入编辑页读取标题/正文，与本地一致则继续确认发布；存在差异才覆盖。")

        editor_url_cache = _index_editors_if_needed(
            page,
            chapter_manage_url=chapter_manage_url,
            chapters=chapters,
            editor_url_cache={},
            log=log,
        )
        if not chapters:
            log("没有需要处理的章节。")

        _process_chapters(
            page=page,
            novel_file=novel_file,
            chapters=chapters,
            local_chapters=local_chapters,
            base_options=options,
            editor_url_cache=editor_url_cache,
            state=state,
            log=log,
            stop_requested=stop_requested,
            pause_requested=pause_requested,
        )
        if not _stop_requested(stop_requested):
            _final_list_verify_if_needed(
                page=page,
                options=options,
                chapter_manage_url=chapter_manage_url,
                local_chapters=local_chapters,
                chapters=chapters,
                state=state,
                log=log,
            )
        return state.results
    finally:
        close_context(p, context)


class MultiChapterSyncState:
    def __init__(self, chapters: list[int], results: list[ChapterSyncResult], result_chapter_numbers: list[int]) -> None:
        self.chapters = chapters
        self.results = results
        self.result_chapter_numbers = result_chapter_numbers

    def append(self, chapter_no: int, result: ChapterSyncResult) -> None:
        self.results.append(result)
        self.result_chapter_numbers.append(chapter_no)


def _clean_previous_sync_artifacts(*, log: Callable[[str], None]) -> None:
    cleaned: list[str] = []
    for directory, label in (
        (CHAPTER_SYNC_DEBUG_DIR, "调试截图"),
        (CHAPTER_SYNC_COMPARE_DIR, "对比报告"),
        (CHAPTER_SYNC_HISTORY_DIR, "Git追踪"),
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except FileNotFoundError:
                        pass
            cleaned.append(label)
        except Exception as exc:
            log(f"启动清理{label}失败：{exc}")
    if cleaned:
        log(f"启动时已清理上次番茄同步数据：{'、'.join(cleaned)}。")


def _local_chapters_by_number(novel_file: Path, chapters: list[int]) -> dict[int, Chapter]:
    local_chapters = chapters_by_number(parse_chapters(novel_file), "本地小说来源")
    missing_local = [no for no in chapters if no not in local_chapters]
    if missing_local:
        raise RuntimeError(f"本地小说来源中没有找到章节：{', '.join(str(no) for no in missing_local)}")
    return local_chapters


def _index_editors_if_needed(
    page,
    *,
    chapter_manage_url: str,
    chapters: list[int],
    editor_url_cache: dict[int, str],
    log: Callable[[str], None],
) -> dict[int, str]:
    if editor_url_cache:
        log(f"章节入口索引：已复用 {len(editor_url_cache)} 个章节入口。")
        return editor_url_cache
    try:
        editor_url_cache = build_chapter_editor_index(page, chapter_manage_url, chapters, log=log)
        if editor_url_cache:
            log(f"章节入口索引：已缓存 {len(editor_url_cache)} 个章节入口，后续会减少重复翻页定位。")
    except Exception as exc:
        log(f"章节入口索引建立失败，自动降级为常规定位：{exc}")
        editor_url_cache = {}
    return editor_url_cache


def _process_chapters(
    *,
    page,
    novel_file: Path,
    chapters: list[int],
    local_chapters: dict[int, Chapter],
    base_options: ChapterSyncOptions,
    editor_url_cache: dict[int, str],
    state: MultiChapterSyncState,
    log: Callable[[str], None],
    stop_requested: Callable[[], bool] | None = None,
    pause_requested: Callable[[], bool] | None = None,
) -> None:
    process_total = len(chapters)
    created_chapter_numbers: set[int] = set()
    per_chapter_options = (
        replace(base_options, verify_after_publish=False)
        if base_options.should_final_list_verify
        else base_options
    )
    for index, chapter_no in enumerate(chapters, start=1):
        if _stop_requested(stop_requested):
            log("已停止同步。")
            break
        _wait_while_paused(pause_requested=pause_requested, stop_requested=stop_requested, log=log, label="同步")
        if _stop_requested(stop_requested):
            log("已停止同步。")
            break
        log(f"后台批量处理：第 {chapter_no} 章（{index}/{process_total}）")
        try:
            state.append(
                chapter_no,
                run_single_chapter_sync(
                    page=page,
                    novel_file=novel_file,
                    chapter_no=chapter_no,
                    options=per_chapter_options,
                    log=log,
                    local_chapter=local_chapters[chapter_no],
                    editor_url_cache=editor_url_cache,
                    created_chapter_numbers=created_chapter_numbers,
                ),
            )
        except Exception as exc:
            _record_chapter_failure(
                page=page,
                chapter_manage_url=base_options.chapter_manage_url,
                chapter_no=chapter_no,
                exc=exc,
                state=state,
                log=log,
            )


def _record_chapter_failure(*, page, chapter_manage_url: str, chapter_no: int, exc: Exception, state: MultiChapterSyncState, log: Callable[[str], None]) -> None:
    save_failure_debug(page, f"chapter_{chapter_no:03d}_failed")
    msg = f"失败：第 {chapter_no} 章｜{exc}"
    log(msg)
    state.append(chapter_no, ChapterSyncResult(ok=False, changed=False, published=False, message=msg, error_stage=ErrorStage.CHAPTER))
    try:
        goto_chapter_manage(page, chapter_manage_url)
        dismiss_popups(page)
    except Exception:
        pass


def _final_list_verify_if_needed(
    *,
    page,
    options: ChapterSyncOptions,
    chapter_manage_url: str,
    local_chapters: dict[int, Chapter],
    chapters: list[int],
    state: MultiChapterSyncState,
    log: Callable[[str], None],
) -> None:
    if not options.should_final_list_verify:
        return
    chapter_numbers = [
        no
        for no, result in zip(state.result_chapter_numbers, state.results)
        if result.ok and result.published
    ]
    if not chapter_numbers:
        log("最终列表校验：没有已提交成功的章节需要校验。")
        return
    log("正在进行最终章节列表校验，确认已发布列表字数是否全部更新...")
    failures = wait_for_chapter_list_word_counts(
        page,
        chapter_manage_url=chapter_manage_url,
        local_chapters=local_chapters,
        chapter_numbers=chapter_numbers,
        log=log,
    )
    if failures:
        _mark_list_verify_failures(failures=failures, state=state, log=log)
    else:
        log("最终章节列表校验通过：本次范围内平台字数均已更新。")


def _mark_list_verify_failures(*, failures: dict[int, str], state: MultiChapterSyncState, log: Callable[[str], None]) -> None:
    for no, reason in failures.items():
        log(f"失败：第 {no} 章｜{reason}")
        for index, chapter in enumerate(state.result_chapter_numbers):
            if chapter == no and index < len(state.results):
                state.results[index].ok = False
                state.results[index].message = reason
                state.results[index].error_stage = ErrorStage.LIST_VERIFY
                break


def _stop_requested(stop_requested: Callable[[], bool] | None) -> bool:
    return bool(stop_requested and stop_requested())


def _wait_while_paused(
    *,
    pause_requested: Callable[[], bool] | None,
    stop_requested: Callable[[], bool] | None,
    log: Callable[[str], None],
    label: str,
) -> None:
    announced = False
    import time
    while pause_requested and pause_requested():
        if _stop_requested(stop_requested):
            return
        if not announced:
            log(f"{label}已暂停，点击继续后会处理下一章。")
            announced = True
        time.sleep(0.5)
