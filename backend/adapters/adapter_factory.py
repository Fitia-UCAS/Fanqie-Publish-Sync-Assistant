
from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.adapters.adapter_protocols import ChapterPublisher, ChapterSyncer
from backend.adapters.fanqie_publisher.fanqie_publish_models import ChapterPublishResult
from backend.adapters.fanqie_syncer.fanqie_sync_models import ChapterSyncResult
from backend.shared.app.app_runtime_defaults import DEFAULT_CHAPTER_MANAGE_URL


class _PublisherImpl:

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
        from backend.adapters.fanqie_publisher.fanqie_publish_service import run_multi_chapter_publish

        return run_multi_chapter_publish(
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


class _SyncerImpl:

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
        from backend.adapters.fanqie_syncer.fanqie_sync_service import run_chapter_sync

        return run_chapter_sync(
            novel_file=novel_file,
            chapter_no=chapter_no,
            chapter_manage_url=chapter_manage_url,
            use_ai=use_ai,
            check_only=check_only,
            direction=direction,
            log=log,
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
            stop_requested=stop_requested,
        )

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
        from backend.adapters.fanqie_syncer.fanqie_sync_service import run_multi_chapter_sync

        return run_multi_chapter_sync(
            novel_file=novel_file,
            chapters=chapters,
            chapter_manage_url=chapter_manage_url,
            use_ai=use_ai,
            direction=direction,
            log=log,
            check_only=check_only,
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
            stop_requested=stop_requested,
            pause_requested=pause_requested,
        )

    def collect_remote_chapter_numbers(
        self,
        chapter_manage_url: str = "",
        log: Callable[[str], None] = print,
    ) -> list[int]:
        from backend.adapters.fanqie_syncer.fanqie_sync_service import collect_remote_chapter_numbers

        return collect_remote_chapter_numbers(chapter_manage_url=chapter_manage_url, log=log)


class AdapterFactory:

    _publisher: ChapterPublisher | None = None
    _syncer: ChapterSyncer | None = None

    @staticmethod
    def get_publisher() -> ChapterPublisher:
        if AdapterFactory._publisher is None:
            AdapterFactory._publisher = _PublisherImpl()
        return AdapterFactory._publisher

    @staticmethod
    def get_syncer() -> ChapterSyncer:
        if AdapterFactory._syncer is None:
            AdapterFactory._syncer = _SyncerImpl()
        return AdapterFactory._syncer

    @staticmethod
    def set_publisher(publisher: ChapterPublisher) -> None:
        AdapterFactory._publisher = publisher

    @staticmethod
    def set_syncer(syncer: ChapterSyncer) -> None:
        AdapterFactory._syncer = syncer

    @staticmethod
    def reset() -> None:
        AdapterFactory._publisher = None
        AdapterFactory._syncer = None


__all__ = [
    "AdapterFactory",
]

