from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Callable

from backend.crawling.records import ChapterContent, ChapterLink, CrawlErrorType, NovelCatalog, ProgressSnapshot
from backend.crawling.sites import NovelSiteAdapter

LogFn = Callable[[str, str], None]
ProgressFn = Callable[[int, int], None]
StopFn = Callable[[], bool]
ChapterFetchedCallback = Callable[[ChapterContent], list[int]]
ChapterWrittenCallback = Callable[[list[int]], None]

SUMMARY_CHAPTER_STEP = 50
SUMMARY_SECONDS = 8.0
RATE_LIMIT_ERROR_MARKERS = ("站点拒绝访问", "HTTP 429", "HTTP 403", "HTTP 444", "限速器退避")


@dataclass(slots=True)
class ChapterRunCounters:

    completed: int = 0
    fetched: int = 0
    failed: int = 0
    limited: int = 0

    def snapshot(self, total: int) -> ProgressSnapshot:
        return ProgressSnapshot(
            done=self.completed,
            total=total,
            fetched=self.fetched,
            failed=self.failed,
            limited=self.limited,
        )


class ChapterCrawlRunner:

    def __init__(
        self,
        *,
        adapter: NovelSiteAdapter,
        catalog: NovelCatalog,
        chapters: list[ChapterLink],
        max_workers: int,
        log: LogFn,
        progress: ProgressFn,
        stop_requested: StopFn,
        detailed_log: bool,
        on_fetched_chapter: ChapterFetchedCallback | None = None,
        log_written_chapters: ChapterWrittenCallback | None = None,
        update_progress: bool = True,
    ) -> None:
        self.adapter = adapter
        self.catalog = catalog
        self.chapters = chapters
        self.max_workers = max(1, max_workers)
        self.log = log
        self.progress = progress
        self.stop_requested = stop_requested
        self.detailed_log = detailed_log
        self.on_fetched_chapter = on_fetched_chapter
        self.log_written_chapters = log_written_chapters
        self.update_progress = update_progress
        self.counters = ChapterRunCounters()
        self._last_summary_at = time.monotonic()
        self._last_summary_done = 0

    def crawl(self) -> list[ChapterContent]:
        results: list[ChapterContent] = []
        workers = min(self.max_workers, len(self.chapters))
        if workers <= 0:
            return results
        chapter_iter = iter(self.chapters)
        future_map: dict[Future, ChapterLink] = {}
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="crawl-novel")
        try:
            for _worker_index in range(workers):
                self._submit_next_chapter(pool, chapter_iter, future_map)
            while future_map:
                if self.stop_requested():
                    self._cancel_pending(future_map)
                    self.log("停止：已停止爬取。", "warn")
                    break
                completed, _pending = wait(future_map, timeout=0.25, return_when=FIRST_COMPLETED)
                if not completed:
                    continue
                for future in completed:
                    chapter = future_map.pop(future)
                    if future.cancelled():
                        continue
                    result = self._future_result(future, chapter)
                    results.append(result)
                    self.counters.completed += 1
                    self._handle_result(result, chapter)
                    if self.update_progress:
                        self.progress(self.counters.completed, len(self.chapters))
                    self._emit_summary(False)
                    self._submit_next_chapter(pool, chapter_iter, future_map)
            self._emit_summary(True)
        finally:
            pool.shutdown(wait=not self.stop_requested(), cancel_futures=True)
        return sorted(results, key=_chapter_content_index)

    def _submit_next_chapter(
        self,
        pool: ThreadPoolExecutor,
        chapter_iter,
        future_map: dict[Future, ChapterLink],
    ) -> bool:
        if self.stop_requested():
            return False
        try:
            chapter = next(chapter_iter)
        except StopIteration:
            return False
        future_map[pool.submit(self.adapter.fetch_chapter, self.catalog, chapter)] = chapter
        return True

    @staticmethod
    def _cancel_pending(future_map: dict[Future, ChapterLink]) -> None:
        for future in future_map:
            future.cancel()

    @staticmethod
    def _future_result(future: Future, chapter: ChapterLink) -> ChapterContent:
        try:
            return future.result()
        except Exception as exc:
            return ChapterContent(chapter.index, chapter.title, "", chapter.url, chapter.source, False, str(exc))

    def _handle_result(self, result: ChapterContent, chapter: ChapterLink) -> None:
        if result.ok and result.content.strip():
            self.counters.fetched += 1
            if self.detailed_log:
                self.log(f"抓取：第 {result.index} 章", "info")
            self._write_if_possible(result)
            return

        error = result.error or "正文为空"
        if is_rate_limit_result(result):
            self.counters.limited += 1
            if self.detailed_log:
                self.log(f"限流：第 {chapter.index} 章｜{chapter_error_text(error)}", "warn")
            return

        self.counters.failed += 1
        if self.detailed_log:
            self.log(f"失败：第 {chapter.index} 章｜{chapter_error_text(error)}", "warn")

    def _write_if_possible(self, result: ChapterContent) -> None:
        if not self.on_fetched_chapter:
            return
        written_indexes = self.on_fetched_chapter(result)
        if self.log_written_chapters:
            self.log_written_chapters(written_indexes)

    def _emit_summary(self, force: bool = False) -> None:
        if self.detailed_log:
            return
        now = time.monotonic()
        done = self.counters.completed
        if not force and done < len(self.chapters) and done - self._last_summary_done < SUMMARY_CHAPTER_STEP and now - self._last_summary_at < SUMMARY_SECONDS:
            return
        self._last_summary_at = now
        self._last_summary_done = done
        snapshot = self.counters.snapshot(len(self.chapters))
        level = "warn" if snapshot.limited else "info"
        self.log(
            f"进度：{snapshot.done}/{snapshot.total}｜"
            f"抓取：{snapshot.fetched}｜"
            f"失败：{snapshot.failed}｜"
            f"限流：{snapshot.limited}",
            level,
        )


def is_rate_limit_result(result: ChapterContent) -> bool:
    if result.error_type == CrawlErrorType.RATE_LIMITED:
        return True
    text = str(result.error or "")
    return any(marker in text for marker in RATE_LIMIT_ERROR_MARKERS)


def chapter_error_text(error: str) -> str:
    text = " ".join(str(error or "正文为空").split())
    return text if len(text) <= 120 else text[:119] + "…"


def _chapter_content_index(chapter: ChapterContent) -> int:
    return chapter.index
