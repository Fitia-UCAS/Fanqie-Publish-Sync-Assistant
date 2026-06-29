from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text

OPEN_STATUS = {"open", "active", "新增", "推进", "未收", "进行中", "隐藏", "hidden", "待回收", "ongoing"}
CLOSED_STATUS = {"closed", "resolved", "回收", "已回收", "完成", "done", "payoff", "settled"}


def build_memory_projection(storage: Any, project_id: str) -> dict[str, Any]:
    """Build deterministic long-memory projection from state + commits.

    This is backend-only and intentionally model-free.  It gives the writer
    pipeline a compact, stable memory scratchpad similar to Tianming's derived
    state/summary/memory projections without adding a new UI surface.
    """
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    paths = storage.paths(project_id)
    commits = _load_commits(paths)
    chapters = storage.list_chapters(project_id)
    latest = int(state.get("latest_chapter") or 0)

    active_characters = []
    for name, item in sorted((state.get("characters") or {}).items(), key=lambda kv: str(kv[0])):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("state") or "active")
        if status in CLOSED_STATUS:
            continue
        active_characters.append({
            "name": str(item.get("name") or name),
            "id": str(item.get("id") or ""),
            "aliases": item.get("aliases") or [],
            "location": str(item.get("location") or ""),
            "faction": str(item.get("faction") or ""),
            "status": status,
            "last_seen_chapter": item.get("last_seen_chapter") or item.get("last_chapter") or "",
            "notes": _first_nonempty([item.get("notes"), item.get("note"), item.get("summary")]),
        })

    open_foreshadows = _open_mapping(state.get("foreshadows") or {})
    open_conflicts = _open_mapping(state.get("conflicts") or {})
    open_secrets = _open_mapping(state.get("secrets") or {})
    open_deadlines = _open_mapping(state.get("deadlines") or {})

    chapter_summaries = []
    summaries = state.get("chapter_summaries") or {}
    titles = state.get("chapter_titles") or {}
    for key in sorted(summaries, key=lambda x: int(x) if str(x).isdigit() else 0):
        chapter_summaries.append({"chapter_no": int(key) if str(key).isdigit() else key, "title": titles.get(str(key)) or "", "summary": summaries.get(key) or summaries.get(str(key)) or ""})

    recent_commits = []
    for commit in commits[-12:]:
        recent_commits.append({
            "chapter_no": commit.get("chapter_no"),
            "title": commit.get("chapter_title"),
            "summary": commit.get("summary") or "",
            "commit_id": commit.get("commit_id") or "",
        })

    risks = []
    for name, item in open_foreshadows.items():
        first = _to_int(item.get("introduced_chapter") or item.get("first_seen_chapter") or item.get("chapter_no"), latest)
        if latest and first and latest - first >= 30:
            risks.append({"type": "long_open_foreshadow", "target": name, "message": f"伏笔《{name}》已开放 {latest - first} 章，写作时需要推进或回收。"})
    for row in active_characters:
        if not row.get("location"):
            risks.append({"type": "missing_character_location", "target": row.get("name"), "message": f"角色《{row.get('name')}》缺少当前位置，容易写乱走位。"})
    if chapters and latest and latest < max(int(x.get("chapterNo") or 0) for x in chapters):
        risks.append({"type": "state_behind_chapters", "target": latest, "message": "story_state.latest_chapter 落后于正式章节文件，请先运行 doctor/ssot。"})

    projection = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "project_id": project_id,
        "latest_chapter": latest,
        "counts": {
            "chapters": len(chapters),
            "active_characters": len(active_characters),
            "open_foreshadows": len(open_foreshadows),
            "open_conflicts": len(open_conflicts),
            "open_secrets": len(open_secrets),
            "open_deadlines": len(open_deadlines),
            "risks": len(risks),
        },
        "active_characters": active_characters,
        "open_foreshadows": open_foreshadows,
        "open_conflicts": open_conflicts,
        "open_secrets": open_secrets,
        "open_deadlines": open_deadlines,
        "recent_commits": recent_commits,
        "chapter_summaries": chapter_summaries[-30:],
        "milestones": (state.get("milestones") or [])[-60:],
        "risks": risks,
    }

    out_dir = ensure_dir(Path(paths.control) / "memory")
    json_path = write_json(out_dir / "project_memory.json", projection)
    md_path = write_text(out_dir / "project_memory.md", memory_markdown(projection))
    scratch_path = write_text(out_dir / "memory_scratchpad.md", scratchpad_markdown(projection))
    projection["paths"] = {"json": str(json_path), "markdown": str(md_path), "scratchpad": str(scratch_path)}
    write_json(out_dir / "project_memory.json", projection)
    return projection


def load_or_build_memory(storage: Any, project_id: str) -> dict[str, Any]:
    path = Path(storage.paths(project_id).control) / "memory" / "project_memory.json"
    data = read_json(path, {}) or {}
    if isinstance(data, dict) and data.get("schema_version"):
        return data
    return build_memory_projection(storage, project_id)


def memory_markdown(projection: dict[str, Any]) -> str:
    lines = ["# 项目长期记忆", "", f"- 生成时间：{projection.get('generated_at')}", f"- 最新章节：{projection.get('latest_chapter') or 0}", ""]
    counts = projection.get("counts") or {}
    lines += ["## 指标", ""]
    for key, value in counts.items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## 活跃角色", ""]
    for item in (projection.get("active_characters") or [])[:80]:
        tail = []
        if item.get("location"):
            tail.append(f"位置={item.get('location')}")
        if item.get("faction"):
            tail.append(f"势力={item.get('faction')}")
        if item.get("status"):
            tail.append(f"状态={item.get('status')}")
        line = f"- {item.get('name')}"
        if tail:
            line += "（" + "；".join(tail) + "）"
        if item.get("notes"):
            line += f"：{item.get('notes')}"
        lines.append(line)
    lines += ["", "## 开放伏笔", ""]
    _append_mapping(lines, projection.get("open_foreshadows") or {})
    lines += ["", "## 开放冲突", ""]
    _append_mapping(lines, projection.get("open_conflicts") or {})
    lines += ["", "## 风险提醒", ""]
    risks = projection.get("risks") or []
    if not risks:
        lines.append("暂无。")
    for item in risks:
        lines.append(f"- [{item.get('type')}] {item.get('message')}")
    lines += ["", "## 近期 Commit", ""]
    for item in projection.get("recent_commits") or []:
        lines.append(f"- 第{item.get('chapter_no')}章 {item.get('title') or ''}：{item.get('summary') or ''}")
    return "\n".join(lines).rstrip() + "\n"


def scratchpad_markdown(projection: dict[str, Any]) -> str:
    lines = ["# 写作记忆便笺", "", "下面内容会被后端上下文包引用，用于提醒模型保持连贯。", ""]
    risks = projection.get("risks") or []
    if risks:
        lines.append("## 必须注意")
        for item in risks[:12]:
            lines.append(f"- {item.get('message')}")
        lines.append("")
    lines.append("## 角色状态")
    for item in (projection.get("active_characters") or [])[:30]:
        desc = " / ".join(x for x in [str(item.get("location") or ""), str(item.get("faction") or ""), str(item.get("status") or "")] if x)
        lines.append(f"- {item.get('name')}: {desc or '待补充'}")
    lines.append("")
    lines.append("## 未结伏笔")
    _append_mapping(lines, projection.get("open_foreshadows") or {}, limit=30)
    lines.append("")
    lines.append("## 未结冲突")
    _append_mapping(lines, projection.get("open_conflicts") or {}, limit=30)
    return "\n".join(lines).rstrip() + "\n"


def _open_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for name, item in mapping.items():
        if not isinstance(item, dict):
            out[str(name)] = {"status": item}
            continue
        status = str(item.get("status") or item.get("state") or "open")
        if status in CLOSED_STATUS:
            continue
        out[str(name)] = item
    return out


def _append_mapping(lines: list[str], mapping: dict[str, Any], limit: int = 80) -> None:
    if not mapping:
        lines.append("暂无。")
        return
    for name, item in list(mapping.items())[:limit]:
        if isinstance(item, dict):
            status = item.get("status") or item.get("state") or ""
            note = _first_nonempty([item.get("note"), item.get("notes"), item.get("summary"), item.get("description")])
            parts = [str(x) for x in [status, note] if x]
            lines.append(f"- {name}" + ("：" + "；".join(parts) if parts else ""))
        else:
            lines.append(f"- {name}: {item}")


def _load_commits(paths: Any) -> list[dict[str, Any]]:
    root = Path(paths.commits)
    rows = []
    for path in sorted(root.glob("第*章_commit.json")):
        data = read_json(path, {}) or {}
        if isinstance(data, dict):
            rows.append(data)
    return rows


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
