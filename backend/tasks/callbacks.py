from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from backend.tasks.events import TaskEvent

LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[float, float], None]
StopCallback = Callable[[], bool]
PauseCallback = Callable[[], bool]
EventCallback = Callable[[TaskEvent], None]


@dataclass(slots=True)
class TaskCallbacks:
    log: LogCallback | None = None
    progress: ProgressCallback | None = None
    should_stop: StopCallback | None = None
    should_pause: PauseCallback | None = None
    event: EventCallback | None = None

    def emit_log(self, message: str, level: str = "info") -> None:
        if self.log:
            self.log(message, level)

    def emit_progress(self, current: float, total: float) -> None:
        if self.progress:
            self.progress(current, total)

    def emit_event(self, event: TaskEvent) -> None:
        if self.event:
            self.event(event)

    def stop_requested(self) -> bool:
        return bool(self.should_stop and self.should_stop())

    def pause_requested(self) -> bool:
        return bool(self.should_pause and self.should_pause())


def is_stop_requested(stop_requested: StopCallback | None) -> bool:
    return bool(stop_requested and stop_requested())


def wait_while_paused(
    *,
    pause_requested: PauseCallback | None,
    stop_requested: StopCallback | None,
    log: Callable[[str], None],
    label: str,
) -> None:
    announced = False
    while pause_requested and pause_requested():
        if stop_requested and stop_requested():
            return
        if not announced:
            log(f"{label}已暂停，点击继续后会处理下一章。")
            announced = True
        time.sleep(0.5)
