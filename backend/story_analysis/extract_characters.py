from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from backend.story_analysis.llm import StoryNotesClient
from backend.story_analysis.llm_json import extract_json_array, read_jsonl, write_jsonl
from backend.story_analysis.materials import (
    CharacterChapterText,
    CharacterNote,
    CharacterNotesReport,
    CharacterNotesStats,
    CharacterTextChunk,
    build_material_stats,
    normalize_content_type,
)
from backend.story_analysis.platforms import StoryNotesPlatform
from backend.story_analysis.chapter_files import (
    format_character_chapter_table,
    load_character_chapter_index,
    load_selected_character_chapters,
    select_character_chapter_metas,
    split_text_file_to_character_project,
)
from backend.story_analysis.material_prompts import build_character_notes_system_prompt, build_character_notes_user_prompt
from backend.paths import STORY_ANALYSIS_OUTPUT_DIR
from backend.filenames import safe_filename
from backend.tasks.callbacks import TaskCallbacks
from backend.text_files import ensure_dir


class CharacterNotesExtractor:
    def __init__(self) -> None:
        self.system_prompt = build_character_notes_system_prompt()

    @staticmethod
    def platforms() -> dict[str, str]:
        return StoryNotesPlatform.list_platforms()

    @staticmethod
    def default_platform_values(platform: str) -> dict[str, str]:
        return StoryNotesPlatform.default_runtime_values(platform)

    def split_novel(self, input_file: str | Path) -> Path:
        return split_text_file_to_character_project(input_file)

    def list_chapters(self, source: str | Path, limit: int | None = 80) -> str:
        return format_character_chapter_table(load_character_chapter_index(source), limit=limit)

    def extract(
        self,
        payload: dict[str, Any],
        callbacks: TaskCallbacks | None = None,
    ) -> CharacterNotesReport:
        callbacks = callbacks or TaskCallbacks()
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("请先选择完整小说 TXT 文件。")

        chapter = _optional_int(payload.get("chapter"))
        start = _optional_int(payload.get("start"))
        end = _optional_int(payload.get("end"))
        all_chapters = _optional_bool(payload.get("allChapters"), True)
        max_workers = max(1, _optional_int(payload.get("maxWorkers")) or 4)
        concurrent = _optional_bool(payload.get("concurrent"), True) and max_workers > 1
        character_target = _clean_text(payload.get("characterTarget"))
        keyword = _clean_text(payload.get("keyword"))

        runtime = StoryNotesPlatform.runtime_from_payload(payload)
        client = StoryNotesClient(runtime)
        metas = select_character_chapter_metas(
            source,
            chapter=chapter,
            start=start,
            end=end,
            all_chapters=all_chapters,
        )
        chapters = load_selected_character_chapters(
            source,
            chapter=chapter,
            start=start,
            end=end,
            all_chapters=all_chapters,
        )
        chapter_tasks = self._chapters_to_tasks(chapters)
        if not chapter_tasks:
            raise ValueError("选中章节没有可处理文本。")

        callbacks.emit_log(f"阶段：已选中 {len(metas)} 章，将按每章独立抽取。", "info")
        if character_target:
            callbacks.emit_log(f"限定人物 / 对象：{character_target}", "info")
        if keyword:
            callbacks.emit_log(f"关键词：{keyword}", "info")
        callbacks.emit_progress(0, len(chapter_tasks))
        materials = self._extract_chapters(
            chapter_tasks,
            client,
            callbacks,
            concurrent=concurrent,
            max_workers=max_workers,
            character_target=character_target,
            keyword=keyword,
        )
        materials = sorted(materials, key=lambda item: (item.chapter_index, item.item_index))
        hit_chapters = {item.chapter_index for item in materials}
        skipped_count = max(0, len(chapter_tasks) - len(hit_chapters))
        callbacks.emit_log(
            f"汇总：选中 {len(chapter_tasks)} 章，命中 {len(hit_chapters)} 章，跳过 {skipped_count} 章，共抽取 {len(materials)} 条。",
            "info",
        )
        output_path = self._resolve_output_path(payload, chapters[0].meta.novel_name, metas[0].chapter_index, metas[-1].chapter_index)
        write_jsonl(output_path, [item.to_dict(include_source_text=False) for item in materials])
        stats = build_material_stats(materials)
        callbacks.emit_log(f"写入：{output_path}", "success")
        return CharacterNotesReport(output_path=output_path, stats=stats)

    def stats_from_output(self, path: str | Path) -> CharacterNotesStats:
        materials = [CharacterNote(**{**row, "source_text": row.get("source_text")}) for row in read_jsonl(path)]
        return build_material_stats(materials)

    def _chapters_to_tasks(self, chapters: list[CharacterChapterText]) -> list[CharacterTextChunk]:
        tasks: list[CharacterTextChunk] = []
        for task_id, chapter in enumerate(chapters):
            text = str(chapter.text or "").strip()
            if not text:
                continue
            tasks.append(
                CharacterTextChunk(
                    novel_name=chapter.meta.novel_name,
                    chapter_index=chapter.meta.chapter_index,
                    chapter_title=chapter.meta.chapter_title,
                    chunk_id=task_id,
                    local_chunk_id=0,
                    text=text,
                )
            )
        return tasks

    def _extract_chapters(
        self,
        chapters: list[CharacterTextChunk],
        client: StoryNotesClient,
        callbacks: TaskCallbacks,
        *,
        concurrent: bool,
        max_workers: int,
        character_target: str = "",
        keyword: str = "",
    ) -> list[CharacterNote]:
        if not concurrent:
            results: list[CharacterNote] = []
            for index, chapter in enumerate(chapters, start=1):
                if callbacks.stop_requested():
                    callbacks.emit_log("停止：已收到停止请求。", "warning")
                    break
                chapter_materials = self._extract_chapter(chapter, client, character_target=character_target, keyword=keyword)
                results.extend(chapter_materials)
                callbacks.emit_progress(index, len(chapters))
                self._emit_chapter_result_log(callbacks, chapter, chapter_materials)
            return results

        results = []
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future[list[CharacterNote]], CharacterTextChunk] = {
                executor.submit(self._extract_chapter, chapter, client, character_target=character_target, keyword=keyword): chapter for chapter in chapters
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
                    chapter_materials = future.result()
                    results.extend(chapter_materials)
                    self._emit_chapter_result_log(callbacks, chapter, chapter_materials)
                except Exception as exc:
                    callbacks.emit_log(f"失败：第 {chapter.chapter_index} 章：{exc}", "error")
                callbacks.emit_progress(completed, len(chapters))
        return results

    def _extract_chapter(
        self,
        chapter: CharacterTextChunk,
        client: StoryNotesClient,
        *,
        character_target: str = "",
        keyword: str = "",
    ) -> list[CharacterNote]:
        raw = client.chat(self.system_prompt, build_character_notes_user_prompt(chapter.text, character_target=character_target, keyword=keyword))
        rows = extract_json_array(raw)
        materials: list[CharacterNote] = []
        seen: set[tuple[str, str, str]] = set()
        for item_index, row in enumerate(rows):
            character = str(row.get("character") or "未知人物").strip() or "未知人物"
            content_type = normalize_content_type(str(row.get("content_type", row.get("category", ""))).strip())
            content = str(row.get("content", row.get("dialogue", ""))).strip()
            if not content_type or not content:
                continue
            if _is_low_value_content(content):
                continue
            key = (character, content_type, content)
            if key in seen:
                continue
            seen.add(key)
            materials.append(
                CharacterNote(
                    novel_name=chapter.novel_name,
                    chapter_index=chapter.chapter_index,
                    chapter_title=chapter.chapter_title,
                    chunk_id=chapter.chunk_id,
                    local_chunk_id=0,
                    item_index=item_index,
                    character=character,
                    content_type=content_type,
                    content=content,
                    source_text=None,
                )
            )
        return materials


    @staticmethod
    def _emit_chapter_result_log(callbacks: TaskCallbacks, chapter: CharacterTextChunk, materials: list[CharacterNote]) -> None:
        if materials:
            callbacks.emit_log(f"完成：第 {chapter.chapter_index} 章，抽取 {len(materials)} 条", "info")
        else:
            callbacks.emit_log(f"跳过：第 {chapter.chapter_index} 章，无匹配素材", "info")

    def _resolve_output_path(self, payload: dict[str, Any], novel_name: str, start: int | None, end: int | None) -> Path:
        raw_output = str(payload.get("outputFile") or "").strip()
        if raw_output:
            path = Path(raw_output).expanduser()
            return path if path.suffix else path / _default_output_name(start, end)
        output_dir = str(payload.get("outputDir") or "").strip()
        root = Path(output_dir).expanduser() if output_dir else STORY_ANALYSIS_OUTPUT_DIR / safe_filename(novel_name)
        return ensure_dir(root) / _default_output_name(start, end)


def _default_output_name(start: int | None, end: int | None) -> str:
    if start is not None and end is not None:
        return f"chapter_{start:03d}_{end:03d}_materials.jsonl" if start != end else f"chapter_{start:03d}_materials.jsonl"
    return "all_materials.jsonl"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()



def _optional_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except Exception:
        return None


def _optional_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "checked", "是", "真", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "unchecked", "否", "假", "关闭"}:
        return False
    return default


_LOW_VALUE_NORMALIZED_CONTENTS = {
    "1",
    "+1",
    "啊",
    "哦",
    "噢",
    "嗯",
    "呃",
    "好",
    "是",
    "对",
    "行",
    "可",
    "同意",
    "赞成",
    "附议",
    "没错",
    "是的",
    "就是",
    "哈哈",
    "哈哈哈",
    "呵呵",
    "嘿嘿",
    "嘻嘻",
    "卧槽",
    "？？",
    "！！",
    "??",
    "!!",
}


def _is_low_value_content(content: str) -> bool:
    text = str(content or "").strip()
    if not text:
        return True
    normalized = _normalize_low_value_text(text)
    if not normalized:
        return all(ch in _LOW_VALUE_PUNCTUATION for ch in text)
    if normalized in _LOW_VALUE_NORMALIZED_CONTENTS:
        return True
    # 只由感叹号、问号、省略号等组成的水句没有角色素材价值。
    return all(ch in "?!？！。…~～" for ch in normalized)


_LOW_VALUE_PUNCTUATION = " \t\r\n。，、,.：:；;！!？?‘’'\"“”【】[]（）()《》<>「」『』—_-～~·…"


def _normalize_low_value_text(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch not in _LOW_VALUE_PUNCTUATION)
