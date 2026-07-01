from __future__ import annotations

import re
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from backend.adapters.character_material.character_material_client import CharacterMaterialClient
from backend.adapters.character_material.character_material_platform import CharacterMaterialPlatform
from backend.adapters.current_plot.current_plot_json import extract_json_object, write_jsonl
from backend.adapters.current_plot.current_plot_models import CurrentPlotChapterSummary, CurrentPlotUpdateResult
from backend.adapters.current_plot.current_plot_prompt import (
    build_current_plot_batch_merge_prompt,
    build_current_plot_fact_prompt,
    build_current_plot_merge_prompt,
    build_current_plot_system_prompt,
    build_current_plot_user_prompt,
)
from backend.models.chapter import Chapter
from backend.services.service_chapter_text_parser import read_chapters
from backend.shared.app.app_paths import CURRENT_PLOT_DEBUG_DIR, CURRENT_PLOT_OUTPUT_DIR
from backend.shared.filename.filename_sanitizer import safe_filename
from backend.shared.task.task_callbacks import TaskCallbacks
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


MODE_SERIAL = "serial"
MODE_EXTRACT_MERGE = "extract_merge"
MODE_FAST_PREVIEW = "fast_preview"
SUPPORTED_MODES = {MODE_SERIAL, MODE_EXTRACT_MERGE, MODE_FAST_PREVIEW}

SCOPE_SINGLE = "single"
SCOPE_AROUND = "around"
SCOPE_RANGE = "range"
SCOPE_ALL = "all"


class CurrentPlotService:
    def __init__(self) -> None:
        self.system_prompt = build_current_plot_system_prompt()

    @staticmethod
    def platforms() -> dict[str, str]:
        return CharacterMaterialPlatform.list_platforms()

    @staticmethod
    def default_platform_values(platform: str) -> dict[str, str]:
        return CharacterMaterialPlatform.default_runtime_values(platform)

    def list_chapters(self, source: str | Path, limit: int | None = 80) -> str:
        chapters = read_chapters(source)
        rows = [f"第 {chapter.number} 章｜{chapter.heading}｜{chapter.word_count} 字" for chapter in chapters]
        if limit is not None and len(rows) > limit:
            rows = rows[:limit] + [f"……共 {len(chapters)} 章，仅显示前 {limit} 章"]
        return "\n".join(rows)

    def update(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> CurrentPlotUpdateResult:
        callbacks = callbacks or TaskCallbacks()
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("请先选择完整小说文件。")

        chapters = read_chapters(source)
        if not chapters:
            raise ValueError("没有识别到章节。")

        scope = _normalize_scope(payload.get("scope"))
        selected = _select_chapters(
            chapters,
            scope=scope,
            chapter=_optional_int(payload.get("chapter")),
            around_chapter=_optional_int(payload.get("aroundChapter")),
            start=_optional_int(payload.get("start")),
            end=_optional_int(payload.get("end")),
            all_chapters=_optional_bool(payload.get("allChapters"), False),
        )
        if not selected:
            raise ValueError("没有选中可处理章节。")

        mode = _normalize_mode(payload.get("mode"))
        runtime = CharacterMaterialPlatform.runtime_from_payload(payload)
        client = CharacterMaterialClient(runtime)
        target_words = max(80, min(_optional_int(payload.get("targetWords")) or 260, 500))
        recent_count = max(0, min(_optional_int(payload.get("recentContextCount")) or 5, 20))
        replace_existing = _optional_bool(payload.get("replaceExisting"), True)
        max_workers = max(1, min(_optional_int(payload.get("maxWorkers")) or 4, 16))

        source_path = Path(source).expanduser()
        novel_name = safe_filename(source_path.stem)
        display_novel_name = source_path.stem.strip()

        existing_path = str(payload.get("currentPlotFile") or "").strip()
        existing_text = _read_optional_text(existing_path)
        current_plot_title = _extract_current_plot_title(existing_text, display_novel_name)
        summaries = _parse_current_plot_markdown(existing_text)
        processed: list[CurrentPlotChapterSummary] = []

        output_path = self._resolve_output_path(payload, novel_name, selected[0].number, selected[-1].number)
        debug_path = self._resolve_debug_path(novel_name, selected[0].number, selected[-1].number, mode)

        callbacks.emit_log(f"阶段：已选中 {len(selected)} 章，范围：第 {selected[0].number}-{selected[-1].number} 章。", "info")
        callbacks.emit_log(f"档位：{_mode_label(mode)}。", "info")
        callbacks.emit_progress(0, len(selected))

        if mode == MODE_SERIAL:
            self._run_serial(
                client,
                selected,
                novel_name,
                current_plot_title,
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
                current_plot_title,
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
                current_plot_title,
                summaries,
                processed,
                output_path,
                debug_path,
                callbacks,
                target_words,
                replace_existing,
                max_workers,
            )
        else:  # pragma: no cover - guarded by _normalize_mode
            raise ValueError(f"不支持的当前剧情总结档位：{mode}")

        if not processed and summaries:
            self._write_outputs(output_path, debug_path, summaries, processed, current_plot_title)

        callbacks.emit_log(f"写入：{output_path}", "success")
        callbacks.emit_log(f"调试 JSONL：{debug_path}", "info")
        return CurrentPlotUpdateResult(
            output_path=output_path,
            debug_path=debug_path,
            total_chapters=len(selected),
            updated_chapters=len(processed),
        )

    def _run_serial(
        self,
        client: CharacterMaterialClient,
        selected: list[Chapter],
        novel_name: str,
        current_plot_title: str,
        summaries: dict[int, str],
        processed: list[CurrentPlotChapterSummary],
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

            current_plot = _render_current_plot_markdown(summaries, current_plot_title)
            recent_summaries = _render_recent_summaries(summaries, chapter.number, recent_count)
            item = self._summarize_chapter(client, chapter, novel_name, current_plot, recent_summaries, target_words)
            summaries[chapter.number] = item.summary
            processed.append(item)
            self._write_outputs(output_path, debug_path, summaries, processed, current_plot_title)
            self._emit_item_log(callbacks, item, prefix="完成")
            callbacks.emit_progress(index, len(selected))

    def _run_extract_then_merge(
        self,
        client: CharacterMaterialClient,
        selected: list[Chapter],
        novel_name: str,
        current_plot_title: str,
        summaries: dict[int, str],
        processed: list[CurrentPlotChapterSummary],
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

            current_plot = _render_current_plot_markdown(summaries, current_plot_title)
            recent_summaries = _render_recent_summaries(summaries, chapter.number, recent_count)
            item = self._merge_chapter_fact(client, chapter, novel_name, current_plot, recent_summaries, fact, target_words)
            summaries[chapter.number] = item.summary
            processed.append(item)
            self._write_outputs(output_path, debug_path, summaries, processed, current_plot_title)
            self._emit_item_log(callbacks, item, prefix="合并完成")
            callbacks.emit_progress(completed, len(selected))

    def _run_fast_preview(
        self,
        client: CharacterMaterialClient,
        selected: list[Chapter],
        novel_name: str,
        current_plot_title: str,
        summaries: dict[int, str],
        processed: list[CurrentPlotChapterSummary],
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
        current_plot = _render_current_plot_markdown(summaries, current_plot_title)
        batch = self._batch_merge_facts(client, novel_name, current_plot, facts, target_words)
        for item in batch:
            if item.chapter_index in summaries and not replace_existing:
                callbacks.emit_log(f"跳过：第 {item.chapter_index} 章已存在，未开启覆盖。", "info")
                continue
            summaries[item.chapter_index] = item.summary
            processed.append(item)
            self._emit_item_log(callbacks, item, prefix="预览合并")

        self._write_outputs(output_path, debug_path, summaries, processed, current_plot_title)
        callbacks.emit_progress(1, 1)

    def _extract_facts_concurrent(
        self,
        client: CharacterMaterialClient,
        chapters: list[Chapter],
        novel_name: str,
        callbacks: TaskCallbacks,
        target_words: int,
        max_workers: int,
    ) -> dict[int, dict[str, Any]]:
        results: dict[int, dict[str, Any]] = {}
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future[CurrentPlotChapterSummary], Chapter] = {
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
        client: CharacterMaterialClient,
        chapter: Chapter,
        novel_name: str,
        current_plot: str,
        recent_summaries: str,
        target_words: int,
    ) -> CurrentPlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_current_plot_user_prompt(
                current_plot=current_plot,
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
        client: CharacterMaterialClient,
        chapter: Chapter,
        novel_name: str,
        target_words: int,
    ) -> CurrentPlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_current_plot_fact_prompt(
                chapter_heading=chapter.heading,
                chapter_text=chapter.to_text(),
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        return self._row_to_summary(row, chapter, novel_name)

    def _merge_chapter_fact(
        self,
        client: CharacterMaterialClient,
        chapter: Chapter,
        novel_name: str,
        current_plot: str,
        recent_summaries: str,
        fact: dict[str, Any],
        target_words: int,
    ) -> CurrentPlotChapterSummary:
        raw = client.chat(
            self.system_prompt,
            build_current_plot_merge_prompt(
                current_plot=current_plot,
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
        client: CharacterMaterialClient,
        novel_name: str,
        current_plot: str,
        facts: list[dict[str, Any]],
        target_words: int,
    ) -> list[CurrentPlotChapterSummary]:
        raw = client.chat(
            self.system_prompt,
            build_current_plot_batch_merge_prompt(
                current_plot=current_plot,
                chapter_facts=facts,
                target_words=target_words,
            ),
        )
        row = extract_json_object(raw)
        chapters = row.get("chapters")
        if not isinstance(chapters, list):
            raise ValueError("模型返回缺少 chapters 数组")

        by_number = {
            _optional_int(fact.get("chapter_index")) or _optional_int(fact.get("chapterIndex")): fact
            for fact in facts
        }
        items: list[CurrentPlotChapterSummary] = []
        for chapter_row in chapters:
            if not isinstance(chapter_row, dict):
                continue
            chapter_number = _optional_int(chapter_row.get("chapter_index")) or _optional_int(chapter_row.get("chapterIndex"))
            if not chapter_number:
                continue
            fact = by_number.get(chapter_number, {})
            title = str(fact.get("chapter_title") or fact.get("chapterTitle") or f"第{chapter_number}章")
            fake_chapter = _ChapterRecord(number=chapter_number, heading=title)
            items.append(self._row_to_summary(chapter_row, fake_chapter, novel_name))
        return sorted(items, key=lambda item: item.chapter_index)

    @staticmethod
    def _row_to_summary(row: dict[str, Any], chapter: Chapter | "_ChapterRecord", novel_name: str) -> CurrentPlotChapterSummary:
        summary = _normalize_summary(str(row.get("chapter_summary") or row.get("summary") or "").strip(), chapter)
        if not summary:
            raise ValueError(f"第 {chapter.number} 章模型返回缺少 chapter_summary")
        return CurrentPlotChapterSummary(
            novel_name=novel_name,
            chapter_index=chapter.number,
            chapter_title=_normalize_chapter_title(str(row.get("chapter_title") or row.get("chapterTitle") or chapter.heading), chapter.number),
            summary=summary,
            chapter_context=_normalize_chapter_context(row.get("chapter_context") or row.get("chapterContext")),
            event_chain=_normalize_event_chain(row.get("event_chain") or row.get("eventChain")),
            key_events=_string_list(row.get("key_events")),
            conflicts=_string_list(row.get("conflicts")),
            highlights=_string_list(row.get("highlights")),
            emotional_beats=_string_list(row.get("emotional_beats") or row.get("emotionalBeats")),
            character_updates=_string_list(row.get("character_updates")),
            story_threads=_story_thread_list(row.get("story_threads") or row.get("storyThreads") or row.get("open_threads")),
            chapter_hook=_normalize_chapter_hook(row.get("chapter_hook") or row.get("chapterHook")),
            unclear_fields=_string_list(row.get("unclear_fields") or row.get("unclearFields")),
            corrections=_string_list(row.get("corrections")),
            warnings=_string_list(row.get("warnings")),
        )

    @staticmethod
    def _emit_item_log(callbacks: TaskCallbacks, item: CurrentPlotChapterSummary, *, prefix: str) -> None:
        callbacks.emit_log(f"{prefix}：第 {item.chapter_index} 章，已更新当前剧情。", "info")
        digest = _format_item_digest(item)
        if digest:
            callbacks.emit_log(f"结构化事实：第 {item.chapter_index} 章\n{digest}\n", "info")
        for field in item.unclear_fields:
            callbacks.emit_log(f"待确认：第 {item.chapter_index} 章：{field}", "info")
        for correction in item.corrections:
            callbacks.emit_log(f"修正提示：第 {item.chapter_index} 章：{correction}", _current_plot_note_level(correction))
        for warning in item.warnings:
            callbacks.emit_log(f"注意：第 {item.chapter_index} 章：{warning}", _current_plot_note_level(warning))

    def _resolve_output_path(self, payload: dict[str, Any], novel_name: str, start: int, end: int) -> Path:
        raw_output = str(payload.get("outputFile") or payload.get("currentPlotFile") or "").strip()
        if raw_output:
            path = Path(raw_output).expanduser()
            return path if path.suffix else path / _default_output_name(start, end)

        output_dir = str(payload.get("outputDir") or "").strip()
        root = Path(output_dir).expanduser() if output_dir else CURRENT_PLOT_OUTPUT_DIR / safe_filename(novel_name)
        return root / _default_output_name(start, end)

    @staticmethod
    def _resolve_debug_path(novel_name: str, start: int, end: int, mode: str) -> Path:
        return CURRENT_PLOT_DEBUG_DIR / safe_filename(novel_name) / _default_debug_name(start, end, mode)

    @staticmethod
    def _write_outputs(
        output_path: Path,
        debug_path: Path,
        summaries: dict[int, str],
        processed: list[CurrentPlotChapterSummary],
        current_plot_title: str = "",
    ) -> None:
        ensure_dir(output_path.parent)
        write_text(output_path, _render_current_plot_markdown(summaries, current_plot_title) + "\n")
        write_jsonl(debug_path, [item.to_dict() for item in processed])


class _ChapterRecord:
    def __init__(self, number: int, heading: str) -> None:
        self.number = number
        self.heading = heading


def _select_chapters(
    chapters: list[Chapter],
    *,
    scope: str,
    chapter: int | None,
    around_chapter: int | None,
    start: int | None,
    end: int | None,
    all_chapters: bool,
) -> list[Chapter]:
    if scope == SCOPE_SINGLE:
        target = chapter or start or chapters[0].number
        return [item for item in chapters if item.number == target]

    if scope == SCOPE_AROUND:
        target = around_chapter or chapter or start or chapters[0].number
        return [item for item in chapters if target - 1 <= item.number <= target + 1]

    if scope == SCOPE_RANGE:
        safe_start = start or chapters[0].number
        safe_end = end if end is not None else chapters[-1].number
        low, high = min(safe_start, safe_end), max(safe_start, safe_end)
        return [item for item in chapters if low <= item.number <= high]

    if all_chapters or scope == SCOPE_ALL:
        return chapters

    if chapter:
        return [item for item in chapters if item.number == chapter]

    if around_chapter:
        return [item for item in chapters if around_chapter - 1 <= item.number <= around_chapter + 1]

    if start or end:
        safe_start = start or chapters[0].number
        safe_end = end if end is not None else chapters[-1].number
        low, high = min(safe_start, safe_end), max(safe_start, safe_end)
        return [item for item in chapters if low <= item.number <= high]

    return []


def _extract_current_plot_title(text: str, novel_name: str = "") -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped

    safe_name = str(novel_name or "").strip()
    if safe_name:
        return f"# 《{safe_name}》剧情"

    return "# 当前剧情"


def _parse_current_plot_markdown(text: str) -> dict[int, str]:
    summaries: dict[int, str] = {}
    pattern = re.compile(r"(?m)^\s*第\s*(\d+)\s*章\s*[，,、：:]?")
    matches = list(pattern.finditer(text or ""))
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapter_number = int(match.group(1))
        block = text[start:end].strip()
        if block:
            summaries[chapter_number] = _compact_block(block)
    return dict(sorted(summaries.items()))


def _render_current_plot_markdown(summaries: dict[int, str], title: str = "") -> str:
    body = "\n\n".join(
        summaries[key].strip()
        for key in sorted(summaries)
        if summaries[key].strip()
    )
    safe_title = str(title or "").strip()

    if safe_title and body:
        return f"{safe_title}\n\n{body}"
    if safe_title:
        return safe_title
    return body


def _render_recent_summaries(summaries: dict[int, str], chapter_number: int, recent_count: int) -> str:
    if recent_count <= 0:
        return ""
    previous_keys = [key for key in sorted(summaries) if key < chapter_number]
    selected = previous_keys[-recent_count:]
    return "\n\n".join(summaries[key] for key in selected)


def _normalize_summary(summary: str, chapter: Chapter | _ChapterRecord) -> str:
    text = _compact_block(summary)
    if not text:
        return ""
    if re.match(rf"^第\s*{chapter.number}\s*章", text):
        return re.sub(rf"^第\s*{chapter.number}\s*章\s*[，,、：:]?\s*", f"第{chapter.number}章，", text, count=1)
    return f"第{chapter.number}章，{text}"


def _compact_block(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    return " ".join(lines).strip()


def _read_optional_text(path: str) -> str:
    if not path:
        return ""
    target = Path(path).expanduser()
    if not target.exists() or not target.is_file():
        return ""
    return read_text_auto(target)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _normalize_chapter_title(title: str, chapter_number: int | None = None) -> str:
    text = str(title or "").strip()
    if not text:
        return ""
    if chapter_number:
        text = re.sub(rf"^\s*第\s*{chapter_number}\s*章\s*", "", text)
    text = re.sub(r"^\s*第\s*\d+\s*章\s*", "", text)
    text = re.sub(r"^[，,、：:\-—\s]+", "", text).strip()
    return text


def _normalize_chapter_context(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"time": "未明确", "locations": [], "characters": []}
    time = str(value.get("time") or value.get("时间") or "未明确").strip() or "未明确"
    locations = _string_list(value.get("locations") or value.get("location") or value.get("地点"))
    characters = _string_list(value.get("characters") or value.get("人物"))
    extra = {
        str(key): val
        for key, val in value.items()
        if key not in {"time", "时间", "locations", "location", "地点", "characters", "人物"}
    }
    return {"time": time, "locations": locations, "characters": characters, **extra}


def _normalize_event_chain(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"cause": "未明确", "process": "未明确", "result": "未明确"}
    cause = str(value.get("cause") or value.get("起因") or "未明确").strip() or "未明确"
    process = str(value.get("process") or value.get("经过") or "未明确").strip() or "未明确"
    result = str(value.get("result") or value.get("结果") or "未明确").strip() or "未明确"
    extra = {
        str(key): val
        for key, val in value.items()
        if key not in {"cause", "起因", "process", "经过", "result", "结果"}
    }
    return {"cause": cause, "process": process, "result": result, **extra}


def _normalize_chapter_hook(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        hook_type = str(value.get("type") or value.get("hook_type") or value.get("钩子类型") or "未明确").strip() or "未明确"
        content = str(value.get("content") or value.get("summary") or value.get("内容") or "无明确章末钩子").strip() or "无明确章末钩子"
        strength = str(value.get("strength") or value.get("hook_strength") or value.get("强度") or "medium").strip() or "medium"
        normal = _optional_bool(value.get("normal_cliffhanger"), True)
        extra = {
            str(key): val
            for key, val in value.items()
            if key not in {"type", "hook_type", "钩子类型", "content", "summary", "内容", "strength", "hook_strength", "强度", "normal_cliffhanger"}
        }
        return {"type": hook_type, "content": content, "strength": strength, "normal_cliffhanger": normal, **extra}
    text = str(value or "").strip()
    if text:
        return {"type": "未明确", "content": text, "strength": "medium", "normal_cliffhanger": True}
    return {"type": "无", "content": "无明确章末钩子", "strength": "none", "normal_cliffhanger": True}


def _story_thread_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        text = str(value or "").strip()
        return [{"type": "未分类", "content": text, "status": "待确认", "needs_followup": True}] if text else []

    rows: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            content = str(item.get("content") or item.get("summary") or item.get("description") or item.get("内容") or "").strip()
            if not content:
                continue
            thread_type = str(item.get("type") or item.get("thread_type") or item.get("类型") or "未分类").strip() or "未分类"
            status = str(item.get("status") or item.get("状态") or "待推进").strip() or "待推进"
            needs_followup = _optional_bool(item.get("needs_followup"), True)
            extra = {
                str(key): val
                for key, val in item.items()
                if key not in {"content", "summary", "description", "内容", "type", "thread_type", "类型", "status", "状态", "needs_followup"}
            }
            rows.append({"type": thread_type, "content": content, "status": status, "needs_followup": needs_followup, **extra})
        else:
            text = str(item or "").strip()
            if text:
                rows.append({"type": "未分类", "content": text, "status": "待推进", "needs_followup": True})
    return rows


def _format_item_digest(item: CurrentPlotChapterSummary) -> str:
    sections: list[list[str]] = []

    def add_section(title: str, rows: list[str]) -> None:
        cleaned = [str(row).strip() for row in rows if str(row).strip()]
        if not cleaned:
            return
        sections.append([f"【{title}】", *cleaned])

    if item.chapter_title:
        add_section("章节", [f"章节名：{item.chapter_title}"])

    context = item.chapter_context or {}
    context_rows: list[str] = []
    if context.get("time"):
        context_rows.append(f"时间：{context.get('time')}")
    locations = _string_list(context.get("locations"))
    if locations:
        context_rows.append("地点：" + "、".join(locations))
    characters = _string_list(context.get("characters"))
    if characters:
        context_rows.append("人物：" + "、".join(characters))
    add_section("章节上下文", context_rows)

    chain = item.event_chain or {}
    if chain:
        add_section(
            "事件链",
            [
                f"起因：{chain.get('cause') or '未明确'}",
                f"经过：{chain.get('process') or '未明确'}",
                f"结果：{chain.get('result') or '未明确'}",
            ],
        )

    grouped = [
        ("关键事件", item.key_events),
        ("冲突", item.conflicts),
        ("爽点/亮点", item.highlights),
        ("情绪点", item.emotional_beats),
        ("人物变化", item.character_updates),
    ]
    for title, values in grouped:
        rows = [f"- {value}" for value in values]
        add_section(title, rows)

    if item.story_threads:
        rows: list[str] = []
        for thread in item.story_threads:
            label = str(thread.get("type") or "未分类").strip() or "未分类"
            content = str(thread.get("content") or "").strip()
            status = str(thread.get("status") or "").strip()
            suffix = f"（{status}）" if status else ""
            if content:
                rows.append(f"- [{label}] {content}{suffix}")
        add_section("后续剧情线/伏笔", rows)

    hook = item.chapter_hook or {}
    content = str(hook.get("content") or "").strip()
    if content and content != "无明确章末钩子":
        hook_type = str(hook.get("type") or "未明确").strip() or "未明确"
        strength = str(hook.get("strength") or "medium").strip() or "medium"
        normal = "是" if _optional_bool(hook.get("normal_cliffhanger"), True) else "否"
        add_section(
            "章末钩子",
            [f"类型：{hook_type}", f"内容：{content}", f"强度：{strength}", f"正常钩子：{normal}"],
        )

    if item.unclear_fields:
        add_section("待前后文确认", [f"- {field}" for field in item.unclear_fields])

    return "\n\n".join("\n".join(section) for section in sections).strip()

def _current_plot_note_level(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return "info"

    benign_keywords = (
        "章末钩子完整",
        "承接正确",
        "承接一致",
        "自然承接",
        "无需修正",
        "不是问题",
        "不影响剧情连贯",
        "正常章末",
        "正常钩子",
        "留下悬念",
        "留下钩子",
        "断句钩",
        "normal_cliffhanger",
    )
    if any(keyword in value for keyword in benign_keywords):
        return "info"

    suspicious_keywords = (
        "疑似截断",
        "明显截断",
        "正文不完整",
        "章节不完整",
        "缺失",
        "乱码",
        "标题与内容不匹配",
        "章号",
        "重复",
        "矛盾",
        "建议",
        "需要",
        "无法判断",
        "不符",
    )
    if any(keyword in value for keyword in suspicious_keywords):
        return "warning"

    return "info"


def _optional_int(value: object) -> int | None:
    try:
        text = str(value or "").strip()
        return int(text) if text else None
    except Exception:
        return None


def _optional_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "checked", "是", "真", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "unchecked", "否", "假", "关闭"}:
        return False
    return default


def _normalize_mode(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "strict": MODE_SERIAL,
        "serial": MODE_SERIAL,
        "串行逐章总结": MODE_SERIAL,
        "逐章精修": MODE_SERIAL,
        "hybrid": MODE_EXTRACT_MERGE,
        "extract_merge": MODE_EXTRACT_MERGE,
        "并发单章提取 + 串行合并": MODE_EXTRACT_MERGE,
        "并发合并": MODE_EXTRACT_MERGE,
        "fast": MODE_FAST_PREVIEW,
        "fast_preview": MODE_FAST_PREVIEW,
        "全部并发后一次总合并": MODE_FAST_PREVIEW,
        "快速预览": MODE_FAST_PREVIEW,
    }
    mode = aliases.get(text, text or MODE_EXTRACT_MERGE)
    if mode not in SUPPORTED_MODES:
        return MODE_EXTRACT_MERGE
    return mode


def _normalize_scope(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "single": SCOPE_SINGLE,
        "单章": SCOPE_SINGLE,
        "around": SCOPE_AROUND,
        "前后章": SCOPE_AROUND,
        "range": SCOPE_RANGE,
        "范围章节": SCOPE_RANGE,
        "all": SCOPE_ALL,
        "全部章节": SCOPE_ALL,
    }
    return aliases.get(text, text or SCOPE_RANGE)


def _mode_label(mode: str) -> str:
    return {
        MODE_SERIAL: "逐章精修｜慢｜最高准确度｜正式更新",
        MODE_EXTRACT_MERGE: "并发合并｜中快｜很高准确度｜推荐",
        MODE_FAST_PREVIEW: "快速预览｜快｜中等准确度｜预览",
    }.get(mode, mode)


def _default_output_name(start: int, end: int) -> str:
    return f"当前剧情_第{start}-{end}章.md" if start != end else f"当前剧情_第{start}章.md"


def _default_debug_name(start: int, end: int, mode: str) -> str:
    name = f"current_plot_debug_{start}_{end}_{mode}.jsonl" if start != end else f"current_plot_debug_{start}_{mode}.jsonl"
    return safe_filename(name)