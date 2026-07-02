from __future__ import annotations

from typing import Callable

from backend.crawling.records import ChapterContent, ChapterLink
from backend.crawling.txt_writer import IncrementalNovelTxtWriter


class OrderedChapterWriteBuffer:

    def __init__(
        self,
        writer: IncrementalNovelTxtWriter,
        chapters: list[ChapterLink],
        has_content: Callable[[ChapterContent | None], bool],
        on_write: Callable[[int], None] | None = None,
    ) -> None:
        self.writer = writer
        self._chapter_order = [chapter.index for chapter in chapters]
        self._pending_chapters: dict[int, ChapterContent] = {}
        self._cursor = 0
        self._has_content = has_content
        self._on_write = on_write
        self.writer.start()

    def add_fetched_chapter(self, chapter: ChapterContent) -> list[int]:
        if self._has_content(chapter):
            self._pending_chapters[chapter.index] = chapter
        return self.flush_ready_chapters()

    def finalize(self, fetched_by_index: dict[int, ChapterContent]) -> list[int]:
        written: list[int] = []
        while self._cursor < len(self._chapter_order):
            chapter_index = self._chapter_order[self._cursor]
            chapter = fetched_by_index.get(chapter_index)
            if chapter is not None and self._has_content(chapter):
                self._pending_chapters[chapter_index] = chapter
                written.extend(self.flush_ready_chapters())
                continue
            self._cursor += 1
            written.extend(self.flush_ready_chapters())
        return written

    def flush_ready_chapters(self) -> list[int]:
        written: list[int] = []
        while self._cursor < len(self._chapter_order):
            chapter_index = self._chapter_order[self._cursor]
            chapter = self._pending_chapters.get(chapter_index)
            if chapter is None:
                break
            if self.writer.append_chapter(chapter):
                written.append(chapter_index)
                if self._on_write:
                    self._on_write(chapter_index)
            self._pending_chapters.pop(chapter_index, None)
            self._cursor += 1
        return written
