from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Locator, Page


@dataclass(slots=True)
class RemoteChapterEditor:

    page: Page
    chapter_no_loc: Locator
    title_loc: Locator
    body_loc: Locator
    created: bool = True
    opened_new_page: bool = False


__all__ = ["RemoteChapterEditor"]


import re
from datetime import date, datetime, timedelta
from typing import Iterable


@dataclass(slots=True, frozen=True)
class ScheduledPublishSlot:
    chapter_no: int
    date: str
    time: str


def build_schedule_slots(
    chapters: Iterable[int],
    *,
    enabled: bool = False,
    start_date: str = "",
    morning_time: str = "10:00",
    morning_count: int = 1,
    afternoon_time: str = "18:00",
    afternoon_count: int = 0,
) -> dict[int, ScheduledPublishSlot]:
    if not enabled:
        return {}
    chapter_numbers = list(chapters)
    if not chapter_numbers:
        return {}
    morning_count = max(0, int(morning_count or 0))
    afternoon_count = max(0, int(afternoon_count or 0))
    if morning_count <= 0 and afternoon_count <= 0:
        morning_count = 1
    start = _parse_schedule_date(start_date) or date.today()
    morning = _normalize_schedule_time(morning_time, fallback="10:00")
    afternoon = _normalize_schedule_time(afternoon_time, fallback="18:00")
    times = [morning] * morning_count + [afternoon] * afternoon_count or [morning]
    slots: dict[int, ScheduledPublishSlot] = {}
    current_day = start
    for index, chapter_no in enumerate(chapter_numbers):
        if index > 0 and index % len(times) == 0:
            current_day += timedelta(days=1)
        slots[chapter_no] = ScheduledPublishSlot(chapter_no=chapter_no, date=current_day.isoformat(), time=times[index % len(times)])
    return slots


def describe_schedule_slots(slots: dict[int, ScheduledPublishSlot]) -> str:
    if not slots:
        return ""
    values = list(slots.values())
    first = values[0]
    last = values[-1]
    if len(values) == 1:
        return f"手动定时：第 {first.chapter_no} 章 → {first.date} {first.time}"
    return f"手动定时：第 {first.chapter_no} 章 → {first.date} {first.time}；第 {last.chapter_no} 章 → {last.date} {last.time}"


def _parse_schedule_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _normalize_schedule_time(value: str, *, fallback: str) -> str:
    raw = str(value or "").strip()
    match = re.match(r"^(\d{1,2}):(\d{1,2})$", raw)
    if not match:
        return fallback
    hour = max(0, min(23, int(match.group(1))))
    minute = max(0, min(59, int(match.group(2))))
    return f"{hour:02d}:{minute:02d}"


__all__ = ["RemoteChapterEditor", "ScheduledPublishSlot", "build_schedule_slots", "describe_schedule_slots"]
