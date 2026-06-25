from __future__ import annotations


from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, TypeVar

from backend.shared.text_file.text_file_storage import read_text_and_encoding
from backend.services.novel_text.text_normalizer import (
    CHAPTER_PATTERN,
    chapter_number_from_title,
    chinese_to_int,
    normalize_chapter_line_breaks,
    strip_chapter_prefix,
)


TChapter = TypeVar("TChapter", bound="ChapterBlock")


@dataclass(slots=True)
class ChapterBlock:
    index: int
    number: int
    raw_number: str
    title: str
    start: int
    header_end: int
    end: int
    text: str
    body: str

    @property
    def no(self) -> int:
        return self.number

    @property
    def subtitle(self) -> str:
        return strip_chapter_prefix(self.title)

    @property
    def content(self) -> str:
        return self.body

    @property
    def full_title(self) -> str:
        return self.title


def parse_chapter_blocks(text: str) -> list[ChapterBlock]:
    normalized = normalize_chapter_line_breaks(text or "")
    matches = _filter_progressive_matches(list(CHAPTER_PATTERN.finditer(normalized)))
    chapters: list[ChapterBlock] = []
    for index, (match, number) in enumerate(matches):
        start = match.start()
        header_end = match.end()
        end = matches[index + 1][0].start() if index + 1 < len(matches) else len(normalized)
        title = match.group(0).strip()
        text_block = normalized[start:end].strip() + "\n"
        body = normalized[header_end:end].strip()
        chapters.append(
            ChapterBlock(
                index=index,
                number=number,
                raw_number=match.group("num"),
                title=title,
                start=start,
                header_end=header_end,
                end=end,
                text=text_block,
                body=body,
            )
        )
    return chapters


def _filter_progressive_matches(matches: list) -> list[tuple]:
    accepted: list[tuple] = []
    last_number: int | None = None
    for match in matches:
        number = chinese_to_int(match.group("num"))
        if number is None:
            continue
        subtitle = strip_chapter_prefix(match.group(0))
        if _looks_like_body_reference(subtitle):
            continue
        if last_number is not None and number <= last_number:
            continue
        accepted.append((match, number))
        last_number = number
    return accepted


def _looks_like_body_reference(subtitle: str) -> bool:
    value = str(subtitle or "").lstrip()
    return bool(value) and value[0] in "，,。！？!?；;"


def parse_chapters_file(path: str | Path) -> list[ChapterBlock]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"找不到小说文件：{file_path}")
    text, _encoding = read_text_and_encoding(file_path)
    chapters = parse_chapter_blocks(text)
    if not chapters:
        raise RuntimeError("没有解析到章节标题。请确认格式类似：第1章 标题")
    return chapters


def detect_chapter_markers(text: str) -> list[tuple[int, str]]:
    markers: list[tuple[int, str]] = []
    for line_no, line in enumerate((text or "").splitlines(), start=1):
        if chapter_number_from_title(line) is not None:
            markers.append((line_no, line.strip()))
    return markers


def find_chapters_in_lines(lines: Iterable[str]) -> list[dict]:
    chapters: list[dict] = []
    for line_index, line in enumerate(lines):
        number = chapter_number_from_title(line)
        if number is not None:
            chapters.append({"index": line_index, "num": number, "title": line.strip()})
    return chapters


def chapter_text_for_write(chapters: Iterable[ChapterBlock]) -> str:
    return "\n\n".join(chapter.text.rstrip() for chapter in chapters).strip() + "\n"


def format_chapter_numbers(numbers: Iterable[int]) -> str:
    return "、".join(f"第{number}章" for number in numbers)


def duplicate_chapter_numbers(chapters: Iterable[ChapterBlock]) -> list[int]:
    counts = Counter(chapter.number for chapter in chapters)
    return sorted(number for number, count in counts.items() if count > 1)


def ensure_unique_chapter_numbers(chapters: Iterable[ChapterBlock], source_name: str = "文本") -> None:
    duplicates = duplicate_chapter_numbers(chapters)
    if duplicates:
        raise ValueError(f"{source_name}中存在重复章节：{format_chapter_numbers(duplicates)}。为避免误覆盖，已停止。")


def chapters_by_number(chapters: Iterable[TChapter], source_name: str = "文本") -> dict[int, TChapter]:
    chapter_list = list(chapters)
    ensure_unique_chapter_numbers(chapter_list, source_name)
    return {chapter.number: chapter for chapter in chapter_list}


def first_chapter_number(text: str) -> Optional[int]:
    chapters = parse_chapter_blocks(text)
    return chapters[0].number if chapters else None


