from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from backend.crawling.chapter_fetch import ChapterCrawlRunner
from backend.crawling.http import HttpClient, HttpPolicy
from backend.crawling.records import (
    SiteAdapterPolicy,
    ChapterContent,
    ChapterLink,
    NovelCatalog,
    NovelCrawlerRequest,
    CrawlReport,
    RetryProfile,
)
from backend.crawling.txt_writer import IncrementalNovelTxtWriter
from backend.crawling.write_order import OrderedChapterWriteBuffer
from backend.crawling.rate_limit import AdaptiveRateLimiter
from backend.crawling.sites import NovelSiteAdapter, adapter_for_url, supported_sites
from backend.filenames import safe_filename

LogFn = Callable[[str, str], None]
ProgressFn = Callable[[int, int], None]
StopFn = Callable[[], bool]


class NovelCrawler:

    RETRY_PROFILES = (
        RetryProfile("第二组参数", 0.50, 2.0, 0.35, 0.90, 30, 1, 4),
        RetryProfile("第三组参数", 0.25, 4.0, 0.80, 1.80, 40, 2, 8),
        RetryProfile("第四组参数", 0.125, 8.0, 1.60, 3.20, 50, 3, 12),
    )

    def crawl_to_txt(
        self,
        request: NovelCrawlerRequest,
        *,
        emit_log: LogFn | None = None,
        emit_progress: ProgressFn | None = None,
        stop_requested: StopFn | None = None,
    ) -> CrawlReport:
        request = request.normalized()
        self._validate(request)
        log = emit_log or _discard_log
        progress = emit_progress or _discard_progress
        should_stop = stop_requested or _not_stopped
        adapter_type = self._adapter_type_for_request(request)
        rate_limiter = self._make_rate_limiter(request)
        adapter = self._make_adapter(request, adapter_type, should_stop, rate_limiter)
        catalog = self._fetch_catalog(request, adapter, log)
        selected = self._select_chapters(catalog.chapters, request.start, request.end)
        log(f"目录：完成 {catalog.title}，共 {len(catalog.chapters)} 章，本次 {len(selected)} 章。", "success")
        if not selected:
            raise RuntimeError("当前范围内没有可抓取章节。")

        output = self.resolve_output_path(request.output_file, catalog)
        writer = IncrementalNovelTxtWriter(output, catalog)
        selected_indexes = {chapter.index for chapter in selected}
        existing_count = writer.existing_chapter_count_in(selected_indexes)
        targets = [chapter for chapter in selected if chapter.index not in writer.chapter_indexes]
        self._log_existing_txt_state(output, writer, existing_count, targets, log)
        progress(existing_count, len(selected))
        if not targets:
            return self._complete_from_existing_txt(output, catalog, selected, existing_count, log, progress)

        write_buffer = self._make_write_buffer(writer, targets, request, log)
        self._log_target_state(existing_count, len(targets), output.name, log)

        results_by_index = self._crawl_chapters_by_stages(
            request=request,
            adapter=adapter,
            adapter_type=adapter_type,
            catalog=catalog,
            selected=targets,
            log=log,
            progress=self._progress_with_existing(progress, existing_count),
            write_buffer=write_buffer,
            stop_requested=should_stop,
            rate_limiter=rate_limiter,
        )
        return self._result_from_crawl(
            request=request,
            catalog=catalog,
            selected=selected,
            targets=targets,
            output=output,
            existing_count=existing_count,
            results_by_index=results_by_index,
            write_buffer=write_buffer,
            should_stop=should_stop,
            log=log,
        )

    @staticmethod
    def sites() -> list[dict[str, str]]:
        return supported_sites()

    def preview_output(self, request: NovelCrawlerRequest) -> tuple[NovelCatalog, Path]:
        request = request.normalized()
        self._validate(request)
        adapter = self._make_adapter(request)
        catalog = adapter.fetch_catalog(request.novel_url)
        return catalog, self.resolve_output_path(request.output_file, catalog)

    def _fetch_catalog(self, request: NovelCrawlerRequest, adapter: NovelSiteAdapter, log: LogFn) -> NovelCatalog:
        log(f"目录：读取 {request.novel_url}", "info")
        return adapter.fetch_catalog(request.novel_url)

    @staticmethod
    def _make_rate_limiter(request: NovelCrawlerRequest) -> AdaptiveRateLimiter:
        return AdaptiveRateLimiter(
            delay_min=request.request_delay_min,
            delay_max=request.request_delay_max,
            cooldown_base=8.0,
            cooldown_max=45.0,
        )

    def _make_write_buffer(
        self,
        writer: IncrementalNovelTxtWriter,
        targets: list[ChapterLink],
        request: NovelCrawlerRequest,
        log: LogFn,
    ) -> OrderedChapterWriteBuffer:
        return OrderedChapterWriteBuffer(
            writer,
            targets,
            self._has_content,
            on_write=(lambda index: log(f"写入：第 {index} 章", "info")) if request.detailed_log else None,
        )

    @staticmethod
    def _progress_with_existing(progress: ProgressFn, existing_count: int) -> ProgressFn:
        def progress_with_existing(current: int, total: int) -> None:
            progress(existing_count + current, existing_count + total)

        return progress_with_existing

    @staticmethod
    def _log_target_state(existing_count: int, target_count: int, output_name: str, log: LogFn) -> None:
        if existing_count:
            log(f"补抓：开始缺失章节 {target_count} 章，已有章节不会重复抓取。", "info")
        else:
            log(f"写入：已创建 TXT，后续会按章节顺序边抓边写：{output_name}", "info")

    def _complete_from_existing_txt(
        self,
        output: Path,
        catalog: NovelCatalog,
        selected: list[ChapterLink],
        existing_count: int,
        log: LogFn,
        progress: ProgressFn,
    ) -> CrawlReport:
        message = f"本地 TXT 已完整：已有 {existing_count}/{len(selected)} 章，无需重新抓取，输出 {output.name}"
        log(f"完成：{message}", "success")
        progress(len(selected), len(selected))
        return CrawlReport(
            ok=True,
            message=message,
            path=output,
            title=catalog.title,
            novel_id=catalog.novel_id,
            total=len(catalog.chapters),
            selected=len(selected),
            success=len(selected),
            failed=0,
            failed_chapters=[],
            existing=existing_count,
            missing=0,
            downloaded=0,
        )

    def _result_from_crawl(
        self,
        *,
        request: NovelCrawlerRequest,
        catalog: NovelCatalog,
        selected: list[ChapterLink],
        targets: list[ChapterLink],
        output: Path,
        existing_count: int,
        results_by_index: dict[int, ChapterContent],
        write_buffer: OrderedChapterWriteBuffer,
        should_stop: StopFn,
        log: LogFn,
    ) -> CrawlReport:
        chapters = sorted(results_by_index.values(), key=_chapter_content_index)
        success = [chapter for chapter in chapters if self._has_content(chapter)]
        failed = [chapter for chapter in chapters if not self._has_content(chapter)]
        total_success = existing_count + len(success)
        self._log_written(write_buffer.finalize(results_by_index), log, request.detailed_log)

        if should_stop():
            message = f"停止：已有 {existing_count} 章，本次写入 {len(success)} 章，输出 {output.name}"
            log(message, "warn")
            return CrawlReport(
                ok=False,
                message=message,
                path=output,
                title=catalog.title,
                novel_id=catalog.novel_id,
                total=len(catalog.chapters),
                selected=len(selected),
                success=total_success,
                failed=len(selected) - total_success,
                failed_chapters=[],
                existing=existing_count,
                missing=len(targets),
                downloaded=len(success),
            )

        if not success and not existing_count:
            raise RuntimeError("没有获取到可写入正文。")

        log(f"完成：TXT 缺章补齐：{output.name}", "success")
        message = f"抓取完成：成功 {total_success}/{len(selected)}，本次补入 {len(success)} 章，输出 {output.name}"
        if failed:
            self._log_failed_summary(failed, log)
        return CrawlReport(
            ok=not failed,
            message=message,
            path=output,
            title=catalog.title,
            novel_id=catalog.novel_id,
            total=len(catalog.chapters),
            selected=len(selected),
            success=total_success,
            failed=len(selected) - total_success,
            failed_chapters=[{"index": c.index, "title": c.title, "error": c.error or "正文为空"} for c in failed],
            existing=existing_count,
            missing=len(targets),
            downloaded=len(success),
        )

    @staticmethod
    def _log_failed_summary(failed: list[ChapterContent], log: LogFn) -> None:
        failed_names = "、".join(f"第 {chapter.index} 章" for chapter in failed[:12])
        suffix = "……" if len(failed) > 12 else ""
        log(f"失败：仍有 {len(failed)} 章未成功：{failed_names}{suffix}", "warn")

    def _validate(self, request: NovelCrawlerRequest) -> None:
        if not request.novel_url:
            raise ValueError("请输入小说链接。")
        if not urlparse(request.novel_url).scheme:
            raise ValueError("小说链接需要包含 http 或 https。")

    def _adapter_type_for_request(self, request: NovelCrawlerRequest) -> type[NovelSiteAdapter]:
        adapter_type = adapter_for_url(request.novel_url)
        if adapter_type is None:
            domains = "、".join(site["domains"] for site in supported_sites()) or "暂无"
            raise ValueError(f"暂不支持这个站点。当前内置站点：{domains}")
        return adapter_type

    def _make_adapter(
        self,
        request: NovelCrawlerRequest,
        adapter_type: type[NovelSiteAdapter] | None = None,
        stop_requested: StopFn | None = None,
        rate_limiter: AdaptiveRateLimiter | None = None,
    ) -> NovelSiteAdapter:
        adapter_type = adapter_type or self._adapter_type_for_request(request)
        client = HttpClient(
            HttpPolicy(
                timeout=request.timeout,
                max_retries=request.max_retries,
                delay_min=request.request_delay_min,
                delay_max=request.request_delay_max,
                headers=adapter_type.default_headers(request.novel_url),
                should_stop=stop_requested,
                rate_limiter=rate_limiter,
            )
        )
        options = SiteAdapterPolicy(
            html_fallback=request.html_fallback,
            detailed_log=request.detailed_log,
        )
        return adapter_type(client, options)

    @staticmethod
    def _select_chapters(chapters: list[ChapterLink], start: int, end: int | None) -> list[ChapterLink]:
        final = end or len(chapters)
        return [chapter for chapter in chapters if start <= chapter.index <= final]

    @classmethod
    def default_output_filename(cls, catalog: NovelCatalog) -> str:
        title = catalog.title or catalog.novel_id or "小说"
        return f"{safe_filename(title)}.txt"

    @classmethod
    def default_output_path(cls, catalog: NovelCatalog, output_dir: Path | None = None) -> Path:
        return Path(output_dir or Path.cwd()) / cls.default_output_filename(catalog)

    @classmethod
    def resolve_output_path(cls, path: Path | None, catalog: NovelCatalog) -> Path:
        raw = str(path or "").strip()
        if not raw:
            return cls.default_output_path(catalog)
        target = Path(raw).expanduser()
        raw_normalized = raw.replace("\\", "/")
        if target.exists() and target.is_dir():
            return target / cls.default_output_filename(catalog)
        if raw_normalized.endswith("/"):
            return target / cls.default_output_filename(catalog)
        if target.suffix.lower() != ".txt":
            return target.with_suffix(".txt")
        return target

    def _crawl_chapters_by_stages(
        self,
        *,
        request: NovelCrawlerRequest,
        adapter: NovelSiteAdapter,
        adapter_type: type[NovelSiteAdapter],
        catalog: NovelCatalog,
        selected: list[ChapterLink],
        log: LogFn,
        progress: ProgressFn,
        write_buffer: OrderedChapterWriteBuffer,
        stop_requested: StopFn,
        rate_limiter: AdaptiveRateLimiter,
    ) -> dict[int, ChapterContent]:
        self._log_stage_start("第一组参数", selected, request, "使用界面参数", log)
        results_by_index = self._run_chapter_stage(
            adapter=adapter,
            catalog=catalog,
            selected=selected,
            request=request,
            log=log,
            progress=progress,
            write_buffer=write_buffer,
            stop_requested=stop_requested,
            update_progress=True,
        )
        failed_targets = self._failed_targets(selected, results_by_index)
        self._log_stage_finish("第一组参数", len(selected), len(failed_targets), log)

        for profile in self.RETRY_PROFILES:
            if stop_requested():
                break
            failed_targets = self._failed_targets(selected, results_by_index)
            if not failed_targets:
                break
            retry_request = self._request_for_retry_profile(request, profile)
            self._log_retry_start(profile, retry_request, failed_targets, log)
            self._cooldown(profile.cooldown, log, stop_requested)
            if stop_requested():
                break
            rate_limiter.configure(delay_min=retry_request.request_delay_min, delay_max=retry_request.request_delay_max)
            retry_adapter = self._make_adapter(retry_request, adapter_type, stop_requested, rate_limiter)
            retry_results = self._run_chapter_stage(
                adapter=retry_adapter,
                catalog=catalog,
                selected=failed_targets,
                request=retry_request,
                log=log,
                progress=progress,
                write_buffer=write_buffer,
                stop_requested=stop_requested,
                update_progress=False,
            )
            self._merge_retry_results(results_by_index, retry_results)
            resolved = len(selected) - len(self._failed_targets(selected, results_by_index))
            log(f"补抓：{profile.name}完成，累计成功 {resolved}/{len(selected)}。", "info")
            progress(resolved, len(selected))
        return results_by_index

    @staticmethod
    def _run_chapter_stage(
        *,
        adapter: NovelSiteAdapter,
        catalog: NovelCatalog,
        selected: list[ChapterLink],
        request: NovelCrawlerRequest,
        log: LogFn,
        progress: ProgressFn,
        write_buffer: OrderedChapterWriteBuffer,
        stop_requested: StopFn,
        update_progress: bool,
    ) -> dict[int, ChapterContent]:
        runner = ChapterCrawlRunner(
            adapter=adapter,
            catalog=catalog,
            chapters=selected,
            max_workers=request.max_workers,
            log=log,
            progress=progress,
            stop_requested=stop_requested,
            detailed_log=request.detailed_log,
            on_fetched_chapter=write_buffer.add_fetched_chapter,
            log_written_chapters=None,
            update_progress=update_progress,
        )
        return {chapter.index: chapter for chapter in runner.crawl()}

    @staticmethod
    def _merge_retry_results(results_by_index: dict[int, ChapterContent], retry_results: dict[int, ChapterContent]) -> None:
        for index, result in retry_results.items():
            current = results_by_index.get(index)
            if NovelCrawler._has_content(result) or not NovelCrawler._has_content(current):
                results_by_index[index] = result

    @staticmethod
    def _log_stage_start(
        profile_name: str,
        selected: list[ChapterLink],
        request: NovelCrawlerRequest,
        suffix: str,
        log: LogFn,
    ) -> None:
        log(
            f"阶段：{profile_name}抓取："
            f"{len(selected)} 章｜"
            f"并发 {request.max_workers}｜"
            f"间隔 {request.request_delay_min:g}-{request.request_delay_max:g}s｜"
            f"重试 {request.max_retries}｜{suffix}",
            "info",
        )

    @staticmethod
    def _log_stage_finish(profile_name: str, total: int, failed_count: int, log: LogFn) -> None:
        success_count = total - failed_count
        suffix = f"，失败 {failed_count} 章，准备降速补抓。" if failed_count else "。"
        log(f"阶段：{profile_name}抓取完成：成功 {success_count}/{total}{suffix}", "warn" if failed_count else "success")

    @staticmethod
    def _log_retry_start(
        profile: RetryProfile,
        retry_request: NovelCrawlerRequest,
        failed_targets: list[ChapterLink],
        log: LogFn,
    ) -> None:
        log(
            "补抓：上一组完成后仍失败，启用针对性补抓："
            f"{len(failed_targets)} 章｜{profile.name}｜"
            f"并发 {retry_request.max_workers}｜"
            f"间隔 {retry_request.request_delay_min:g}-{retry_request.request_delay_max:g}s｜"
            f"重试 {retry_request.max_retries}",
            "warn",
        )

    @staticmethod
    def _request_for_retry_profile(request: NovelCrawlerRequest, profile: RetryProfile) -> NovelCrawlerRequest:
        worker_count = max(1, math.ceil(request.max_workers * profile.worker_ratio))
        if request.max_workers > 1:
            worker_count = min(worker_count, request.max_workers - 1)
        delay_min = max(request.request_delay_min * profile.delay_ratio, profile.delay_min_floor)
        delay_max = max(request.request_delay_max * profile.delay_ratio, profile.delay_max_floor, delay_min)
        return replace(
            request,
            max_workers=worker_count,
            request_delay_min=delay_min,
            request_delay_max=delay_max,
            timeout=max(request.timeout, profile.timeout_floor),
            max_retries=max(request.max_retries + profile.retry_bonus, request.max_retries),
        ).normalized()

    @staticmethod
    def _cooldown(seconds: float, log: LogFn, stop_requested: StopFn) -> None:
        if seconds <= 0:
            return
        log(f"限流：等待 {int(seconds)} 秒后继续。", "warn")
        end_at = time.monotonic() + seconds
        while time.monotonic() < end_at:
            if stop_requested():
                return
            time.sleep(min(0.25, end_at - time.monotonic()))

    @classmethod
    def _failed_targets(
        cls,
        selected: list[ChapterLink],
        results_by_index: dict[int, ChapterContent],
    ) -> list[ChapterLink]:
        return [chapter for chapter in selected if not cls._has_content(results_by_index.get(chapter.index))]

    @staticmethod
    def _has_content(chapter: ChapterContent | None) -> bool:
        return bool(chapter and chapter.ok and chapter.content.strip())

    @staticmethod
    def _log_written(indexes: list[int], log: LogFn, detailed_log: bool) -> None:
        if not detailed_log:
            return
        for index in indexes:
            log(f"写入：第 {index} 章", "info")

    @staticmethod
    def _format_chapter_indexes(indexes: list[int]) -> str:
        if not indexes:
            return "无"
        first_items = indexes[:30]
        text = "、".join(f"第 {index} 章" for index in first_items)
        return text + ("……" if len(indexes) > len(first_items) else "")

    def _log_existing_txt_state(
        self,
        output: Path,
        writer: IncrementalNovelTxtWriter,
        existing_count: int,
        targets: list[ChapterLink],
        log: LogFn,
    ) -> None:
        if output.exists():
            log(
                f"检测：已有 TXT：{output.name}，已识别 {writer.existing_chapter_count} 章，"
                f"本次范围已有 {existing_count} 章，缺 {len(targets)} 章。",
                "info",
            )
            if targets:
                log(f"缺章：{self._format_chapter_indexes([chapter.index for chapter in targets])}", "info")
            return
        log(f"检测：没有已有 TXT，将创建新文件：{output.name}", "info")


def _chapter_content_index(chapter: ChapterContent) -> int:
    return chapter.index


def _discard_log(_message: str, _level: str = "info") -> None:
    return None


def _discard_progress(_current: int, _total: int) -> None:
    return None


def _not_stopped() -> bool:
    return False
