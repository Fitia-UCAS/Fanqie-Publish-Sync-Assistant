from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from backend.adapters.adapter_factory import AdapterFactory
from backend.shared.task.task_callbacks import TaskCallbacks
from backend.shared.task.task_result import TaskResult
from backend.task_logs.fanqie_task_log import FanqieTaskLog
from backend.services.novel_text.chapter_parser import split_chapter_source_paths


def publish_missing_chapters(payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
    callbacks = callbacks or TaskCallbacks()
    novel_file = _require_source(payload.get("novelFile"))
    url = str(payload.get("chapterManageUrl") or "").strip()
    if not url.startswith("http"):
        return TaskResult(False, "请填写番茄章节管理 URL。")

    start, end = _chapter_range(payload)
    chapters = list(range(start, end + 1))
    concise_log = FanqieTaskLog(
        callbacks=callbacks,
        task_kind="auto_publish",
        operation="publish",
        start=start,
        end=end,
        total=len(chapters),
    )
    concise_log.emit_start("publish", start, end)
    results = AdapterFactory.get_publisher().run_multi_chapter_publish(
        novel_file=novel_file,
        chapters=chapters,
        chapter_manage_url=url,
        use_ai=bool(payload.get("useAi", False)),
        verify_after_publish=bool(payload.get("verifyAfterPublish", True)),
        debug_screenshots=bool(payload.get("debugScreenshots", True)),
        failure_screenshots=bool(payload.get("failureScreenshots", True)),
        git_tracking=bool(payload.get("gitTracking", True)),
        clean_before_run=bool(payload.get("cleanBeforeRun", True)),
        headless=bool(payload.get("headless", False)),
        auth_state_path=str(payload.get("authStatePath") or ""),
        manual_schedule_enabled=bool(payload.get("manualSchedule", False)),
        schedule_start_date=str(payload.get("scheduleStartDate") or ""),
        schedule_morning_time=str(payload.get("scheduleMorningTime") or "10:00"),
        schedule_morning_count=int(payload.get("scheduleMorningCount") or 1),
        schedule_afternoon_time=str(payload.get("scheduleAfternoonTime") or "18:00"),
        schedule_afternoon_count=int(payload.get("scheduleAfternoonCount") or 0),
        log=concise_log.log,
        stop_requested=callbacks.stop_requested,
        pause_requested=callbacks.pause_requested,
    )
    ok_count = sum(1 for item in results if getattr(item, "ok", False))
    concise_log.finish(ok_count, len(results))
    stopped = callbacks.stop_requested()
    message = f"已停止发布：成功 {ok_count}/{len(chapters)}。" if stopped else f"任务结束：成功 {ok_count}/{len(chapters)}。"
    return TaskResult((not stopped) and ok_count == len(chapters), message, path=concise_log.path, data={"items": [_to_dict(item) for item in results], "stopped": stopped})


def _chapter_range(payload: dict[str, Any]) -> tuple[int, int]:
    start = int(payload.get("start") or 1)
    end = int(payload.get("end") or start)
    if end < start:
        start, end = end, start
    return start, end


def _require_source(value: Any) -> Path | str:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("请先选择小说文件或章节文件夹。")
    paths = split_chapter_source_paths(raw)
    if not paths:
        raise RuntimeError("请先选择小说文件或章节文件夹。")
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"请选择存在的小说文件或章节文件夹：{missing[0]}")
    return paths[0] if len(paths) == 1 else "\n".join(str(path) for path in paths)


def _to_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        data = asdict(value)
    elif hasattr(value, "__dict__"):
        data = dict(value.__dict__)
    else:
        return {"message": str(value)}
    return {key: str(item) if isinstance(item, Path) else item for key, item in data.items()}
