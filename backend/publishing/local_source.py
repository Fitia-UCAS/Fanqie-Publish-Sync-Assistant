from __future__ import annotations

from pathlib import Path

from backend.novel.source import ChapterBlock
from backend.novel.source import load_chapters_by_number, parse_chapter_source

Chapter = ChapterBlock


def parse_chapters(novel_file: Path) -> list[Chapter]:
    return parse_chapter_source(novel_file)


def load_local_chapters_by_number(novel_file: Path, chapters: list[int]) -> dict[int, Chapter]:
    return load_chapters_by_number(novel_file, chapters, "本地小说来源")
