from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from backend.shared.text_file.text_file_storage import ensure_dir


def extract_json_array(text: str) -> list[dict[str, Any]]:
    content = (text or "").strip()
    content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE).strip()
    content = re.sub(r"```$", "", content).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", content)
        if not match:
            raise
        parsed = json.loads(match.group(0))

    if isinstance(parsed, dict):
        for key in ("items", "materials", "data", "result", "results"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break

    if not isinstance(parsed, list):
        raise ValueError("模型返回内容不是 JSON 数组")
    return [item for item in parsed if isinstance(item, dict)]


def write_json(path: str | Path, data: Any) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    with target.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    return target


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
    return rows
