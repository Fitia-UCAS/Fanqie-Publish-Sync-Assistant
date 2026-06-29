from __future__ import annotations

import json
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_models import CONTROL_ENTITY_BUCKETS, now_iso
from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text

OPEN_STATUS = {"open", "active", "新增", "推进", "未收", "进行中", "隐藏", "hidden", "待回收"}
CLOSED_STATUS = {"closed", "resolved", "回收", "已回收", "完成", "done", "payoff"}
ENTITY_CN = {
    "characters": "角色",
    "locations": "地点",
    "factions": "势力",
    "items": "物品",
    "foreshadows": "伏笔",
    "conflicts": "冲突",
    "secrets": "秘密",
    "pledges": "誓约",
    "deadlines": "截止约束",
}
REF_FIELDS = {
    "characters": [("location", "locations", "位置"), ("faction", "factions", "势力")],
    "factions": [("members", "characters", "成员")],
    "items": [("owner", "characters", "拥有者")],
    "foreshadows": [("related_characters", "characters", "相关角色"), ("characters", "characters", "相关角色"), ("involved_characters", "characters", "相关角色")],
    "conflicts": [("participants", "characters", "参与角色"), ("characters", "characters", "参与角色"), ("factions", "factions", "参与势力")],
    "secrets": [("knowers", "characters", "知情人")],
    "pledges": [("characters", "characters", "相关角色")],
}


def audit_project(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.paths(project_id)
    root = Path(paths.root)
    state = storage.load_state(project_id)
    chapters = storage.list_chapters(project_id)
    blueprints = _load_blueprints(paths)
    issues: list[dict[str, Any]] = []
    todos: list[dict[str, Any]] = []

    _audit_entities(state, issues, todos)
    _audit_blueprints(state, blueprints, chapters, issues, todos)
    _audit_chapters(storage, project_id, chapters, blueprints, issues, todos)
    _audit_debts(state, issues, todos)
    _audit_runtime_files(paths, issues, todos)

    relations = _build_dependency_index(state, blueprints)
    risk = _risk_score(issues)
    report = {
        "ok": not any(i.get("level") == "error" for i in issues),
        "audited_at": now_iso(),
        "risk_score": risk,
        "issue_count": len(issues),
        "todo_count": len(todos),
        "issues": issues,
        "todos": todos,
        "metrics": {
            "chapters": len(chapters),
            "blueprints": len(blueprints),
            "characters": len(state.get("characters") or {}),
            "locations": len(state.get("locations") or {}),
            "factions": len(state.get("factions") or {}),
            "foreshadows_open": _count_open(state.get("foreshadows") or {}),
            "conflicts_open": _count_open(state.get("conflicts") or {}),
            "relations": len(relations),
        },
        "dependency_index": relations,
    }
    report_dir = ensure_dir(root / "writer_control" / "reports")
    write_json(report_dir / "last_backend_audit.json", report)
    write_text(report_dir / "last_backend_audit.md", audit_markdown(report))
    write_text(report_dir / "todo.md", todo_markdown(todos))
    write_json(root / "writer_control" / "relations" / "dependency_index.json", {"updated_at": now_iso(), "relations": relations})
    return report


def make_snapshot(storage: Any, project_id: str, reason: str = "manual") -> dict[str, Any]:
    paths = storage.paths(project_id)
    root = Path(paths.root)
    out_dir = ensure_dir(root / "writer_control" / "snapshots")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"snapshot_{stamp}_{_safe(reason)}.zip"
    include_dirs = ["writer_control", "chapters", "blueprints", "commits", "reviews", "runtime", "artifacts", "validation"]
    include_files = ["project.json", "story_config.json", "story_state.json"]
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in include_files:
            p = root / name
            if p.exists() and p.is_file():
                zf.write(p, p.relative_to(root))
        for name in include_dirs:
            base = root / name
            if not base.exists():
                continue
            for p in base.rglob("*"):
                if p.is_file() and "snapshots" not in p.parts:
                    zf.write(p, p.relative_to(root))
    manifest = {"ok": True, "created_at": now_iso(), "reason": reason, "path": str(out), "size": out.stat().st_size}
    write_json(out_dir / "last_snapshot.json", manifest)
    return manifest


def impact_report(storage: Any, project_id: str, target: str = "") -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.paths(project_id)
    state = storage.load_state(project_id)
    blueprints = _load_blueprints(paths)
    relations = _build_dependency_index(state, blueprints)
    target_norm = str(target or "").strip()
    hits = []
    for row in relations:
        if not target_norm or target_norm in {str(row.get("source")), str(row.get("target"))} or target_norm == str(row.get("source_id")) or target_norm == str(row.get("target_id")):
            hits.append(row)
    affected_chapters = sorted({int(r.get("chapter_no") or 0) for r in hits if int(r.get("chapter_no") or 0) > 0})
    affected_entities = sorted({str(r.get("source")) for r in hits if r.get("source")} | {str(r.get("target")) for r in hits if r.get("target")})
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "target": target_norm,
        "relation_count": len(hits),
        "affected_chapters": affected_chapters,
        "affected_entities": affected_entities,
        "relations": hits,
    }
    report_dir = ensure_dir(Path(paths.root) / "writer_control" / "reports")
    write_json(report_dir / "last_impact_report.json", report)
    write_text(report_dir / "last_impact_report.md", impact_markdown(report))
    return report


def audit_markdown(report: dict[str, Any]) -> str:
    lines = ["# 后端体检报告", "", f"- 时间：{report.get('audited_at')}", f"- 风险分：{report.get('risk_score')}", f"- 问题数：{report.get('issue_count')}", ""]
    metrics = report.get("metrics") or {}
    if metrics:
        lines += ["## 指标", ""]
        for k, v in metrics.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    lines += ["## 问题", ""]
    issues = report.get("issues") or []
    if not issues:
        lines.append("暂未发现问题。")
    for item in issues:
        lines.append(f"- [{item.get('level', 'info')}] {item.get('type', '')}: {item.get('message', '')}")
    lines += ["", "## 待办", ""]
    todos = report.get("todos") or []
    if not todos:
        lines.append("暂无待办。")
    for idx, item in enumerate(todos, start=1):
        lines.append(f"{idx}. {item.get('title', '')} — {item.get('action', '')}")
    return "\n".join(lines).rstrip() + "\n"


def todo_markdown(todos: list[dict[str, Any]]) -> str:
    lines = ["# 网文项目待办", ""]
    if not todos:
        lines.append("- [ ] 暂无待办。")
    for item in todos:
        lines.append(f"- [ ] {item.get('title', '')}")
        if item.get("action"):
            lines.append(f"  - 建议：{item.get('action')}")
        if item.get("path"):
            lines.append(f"  - 文件：`{item.get('path')}`")
    return "\n".join(lines).rstrip() + "\n"


def impact_markdown(report: dict[str, Any]) -> str:
    lines = ["# 影响分析", "", f"- 目标：{report.get('target') or '全部'}", f"- 关系数：{report.get('relation_count')}", ""]
    chapters = report.get("affected_chapters") or []
    entities = report.get("affected_entities") or []
    lines += ["## 受影响章节", "", ", ".join(f"第{x}章" for x in chapters) if chapters else "暂无。", ""]
    lines += ["## 受影响实体", "", ", ".join(entities[:80]) if entities else "暂无。", ""]
    lines += ["## 关系明细", ""]
    for row in (report.get("relations") or [])[:200]:
        chapter = f"第{row.get('chapter_no')}章 " if row.get("chapter_no") else ""
        lines.append(f"- {chapter}{row.get('source_type')}:{row.get('source')} --{row.get('relation')}--> {row.get('target_type')}:{row.get('target')}")
    return "\n".join(lines).rstrip() + "\n"


def _audit_entities(state: dict[str, Any], issues: list[dict[str, Any]], todos: list[dict[str, Any]]) -> None:
    ids = Counter()
    aliases = defaultdict(list)
    for bucket in CONTROL_ENTITY_BUCKETS:
        mapping = state.get(bucket) or {}
        if not isinstance(mapping, dict):
            issues.append(_issue("error", "state_shape", f"{bucket} 必须是对象。"))
            continue
        for name, item in mapping.items():
            if not isinstance(item, dict):
                issues.append(_issue("warning", "entity_shape", f"{ENTITY_CN.get(bucket, bucket)}《{name}》不是对象。"))
                continue
            entity_id = str(item.get("id") or "").strip()
            if not entity_id:
                issues.append(_issue("warning", "entity_id", f"{ENTITY_CN.get(bucket, bucket)}《{name}》缺少 id。"))
                todos.append(_todo(f"补齐《{name}》ID", f"在 writer_control/entities/{bucket}.md 中为《{name}》添加 - id:"))
            else:
                ids[entity_id] += 1
            for alias in _as_list(item.get("aliases")):
                aliases[str(alias)].append(str(name))
            for field, target_bucket, label in REF_FIELDS.get(bucket, []):
                known = state.get(target_bucket) or {}
                for value in _as_list(item.get(field)):
                    if str(value).strip() and str(value).strip() not in known:
                        issues.append(_issue("warning", "unknown_reference", f"{ENTITY_CN.get(bucket, bucket)}《{name}》的{label}《{value}》未登记。"))
    for entity_id, count in ids.items():
        if count > 1:
            issues.append(_issue("error", "duplicate_id", f"实体 id `{entity_id}` 重复 {count} 次。"))
    for alias, names in aliases.items():
        if alias and len(set(names)) > 1:
            issues.append(_issue("warning", "alias_collision", f"别名《{alias}》同时指向：{', '.join(sorted(set(names)))}。"))


def _audit_blueprints(state: dict[str, Any], blueprints: dict[int, dict[str, Any]], chapters: list[dict[str, Any]], issues: list[dict[str, Any]], todos: list[dict[str, Any]]) -> None:
    known = {"required_characters": state.get("characters") or {}, "required_locations": state.get("locations") or {}, "required_factions": state.get("factions") or {}}
    label = {"required_characters": "角色", "required_locations": "地点", "required_factions": "势力"}
    chapter_numbers = {int(row.get("chapterNo") or 0) for row in chapters}
    for no, bp in blueprints.items():
        if not str(bp.get("goal") or "").strip():
            issues.append(_issue("warning", "blueprint_goal", f"第 {no} 章蓝图缺少章节目标。"))
        if not (bp.get("must_cover_nodes") or []):
            issues.append(_issue("warning", "blueprint_nodes", f"第 {no} 章蓝图没有必达节点。"))
        if chapter_numbers and no not in chapter_numbers and no < max(chapter_numbers):
            issues.append(_issue("info", "blueprint_without_chapter", f"第 {no} 章有蓝图但没有正文。"))
        for field, mapping in known.items():
            for value in _as_list(bp.get(field)):
                if str(value).strip() and str(value).strip() not in mapping:
                    issues.append(_issue("warning", "blueprint_unknown_entity", f"第 {no} 章蓝图引用的{label[field]}《{value}》未登记。"))
                    todos.append(_todo(f"登记{label[field]}《{value}》", f"在对应 entities Markdown 中补建《{value}》。"))


def _audit_chapters(storage: Any, project_id: str, chapters: list[dict[str, Any]], blueprints: dict[int, dict[str, Any]], issues: list[dict[str, Any]], todos: list[dict[str, Any]]) -> None:
    numbers = sorted(int(row.get("chapterNo") or 0) for row in chapters)
    if numbers:
        missing = [n for n in range(numbers[0], numbers[-1] + 1) if n not in numbers]
        for no in missing[:50]:
            issues.append(_issue("warning", "chapter_gap", f"缺少第 {no} 章正文。"))
    for row in chapters:
        no = int(row.get("chapterNo") or 0)
        path = Path(row.get("path") or "")
        text = read_text_auto(path) if path.exists() else ""
        if len(text.strip()) < 300:
            issues.append(_issue("warning", "short_chapter", f"第 {no} 章正文偏短。"))
        bp = blueprints.get(no) or {}
        if bp:
            for node in _as_list(bp.get("must_cover_nodes")):
                if node and not _rough_contains(text, node):
                    issues.append(_issue("warning", "must_node_maybe_missing", f"第 {no} 章可能未覆盖必达节点：{node}"))
            for forbidden in _as_list(bp.get("forbidden_zones")):
                if forbidden and _rough_contains(text, forbidden):
                    issues.append(_issue("warning", "forbidden_maybe_hit", f"第 {no} 章可能触发禁区：{forbidden}"))
        else:
            todos.append(_todo(f"补第 {no} 章蓝图", f"创建 writer_control/blueprints/chapter_{no:04d}.md。"))


def _audit_debts(state: dict[str, Any], issues: list[dict[str, Any]], todos: list[dict[str, Any]]) -> None:
    latest = int(state.get("latest_chapter") or 0)
    for name, item in (state.get("foreshadows") or {}).items():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        due = _to_int(item.get("due_chapter"))
        first = _to_int(item.get("introduced_chapter") or item.get("first_seen_chapter"))
        if due and latest and due < latest and status not in CLOSED_STATUS:
            issues.append(_issue("warning", "foreshadow_overdue", f"伏笔《{name}》已超过计划回收章 {due}。"))
            todos.append(_todo(f"处理逾期伏笔《{name}》", "补推进、回收，或在 foreshadows.md 调整 due_chapter。"))
        elif first and latest and latest - first >= 30 and status in OPEN_STATUS:
            issues.append(_issue("info", "foreshadow_long_open", f"伏笔《{name}》已开启 {latest - first} 章。"))
    for name, item in (state.get("deadlines") or {}).items():
        if not isinstance(item, dict):
            continue
        due = _to_int(item.get("due_chapter"))
        status = str(item.get("status") or "").strip()
        if due and latest and due < latest and status not in CLOSED_STATUS:
            issues.append(_issue("warning", "deadline_overdue", f"截止约束《{name}》已逾期：due_chapter={due}。"))


def _audit_runtime_files(paths: Any, issues: list[dict[str, Any]], todos: list[dict[str, Any]]) -> None:
    root = Path(paths.root)
    for folder, label in [("commits", "Commit"), ("reviews", "Review")]:
        p = root / folder
        if not p.exists():
            continue
        bad = []
        for file in p.glob("*.json"):
            try:
                json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                bad.append(file.name)
        for name in bad[:30]:
            issues.append(_issue("error", "bad_json", f"{label} 文件无法读取：{name}"))


def _load_blueprints(paths: Any) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    roots = [Path(paths.blueprints), Path(paths.control) / "blueprints"]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            data = read_json(path, None)
            if not isinstance(data, dict):
                continue
            no = _to_int(data.get("chapter_no") or data.get("chapterNo")) or _chapter_from_name(path.name)
            if no:
                out[no] = data
    return out


def _build_dependency_index(state: dict[str, Any], blueprints: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(source_type: str, source: str, relation: str, target_type: str, target: str, chapter_no: int = 0, note: str = "") -> None:
        if source and target:
            rows.append({"source_type": source_type, "source": source, "relation": relation, "target_type": target_type, "target": target, "chapter_no": chapter_no, "note": note})

    for bucket, mapping in ((k, state.get(k) or {}) for k in CONTROL_ENTITY_BUCKETS):
        for name, item in mapping.items():
            if not isinstance(item, dict):
                continue
            for field, target_bucket, label in REF_FIELDS.get(bucket, []):
                for value in _as_list(item.get(field)):
                    add(bucket, str(name), field, target_bucket, str(value))
            for rel in item.get("relations") or []:
                if isinstance(rel, dict):
                    add(bucket, str(name), str(rel.get("type") or "related_to"), "characters", str(rel.get("target") or ""), note=str(rel.get("note") or ""))
    for no, bp in blueprints.items():
        for field, target_bucket in [("required_characters", "characters"), ("required_locations", "locations"), ("required_factions", "factions"), ("foreshadow_actions", "foreshadows")]:
            for value in _as_list(bp.get(field)):
                if isinstance(value, dict):
                    value = value.get("id") or value.get("name") or value.get("target") or ""
                add("blueprint", f"chapter_{no:04d}", field, target_bucket, str(value), chapter_no=no)
    return rows


def _risk_score(issues: list[dict[str, Any]]) -> int:
    score = 0
    for item in issues:
        level = item.get("level")
        score += 20 if level == "error" else 6 if level == "warning" else 1
    return min(100, score)


def _count_open(mapping: dict[str, Any]) -> int:
    count = 0
    for item in mapping.values():
        if isinstance(item, dict) and str(item.get("status") or "").strip() not in CLOSED_STATUS:
            count += 1
    return count


def _issue(level: str, typ: str, message: str) -> dict[str, Any]:
    return {"level": level, "type": typ, "message": message}


def _todo(title: str, action: str, path: str = "") -> dict[str, Any]:
    return {"title": title, "action": action, "path": path}


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return list(value.values())
    return [x.strip() for x in re.split(r"[,，、;；]", str(value)) if x.strip()]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _chapter_from_name(name: str) -> int:
    m = re.search(r"(?:chapter_|第)(\d+)", name)
    return int(m.group(1)) if m else 0


def _rough_contains(text: str, needle: str) -> bool:
    needle = str(needle or "").strip()
    if not needle:
        return True
    if needle in text:
        return True
    parts = [p for p in re.split(r"[，,。；;、\s]+", needle) if len(p) >= 2]
    if not parts:
        return False
    return sum(1 for p in parts[:6] if p in text) >= max(1, min(2, len(parts)))


def _safe(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value or "manual").strip("_")[:32] or "manual"
