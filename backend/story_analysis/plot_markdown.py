from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.novel.chapters import Chapter
from backend.story_analysis.summaries import PlotChapterSummary
from backend.story_analysis.plot_scope import optional_bool, optional_int
from backend.text_files import read_text_auto


class ChapterRecord:
    def __init__(self, number: int, heading: str) -> None:
        self.number = number
        self.heading = heading


def extract_plot_notes_title(text: str, novel_name: str = "") -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped

    safe_name = str(novel_name or "").strip()
    if safe_name:
        return f"# 《{safe_name}》剧情"

    return "# 当前剧情"


def parse_plot_notes_markdown(text: str) -> dict[int, str]:
    summaries: dict[int, str] = {}
    pattern = re.compile(r"(?m)^\s*第\s*(\d+)\s*章\s*[，,、：:]?")
    matches = list(pattern.finditer(text or ""))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapter_number = int(match.group(1))
        block = text[start:end].strip()
        if block:
            summaries[chapter_number] = compact_plot_block(block)
    return dict(sorted(summaries.items()))


def render_plot_notes_markdown(summaries: dict[int, str], title: str = "") -> str:
    body = "\n\n".join(
        summaries[key].strip()
        for key in sorted(summaries)
        if summaries[key].strip()
    )
    safe_title = str(title or "").strip()

    if safe_title and body:
        return f"{safe_title}\n\n{body}"
    if safe_title:
        return safe_title
    return body


def render_recent_summaries(summaries: dict[int, str], chapter_number: int, recent_count: int) -> str:
    if recent_count <= 0:
        return ""
    previous_keys = [key for key in sorted(summaries) if key < chapter_number]
    selected = previous_keys[-recent_count:]
    return "\n\n".join(summaries[key] for key in selected)


def normalize_plot_summary(summary: str, chapter: Chapter | ChapterRecord) -> str:
    text = compact_plot_block(summary)
    if not text:
        return ""
    if re.match(rf"^第\s*{chapter.number}\s*章", text):
        return re.sub(rf"^第\s*{chapter.number}\s*章\s*[，,、：:]?\s*", f"第{chapter.number}章，", text, count=1)
    return f"第{chapter.number}章，{text}"


def compact_plot_block(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    return " ".join(lines).strip()


def read_optional_plot_text(path: str) -> str:
    if not path:
        return ""
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return ""
    return read_text_auto(target)


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def normalize_chapter_title(title: str, chapter_number: int | None = None) -> str:
    text = str(title or "").strip()
    if not text:
        return ""
    if chapter_number:
        text = re.sub(rf"^\s*第\s*{chapter_number}\s*章\s*", "", text)
    text = re.sub(r"^\s*第\s*\d+\s*章\s*", "", text)
    text = re.sub(r"^[，,、：:\-—\s]+", "", text).strip()
    return text


def normalize_chapter_context(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"time": "未明确", "locations": [], "characters": []}
    time = str(value.get("time") or value.get("时间") or "未明确").strip() or "未明确"
    locations = string_list(value.get("locations") or value.get("location") or value.get("地点"))
    characters = string_list(value.get("characters") or value.get("人物"))
    extra = {
        str(key): val
        for key, val in value.items()
        if key not in {"time", "时间", "locations", "location", "地点", "characters", "人物"}
    }
    return {"time": time, "locations": locations, "characters": characters, **extra}


def normalize_event_chain(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"cause": "未明确", "process": "未明确", "result": "未明确"}
    cause = str(value.get("cause") or value.get("起因") or "未明确").strip() or "未明确"
    process = str(value.get("process") or value.get("经过") or "未明确").strip() or "未明确"
    result = str(value.get("result") or value.get("结果") or "未明确").strip() or "未明确"
    extra = {
        str(key): val
        for key, val in value.items()
        if key not in {"cause", "起因", "process", "经过", "result", "结果"}
    }
    return {"cause": cause, "process": process, "result": result, **extra}


def normalize_chapter_hook(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        hook_type = str(value.get("type") or value.get("hook_type") or value.get("钩子类型") or "未明确").strip() or "未明确"
        content = str(value.get("content") or value.get("summary") or value.get("内容") or "无明确章末钩子").strip() or "无明确章末钩子"
        strength = str(value.get("strength") or value.get("hook_strength") or value.get("强度") or "medium").strip() or "medium"
        normal = optional_bool(value.get("normal_cliffhanger"), True)
        extra = {
            str(key): val
            for key, val in value.items()
            if key not in {"type", "hook_type", "钩子类型", "content", "summary", "内容", "strength", "hook_strength", "强度", "normal_cliffhanger"}
        }
        return {"type": hook_type, "content": content, "strength": strength, "normal_cliffhanger": normal, **extra}
    text = str(value or "").strip()
    if text:
        return {"type": "未明确", "content": text, "strength": "medium", "normal_cliffhanger": True}
    return {"type": "无", "content": "无明确章末钩子", "strength": "none", "normal_cliffhanger": True}


def story_thread_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        text = str(value or "").strip()
        return [{"type": "未分类", "content": text, "status": "待确认", "needs_followup": True}] if text else []

    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            content = str(item.get("content") or item.get("summary") or item.get("description") or item.get("内容") or "").strip()
            if not content:
                continue
            thread_type = str(item.get("type") or item.get("thread_type") or item.get("类型") or "未分类").strip() or "未分类"
            status = str(item.get("status") or item.get("状态") or "待推进").strip() or "待推进"
            needs_followup = optional_bool(item.get("needs_followup"), True)
            extra = {
                str(key): val
                for key, val in item.items()
                if key not in {"content", "summary", "description", "内容", "type", "thread_type", "类型", "status", "状态", "needs_followup"}
            }
            rows.append({"type": thread_type, "content": content, "status": status, "needs_followup": needs_followup, **extra})
        else:
            text = str(item or "").strip()
            if text:
                rows.append({"type": "未分类", "content": text, "status": "待推进", "needs_followup": True})
    return rows


def format_summary_digest(item: PlotChapterSummary) -> str:
    sections: list[list[str]] = []

    def add_section(title: str, rows: list[str]) -> None:
        cleaned = [str(row).strip() for row in rows if str(row).strip()]
        if not cleaned:
            return
        sections.append([f"【{title}】", *cleaned])

    if item.chapter_title:
        add_section("章节", [f"章节名：{item.chapter_title}"])

    context = item.chapter_context or {}
    context_rows: list[str] = []
    if context.get("time"):
        context_rows.append(f"时间：{context.get('time')}")
    locations = string_list(context.get("locations"))
    if locations:
        context_rows.append("地点：" + "、".join(locations))
    characters = string_list(context.get("characters"))
    if characters:
        context_rows.append("人物：" + "、".join(characters))
    add_section("章节上下文", context_rows)

    chain = item.event_chain or {}
    if chain:
        add_section(
            "事件链",
            [
                f"起因：{chain.get('cause') or '未明确'}",
                f"经过：{chain.get('process') or '未明确'}",
                f"结果：{chain.get('result') or '未明确'}",
            ],
        )

    grouped = [
        ("关键事件", item.key_events),
        ("冲突", item.conflicts),
        ("爽点/亮点", item.highlights),
        ("情绪点", item.emotional_beats),
        ("人物变化", item.character_updates),
    ]
    for title, values in grouped:
        rows = [f"- {value}" for value in values]
        add_section(title, rows)

    if item.story_threads:
        rows: list[str] = []
        for thread in item.story_threads:
            label = str(thread.get("type") or "未分类").strip() or "未分类"
            content = str(thread.get("content") or "").strip()
            status = str(thread.get("status") or "").strip()
            suffix = f"（{status}）" if status else ""
            if content:
                rows.append(f"- [{label}] {content}{suffix}")
        add_section("后续剧情线/伏笔", rows)

    hook = item.chapter_hook or {}
    content = str(hook.get("content") or "").strip()
    if content and content != "无明确章末钩子":
        hook_type = str(hook.get("type") or "未明确").strip() or "未明确"
        strength = str(hook.get("strength") or "medium").strip() or "medium"
        normal = "是" if optional_bool(hook.get("normal_cliffhanger"), True) else "否"
        add_section(
            "章末钩子",
            [f"类型：{hook_type}", f"内容：{content}", f"强度：{strength}", f"正常钩子：{normal}"],
        )

    if item.unclear_fields:
        add_section("待前后文确认", [f"- {field}" for field in item.unclear_fields])

    return "\n\n".join("\n".join(section) for section in sections).strip()


def plot_notes_note_level(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "info"

    benign_keywords = (
        "章末钩子完整",
        "承接正确",
        "承接一致",
        "自然承接",
        "无需修正",
        "不是问题",
        "不影响剧情连贯",
        "正常章末",
        "正常钩子",
        "留下悬念",
        "留下钩子",
        "断句钩",
        "normal_cliffhanger",
    )
    if any(keyword in value for keyword in benign_keywords):
        return "info"

    suspicious_keywords = (
        "疑似截断",
        "明显截断",
        "正文不完整",
        "章节不完整",
        "缺失",
        "乱码",
        "标题与内容不匹配",
        "章号",
        "重复",
        "矛盾",
        "建议",
        "需要",
        "无法判断",
        "不符",
    )
    if any(keyword in value for keyword in suspicious_keywords):
        return "warning"

    return "info"
