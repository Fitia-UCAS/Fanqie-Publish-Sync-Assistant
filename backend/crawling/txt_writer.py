from __future__ import annotations

from pathlib import Path

from backend.crawling.clean import clean_title
from backend.novel.text_cleaning import normalize_chapter_title_line
from backend.crawling.records import ChapterContent, NovelCatalog
from backend.novel.text_cleaning import chapter_number_from_title
from backend.novel.source import ChapterBlock, parse_chapter_blocks
from backend.text_files import ensure_dir, read_text_auto, write_text

CHAPTER_TITLE_PREFIXES = ("序", "楔子", "番外", "后记", "终章")


def build_chapter_heading(chapter: ChapterContent) -> str:
    title = clean_title(chapter.title)
    normalized = normalize_chapter_title_line(title)
    if chapter_number_from_title(normalized) is not None:
        return normalized
    if title.startswith(CHAPTER_TITLE_PREFIXES):
        return title
    return f"第{chapter.index}章 {title}" if title else f"第{chapter.index}章"


def build_txt_header(catalog: NovelCatalog) -> str:
    blocks = [
        f"书名：{catalog.title}",
        f"小说 ID：{catalog.novel_id}",
        f"来源：{catalog.url}",
        "=" * 60,
        "",
    ]
    return "\n".join(blocks)


def build_chapter_block(chapter: ChapterContent) -> str:
    if not chapter.ok or not chapter.content.strip():
        return ""
    return "\n".join(
        [
            build_chapter_heading(chapter),
            "",
            chapter.content.strip(),
            "",
        ]
    )


def build_txt(catalog: NovelCatalog, chapters: list[ChapterContent]) -> str:
    blocks = [build_txt_header(catalog)]
    for chapter in sorted(chapters, key=_chapter_content_index):
        block = build_chapter_block(chapter)
        if block:
            blocks.append(block)
    return "\n".join(blocks).rstrip() + "\n"


def write_novel_txt(path: Path, catalog: NovelCatalog, chapters: list[ChapterContent]) -> Path:
    return write_text(path, build_txt(catalog, chapters))


class IncrementalNovelTxtWriter:

    def __init__(self, path: Path, catalog: NovelCatalog) -> None:
        self.path = Path(path)
        self.catalog = catalog
        self._started = False
        self._chapters = self._read_existing_chapters()
        self._written_indexes: set[int] = set()

    def start(self) -> Path:
        ensure_dir(self.path.parent)
        if not self.path.exists():
            self._rewrite_all()
        self._started = True
        return self.path

    def append_chapter(self, chapter: ChapterContent) -> bool:
        if not chapter.ok or not chapter.content.strip() or chapter.index in self._chapters:
            return False
        if not self._started:
            self.start()
        self._chapters[chapter.index] = chapter
        self._rewrite_all()
        self._written_indexes.add(chapter.index)
        return True

    @property
    def written_indexes(self) -> set[int]:
        return set(self._written_indexes)

    @property
    def existing_indexes(self) -> set[int]:
        return {index for index in self._chapters if index not in self._written_indexes}

    @property
    def chapter_indexes(self) -> set[int]:
        return set(self._chapters)

    @property
    def existing_chapter_count(self) -> int:
        return len(self.existing_indexes)

    def existing_chapter_count_in(self, chapter_indexes: set[int]) -> int:
        return len(self.existing_indexes.intersection(chapter_indexes))

    def _read_existing_chapters(self) -> dict[int, ChapterContent]:
        if not self.path.exists() or self.path.is_dir():
            return {}
        try:
            blocks = parse_chapter_blocks(read_text_auto(self.path))
        except Exception:
            return {}
        chapters: dict[int, ChapterContent] = {}
        for block in blocks:
            chapter = _chapter_content_from_block(block)
            if chapter and chapter.index not in chapters:
                chapters[chapter.index] = chapter
        return chapters

    def _rewrite_all(self) -> Path:
        ensure_dir(self.path.parent)
        text = build_txt(self.catalog, list(self._chapters.values()))
        temp_path = self.path.with_name(self.path.name + ".tmp")
        temp_path.write_text(text, encoding="utf-8", newline="")
        temp_path.replace(self.path)
        return self.path


def _chapter_content_from_block(block: ChapterBlock) -> ChapterContent | None:
    body = (block.body or "").strip()
    if not body:
        return None
    title = normalize_chapter_title_line(block.title, block.number)
    return ChapterContent(
        index=block.number,
        title=title,
        content=body,
        url="",
        source="existing_txt",
        ok=True,
        error="",
    )


def _chapter_content_index(chapter: ChapterContent) -> int:
    return chapter.index
