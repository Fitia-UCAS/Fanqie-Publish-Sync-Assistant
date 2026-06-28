from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.adapters.fanqie_syncer.fanqie_sync_models import ChapterSyncResult
from backend.adapters.fanqie_syncer.fanqie_sync_multi_runner import run_multi_chapter_sync
from backend.adapters.fanqie_syncer.fanqie_sync_options import make_chapter_sync_options
from backend.adapters.fanqie_syncer.fanqie_sync_remote_catalog import collect_remote_chapter_numbers
from backend.adapters.fanqie_syncer.fanqie_sync_single_runner import run_single_chapter_sync
from backend.adapters.fanqie_web.browser.browser_session import close_context, make_context
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


def run_chapter_sync(
    novel_file: Path,
    chapter_no: int = 1,
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
) -> ChapterSyncResult:
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
    )
    p, context, page = make_context(headless=headless, debug_category="chapter_sync", debug_enabled=debug_screenshots, failure_debug_enabled=failure_screenshots, auth_state_path=auth_state_path)
    try:
        return run_single_chapter_sync(page=page, novel_file=novel_file, chapter_no=chapter_no, options=options, log=log)
    finally:
        close_context(p, context)


__all__ = [
    "ChapterSyncResult",
    "run_chapter_sync",
    "run_multi_chapter_sync",
    "collect_remote_chapter_numbers",
]
