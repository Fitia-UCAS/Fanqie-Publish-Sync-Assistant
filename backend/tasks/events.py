from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from backend.json_files import JsonValue, to_json_safe


@dataclass(slots=True, frozen=True)
class TaskEvent:
    page: str
    label: str
    message: str
    level: str = "info"
    event_type: str = "log"
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_log_message(cls, page: str, message: str, level: str = "info") -> "TaskEvent":
        label, detail = split_log_label(message)
        return cls(page=page, label=label, message=detail, level=level, event_type=event_type_for_label(label))

    @classmethod
    def progress(cls, page: str, current: float, total: float) -> "TaskEvent":
        return cls(
            page=page,
            label="进度",
            message=format_progress_message(current, total),
            level="info",
            event_type="progress",
            payload={"progress": {"current": current, "total": total}},
        )

    def display_message(self) -> str:
        if not self.label:
            return self.message
        if not self.message:
            return self.label
        return f"{self.label}：{self.message}"

    def to_dict(self) -> dict[str, JsonValue]:
        return to_json_safe(
            {
                "page": self.page,
                "label": self.label,
                "message": self.message,
                "level": self.level,
                "eventType": self.event_type,
                "payload": self.payload,
                "timestamp": self.timestamp,
                "displayMessage": self.display_message(),
            }
        )


def split_log_label(message: str) -> tuple[str, str]:
    text = str(message or "").strip()
    if "：" not in text:
        return "信息", text
    label, detail = text.split("：", 1)
    label = label.strip() or "信息"
    return label[:4], detail.strip()


def event_type_for_label(label: str) -> str:
    return {
        "阶段": "stage",
        "进度": "progress",
        "抓取": "chapter_fetched",
        "写入": "chapter_written",
        "限流": "rate_limited",
        "补抓": "retry",
        "完成": "completed",
        "停止": "stopped",
        "失败": "failed",
        "错误": "error",
        "目录": "catalog",
        "检测": "scan",
        "缺章": "missing",
    }.get(label, "log")


def format_progress_message(current: float, total: float) -> str:
    total_value = max(0.0, float(total or 0))
    current_value = max(0.0, float(current or 0))
    percent = 0 if total_value <= 0 else round(max(0.0, min(100.0, current_value * 100 / total_value)))
    return f"{int(current_value)}/{int(total_value)}｜{percent}%"
