from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from backend.adapters.character_material.character_material_client import CharacterMaterialClient
from backend.adapters.character_material.character_material_json import extract_json_array, read_jsonl, write_jsonl
from backend.adapters.character_material.character_material_models import (
    CharacterChapterText,
    CharacterMaterial,
    CharacterMaterialExtractResult,
    CharacterMaterialStats,
    CharacterTextChunk,
    build_material_stats,
    normalize_content_type,
)
from backend.adapters.character_material.character_material_platform import CharacterMaterialPlatform
from backend.adapters.character_material.character_material_project import (
    format_character_chapter_table,
    load_character_chapter_index,
    load_selected_character_chapters,
    select_character_chapter_metas,
    split_text_file_to_character_project,
)
from backend.adapters.character_material.character_material_prompt import build_character_material_system_prompt, build_character_material_user_prompt
from backend.shared.app.app_paths import CHARACTER_MATERIAL_OUTPUT_DIR
from backend.shared.filename.filename_sanitizer import safe_filename
from backend.shared.task.task_callbacks import TaskCallbacks
from backend.shared.text_file.text_file_storage import ensure_dir


class CharacterMaterialService:
    def __init__(self) -> None:
        self.system_prompt = build_character_material_system_prompt()

    @staticmethod
    def platforms() -> dict[str, str]:
        return CharacterMaterialPlatform.list_platforms()

    @staticmethod
    def default_platform_values(platform: str) -> dict[str, str]:
        return CharacterMaterialPlatform.default_runtime_values(platform)

    def split_novel(self, input_file: str | Path) -> Path:
        return split_text_file_to_character_project(input_file)

    def list_chapters(self, source: str | Path, limit: int | None = 80) -> str:
        return format_character_chapter_table(load_character_chapter_index(source), limit=limit)

    def extract(
        self,
        payload: dict[str, Any],
        callbacks: TaskCallbacks | None = None,
    ) -> CharacterMaterialExtractResult:
        callbacks = callbacks or TaskCallbacks()
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("请先选择完整小说 TXT 文件。")

        chapter = _optional_int(payload.get("chapter"))
        start = _optional_int(payload.get("start"))
        end = _optional_int(payload.get("end"))
        all_chapters = bool(payload.get("allChapters", True))
        max_workers = max(1, _optional_int(payload.get("maxWorkers")) or 4)
        concurrent = bool(payload.get("concurrent", True)) and max_workers > 1
        character_target = _clean_text(payload.get("characterTarget"))
        keyword = _clean_text(payload.get("keyword"))

        runtime = CharacterMaterialPlatform.runtime_from_payload(payload)
        client = CharacterMaterialClient(runtime)
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
        output_path = self._resolve_output_path(payload, chapters[0].meta.novel_name, metas[0].chapter_index, metas[-1].chapter_index)
        write_jsonl(output_path, [item.to_dict(include_source_text=False) for item in materials])
        stats = build_material_stats(materials)
        callbacks.emit_log(f"写入：{output_path}", "success")
        return CharacterMaterialExtractResult(output_path=output_path, stats=stats)

    def stats_from_output(self, path: str | Path) -> CharacterMaterialStats:
        materials = [CharacterMaterial(**{**row, "source_text": row.get("source_text")}) for row in read_jsonl(path)]
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
        client: CharacterMaterialClient,
        callbacks: TaskCallbacks,
        *,
        concurrent: bool,
        max_workers: int,
        character_target: str = "",
        keyword: str = "",
    ) -> list[CharacterMaterial]:
        if not concurrent:
            results: list[CharacterMaterial] = []
            for index, chapter in enumerate(chapters, start=1):
                if callbacks.stop_requested():
                    callbacks.emit_log("停止：已收到停止请求。", "warning")
                    break
                results.extend(self._extract_chapter(chapter, client, character_target=character_target, keyword=keyword))
                callbacks.emit_progress(index, len(chapters))
                callbacks.emit_log(f"完成：第 {chapter.chapter_index} 章", "info")
            return results

        results = []
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future[list[CharacterMaterial]], CharacterTextChunk] = {
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
                    results.extend(future.result())
                    callbacks.emit_log(f"完成：第 {chapter.chapter_index} 章", "info")
                except Exception as exc:
                    callbacks.emit_log(f"失败：第 {chapter.chapter_index} 章：{exc}", "error")
                callbacks.emit_progress(completed, len(chapters))
        return results

    def _extract_chapter(
        self,
        chapter: CharacterTextChunk,
        client: CharacterMaterialClient,
        *,
        character_target: str = "",
        keyword: str = "",
    ) -> list[CharacterMaterial]:
        raw = client.chat(self.system_prompt, build_character_material_user_prompt(chapter.text, character_target=character_target, keyword=keyword))
        rows = extract_json_array(raw)
        materials: list[CharacterMaterial] = []
        seen: set[tuple[str, str, str]] = set()
        for item_index, row in enumerate(rows):
            character = str(row.get("character") or "未知人物").strip() or "未知人物"
            content_type = normalize_content_type(str(row.get("content_type", row.get("category", ""))).strip())
            content = str(row.get("content", row.get("dialogue", ""))).strip()
            if not content_type or not content:
                continue
            key = (character, content_type, content)
            if key in seen:
                continue
            seen.add(key)
            materials.append(
                CharacterMaterial(
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

    def _resolve_output_path(self, payload: dict[str, Any], novel_name: str, start: int | None, end: int | None) -> Path:
        raw_output = str(payload.get("outputFile") or "").strip()
        if raw_output:
            path = Path(raw_output).expanduser()
            return path if path.suffix else path / _default_output_name(start, end)
        output_dir = str(payload.get("outputDir") or "").strip()
        root = Path(output_dir).expanduser() if output_dir else CHARACTER_MATERIAL_OUTPUT_DIR / safe_filename(novel_name)
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
