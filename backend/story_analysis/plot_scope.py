from __future__ import annotations

from typing import Any

from backend.novel.chapters import Chapter


MODE_SERIAL = "serial"
MODE_EXTRACT_MERGE = "extract_merge"
MODE_FAST_PREVIEW = "fast_preview"
SUPPORTED_MODES = {MODE_SERIAL, MODE_EXTRACT_MERGE, MODE_FAST_PREVIEW}

SCOPE_SINGLE = "single"
SCOPE_AROUND = "around"
SCOPE_RANGE = "range"
SCOPE_ALL = "all"


def select_plot_chapters(
    chapters: list[Chapter],
    *,
    scope: str,
    chapter: int | None,
    around_chapter: int | None,
    start: int | None,
    end: int | None,
    all_chapters: bool,
) -> list[Chapter]:
    if scope == SCOPE_SINGLE:
        target = chapter or start or chapters[0].number
        return [item for item in chapters if item.number == target]

    if scope == SCOPE_AROUND:
        target = around_chapter or chapter or start or chapters[0].number
        return [item for item in chapters if target - 1 <= item.number <= target + 1]

    if scope == SCOPE_RANGE:
        safe_start = start or chapters[0].number
        safe_end = end if end is not None else chapters[-1].number
        low, high = min(safe_start, safe_end), max(safe_start, safe_end)
        return [item for item in chapters if low <= item.number <= high]

    if all_chapters or scope == SCOPE_ALL:
        return chapters

    if chapter:
        return [item for item in chapters if item.number == chapter]

    if around_chapter:
        return [item for item in chapters if around_chapter - 1 <= item.number <= around_chapter + 1]

    if start or end:
        safe_start = start or chapters[0].number
        safe_end = end if end is not None else chapters[-1].number
        low, high = min(safe_start, safe_end), max(safe_start, safe_end)
        return [item for item in chapters if low <= item.number <= high]

    return []


def optional_int(value: object) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except Exception:
        return None


def optional_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "checked", "是", "真", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "unchecked", "否", "假", "关闭"}:
        return False
    return default


def normalize_plot_mode(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "strict": MODE_SERIAL,
        "serial": MODE_SERIAL,
        "串行逐章总结": MODE_SERIAL,
        "逐章精修": MODE_SERIAL,
        "hybrid": MODE_EXTRACT_MERGE,
        "extract_merge": MODE_EXTRACT_MERGE,
        "并发单章提取 + 串行合并": MODE_EXTRACT_MERGE,
        "并发合并": MODE_EXTRACT_MERGE,
        "fast": MODE_FAST_PREVIEW,
        "fast_preview": MODE_FAST_PREVIEW,
        "全部并发后一次总合并": MODE_FAST_PREVIEW,
        "快速预览": MODE_FAST_PREVIEW,
    }
    mode = aliases.get(text, text or MODE_EXTRACT_MERGE)
    if mode not in SUPPORTED_MODES:
        return MODE_EXTRACT_MERGE
    return mode


def normalize_plot_scope(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "single": SCOPE_SINGLE,
        "单章": SCOPE_SINGLE,
        "around": SCOPE_AROUND,
        "前后章": SCOPE_AROUND,
        "range": SCOPE_RANGE,
        "范围章节": SCOPE_RANGE,
        "all": SCOPE_ALL,
        "全部章节": SCOPE_ALL,
    }
    return aliases.get(text, text or SCOPE_RANGE)


def plot_mode_label(mode: str) -> str:
    return {
        MODE_SERIAL: "逐章精修｜慢｜最高准确度｜正式更新",
        MODE_EXTRACT_MERGE: "并发合并｜中快｜很高准确度｜推荐",
        MODE_FAST_PREVIEW: "快速预览｜快｜中等准确度｜预览",
    }.get(mode, mode)


def default_plot_output_name(start: int, end: int) -> str:
    return f"当前剧情_第{start}-{end}章.md" if start != end else f"当前剧情_第{start}章.md"


def default_plot_debug_name(start: int, end: int, mode: str) -> str:
    name = f"plot_notes_debug_{start}_{end}_{mode}.jsonl" if start != end else f"plot_notes_debug_{start}_{mode}.jsonl"
    return safe_filename(name)
