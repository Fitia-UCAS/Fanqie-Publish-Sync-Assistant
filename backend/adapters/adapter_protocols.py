
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from backend.adapters.fanqie_publisher.fanqie_publish_models import ChapterPublishResult
from backend.adapters.fanqie_syncer.fanqie_sync_models import ChapterSyncResult
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


@runtime_checkable
class ChapterPublisher(Protocol):

    def run_multi_chapter_publish(
        self,
        novel_file: Path,
        chapters: list[int],
        *,
        chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
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
        ...


@runtime_checkable
class ChapterSyncer(Protocol):

    def run_chapter_sync(
        self,
        novel_file: Path,
        chapter_no: int = 1,
        *,
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
        ...

    def run_multi_chapter_sync(
        self,
        novel_file: Path,
        chapters: list[int],
        *,
        chapter_manage_url: str = DEFAULT_CHAPTER_MANAGE_URL,
        use_ai: bool = False,
        direction: str = "local_to_remote",
        log: Callable[[str], None] = print,
        check_only: bool = False,
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
        ...

    def collect_remote_chapter_numbers(
        self,
        chapter_manage_url: str = "",
        log: Callable[[str], None] = print,
    ) -> list[int]:
        ...


__all__ = [
    "ChapterPublisher",
    "ChapterSyncer",
]

