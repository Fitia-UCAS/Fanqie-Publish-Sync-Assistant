from __future__ import annotations


import json
import re
from typing import Any

from backend.log_setup import get_logger
from backend.json_files import to_json_safe
from backend.tasks.events import TaskEvent

LOGGER = get_logger(__name__)


class FrontendBridge:
    def __init__(self) -> None:
        self._window: Any | None = None

    def bind_window(self, window: Any) -> None:
        self._window = window

    def emit_log(self, page: str, message: str, level: str = "info") -> None:
        text = str(message or "").strip()
        if self._should_suppress_ui_log(page, text):
            return
        self.emit_event(TaskEvent.from_log_message(page, text, level))

    def emit_event(self, event: TaskEvent) -> None:
        payload = event.to_dict()
        self.evaluate_js(
            "window.NovelTools && (window.NovelTools.applyTaskEvent ? window.NovelTools.applyTaskEvent(%s) : window.NovelTools.appendLog(%s, %s, %s));"
            % (
                json.dumps(payload, ensure_ascii=False),
                json.dumps(event.page),
                json.dumps(event.display_message(), ensure_ascii=False),
                json.dumps(event.level),
            )
        )

    def emit_progress(self, page: str, current: float, total: float) -> None:
        self.evaluate_js(
            "window.NovelTools && window.NovelTools.setProgress(%s, %s, %s);"
            % (json.dumps(page), float(current), float(total))
        )
        self.emit_event(TaskEvent.progress(page, current, total))

    def emit_done(self, page: str, ok: bool, result: dict[str, Any]) -> None:
        safe_result = to_json_safe(result)
        self.evaluate_js(
            "window.NovelTools && window.NovelTools.taskDone(%s, %s, %s);"
            % (json.dumps(page), json.dumps(ok), json.dumps(safe_result, ensure_ascii=False))
        )

    def evaluate_js(self, script: str) -> None:
        if self._window is None:
            return
        try:
            self._window.evaluate_js(script)
        except Exception:
            LOGGER.debug("evaluate_js failed", exc_info=True)

    @staticmethod
    def _should_suppress_ui_log(page: str, message: str) -> bool:
        if page != "web_crawler":
            return False

        return bool(re.match(r"^完成：第\s*\d+\s*章", message))


