from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.publishing.outcome import PublishedChapter
from backend.publishing.batch import run_multi_chapter_publish as _run_multi_chapter_publish
from backend.defaults import DEFAULT_CHAPTER_MANAGE_URL


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
) -> list[PublishedChapter]:
    return _run_multi_chapter_publish(
        novel_file=novel_file,
        chapters=chapters,
        chapter_manage_url=chapter_manage_url,
        use_ai=use_ai,
        verify_after_publish=verify_after_publish,
        debug_screenshots=debug_screenshots,
        failure_screenshots=failure_screenshots,
        git_tracking=git_tracking,
        clean_before_run=clean_before_run,
        headless=headless,
        auth_state_path=auth_state_path,
        manual_schedule_enabled=manual_schedule_enabled,
        schedule_start_date=schedule_start_date,
        schedule_morning_time=schedule_morning_time,
        schedule_morning_count=schedule_morning_count,
        schedule_afternoon_time=schedule_afternoon_time,
        schedule_afternoon_count=schedule_afternoon_count,
        log=log,
        stop_requested=stop_requested,
        pause_requested=pause_requested,
    )
