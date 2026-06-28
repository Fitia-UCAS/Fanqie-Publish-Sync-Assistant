from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from backend.adapters.fanqie_publisher.fanqie_publish_tracker import clean_previous_publish_artifacts
from backend.adapters.fanqie_publisher.fanqie_publish_local_file import load_local_chapters_by_number
from backend.shared.app.app_errors import ErrorStage
from backend.adapters.fanqie_publisher.fanqie_publish_models import ChapterPublishResult
from backend.adapters.fanqie_publisher.fanqie_publish_options import ChapterPublishOptions, make_chapter_publish_options
from backend.adapters.fanqie_publisher.fanqie_publish_single_runner import run_single_chapter_publish
from backend.adapters.fanqie_publisher.fanqie_publish_verifier import wait_for_chapter_list_word_counts
from backend.adapters.fanqie_web.browser.browser_session import close_context, make_context, save_failure_debug
from backend.adapters.fanqie_web.models import build_schedule_slots, describe_schedule_slots
from backend.shared.app.app_paths import PUBLISH_DEBUG_DIR, PUBLISH_TRACKER_DIR
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


def run_multi_chapter_publish(
    novel_file: Path,
    chapters: list[int],
    chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
    *,
    use_ai: bool = False,
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
    log: Callable[[str], None] = print,
    stop_requested: Callable[[], bool] | None = None,
    pause_requested: Callable[[], bool] | None = None,
) -> list[ChapterPublishResult]:
    options = make_chapter_publish_options(
        chapter_manage_url=chapter_manage_url,
        use_ai=use_ai,
        verify_after_publish=verify_after_publish,
        debug_screenshots=debug_screenshots,
        failure_screenshots=failure_screenshots,
        git_tracking=git_tracking,
        clean_before_run=clean_before_run,
        headless=headless,
        auth_state_path=auth_state_path,
        schedule_slots=build_schedule_slots(
            chapters,
            enabled=manual_schedule_enabled,
            start_date=schedule_start_date,
            morning_time=schedule_morning_time,
            morning_count=schedule_morning_count,
            afternoon_time=schedule_afternoon_time,
            afternoon_count=schedule_afternoon_count,
        ),
    )
    return run_multi_chapter_publish_with_options(novel_file=novel_file, chapters=chapters, options=options, log=log, stop_requested=stop_requested, pause_requested=pause_requested)


def run_multi_chapter_publish_with_options(
    *,
    novel_file: Path,
    chapters: list[int],
    options: ChapterPublishOptions,
    log: Callable[[str], None] = print,
    stop_requested: Callable[[], bool] | None = None,
    pause_requested: Callable[[], bool] | None = None,
) -> list[ChapterPublishResult]:
    local_chapters = load_local_chapters_by_number(novel_file, chapters)
    if options.clean_before_run:
        clean_previous_publish_artifacts(log=log)
    else:
        log("启动清理旧番茄发布数据已关闭。")
    if options.debug_screenshots:
        log(f"番茄发布调试截图已开启：{PUBLISH_DEBUG_DIR}")
    else:
        log("番茄发布调试截图已关闭。")
    if options.git_tracking:
        log(f"番茄发布 Git追踪已开启：{PUBLISH_TRACKER_DIR}")
    else:
        log("番茄发布 Git追踪已关闭。")
    log("番茄发布流程：不会定位/读取既有章节，将按本地范围直接新建章节。")
    schedule_desc = describe_schedule_slots(options.schedule_slots)
    if schedule_desc:
        log(schedule_desc)

    p, context, page = make_context(headless=options.headless, debug_category="auto_publish", debug_enabled=options.debug_screenshots, failure_debug_enabled=options.failure_screenshots, auth_state_path=options.auth_state_path)
    results: list[ChapterPublishResult] = []
    try:
        if not chapters:
            log("没有需要处理的章节。")
        per_chapter_options = replace(options, verify_after_publish=False) if options.verify_after_publish else options
        for index, chapter_no in enumerate(chapters, start=1):
            if _stop_requested(stop_requested):
                log("已停止发布。")
                break
            _wait_while_paused(pause_requested=pause_requested, stop_requested=stop_requested, log=log, label="发布")
            if _stop_requested(stop_requested):
                log("已停止发布。")
                break
            log(f"后台批量处理：第 {chapter_no} 章（{index}/{len(chapters)}）")
            try:
                results.append(
                    run_single_chapter_publish(
                        page=page,
                        chapter_no=chapter_no,
                        local=local_chapters[chapter_no],
                        options=per_chapter_options,
                        log=log,
                    )
                )
            except Exception as exc:
                save_failure_debug(page, f"chapter_{chapter_no:03d}_failed")
                msg = f"失败：第 {chapter_no} 章｜{exc}"
                log(msg)
                results.append(ChapterPublishResult(ok=False, chapter_no=chapter_no, published=False, message=msg, error_stage=ErrorStage.CHAPTER))
            finally:
                _return_to_first_page(context)
        if not _stop_requested(stop_requested):
            _final_list_verify_if_needed(
                page=page,
                options=options,
                local_chapters=local_chapters,
                results=results,
                log=log,
            )
        return results
    finally:
        close_context(p, context)


def _return_to_first_page(context) -> None:
    try:
        pages = list(context.pages)
        if len(pages) <= 1:
            return
        for extra in pages[1:]:
            try:
                extra.close()
            except Exception:
                pass
        if context.pages:
            context.pages[0].bring_to_front()
        else:
            context.new_page()
    except Exception:
        pass


def _final_list_verify_if_needed(
    *,
    page,
    options: ChapterPublishOptions,
    local_chapters: dict[int, object],
    results: list[ChapterPublishResult],
    log: Callable[[str], None],
) -> None:
    if not options.verify_after_publish:
        return
    chapter_numbers = [result.chapter_no for result in results if result.ok and result.published]
    if not chapter_numbers:
        log("最终列表校验：没有已提交成功的章节需要校验。")
        return
    log("正在进行最终章节列表校验，确认已发布列表字数是否全部更新...")
    failures = wait_for_chapter_list_word_counts(
        page,
        chapter_manage_url=options.chapter_manage_url,
        local_chapters=local_chapters,
        chapter_numbers=chapter_numbers,
        log=log,
    )
    if failures:
        _mark_list_verify_failures(failures=failures, results=results, log=log)
    else:
        log("最终章节列表校验通过：本次成功提交的章节平台字数均已更新。")


def _mark_list_verify_failures(
    *,
    failures: dict[int, str],
    results: list[ChapterPublishResult],
    log: Callable[[str], None],
) -> None:
    for no, reason in failures.items():
        log(f"失败：第 {no} 章｜{reason}")
        for result in results:
            if result.chapter_no == no:
                result.ok = False
                result.message = reason
                result.error_stage = ErrorStage.LIST_VERIFY
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
