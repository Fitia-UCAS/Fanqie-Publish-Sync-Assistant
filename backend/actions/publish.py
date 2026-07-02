from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.publishing.flow import run_multi_chapter_publish
from backend.tasks.callbacks import TaskCallbacks
from backend.tasks.outcome import TaskOutcome
from backend.tasks.fanqie_log import FanqieLog
from backend.form_inputs import chapter_range, dataclass_payload, int_value, required_chapter_source


@dataclass(slots=True)
class PublishInput:
    novel_file: Path | str
    chapter_manage_url: str
    start: int
    end: int
    use_ai: bool = False
    verify_after_publish: bool = True
    debug_screenshots: bool = True
    failure_screenshots: bool = True
    git_tracking: bool = True
    clean_before_run: bool = True
    headless: bool = False
    auth_state_path: str = ""
    manual_schedule: bool = False
    schedule_start_date: str = ""
    schedule_morning_time: str = "10:00"
    schedule_morning_count: int = 1
    schedule_afternoon_time: str = "18:00"
    schedule_afternoon_count: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PublishInput":
        novel_file = required_chapter_source(payload.get("novelFile"))
        url = str(payload.get("chapterManageUrl") or "").strip()
        if not url.startswith("http"):
            raise ValueError("请填写番茄章节管理 URL。")
        start, end = chapter_range(payload)
        return cls(
            novel_file=novel_file,
            chapter_manage_url=url,
            start=start,
            end=end,
            use_ai=bool(payload.get("useAi", False)),
            verify_after_publish=bool(payload.get("verifyAfterPublish", True)),
            debug_screenshots=bool(payload.get("debugScreenshots", True)),
            failure_screenshots=bool(payload.get("failureScreenshots", True)),
            git_tracking=bool(payload.get("gitTracking", True)),
            clean_before_run=bool(payload.get("cleanBeforeRun", True)),
            headless=bool(payload.get("headless", False)),
            auth_state_path=str(payload.get("authStatePath") or ""),
            manual_schedule=bool(payload.get("manualSchedule", False)),
            schedule_start_date=str(payload.get("scheduleStartDate") or ""),
            schedule_morning_time=str(payload.get("scheduleMorningTime") or "10:00"),
            schedule_morning_count=int_value(payload.get("scheduleMorningCount"), 1),
            schedule_afternoon_time=str(payload.get("scheduleAfternoonTime") or "18:00"),
            schedule_afternoon_count=int_value(payload.get("scheduleAfternoonCount"), 0),
        )

    @property
    def chapters(self) -> list[int]:
        return list(range(self.start, self.end + 1))


def publish_chapters(payload: dict[str, Any] | PublishInput, callbacks: TaskCallbacks | None = None) -> TaskOutcome:
    callbacks = callbacks or TaskCallbacks()
    try:
        request = payload if isinstance(payload, PublishInput) else PublishInput.from_payload(payload)
    except ValueError as exc:
        return TaskOutcome(False, str(exc))

    chapters = request.chapters
    concise_log = FanqieLog(
        callbacks=callbacks,
        task_kind="auto_publish",
        operation="publish",
        start=request.start,
        end=request.end,
        total=len(chapters),
    )
    concise_log.emit_start("publish", request.start, request.end)
    results = run_multi_chapter_publish(
        novel_file=request.novel_file,
        chapters=chapters,
        chapter_manage_url=request.chapter_manage_url,
        use_ai=request.use_ai,
        verify_after_publish=request.verify_after_publish,
        debug_screenshots=request.debug_screenshots,
        failure_screenshots=request.failure_screenshots,
        git_tracking=request.git_tracking,
        clean_before_run=request.clean_before_run,
        headless=request.headless,
        auth_state_path=request.auth_state_path,
        manual_schedule_enabled=request.manual_schedule,
        schedule_start_date=request.schedule_start_date,
        schedule_morning_time=request.schedule_morning_time,
        schedule_morning_count=request.schedule_morning_count,
        schedule_afternoon_time=request.schedule_afternoon_time,
        schedule_afternoon_count=request.schedule_afternoon_count,
        log=concise_log.log,
        stop_requested=callbacks.stop_requested,
        pause_requested=callbacks.pause_requested,
    )
    ok_count = sum(1 for item in results if getattr(item, "ok", False))
    concise_log.finish(ok_count, len(results))
    stopped = callbacks.stop_requested()
    message = f"已停止发布：成功 {ok_count}/{len(chapters)}。" if stopped else f"任务结束：成功 {ok_count}/{len(chapters)}。"
    return TaskOutcome((not stopped) and ok_count == len(chapters), message, path=concise_log.path, data={"items": [dataclass_payload(item) for item in results], "stopped": stopped})
