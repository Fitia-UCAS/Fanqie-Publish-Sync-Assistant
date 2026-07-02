

from __future__ import annotations


import re
from typing import Optional

SEPARATOR_LINE = "==============="
CHAPTER_NUM_FRAGMENT = r"\d+|[零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+"
CHAPTER_PATTERN = re.compile(
    rf"(?m)^[ \t　]*(?:#{{1,6}}\s*)?第\s*(?P<num>{CHAPTER_NUM_FRAGMENT})\s*章(?![的中内外里节回项条])[^\r\n]*"
)
INLINE_CHAPTER_PATTERN = re.compile(
    rf"第\s*(?P<num>{CHAPTER_NUM_FRAGMENT})\s*章(?![的中内外里节回项条])"
)
CHAPTER_TITLE_PATTERN = re.compile(
    rf"^(?:#{{1,6}}\s*)?第\s*(?P<num>{CHAPTER_NUM_FRAGMENT})\s*章(?![的中内外里节回项条])[ \t]*(?P<title>.*?)\s*$",
    re.MULTILINE,
)
CHAPTER_PREFIX_PATTERN = re.compile(
    rf"^(?:#{{1,6}}\s*)?第\s*({CHAPTER_NUM_FRAGMENT})\s*章(?![的中内外里节回项条])[ \t]*"
)
CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "壹": 1,
    "二": 2,
    "贰": 2,
    "两": 2,
    "三": 3,
    "叁": 3,
    "四": 4,
    "肆": 4,
    "五": 5,
    "伍": 5,
    "六": 6,
    "陆": 6,
    "七": 7,
    "柒": 7,
    "八": 8,
    "捌": 8,
    "九": 9,
    "玖": 9,
}
CN_UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000, "万": 10000}


def normalize_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in s.split("\n")]
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


def normalize_chapter_line_breaks(text: str) -> str:
    if not text:
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    split_before_chars = set(" \t　。！？!?；;，,、：:…）)]】》」』”\"'")

    def _split(match: re.Match[str]) -> str:
        start = match.start()
        if start == 0 or normalized[start - 1] == "\n":
            return match.group(0)
        line_start = normalized.rfind("\n", 0, start) + 1
        prefix = normalized[line_start:start]
        if re.match(r"^[ \t　]*#{1,6}\s*$", prefix) or CHAPTER_PATTERN.match(prefix):
            return match.group(0)
        previous_char = normalized[start - 1]
        if previous_char in split_before_chars or previous_char.isspace():
            return "\n" + match.group(0)
        return match.group(0)

    return INLINE_CHAPTER_PATTERN.sub(_split, normalized)


def normalized_lines(text_or_lines: str | list[str]) -> list[str]:
    if isinstance(text_or_lines, str):
        return normalize_chapter_line_breaks(text_or_lines).splitlines(keepends=True)
    return normalize_chapter_line_breaks("".join(text_or_lines)).splitlines(keepends=True)


def chinese_to_int(text: str) -> Optional[int]:
    value = (text or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    total = 0
    section = 0
    number = 0
    has_valid_char = False
    for char in value:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
            has_valid_char = True
            continue
        if char in CN_UNITS:
            unit = CN_UNITS[char]
            has_valid_char = True
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                if number == 0:
                    number = 1
                section += number * unit
            number = 0
            continue
        return None
    if not has_valid_char:
        return None
    return total + section + number


def chapter_number_from_title(line: str) -> Optional[int]:
    value = line.strip()
    match = CHAPTER_PATTERN.match(value)
    if not match:
        return None
    subtitle = CHAPTER_PREFIX_PATTERN.sub("", value).strip()
    if _looks_like_body_reference(subtitle):
        return None
    return chinese_to_int(match.group("num"))


def _looks_like_body_reference(subtitle: str) -> bool:
    value = str(subtitle or "").lstrip()
    return bool(value) and value[0] in "，,。！？!?；;"


def normalize_chapter_title_line(line: str, fallback_number: Optional[int] = None) -> str:
    value = (line or "").strip()
    match = CHAPTER_TITLE_PATTERN.match(value)
    if match:
        number = chinese_to_int(match.group("num"))
        if number is not None:
            subtitle = (match.group("title") or "").strip().lstrip("：:　 ")
            return f"第{number}章" + (f" {subtitle}" if subtitle else "")
    if fallback_number is not None and value:
        return f"第{fallback_number}章 {value}"
    if fallback_number is not None:
        return f"第{fallback_number}章"
    return value

def strip_chapter_prefix(title: str) -> str:
    return CHAPTER_PREFIX_PATTERN.sub("", (title or "").strip()).strip()


def split_lines(text_or_lines: str | list[str]) -> list[str]:
    return normalized_lines(text_or_lines)


def remove_separator_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() != SEPARATOR_LINE]


def clean_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        stripped_left = line.lstrip()
        if stripped_left.strip() == "":
            continue
        cleaned.append(stripped_left.rstrip() + "\n")
    return cleaned


def build_formatted_novel_lines(text_or_lines: str | list[str], use_separator: bool = False) -> list[str]:
    lines = remove_separator_lines(split_lines(text_or_lines))
    lines = clean_lines(lines)
    formatted: list[str] = []
    for line in lines:
        stripped = line.strip()
        is_chapter = chapter_number_from_title(stripped) is not None
        if is_chapter:
            stripped = normalize_chapter_title_line(stripped)
            if formatted and formatted[-1].strip():
                formatted.append("\n")
            if use_separator:
                formatted.append(SEPARATOR_LINE + "\n")
            formatted.append(stripped + "\n")
            if use_separator:
                formatted.append(SEPARATOR_LINE + "\n")
            formatted.append("\n")
            continue
        formatted.append(stripped + "\n")
    while formatted and not formatted[-1].strip():
        formatted.pop()
    if formatted and not formatted[-1].endswith("\n"):
        formatted[-1] += "\n"
    return formatted


def format_novel_text(text: str, use_separator: bool = False) -> str:
    return "".join(build_formatted_novel_lines(text, use_separator=use_separator))


def normalize_novel_body(s: str) -> str:
    formatted = format_novel_text(s or "", use_separator=False)
    return "\n".join(line.strip() for line in formatted.split("\n") if line.strip())


def compact_text(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def same_text(a: str, b: str) -> bool:
    return normalize_novel_body(a) == normalize_novel_body(b)


