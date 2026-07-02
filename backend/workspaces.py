from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any

from backend.paths import WORKSPACES_DIR
from backend.json_files import read_json, write_json


def workspace_id_from_payload(payload: dict[str, Any] | None) -> str:
    payload = payload or {}
    source = _first_non_empty(
        payload.get("novelFile"),
        payload.get("source"),
        payload.get("novelUrl"),
        payload.get("inputFile"),
        payload.get("outputFile"),
        "default",
    )
    digest = hashlib.sha1(str(source).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"novel_{digest}"


def ensure_workspace_for_payload(payload: dict[str, Any] | None, *, workflow: str = "") -> str:
    payload = payload or {}
    workspace_id = workspace_id_from_payload(payload)
    path = workspace_dir(workspace_id)
    existing = read_json(path / "novel.json")
    data = {
        **existing,
        "id": workspace_id,
        "title": existing.get("title") or _infer_title(payload),
        "source": _source_descriptor(payload),
        "fanqie": {
            **(existing.get("fanqie") if isinstance(existing.get("fanqie"), dict) else {}),
            "chapterManageUrl": str(payload.get("chapterManageUrl") or ""),
            "accountId": str(payload.get("accountId") or "default"),
        },
        "output": {
            **(existing.get("output") if isinstance(existing.get("output"), dict) else {}),
            "root": str(payload.get("outputDir") or payload.get("outputFile") or ""),
        },
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    if not existing.get("createdAt"):
        data["createdAt"] = data["updatedAt"]
    if workflow:
        workflows = list(existing.get("workflows") if isinstance(existing.get("workflows"), list) else [])
        if workflow not in workflows:
            workflows.append(workflow)
        data["workflows"] = workflows
    save_workspace(workspace_id, data)
    ensure_chapter_map(workspace_id)
    return workspace_id


def workspace_dir(workspace_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(workspace_id or "default")).strip("_")
    return WORKSPACES_DIR / (safe or "default")


def load_workspace(workspace_id: str) -> dict[str, Any]:
    return read_json(workspace_dir(workspace_id) / "novel.json")


def save_workspace(workspace_id: str, data: dict[str, Any]) -> Path:
    payload = {**data, "id": workspace_id}
    path = workspace_dir(workspace_id) / "novel.json"
    write_json(path, payload)
    return path


def ensure_chapter_map(workspace_id: str) -> Path:
    path = workspace_dir(workspace_id) / "chapter_map.json"
    if not path.exists():
        write_json(path, {"novelId": workspace_id, "chapters": []})
    return path


def _source_descriptor(payload: dict[str, Any]) -> dict[str, str]:
    if payload.get("novelUrl"):
        return {"type": "web_url", "url": str(payload.get("novelUrl") or "")}
    source = _first_non_empty(payload.get("novelFile"), payload.get("source"), payload.get("inputFile"), payload.get("outputFile"), "")
    return {"type": "local_path" if source else "unknown", "path": str(source)}


def _infer_title(payload: dict[str, Any]) -> str:
    source = _first_non_empty(payload.get("novelFile"), payload.get("source"), payload.get("novelUrl"), payload.get("inputFile"), "")
    if not source:
        return "未命名小说"
    text = str(source)
    if text.startswith("http"):
        return text.rstrip("/").rsplit("/", 1)[-1] or "网页小说"
    return Path(text.splitlines()[0]).stem or "未命名小说"


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if str(value or "").strip():
            return value
    return ""
