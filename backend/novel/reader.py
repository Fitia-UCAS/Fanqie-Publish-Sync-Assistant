from __future__ import annotations


import re
from pathlib import Path

from backend.errors import ChapterParseError
from backend.text_files import normalize_newlines
from backend.novel.chapters import Chapter
from backend.text_files import read_text_auto

CHAPTER_HEADING_RE = re.compile(r"^\s*第\s*([0-9０-９零〇一二两三四五六七八九十百千万]+)\s*章\s*[:：、.．\-—_ ]*\s*(.*?)\s*$")
CHINESE_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CHINESE_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}
FULL_WIDTH_TRANSLATION = str.maketrans("０１２３４５６７８９", "0123456789")


def parse_chapter_number(raw_number: str) -> int:
    text = str(raw_number).strip().translate(FULL_WIDTH_TRANSLATION)
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in CHINESE_DIGITS:
            number = CHINESE_DIGITS[char]
        elif char in CHINESE_UNITS:
            unit = CHINESE_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            raise ChapterParseError(f"无法识别章节号：{raw_number}")
    return total + section + number


def parse_chapters(text: str) -> list[Chapter]:
    lines = normalize_newlines(text).split("\n")
    candidate_headings: list[tuple[int, int, str, str]] = []
    for index, line in enumerate(lines):
        match = CHAPTER_HEADING_RE.match(line)
        if not match:
            continue
        title = match.group(2).strip()
        if _looks_like_body_reference(title):
            continue
        number = parse_chapter_number(match.group(1))
        candidate_headings.append((index, number, title, line.strip()))

    headings = _filter_progressive_headings(candidate_headings)
    if not headings:
        raise ChapterParseError("没有识别到章节标题，请确认文本中存在“第N章 标题”。")

    chapters: list[Chapter] = []
    for position, (line_index, number, title, raw_heading) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_index + 1:next_index]).strip()
        chapters.append(Chapter(number=number, title=title, body=body, raw_heading=raw_heading))
    return chapters


def _looks_like_body_reference(title: str) -> bool:
    stripped = str(title or "").lstrip()
    return bool(stripped) and stripped[0] in "，,。！？!?；;"


def _filter_progressive_headings(headings: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    accepted: list[tuple[int, int, str, str]] = []
    for heading in headings:
        _line_index, number, _title, _raw_heading = heading
        if accepted and number <= accepted[-1][1]:
            continue
        accepted.append(heading)
    return accepted


def read_chapters(file_path: str | Path | None) -> list[Chapter]:
    raw_path = str(file_path or "").strip()
    if not raw_path:
        raise ChapterParseError("请先选择小说 TXT 文件。")
    path = Path(raw_path)
    if path.is_dir():
        raise ChapterParseError(f"请选择 TXT 文件，不是文件夹：{path}")
    if not path.exists():
        raise ChapterParseError(f"文件不存在：{path}")
    text = read_text_auto(path)
    return parse_chapters(text)


def chapters_to_preview(chapters: list[Chapter]) -> list[dict[str, object]]:
    return [chapter.to_preview() for chapter in chapters]


def select_chapters(chapters: list[Chapter], start: int, end: int) -> list[Chapter]:
    safe_start, safe_end = min(start, end), max(start, end)
    return [chapter for chapter in chapters if safe_start <= chapter.number <= safe_end]


