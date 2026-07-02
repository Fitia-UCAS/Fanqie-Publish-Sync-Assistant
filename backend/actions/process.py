from __future__ import annotations


from pathlib import Path
from typing import Any

from backend.novel.formatting import format_chapters
from backend.novel.reader import chapters_to_preview, read_chapters, select_chapters
from backend.novel.file_rewrite import update_text_file_in_place
from backend.tasks.callbacks import TaskCallbacks
from backend.text_files import iter_text_files
from backend.paths import PROCESS_BACKUP_DIR, PROCESS_OUTPUT_DIR
from backend.tasks.outcome import TaskOutcome
from backend.form_inputs import required_text_file
from backend.novel.chapters import Chapter
from backend.novel.text_cleaning import format_novel_text

FORMAT_BACKUP_DIR = PROCESS_BACKUP_DIR / "format_novel"


EXTRACT_TEXT_MODES = {"single", "around", "range"}


MODE_LABELS = {
    "single": "提取单章",
    "around": "提取前后章",
    "range": "提取范围",
    "organizeSingle": "整理单章",
    "organizeAround": "整理前后章",
    "organizeRange": "整理范围",
}


def analyze_novel_file(file_path: str) -> TaskOutcome:
    chapters = read_chapters(file_path)
    return TaskOutcome(True, f"已识别 {len(chapters)} 个章节。", data={"chapters": chapters_to_preview(chapters)})


def process_novel(payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskOutcome:
    callbacks = callbacks or TaskCallbacks()
    mode = str(payload.get("mode") or "range")
    if mode == "formatFolder":
        return format_batch_files(payload, callbacks)

    novel_file = required_text_file(payload.get("novelFile"))
    if mode == "formatNovel":
        return format_single_file(novel_file, callbacks)

    chapters = read_chapters(novel_file)
    callbacks.emit_progress(0, 1)
    callbacks.emit_log(f"已识别 {len(chapters)} 个章节。")
    selected = _select_by_mode(chapters, payload, mode)
    if not selected:
        return TaskOutcome(False, "没有匹配到目标章节。")

    selected_text = format_chapters(selected)
    target = _chapter_output_path(payload, novel_file, selected, mode)
    target.write_text(selected_text, encoding="utf-8")
    callbacks.emit_progress(1, 1)
    callbacks.emit_log(f"已写出：{target.name}", "success")
    data: dict[str, Any] = {}
    if mode in EXTRACT_TEXT_MODES:
        data["resultDisplayMode"] = "chapter_text"
        data["resultText"] = selected_text
    return TaskOutcome(
        True,
        f"{MODE_LABELS.get(mode, '处理')}完成。",
        path=target,
        result_kind="output_file",
        display_name=target.name,
        data=data,
    )


def _select_by_mode(chapters: list[Chapter], payload: dict[str, Any], mode: str) -> list[Chapter]:
    if mode in {"single", "organizeSingle"}:
        number = int(payload.get("chapter") or 1)
        return select_chapters(chapters, number, number)
    if mode in {"around", "organizeAround"}:
        number = int(payload.get("aroundChapter") or payload.get("chapter") or 1)
        return select_chapters(chapters, max(1, number - 1), number + 1)
    if mode in {"range", "organizeRange"}:
        return select_chapters(chapters, int(payload.get("start") or 1), int(payload.get("end") or 1))
    return chapters


def format_single_file(novel_file: Path, callbacks: TaskCallbacks) -> TaskOutcome:
    callbacks.emit_progress(0, 1)
    update = update_text_file_in_place(novel_file, format_novel_text, backup_dir=FORMAT_BACKUP_DIR, backup=True)
    callbacks.emit_progress(1, 1)
    data: dict[str, Any] = {"changed": update.changed}
    if update.backup_path:
        data["backupPath"] = str(update.backup_path)
        data["backupDir"] = str(update.backup_path.parent)
    return TaskOutcome(
        True,
        "格式化整本完成，已覆盖原文件。" if update.changed else "格式已规范，无需修改。",
        path=novel_file,
        result_kind="in_place",
        display_name=novel_file.name,
        data=data,
    )


def format_batch_files(payload: dict[str, Any], callbacks: TaskCallbacks) -> TaskOutcome:
    folder = str(payload.get("batchFolder") or "").strip()
    files = iter_text_files(folder)
    if not files:
        return TaskOutcome(False, "文件夹中没有 TXT 文件。")

    changed = 0
    backup_paths: list[str] = []
    for index, file_path in enumerate(files, start=1):
        update = update_text_file_in_place(
            file_path,
            format_novel_text,
            backup_dir=FORMAT_BACKUP_DIR / file_path.parent.name,
            backup=True,
        )
        if update.changed:
            changed += 1
        if update.backup_path:
            backup_paths.append(str(update.backup_path))
        callbacks.emit_progress(index, len(files))
        callbacks.emit_log(f"完成：{file_path.name}")
    message = f"批量格式化完成：{len(files)} 个文件，覆盖修改 {changed} 个。"
    callbacks.emit_log(message, "success")
    data: dict[str, Any] = {"changed": changed, "backupPaths": backup_paths}
    if backup_paths:
        data["backupPath"] = backup_paths[-1]
        data["backupDir"] = str(Path(backup_paths[-1]).parent)
    return TaskOutcome(
        True,
        message,
        path=Path(folder),
        result_kind="in_place_batch",
        display_name=Path(folder).name,
        data=data,
    )


def _chapter_output_path(payload: dict[str, Any], novel_file: Path, selected: list[Chapter], mode: str) -> Path:
    raw = str(payload.get("outputFile") or "").strip()
    if raw:
        target = Path(raw)
        if target.exists() and target.is_dir():
            target = target / _default_output_name(novel_file, selected, mode)
        elif not target.suffix:
            target = target / _default_output_name(novel_file, selected, mode)
    else:
        target = PROCESS_OUTPUT_DIR / _default_output_name(novel_file, selected, mode)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _default_output_name(novel_file: Path, selected: list[Chapter], mode: str) -> str:
    if not selected:
        return "章节输出.txt"
    first = selected[0]
    last = selected[-1]
    if first.number == last.number:
        return f"第{first.number}章.txt"
    return f"第{first.number}-{last.number}章.txt"
