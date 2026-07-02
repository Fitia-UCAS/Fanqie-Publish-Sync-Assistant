from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from backend.novel.source import split_chapter_source_paths


def required_text_file(value: Any) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("请先选择小说 TXT 文件。")
    path = Path(raw)
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"请选择一个存在的小说 TXT 文件：{path}")
    return path


def chapter_range(payload: dict[str, Any]) -> tuple[int, int]:
    start = int_value(payload.get("start"), 1)
    end = int_value(payload.get("end"), start)
    if end < start:
        start, end = end, start
    return start, end


def int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def required_chapter_source(value: Any) -> Path | str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("请先选择小说文件或章节文件夹。")
    paths = split_chapter_source_paths(raw)
    if not paths:
        raise ValueError("请先选择小说文件或章节文件夹。")
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise ValueError(f"请选择存在的小说文件或章节文件夹：{missing[0]}")
    return paths[0] if len(paths) == 1 else "\n".join(str(path) for path in paths)


def dataclass_payload(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        data = asdict(value)
    elif hasattr(value, "__dict__"):
        data = dict(value.__dict__)
    else:
        return {"message": str(value)}
    return {key: str(item) if isinstance(item, Path) else item for key, item in data.items()}
