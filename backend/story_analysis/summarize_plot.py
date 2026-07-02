from __future__ import annotations

import re
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from backend.story_analysis.llm import StoryNotesClient
from backend.story_analysis.platforms import StoryNotesPlatform
from backend.story_analysis.llm_json import extract_json_object, write_jsonl
from backend.story_analysis.summaries import PlotChapterSummary, PlotUpdateReport
from backend.story_analysis.plot_markdown import (
    ChapterRecord,
    extract_plot_notes_title,
    format_summary_digest,
    parse_plot_notes_markdown,
    read_optional_plot_text,
    render_plot_notes_markdown,
    render_recent_summaries,
    normalize_plot_summary,
)
from backend.story_analysis.plot_scope import (
    MODE_EXTRACT_MERGE,
    MODE_FAST_PREVIEW,
    MODE_SERIAL,
    default_plot_debug_name,
    default_plot_output_name,
    normalize_plot_mode,
    normalize_plot_scope,
    optional_bool,
    optional_int,
    plot_mode_label,
    select_plot_chapters,
)
from backend.story_analysis.summary_prompts import (
    build_plot_batch_merge_prompt,
    build_plot_fact_prompt,
    build_plot_merge_prompt,
    build_plot_system_prompt,
    build_plot_user_prompt,
)
from backend.novel.chapters import Chapter
from backend.novel.reader import read_chapters
from backend.paths import STORY_ANALYSIS_DEBUG_DIR, STORY_ANALYSIS_OUTPUT_DIR
from backend.filenames import safe_filename
from backend.tasks.callbacks import TaskCallbacks
from backend.text_files import ensure_dir, write_text


class PlotSummaryUpdater:
    def __init__(self) -> None:
        self.system_prompt = build_plot_system_prompt()

    @staticmethod
    def platforms() -> dict[str, str]:
        return StoryNotesPlatform.list_platforms()

    @staticmethod
    def default_platform_values(platform: str) -> dict[str, str]:
        return StoryNotesPlatform.default_runtime_values(platform)

    def list_chapters(self, source: str | Path, limit: int | None = 80) -> str:
        chapters = read_chapters(source)
        rows = [f"第 {chapter.number} 章｜{chapter.heading}｜{chapter.word_count} 字" for chapter in chapters]
        if limit is not None and len(rows) > limit:
            rows = rows[:limit] + [f"……共 {len(chapters)} 章，仅显示前 {limit} 章"]
        return "\n".join(rows)

    def update(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> PlotUpdateReport:
        callbacks = callbacks or TaskCallbacks()
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("请先选择完整小说文件。")

        chapters = read_chapters(source)
        if not chapters:
            raise ValueError("没有识别到章节。")

        scope = normalize_plot_scope(payload.get("scope"))
        selected = select_plot_chapters(
            chapters,
            scope=scope,
            chapter=optional_int(payload.get("chapter")),
            around_chapter=optional_int(payload.get("aroundChapter")),
            start=optional_int(payload.get("start")),
            end=optional_int(payload.get("end")),
            all_chapters=optional_bool(payload.get("allChapters"), False),
        )
        if not selected:
            raise ValueError("没有选中可处理章节。")

        mode = normalize_plot_mode(payload.get("mode"))
        runtime = StoryNotesPlatform.runtime_from_payload(payload)
        client = StoryNotesClient(runtime)
        target_words = max(80, min(optional_int(payload.get("targetWords")) or 260, 500))
        recent_count = max(0, min(optional_int(payload.get("recentContextCount")) or 5, 20))
        replace_existing = optional_bool(payload.get("replaceExisting"), True)
        max_workers = max(1, min(optional_int(payload.get("maxWorkers")) or 4, 16))

        source_path = Path(source).expanduser()
        novel_name = safe_filename(source_path.stem)
        display_novel_name = source_path.stem.strip()

        existing_path = str(payload.get("plotNotesFile") or "").strip()
        existing_text = read_optional_plot_text(existing_path)
        plot_notes_title = extract_plot_notes_title(existing_text, display_novel_name)
        summaries = parse_plot_notes_markdown(existing_text)
        processed: list[PlotChapterSummary] = []

        output_path = self._resolve_output_path(payload, novel_name, selected[0].number, selected[-1].number)
        debug_path = self._resolve_debug_path(novel_name, selected[0].number, selected[-1].number, mode)

        callbacks.emit_log(f"阶段：已选中 {len(selected)} 章，范围：第 {selected[0].number}-{selected[-1].number} 章。", "info")
        callbacks.emit_log(f"档位：{plot_mode_label(mode)}。", "info")
        callbacks.emit_progress(0, len(selected))

        if mode == MODE_SERIAL:
            self._run_serial(
                client,
                selected,
                novel_name,
                plot_notes_title,
                summaries,
                processed,
                output_path,
                debug_path,
                callbacks,
                target_words,
                recent_count,
                replace_existing,
            )
        elif mode == MODE_EXTRACT_MERGE:
            self._run_extract_then_merge(
                client,
                selected,
                novel_name,
                plot_notes_title,
                summaries,
                processed,
                output_path,
                debug_path,
                callbacks,
                target_words,
                recent_count,
                replace_existing,
                max_workers,
            )
        elif mode == MODE_FAST_PREVIEW:
            self._run_fast_preview(
                client,
                selected,
                novel_name,
                plot_notes_title,
                summaries,
                processed,
                output_path,
                debug_path,
                callbacks,
                target_words,
                replace_existing,
                max_workers,
            )
        else:  # pragma: no cover - guarded by normalize_plot_mode
            raise ValueError(f"不支持的当前剧情总结档位：{mode}")

        if not processed and summaries:
            self._write_outputs(output_path, debug_path, summaries, processed, plot_notes_title)

        callbacks.emit_log(f"写入：{output_path}", "success")
        callbacks.emit_log(f"调试 JSONL：{debug_path}", "info")
        return PlotUpdateReport(
            output_path=output_path,
            debug_path=debug_path,
            total_chapters=len(selected),
            updated_chapters=len(processed),
        )

    def _run_serial(
        self,
        client: StoryNotesClient,
        selected: list[Chapter],
        novel_name: str,
        plot_notes_title: str,
        summaries: dict[int, str],
        processed: list[PlotChapterSummary],
        output_path: Path,
        debug_path: Path,
        callbacks: TaskCallbacks,
        target_words: int,
        recent_count: int,
        replace_existing: bool,
    ) -> None:
        callbacks.emit_log("说明：严格串行逐章总结，每章直接读取上一章后的当前剧情。", "info")
        for index, chapter in enumerate(selected, start=1):
            if callbacks.stop_requested():
                callbacks.emit_log("停止：已收到停止请求，当前剧情已写入已完成章节。", "warning")
                break
            if chapter.number in summaries and not replace_existing:
                callbacks.emit_log(f"跳过：第 {chapter.number} 章已存在，未开启覆盖。", "info")
                callbacks.emit_progress(index, len(selected))
                continue

            plot_notes = render_plot_notes_markdown(summaries, plot_notes_title)
            recent_summaries = render_recent_summaries(summaries, chapter.number, recent_count)
            item = self._summarize_chapter(client, chapter, novel_name, plot_notes, recent_summaries, target_words)
            summaries[chapter.number] = item.summary
            processed.append(item)
            self._write_outputs(output_path, debug_path, summaries, processed, plot_notes_title)
            self._emit_item_log(callbacks, item, prefix="完成")
            callbacks.emit_progress(index, len(selected))

    def _run_extract_then_merge(
        self,
        client: StoryNotesClient,
        selected: list[Chapter],
        novel_name: str,
        plot_notes_title: str,
        summaries: dict[int, str],
        processed: list[PlotChapterSummary],
        output_path: Path,
        debug_path: Path,
        callbacks: TaskCallbacks,
        target_words: int,
        recent_count: int,
        replace_existing: bool,
        max_workers: int,
    ) -> None:
        callbacks.emit_log(f"阶段：并发提取单章事实，最大并发 {max_workers}。", "info")
        facts = self._extract_facts_concurrent(client, selected, novel_name, callbacks, target_words, max_workers)
        if callbacks.stop_requested():
            callbacks.emit_log("停止：已收到停止请求，未进入串行合并。", "warning")
            return

        callbacks.emit_log("阶段：按章序串行合并进当前剧情。", "info")
        callbacks.emit_progress(0, len(selected))
        completed = 0
        for chapter in selected:
            completed += 1
            if callbacks.stop_requested():
                callbacks.emit_log("停止：已收到停止请求，当前剧情已写入已完成章节。", "warning")
                break
            if chapter.number in summaries and not replace_existing:
                callbacks.emit_log(f"跳过：第 {chapter.number} 章已存在，未开启覆盖。", "info")
                callbacks.emit_progress(completed, len(selected))
                continue

            fact = facts.get(chapter.number)
            if not fact:
                callbacks.emit_log(f"跳过：第 {chapter.number} 章事实提取失败或为空。", "warning")
                callbacks.emit_progress(completed, len(selected))
                continue

            plot_notes = render_plot_notes_markdown(summaries, plot_notes_title)
            recent_summaries = render_recent_summaries(summaries, chapter.number, recent_count)
            item = self._merge_chapter_fact(client, chapter, novel_name, plot_notes, recent_summaries, fact, target_words)
            summaries[chapter.number] = item.summary
            processed.append(item)
            self._write_outputs(output_path, debug_path, summaries, processed, plot_notes_title)
            self._emit_item_log(callbacks, item, prefix="合并完成")
            callbacks.emit_progress(completed, len(selected))

    def _run_fast_preview(
        self,
        client: StoryNotesClient,
        selected: list[Chapter],
        novel_name: str,
        plot_notes_title: str,
        summaries: dict[int, str],
        processed: list[PlotChapterSummary],
        output_path: Path,
        debug_path: Path,
        callbacks: TaskCallbacks,
        target_words: int,
        replace_existing: bool,
        max_workers: int,
    ) -> None:
        callbacks.emit_log(f"阶段：并发提取单章事实，最大并发 {max_workers}。", "info")
        facts_by_chapter = self._extract_facts_concurrent(client, selected, novel_name, callbacks, target_words, max_workers)
        if callbacks.stop_requested():
            callbacks.emit_log("停止：已收到停止请求，未进入一次性合并。", "warning")
            return

        facts = [facts_by_chapter[key] for key in sorted(facts_by_chapter)]
        if not facts:
            callbacks.emit_log("停止：没有可用于合并的单章事实。", "warning")
            return

        callbacks.emit_log("阶段：全部事实一次性总合并，适合快速预览，不建议覆盖正式档案。", "warning")
        callbacks.emit_progress(0, 1)
        plot_notes = render_plot_notes_markdown(summaries, plot_notes_title)
        batch = self._batch_merge_facts(client, novel_name, plot_notes, facts, target_words)
        for item in batch:
            if item.chapter_index in summaries and not replace_existing:
                callbacks.emit_log(f"跳过：第 {item.chapter_index} 章已存在，未开启覆盖。", "info")
                continue
            summaries[item.chapter_index] = item.summary
            processed.append(item)
            self._emit_item_log(callbacks, item, prefix="预览合并")

        self._write_outputs(output_path, debug_path, summaries, processed, plot_notes_title)
        callbacks.emit_progress(1, 1)

    def _extract_facts_concurrent(
        self,
        client: StoryNotesClient,
        chapters: list[Chapter],
        novel_name: str,
        callbacks: TaskCallbacks,
        target_words: int,
        max_workers: int,
    ) -> dict[int, dict[str, Any]]:
        results: dict[int, dict[str, Any]] = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future[PlotChapterSummary], Chapter] = {
                executor.submit(self._extract_chapter_fact, client, chapter, novel_name, target_words): chapter for chapter in chapters
            }
            for future in as_completed(futures):
                chapter = futures[future]
                if callbacks.stop_requested():
                    for pending in futures:
                        pending.cancel()
                    callbacks.emit_log("停止：已收到停止请求，正在结束未完成章节。", "warning")
                    break
                completed += 1
                try:
                    item = future.result()
                    results[chapter.number] = item.to_dict()
                    self._emit_item_log(callbacks, item, prefix="提取完成")
                except Exception as exc:
                    callbacks.emit_log(f"失败：第 {chapter.number} 章事实提取失败：{exc}", "error")
                callbacks.emit_progress(completed, len(chapters))
        return results

    def _summarize_chapter(
        self,
        client: StoryNotesClient,
        chapter: Chapter,
        novel_name: str,
        plot_notes: str,
        recent_summaries: str,
        target_words: int,
    ) -> PlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_plot_user_prompt(
                plot_notes=plot_notes,
                recent_summaries=recent_summaries,
                chapter_heading=chapter.heading,
                chapter_text=chapter.to_text(),
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        return self._row_to_summary(row, chapter, novel_name)

    def _extract_chapter_fact(
        self,
        client: StoryNotesClient,
        chapter: Chapter,
        novel_name: str,
        target_words: int,
    ) -> PlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_plot_fact_prompt(
                chapter_heading=chapter.heading,
                chapter_text=chapter.to_text(),
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        return self._row_to_summary(row, chapter, novel_name)

    def _merge_chapter_fact(
        self,
        client: StoryNotesClient,
        chapter: Chapter,
        novel_name: str,
        plot_notes: str,
        recent_summaries: str,
        fact: dict[str, Any],
        target_words: int,
    ) -> PlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_plot_merge_prompt(
                plot_notes=plot_notes,
                recent_summaries=recent_summaries,
                chapter_heading=chapter.heading,
                chapter_fact=fact,
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        return self._row_to_summary(row, chapter, novel_name)

    def _batch_merge_facts(
        self,
        client: StoryNotesClient,
        novel_name: str,
        plot_notes: str,
        facts: list[dict[str, Any]],
        target_words: int,
    ) -> list[PlotChapterSummary]:
        raw = client.chat(
            self.system_prompt,
            build_plot_batch_merge_prompt(
                plot_notes=plot_notes,
                chapter_facts=facts,
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        chapters = row.get("chapters")
        if not isinstance(chapters, list):
            raise ValueError("模型返回缺少 chapters 数组")

        by_number = {
            optional_int(fact.get("chapter_index")) or optional_int(fact.get("chapterIndex")): fact
            for fact in facts
        }
        items: list[PlotChapterSummary] = []
        for chapter_row in chapters:
            if not isinstance(chapter_row, dict):
                continue
            chapter_number = optional_int(chapter_row.get("chapter_index")) or optional_int(chapter_row.get("chapterIndex"))
            if not chapter_number:
                continue
            fact = by_number.get(chapter_number, {})
            title = str(fact.get("chapter_title") or fact.get("chapterTitle") or f"第{chapter_number}章")
            fake_chapter = ChapterRecord(number=chapter_number, heading=title)
            items.append(self._row_to_summary(chapter_row, fake_chapter, novel_name))
        return sorted(items, key=lambda item: item.chapter_index)

    @staticmethod
    def _row_to_summary(row: dict[str, Any], chapter: Chapter | "ChapterRecord", novel_name: str) -> PlotChapterSummary:
        summary = normalize_plot_summary(str(row.get("chapter_summary") or row.get("summary") or "").strip(), chapter)
        if not summary:
            raise ValueError(f"第 {chapter.number} 章模型返回缺少 chapter_summary")
        return PlotChapterSummary(
            novel_name=novel_name,
            chapter_index=chapter.number,
            chapter_title=normalize_chapter_title(str(row.get("chapter_title") or row.get("chapterTitle") or chapter.heading), chapter.number),
            summary=summary,
            chapter_context=normalize_chapter_context(row.get("chapter_context") or row.get("chapterContext")),
            event_chain=normalize_event_chain(row.get("event_chain") or row.get("eventChain")),
            key_events=string_list(row.get("key_events")),
            conflicts=string_list(row.get("conflicts")),
            highlights=string_list(row.get("highlights")),
            emotional_beats=string_list(row.get("emotional_beats") or row.get("emotionalBeats")),
            character_updates=string_list(row.get("character_updates")),
            story_threads=story_thread_list(row.get("story_threads") or row.get("storyThreads") or row.get("open_threads")),
            chapter_hook=normalize_chapter_hook(row.get("chapter_hook") or row.get("chapterHook")),
            unclear_fields=string_list(row.get("unclear_fields") or row.get("unclearFields")),
            corrections=string_list(row.get("corrections")),
            warnings=string_list(row.get("warnings")),
        )

    @staticmethod
    def _emit_item_log(callbacks: TaskCallbacks, item: PlotChapterSummary, *, prefix: str) -> None:
        callbacks.emit_log(f"{prefix}：第 {item.chapter_index} 章，已更新当前剧情。", "info")
        digest = format_summary_digest(item)
        if digest:
            callbacks.emit_log(f"结构化事实：第 {item.chapter_index} 章\n{digest}\n", "info")
        for field in item.unclear_fields:
            callbacks.emit_log(f"待确认：第 {item.chapter_index} 章：{field}", "info")
        for correction in item.corrections:
            callbacks.emit_log(f"修正提示：第 {item.chapter_index} 章：{correction}", plot_notes_note_level(correction))
        for warning in item.warnings:
            callbacks.emit_log(f"注意：第 {item.chapter_index} 章：{warning}", plot_notes_note_level(warning))

    def _resolve_output_path(self, payload: dict[str, Any], novel_name: str, start: int, end: int) -> Path:
        raw_output = str(payload.get("outputFile") or payload.get("plotNotesFile") or "").strip()
        if raw_output:
            path = Path(raw_output).expanduser()
            return path if path.suffix else path / default_plot_output_name(start, end)

        output_dir = str(payload.get("outputDir") or "").strip()
        root = Path(output_dir).expanduser() if output_dir else STORY_ANALYSIS_OUTPUT_DIR / safe_filename(novel_name)
        return root / default_plot_output_name(start, end)

    @staticmethod
    def _resolve_debug_path(novel_name: str, start: int, end: int, mode: str) -> Path:
        return STORY_ANALYSIS_DEBUG_DIR / safe_filename(novel_name) / default_plot_debug_name(start, end, mode)

    @staticmethod
    def _write_outputs(
        output_path: Path,
        debug_path: Path,
        summaries: dict[int, str],
        processed: list[PlotChapterSummary],
        plot_notes_title: str = "",
    ) -> None:
        ensure_dir(output_path.parent)
        write_text(output_path, render_plot_notes_markdown(summaries, plot_notes_title) + "\n")
        write_jsonl(debug_path, [item.to_dict() for item in processed])
