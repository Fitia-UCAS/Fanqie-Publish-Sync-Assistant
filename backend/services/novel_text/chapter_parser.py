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
    normalize_chapter_title_line,
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
    source_path: Path | None = None

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
        title = normalize_chapter_title_line(match.group(0).strip(), fallback_number=number)
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
    for chapter in chapters:
        chapter.source_path = file_path
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



import re
from dataclasses import dataclass

SUPPORTED_CHAPTER_SOURCE_SUFFIXES = {".txt", ".md"}


@dataclass(slots=True)
class ChapterSourceSummary:
    source_path: Path
    source_kind: str
    chapters: list[ChapterBlock]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


def parse_chapter_source(source: str | Path) -> list[ChapterBlock]:
    return read_chapter_source(source).chapters


def read_chapter_source(source: str | Path) -> ChapterSourceSummary:
    paths = split_chapter_source_paths(source)
    if len(paths) > 1:
        chapters: list[ChapterBlock] = []
        for item in paths:
            chapters.extend(read_chapter_source(item).chapters)
        if not chapters:
            raise RuntimeError("没有从已选小说来源中识别到章节。")
        return ChapterSourceSummary(source_path=paths[0], source_kind="multi", chapters=chapters)

    source_path = paths[0] if paths else Path(str(source or ""))
    if not source_path.exists():
        raise FileNotFoundError(f"找不到小说来源：{source_path}")
    if source_path.is_dir():
        chapters = _parse_chapter_folder(source_path)
        if not chapters:
            raise RuntimeError("文件夹中没有识别到章节文件。支持 .txt / .md。")
        return ChapterSourceSummary(source_path=source_path, source_kind="folder", chapters=chapters)
    if source_path.suffix.lower() not in SUPPORTED_CHAPTER_SOURCE_SUFFIXES:
        raise RuntimeError("请选择 TXT / Markdown 文件，或包含章节文件的文件夹。")
    chapters = parse_chapters_file(source_path)
    return ChapterSourceSummary(source_path=source_path, source_kind="file", chapters=chapters)


def split_chapter_source_paths(source: str | Path) -> list[Path]:
    if isinstance(source, Path):
        return [source]
    raw = str(source or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n") if part.strip()]
    return [Path(part).expanduser() for part in parts]


def is_multi_chapter_source(source: str | Path) -> bool:
    return len(split_chapter_source_paths(source)) > 1


def load_chapters_by_number(source: str | Path, chapters: Iterable[int], source_name: str = "本地来源") -> dict[int, ChapterBlock]:
    wanted = list(chapters)
    by_number = chapters_by_number(parse_chapter_source(source), source_name)
    missing = [no for no in wanted if no not in by_number]
    if missing:
        raise RuntimeError(f"{source_name}中没有找到章节：{', '.join(str(no) for no in missing)}")
    return {no: by_number[no] for no in wanted}


def _parse_chapter_folder(folder: Path) -> list[ChapterBlock]:
    scan_dir = folder / "chapters" if (folder / "chapters").is_dir() else folder
    files = [path for path in scan_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_CHAPTER_SOURCE_SUFFIXES]
    found: list[ChapterBlock] = []
    for path in sorted(files, key=_chapter_file_sort_key):
        found.extend(_parse_single_chapter_file(path))
    return sorted(found, key=lambda chapter: (chapter.number, str(chapter.source_path or "")))


def _parse_single_chapter_file(path: Path) -> list[ChapterBlock]:
    text, _encoding = read_text_and_encoding(path)
    blocks = parse_chapter_blocks(text)
    if blocks:
        for block in blocks:
            block.source_path = path
        return blocks
    number = _chapter_number_from_filename(path)
    if number is None:
        return []
    title = _title_from_filename(path, number=number) or _title_from_first_heading(text) or f"第{number}章"
    title_line = normalize_chapter_title_line(title, fallback_number=number)
    body = _strip_leading_title_line(text, title_line=title_line)
    full_text = f"{title_line}\n\n{body.strip()}\n"
    return [
        ChapterBlock(
            index=0,
            number=number,
            raw_number=str(number),
            title=title_line,
            start=0,
            header_end=len(title_line),
            end=len(full_text),
            text=full_text,
            body=body.strip(),
            source_path=path,
        )
    ]


def _chapter_file_sort_key(path: Path) -> tuple[int, str]:
    number = _chapter_number_from_filename(path)
    return (number if number is not None else 10**9, path.name.lower())


def _chapter_number_from_filename(path: Path) -> int | None:
    name = path.stem.strip()
    patterns = [
        r"第\s*([0-9０-９零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+)\s*章",
        r"(?:^|[_\-\s])ch(?:apter)?\s*([0-9]+)(?:$|[_\-\s])",
        r"(?:^|[_\-\s])chapter\s*([0-9]+)(?:$|[_\-\s])",
        r"(?:^|[_\-\s])([0-9]{1,5})(?:$|[_\-\s])",
        r"([0-9]{1,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, name, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        if value.isdigit():
            return int(value)
        parsed = chinese_to_int(value)
        if parsed is not None:
            return parsed
    return None


def _title_from_filename(path: Path, *, number: int) -> str:
    title = path.stem.strip()
    title = re.sub(r"^\s*第\s*[0-9０-９零〇一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+\s*章\s*", "", title)
    title = re.sub(r"^\s*(?:ch(?:apter)?|chapter)?\s*0*%d\s*" % number, "", title, flags=re.IGNORECASE)
    title = re.sub(r"^[\s_\-—.．、:：]+", "", title).strip()
    return f"第{number}章 {title}" if title else f"第{number}章"


def _title_from_first_heading(text: str) -> str:
    for line in (text or "").splitlines():
        value = line.strip()
        if not value:
            continue
        value = re.sub(r"^#{1,6}\s*", "", value).strip()
        return value[:80]
    return ""


def _strip_leading_title_line(text: str, *, title_line: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ""
    first = re.sub(r"^#{1,6}\s*", "", lines[0].strip()).strip()
    title_compact = re.sub(r"\s+", "", strip_chapter_prefix(title_line) or title_line)
    first_compact = re.sub(r"\s+", "", strip_chapter_prefix(first) or first)
    if first_compact and (first_compact == title_compact or title_compact in first_compact or first_compact in title_compact):
        lines.pop(0)
    return "\n".join(lines).strip()
