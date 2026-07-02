from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.novel.splitter import (
    SplitPlan,
    SPLIT_MODE_LABELS,
    default_split_output_dir,
    split_novel_text,
)
from backend.paths import PROCESS_OUTPUT_DIR
from backend.tasks.callbacks import TaskCallbacks
from backend.tasks.outcome import TaskOutcome
from backend.form_inputs import required_text_file


def preview_novel_split_output(input_file: str = "", output_dir: str = "") -> dict[str, Any]:
    source = Path(str(input_file or "").strip())
    if not source.exists() or not source.is_file():
        return {"ok": False, "message": "请先选择小说 TXT 文件。", "outputDir": ""}
    target = Path(str(output_dir or "").strip()) if str(output_dir or "").strip() else default_split_output_dir(source, PROCESS_OUTPUT_DIR)
    return {"ok": True, "message": "已生成默认输出目录。", "outputDir": str(target)}


def split_novel(payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskOutcome:
    callbacks = callbacks or TaskCallbacks()
    options = _options_from_payload(payload)
    callbacks.emit_progress(0, 1)
    callbacks.emit_log(f"分割方式：{SPLIT_MODE_LABELS.get(options.split_mode, options.split_mode)}")
    callbacks.emit_log(f"输入文件：{options.input_file}")
    callbacks.emit_log(f"输出目录：{options.output_dir}")

    result = split_novel_text(options)
    total = max(1, result.file_count)
    callbacks.emit_progress(total, total)
    if callbacks.stop_requested():
        return TaskOutcome(False, "已请求停止，小说分割提前结束。", path=result.output_dir)

    message = f"小说分割完成：生成 {result.file_count} 个 TXT 文件。"
    callbacks.emit_log(message, "success")
    return TaskOutcome(
        True,
        message,
        path=result.output_dir,
        result_kind="output_dir",
        display_name=result.output_dir.name,
        data={
            "outputDir": str(result.output_dir),
            "fileCount": result.file_count,
            "totalBytes": result.total_bytes,
            "splitMode": result.mode,
            "encoding": result.encoding,
            "files": [
                {
                    "name": item.path.name,
                    "path": str(item.path),
                    "bytes": item.bytes_size,
                    "chapters": item.chapter_count,
                    "lines": item.line_count,
                }
                for item in result.files
            ],
        },
    )


def _options_from_payload(payload: dict[str, Any]) -> SplitPlan:
    input_file = required_text_file(payload.get("inputFile"))
    output_dir = _output_dir(payload, input_file)
    return SplitPlan(
        input_file=input_file,
        output_dir=output_dir,
        split_mode=str(payload.get("splitMode") or "chapter_count"),
        chapters_per_file=max(1, int(payload.get("chaptersPerFile") or 10)),
        max_size_mb=max(0.1, float(payload.get("maxSizeMb") or 5.0)),
        clean_output=bool(payload.get("cleanOutput")),
        include_prelude=payload.get("includePrelude") is not False,
    )


def _output_dir(payload: dict[str, Any], input_file: Path) -> Path:
    raw = str(payload.get("outputDir") or "").strip()
    if raw:
        return Path(raw)
    return default_split_output_dir(input_file, PROCESS_OUTPUT_DIR)
