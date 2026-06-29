from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import write_json
from backend.adapters.webnovel_writer.webnovel_writer_memory import CLOSED_STATUS, OPEN_STATUS
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, write_text


def build_truth_projection(storage: Any, project_id: str) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    paths = storage.paths(project_id)
    out_dir = ensure_dir(Path(paths.control) / "truth")

    projections = {
        "characters": _entity_truth(state, "characters", title="角色真相表"),
        "locations": _entity_truth(state, "locations", title="地点真相表"),
        "factions": _entity_truth(state, "factions", title="势力真相表"),
        "items": _entity_truth(state, "items", title="物品真相表"),
        "foreshadows": _entity_truth(state, "foreshadows", title="伏笔真相表"),
        "conflicts": _entity_truth(state, "conflicts", title="冲突真相表"),
        "timeline": _timeline_truth(state),
        "debts": build_debt_report(storage, project_id, write_files=False),
        "glossary": _glossary_truth(state),
    }
    files = []
    for name, data in projections.items():
        json_path = write_json(out_dir / f"{name}.json", data)
        md_path = write_text(out_dir / f"{name}.md", _truth_markdown(name, data))
        files.append({"name": name, "json": str(json_path), "markdown": str(md_path), "count": data.get("count")})
    index = {"ok": True, "schema_version": 1, "generated_at": now_iso(), "project_id": project_id, "files": files}
    index_json = write_json(out_dir / "truth_index.json", index)
    index_md = write_text(out_dir / "truth_index.md", _truth_index_markdown(index))
    index["paths"] = {"json": str(index_json), "markdown": str(index_md), "dir": str(out_dir)}
    write_json(index_json, index)
    return index


def build_debt_report(storage: Any, project_id: str, *, write_files: bool = True) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    latest = int(state.get("latest_chapter") or 0)
    story_config = storage.load_story_config(project_id)
    threshold = int((story_config.get("gate_policy") or {}).get("long_foreshadow_warning_chapters") or 30)
    rows: list[dict[str, Any]] = []

    def scan(bucket: str, label: str) -> None:
        for name, item in (state.get(bucket) or {}).items():
            item = item if isinstance(item, dict) else {"status": item}
            status = str(item.get("status") or item.get("state") or "open")
            if status in CLOSED_STATUS:
                continue
            first = _to_int(item.get("introduced_chapter") or item.get("first_seen_chapter") or item.get("chapter_no"), latest)
            age = max(0, latest - first) if first else 0
            priority = _priority(bucket, status, age, threshold)
            rows.append({
                "bucket": bucket,
                "label": label,
                "name": str(name),
                "id": str(item.get("id") or ""),
                "status": status,
                "first_chapter": first,
                "age": age,
                "priority": priority,
                "suggested_action": _suggested_action(bucket, status, age, threshold),
                "note": _first_nonempty([item.get("note"), item.get("notes"), item.get("summary"), item.get("description")]),
            })

    scan("foreshadows", "伏笔")
    scan("conflicts", "冲突")
    scan("secrets", "秘密")
    scan("deadlines", "截止约束")
    rows.sort(key=lambda r: ({"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(str(r.get("priority")), 4), -int(r.get("age") or 0), r.get("name") or ""))
    report = {
        "ok": not any(r.get("priority") == "urgent" for r in rows),
        "schema_version": 1,
        "generated_at": now_iso(),
        "latest_chapter": latest,
        "threshold": threshold,
        "count": len(rows),
        "priority_counts": _counts(rows, "priority"),
        "rows": rows,
    }
    if write_files:
        out_dir = ensure_dir(Path(storage.paths(project_id).control) / "reports" / "debts")
        json_path = write_json(out_dir / "last_debt_report.json", report)
        md_path = write_text(out_dir / "last_debt_report.md", debt_markdown(report))
        report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
        write_json(json_path, report)
    return report


def debt_markdown(report: dict[str, Any]) -> str:
    lines = ["# 故事债务报告", "", f"- 生成时间：{report.get('generated_at')}", f"- 最新章节：{report.get('latest_chapter')}", f"- 未结数量：{report.get('count')}", "", "## 优先级统计", ""]
    for key, value in (report.get("priority_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## 待处理", ""]
    if not report.get("rows"):
        lines.append("暂无。")
    for row in report.get("rows") or []:
        lines.append(f"- [{row.get('priority')}] {row.get('label')}《{row.get('name')}》 age={row.get('age')} 状态={row.get('status')} → {row.get('suggested_action')}")
        if row.get("note"):
            lines.append(f"  - 备注：{row.get('note')}")
    return "\n".join(lines).rstrip() + "\n"


def _entity_truth(state: dict[str, Any], bucket: str, *, title: str) -> dict[str, Any]:
    rows = []
    for name, item in sorted((state.get(bucket) or {}).items(), key=lambda kv: str(kv[0])):
        if not isinstance(item, dict):
            item = {"status": item}
        rows.append({
            "name": str(item.get("name") or name),
            "id": str(item.get("id") or ""),
            "aliases": item.get("aliases") or [],
            "status": str(item.get("status") or item.get("state") or ""),
            "first_seen_chapter": item.get("first_seen_chapter") or item.get("introduced_chapter") or "",
            "last_seen_chapter": item.get("last_seen_chapter") or item.get("resolved_chapter") or "",
            "location": item.get("location") or "",
            "owner": item.get("owner") or "",
            "faction": item.get("faction") or "",
            "progress": item.get("progress") or "",
            "note": _first_nonempty([item.get("note"), item.get("notes"), item.get("summary"), item.get("description")]),
            "raw": item,
        })
    return {"schema_version": 1, "generated_at": now_iso(), "title": title, "bucket": bucket, "count": len(rows), "rows": rows}


def _timeline_truth(state: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in state.get("timeline") or []:
        if isinstance(item, dict):
            rows.append(item)
        else:
            rows.append({"event": str(item)})
    for item in state.get("milestones") or []:
        if isinstance(item, dict):
            rows.append({"kind": "milestone", **item})
        else:
            rows.append({"kind": "milestone", "event": str(item)})
    return {"schema_version": 1, "generated_at": now_iso(), "title": "时间线真相表", "count": len(rows), "rows": rows[-300:]}


def _glossary_truth(state: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
        for name, item in (state.get(bucket) or {}).items():
            item = item if isinstance(item, dict) else {}
            rows.append({"term": str(name), "bucket": bucket, "id": str(item.get("id") or ""), "aliases": item.get("aliases") or [], "note": _first_nonempty([item.get("summary"), item.get("note"), item.get("notes"), item.get("status")])})
    return {"schema_version": 1, "generated_at": now_iso(), "title": "实体词典", "count": len(rows), "rows": rows}


def _truth_markdown(name: str, data: dict[str, Any]) -> str:
    title = data.get("title") or name
    lines = [f"# {title}", "", f"- 生成时间：{data.get('generated_at')}", f"- 数量：{data.get('count')}", ""]
    rows = data.get("rows") or []
    if not rows:
        lines.append("暂无。")
        return "\n".join(lines).rstrip() + "\n"
    for row in rows:
        if not isinstance(row, dict):
            lines.append(f"- {row}")
            continue
        label = row.get("name") or row.get("term") or row.get("event") or row.get("title") or row.get("id") or "记录"
        bits = []
        for key in ["id", "status", "location", "owner", "faction", "progress", "first_seen_chapter", "last_seen_chapter", "bucket"]:
            if row.get(key) not in (None, "", []):
                bits.append(f"{key}={row.get(key)}")
        line = f"- {label}"
        if bits:
            line += "（" + "；".join(bits) + "）"
        if row.get("note"):
            line += f"：{row.get('note')}"
        lines.append(line)
        aliases = row.get("aliases") or []
        if aliases:
            lines.append("  - aliases: " + ", ".join(map(str, aliases)))
    return "\n".join(lines).rstrip() + "\n"


def _truth_index_markdown(index: dict[str, Any]) -> str:
    lines = ["# 真相文件投影", "", f"- 生成时间：{index.get('generated_at')}", ""]
    for row in index.get("files") or []:
        lines.append(f"- {row.get('name')}: {row.get('count')} 条 `{row.get('markdown')}`")
    return "\n".join(lines).rstrip() + "\n"


def _priority(bucket: str, status: str, age: int, threshold: int) -> str:
    if bucket == "deadlines" and status in OPEN_STATUS:
        return "urgent" if age >= threshold // 2 else "high"
    if age >= threshold:
        return "urgent"
    if age >= max(1, threshold * 2 // 3):
        return "high"
    if age >= max(1, threshold // 3):
        return "medium"
    return "low"


def _suggested_action(bucket: str, status: str, age: int, threshold: int) -> str:
    if bucket == "foreshadows":
        return "本卷内安排推进/回收；若暂不回收，下一章至少提醒一次。" if age >= threshold else "后续章节保持可见，避免遗忘。"
    if bucket == "conflicts":
        return "安排一次对抗或阶段性胜负，更新 progress。"
    if bucket == "deadlines":
        return "确认倒计时是否到期；到期则必须兑现后果或解释延期。"
    if bucket == "secrets":
        return "确认知情人列表，避免未揭示角色突然知道秘密。"
    return "保持状态更新。"


def _counts(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        out[value] = out.get(value, 0) + 1
    return out


def _first_nonempty(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
