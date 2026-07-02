from __future__ import annotations

from backend.tasks.events import TaskEvent, event_type_for_label, split_log_label


def test_task_event_splits_two_character_label_from_message() -> None:
    event = TaskEvent.from_log_message("web_crawler", "限流：第 191 章｜HTTP 429，退避 11 秒", "warn")

    assert event.label == "限流"
    assert event.message == "第 191 章｜HTTP 429，退避 11 秒"
    assert event.event_type == "rate_limited"
    assert event.display_message() == "限流：第 191 章｜HTTP 429，退避 11 秒"


def test_task_event_progress_payload_uses_structured_values() -> None:
    event = TaskEvent.progress("web_crawler", 590, 996)
    payload = event.to_dict()

    assert payload["label"] == "进度"
    assert payload["eventType"] == "progress"
    assert payload["payload"] == {"progress": {"current": 590, "total": 996}}
    assert payload["displayMessage"] == "进度：590/996｜59%"


def test_unknown_log_message_uses_information_label() -> None:
    label, detail = split_log_label("任务正在运行")

    assert label == "信息"
    assert detail == "任务正在运行"
    assert event_type_for_label(label) == "log"
