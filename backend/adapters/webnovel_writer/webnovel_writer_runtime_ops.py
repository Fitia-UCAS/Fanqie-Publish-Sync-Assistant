from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json, read_jsonl
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def control_reports_dir(storage: Any, project_id: str, *parts: str) -> Path:
    root = Path(storage.paths(project_id).control) / "reports"
    for part in parts:
        root = root / part
    root.mkdir(parents=True, exist_ok=True)
    return root


def report_write(root: Path, stem: str, data: dict[str, Any], markdown: str | None = None) -> dict[str, str]:
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / f"{stem}.json"
    write_json(json_path, data)
    paths = {"json": str(json_path)}
    if markdown is not None:
        md_path = root / f"{stem}.md"
        write_text(md_path, markdown)
        paths["markdown"] = str(md_path)
    return paths


def where_report(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "project_id": project_id,
        "root": str(Path(paths.root).resolve()),
        "exists": Path(paths.root).exists(),
        "paths": paths.to_dict(),
    }
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "runtime"), "last_where", report, _where_md(report))
    return report


def use_project(storage: Any, project_id: str, workspace: str = "") -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    workspace_path = Path(workspace).expanduser() if workspace else Path.cwd()
    binding = {
        "ok": True,
        "bound_at": now_iso(),
        "workspace": str(workspace_path.resolve()),
        "project_id": project_id,
        "project_root": str(Path(paths.root).resolve()),
    }
    out_dir = Path(paths.control) / "bindings"
    out_dir.mkdir(parents=True, exist_ok=True)
    binding_path = write_json(out_dir / "current_project.json", binding)
    # Workspace sidecar is useful for CLI workflows; if it fails, the project binding still exists.
    try:
        write_json(workspace_path / ".webnovel_current_project.json", binding)
        binding["workspace_binding"] = str(workspace_path / ".webnovel_current_project.json")
    except Exception as exc:
        binding["workspace_binding_error"] = str(exc)
    binding["paths_written"] = {"json": str(binding_path)}
    return binding


def write_gate_report(storage: Any, project_id: str, chapter_no: int, stage: str) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    paths = storage.paths(project_id)
    issues: list[dict[str, Any]] = []
    stage = (stage or "prewrite").strip().lower()
    blueprint = storage.load_blueprint_json(project_id, chapter_no)
    chapter_path, chapter_text = storage.load_chapter(project_id, chapter_no)
    commit_path = Path(paths.commits) / f"第{chapter_no:04d}章_commit.json"
    review_path = Path(paths.reviews) / f"第{chapter_no:04d}章_review.json"
    context_path = Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json"

    if stage == "prewrite":
        if not blueprint:
            issues.append(_issue("warning", "missing_blueprint", f"第 {chapter_no} 章缺少蓝图。"))
        if chapter_no > 1 and not storage.load_chapter(project_id, chapter_no - 1)[1]:
            issues.append(_issue("warning", "missing_previous_chapter", f"上一章第 {chapter_no - 1} 章正文缺失。"))
        if not context_path.exists():
            issues.append(_issue("info", "context_not_generated", "本章上下文包尚未生成，可先运行 context/contract。"))
    elif stage == "precommit":
        if not chapter_text.strip():
            issues.append(_issue("error", "missing_chapter_text", "提交前正文不存在。"))
        if not review_path.exists():
            issues.append(_issue("warning", "missing_review", "提交前缺少 review 结果。"))
        artifact_dir = Path(paths.artifacts) / f"第{chapter_no:04d}章"
        required = ["fulfillment", "extraction", "consistency", "quality"]
        names = "\n".join(p.name for p in artifact_dir.glob("*.json")) if artifact_dir.exists() else ""
        for token in required:
            if token not in names:
                issues.append(_issue("warning", f"missing_{token}_artifact", f"提交前缺少 {token} artifact。"))
    elif stage == "postcommit":
        if not commit_path.exists():
            issues.append(_issue("error", "missing_commit", "提交后 commit 文件不存在。"))
        if str(chapter_no) not in (state.get("chapter_summaries") or {}):
            issues.append(_issue("error", "summary_not_projected", "story_state 未投影本章摘要。"))
        if (state.get("chapter_status") or {}).get(str(chapter_no)) != "committed":
            issues.append(_issue("error", "chapter_not_committed", "story_state.chapter_status 未标记 committed。"))
    else:
        issues.append(_issue("error", "unknown_stage", f"未知 write-gate 阶段：{stage}"))

    report = {
        "ok": not any(i["level"] == "error" for i in issues),
        "generated_at": now_iso(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "stage": stage,
        "issues": issues,
        "summary": {"error": sum(1 for i in issues if i["level"] == "error"), "warning": sum(1 for i in issues if i["level"] == "warning"), "info": sum(1 for i in issues if i["level"] == "info")},
    }
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "gates"), f"chapter_{chapter_no:04d}_{stage}_gate", report, _gate_md(report))
    return report


def story_events_report(storage: Any, project_id: str, chapter_no: int = 0, health: bool = False) -> dict[str, Any]:
    events = storage.read_events(project_id)
    rows = []
    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            rows.append({"index": idx, "invalid": True, "raw": event})
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        ch = int(payload.get("chapter_no") or payload.get("chapterNo") or 0) if str(payload.get("chapter_no") or payload.get("chapterNo") or "0").isdigit() else 0
        if chapter_no and ch != chapter_no:
            continue
        rows.append({"index": idx, "event_id": event.get("event_id"), "type": event.get("type"), "at": event.get("at"), "chapter_no": ch, "fingerprint": event.get("fingerprint"), "prev_fingerprint": event.get("prev_fingerprint"), "payload": payload})
    issues: list[dict[str, Any]] = []
    if health:
        seen = set()
        prev = ""
        for idx, event in enumerate(events):
            if not isinstance(event, dict):
                issues.append(_issue("error", "invalid_event", f"事件 #{idx} 不是对象。"))
                continue
            eid = str(event.get("event_id") or "")
            if eid in seen:
                issues.append(_issue("warning", "duplicate_event_id", f"重复 event_id：{eid}"))
            seen.add(eid)
            if str(event.get("prev_fingerprint") or "") != prev:
                issues.append(_issue("error", "event_chain_break", f"事件链在 #{idx} 处断裂。"))
            prev = str(event.get("fingerprint") or "")
    report = {"ok": not any(i["level"] == "error" for i in issues), "generated_at": now_iso(), "project_id": project_id, "chapter_no": chapter_no or None, "health": health, "event_count": len(rows), "events": rows, "issues": issues}
    stem = "story_events_health" if health else (f"chapter_{chapter_no:04d}_story_events" if chapter_no else "all_story_events")
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "events"), stem, report, _events_md(report))
    return report


def run_log(storage: Any, project_id: str, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    log_dir = Path(paths.control) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run_last.log"
    clean = _sanitize_payload(payload or {})
    line = json.dumps({"at": now_iso(), "event": event or "manual", "payload": clean}, ensure_ascii=False)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return {"ok": True, "path": str(log_path), "event": event or "manual"}


def run_ledger(storage: Any, project_id: str, action: str, chapter_no: int = 0, step: str = "", status: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    ledger_dir = Path(paths.control) / "run_ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / f"chapter_{chapter_no:04d}_ledger.json" if chapter_no else ledger_dir / "project_ledger.json"
    ledger = read_json(ledger_path, {}) or {}
    ledger.setdefault("schema_version", 1)
    ledger.setdefault("project_id", project_id)
    ledger.setdefault("chapter_no", chapter_no or None)
    ledger.setdefault("steps", [])
    action = (action or "summary").strip().lower()
    if action in {"record", "record-write-step"}:
        item = {"at": now_iso(), "step": step or "manual", "status": status or "unknown", "payload": _sanitize_payload(payload or {})}
        ledger["steps"].append(item)
        write_json(ledger_path, ledger)
    elif action in {"write-resume", "resume"}:
        ledger["resume_advice"] = _resume_advice(storage, project_id, chapter_no, ledger)
        write_json(ledger_path, ledger)
    else:
        if ledger_path.exists():
            ledger = read_json(ledger_path, {}) or ledger
    report = {"ok": True, "generated_at": now_iso(), "action": action, "ledger": ledger, "path": str(ledger_path)}
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "run_ledger"), f"chapter_{chapter_no:04d}_{action}" if chapter_no else f"project_{action}", report, _ledger_md(report))
    return report


def user_report(storage: Any, project_id: str, stage: str = "write", chapter_no: int = 0) -> dict[str, Any]:
    paths = storage.paths(project_id)
    status = "已完成"
    produced: list[str] = []
    problems: list[str] = []
    next_steps: list[str] = []
    stage = (stage or "write").strip().lower()
    if chapter_no:
        for label, path in [
            ("蓝图", Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.json"),
            ("正文", next(iter(sorted(Path(paths.chapters).glob(f"第{chapter_no:04d}章_*.txt"))), None) if Path(paths.chapters).exists() else None),
            ("Review", Path(paths.reviews) / f"第{chapter_no:04d}章_review.json"),
            ("Commit", Path(paths.commits) / f"第{chapter_no:04d}章_commit.json"),
            ("上下文包", Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json"),
        ]:
            if path and Path(path).exists():
                produced.append(f"{label}: {path}")
            else:
                problems.append(f"缺少{label}")
        if any("Commit" in p for p in problems):
            status = "部分完成" if produced else "未完成"
            next_steps.append("运行 review/heal 或重新 write 以生成可信 commit。")
    else:
        produced.append(f"项目根目录: {paths.root}")
        next_steps.append("运行 project-status / doctor / preflight 查看下一步。")
    if not problems and produced:
        next_steps.append("可以进入下一阶段。")
    report = {"ok": status in {"已完成", "部分完成"}, "generated_at": now_iso(), "project_id": project_id, "stage": stage, "chapter_no": chapter_no or None, "status": status, "produced": produced, "problems": problems, "next_steps": next_steps}
    stem = f"{stage}_chapter_{chapter_no:04d}_user_report" if chapter_no else f"{stage}_user_report"
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "user_reports"), stem, report, _user_report_md(report))
    return report


def update_state(storage: Any, project_id: str, patch: dict[str, Any], reason: str = "manual") -> dict[str, Any]:
    state = storage.load_state(project_id)
    before = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    _deep_merge(state, patch or {})
    path = storage.save_state(project_id, state)
    storage.append_event(project_id, "state_updated", {"reason": reason, "patch": patch})
    after = hashlib.sha1(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "reason": reason, "before_hash": before, "after_hash": after, "state_path": str(path), "patch": patch}
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "state"), "last_update_state", report, _state_md(report))
    return report


def archive_project(storage: Any, project_id: str, reason: str = "manual") -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    root = Path(paths.root)
    archive_dir = Path(paths.control) / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_base = archive_dir / f"project_archive_{stamp}_{_safe(reason)}"
    archive_path = shutil.make_archive(str(zip_base), "zip", root_dir=root)
    storage.append_event(project_id, "project_archived", {"reason": reason, "archive": archive_path})
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "reason": reason, "archive": archive_path}
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "archive"), "last_archive", report, _archive_md(report))
    return report



def backup_management(storage: Any, project_id: str, action: str = "create", reason: str = "manual", target: str = "") -> dict[str, Any]:
    """Reference-compatible backup management command: create/list/verify/restore-plan."""
    paths = storage.ensure_project_dirs(project_id)
    action = (action or "create").strip().lower().replace("_", "-")
    backup_dir = Path(paths.control) / "snapshots"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if action in {"", "create", "snapshot"}:
        archive_path, manifest = _make_project_zip(paths, backup_dir, f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe(reason)}", include_control=True)
        manifest.update({"ok": True, "command": "backup", "action": "create", "reason": reason, "path": str(archive_path)})
        write_json(backup_dir / "last_snapshot.json", manifest)
        storage.append_event(project_id, "backup_created", {"reason": reason, "path": str(archive_path), "size": manifest.get("size")})
        report = manifest
    elif action in {"list", "ls"}:
        items = _list_archives(backup_dir)
        report = {"ok": True, "command": "backup", "action": "list", "count": len(items), "items": items}
    elif action in {"verify", "check"}:
        selected = _select_archive(backup_dir, target)
        report = _verify_archive(selected)
        report.update({"command": "backup", "action": "verify"})
    elif action in {"restore", "restore-plan", "plan"}:
        selected = _select_archive(backup_dir, target)
        report = _restore_plan(paths, selected)
        report.update({"command": "backup", "action": action})
    else:
        report = {"ok": False, "command": "backup", "action": action, "errors": [f"未知 backup action: {action}"]}
    report.setdefault("generated_at", now_iso())
    report.setdefault("project_id", project_id)
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "backup"), f"backup_{action.replace('-', '_')}", report, _backup_mgmt_md(report))
    return report


def archive_management(storage: Any, project_id: str, action: str = "create", reason: str = "manual", target: str = "") -> dict[str, Any]:
    """Reference-compatible archive management command: create/list/verify/restore-plan."""
    paths = storage.ensure_project_dirs(project_id)
    action = (action or "create").strip().lower().replace("_", "-")
    archive_dir = Path(paths.control) / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    if action in {"", "create", "archive"}:
        archive_path, manifest = _make_project_zip(paths, archive_dir, f"project_archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe(reason)}", include_control=True, full=True)
        manifest.update({"ok": True, "command": "archive", "action": "create", "reason": reason, "archive": str(archive_path), "path": str(archive_path)})
        storage.append_event(project_id, "project_archived", {"reason": reason, "archive": str(archive_path), "size": manifest.get("size")})
        report = manifest
    elif action in {"list", "ls"}:
        items = _list_archives(archive_dir)
        report = {"ok": True, "command": "archive", "action": "list", "count": len(items), "items": items}
    elif action in {"verify", "check"}:
        selected = _select_archive(archive_dir, target)
        report = _verify_archive(selected)
        report.update({"command": "archive", "action": "verify"})
    elif action in {"restore", "restore-plan", "plan"}:
        selected = _select_archive(archive_dir, target)
        report = _restore_plan(paths, selected)
        report.update({"command": "archive", "action": action})
    else:
        report = {"ok": False, "command": "archive", "action": action, "errors": [f"未知 archive action: {action}"]}
    report.setdefault("generated_at", now_iso())
    report.setdefault("project_id", project_id)
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "archive"), f"archive_{action.replace('-', '_')}", report, _backup_mgmt_md(report))
    return report


def extract_context_report(storage: Any, project_id: str, chapter_no: int, context_payload: dict[str, Any]) -> dict[str, Any]:
    # The caller supplies already-generated context paths/data so this remains a thin report wrapper.
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "chapter_no": chapter_no, "context": context_payload}
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "context_extract"), f"chapter_{chapter_no:04d}_extract_context", report, _extract_context_md(report))
    return report


def memory_command(storage: Any, project_id: str, action: str, query: str = "", category: str = "", subject: str = "", status: str = "") -> dict[str, Any]:
    from backend.adapters.webnovel_writer.webnovel_writer_memory import build_memory_projection
    projection = build_memory_projection(storage, project_id)
    scratchpad = projection.get("scratchpad") if isinstance(projection.get("scratchpad"), list) else []
    action = (action or "stats").strip().lower()
    if action == "stats":
        data = {"total": len(scratchpad), "by_category": _counter(scratchpad, "category"), "by_status": _counter(scratchpad, "status")}
    elif action == "query":
        rows = []
        q = query.strip().lower()
        for item in scratchpad:
            text = json.dumps(item, ensure_ascii=False).lower()
            if q and q not in text:
                continue
            if category and str(item.get("category") or "") != category:
                continue
            if subject and str(item.get("subject") or "") != subject:
                continue
            if status and str(item.get("status") or "") != status:
                continue
            rows.append(item)
        data = {"count": len(rows), "items": rows}
    elif action == "dump":
        data = {"count": len(scratchpad), "items": scratchpad}
    elif action == "conflicts":
        groups: dict[str, list[Any]] = {}
        for item in scratchpad:
            key = f"{item.get('category')}::{item.get('subject')}::{item.get('key') or item.get('name') or ''}"
            if str(item.get("status") or "active") == "active":
                groups.setdefault(key, []).append(item)
        data = {"count": sum(1 for v in groups.values() if len(v) > 1), "conflicts": {k: v for k, v in groups.items() if len(v) > 1}}
    elif action == "bootstrap":
        data = {"message": "已从当前 state / commits / summaries 重新生成 memory projection。", "projection": projection}
    elif action == "update":
        # Local projects use commits as the source of truth; explicit update records an event for traceability.
        storage.append_event(project_id, "memory_update_requested", {"query": query, "category": category, "subject": subject, "status": status})
        data = {"message": "已记录 memory update 请求；下次 memory/bootstrap 会重建投影。"}
    else:
        data = {"error": f"unknown memory action: {action}"}
    report = {"ok": "error" not in data, "generated_at": now_iso(), "project_id": project_id, "action": action, "data": data, "memory_paths": projection.get("paths")}
    report["paths_written"] = report_write(control_reports_dir(storage, project_id, "memory"), f"memory_{action}", report, _memory_cmd_md(report))
    return report



def _make_project_zip(paths: Any, out_dir: Path, stem: str, include_control: bool = True, full: bool = False) -> tuple[Path, dict[str, Any]]:
    root = Path(paths.root)
    out = out_dir / f"{stem}.zip"
    include_files = ["project.json", "story_config.json", "story_state.json"]
    include_dirs = ["chapters", "blueprints", "commits", "reviews", "runtime", "artifacts", "validation", "exports"]
    if include_control:
        include_dirs.append("writer_control")
    written = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        candidates: list[Path] = []
        if full:
            candidates = [p for p in root.rglob("*") if p.is_file()]
        else:
            for name in include_files:
                p = root / name
                if p.exists() and p.is_file():
                    candidates.append(p)
            for name in include_dirs:
                base = root / name
                if base.exists():
                    candidates.extend(p for p in base.rglob("*") if p.is_file())
        for p in candidates:
            rel = p.relative_to(root)
            parts = set(rel.parts)
            if ".pytest_cache" in parts or "__pycache__" in parts:
                continue
            if "snapshots" in parts or "archives" in parts:
                continue
            if p.resolve() == out.resolve():
                continue
            zf.write(p, rel)
            written += 1
    return out, {"file_count": written, "size": out.stat().st_size, "sha256": _file_sha(out)}


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _list_archives(folder: Path) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(folder.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        rows.append({"name": p.name, "path": str(p), "size": p.stat().st_size, "modified_at": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    return rows


def _select_archive(folder: Path, target: str = "") -> Path:
    raw = str(target or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = folder / raw
        return p
    items = sorted(folder.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True)
    return items[0] if items else folder / ""


def _verify_archive(path: Path) -> dict[str, Any]:
    if not path or not path.exists() or not path.is_file():
        return {"ok": False, "path": str(path), "errors": ["未找到可验证的 zip 文件。"]}
    errors = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad:
                errors.append(f"zip 内部文件损坏：{bad}")
            names = zf.namelist()
    except Exception as exc:
        errors.append(str(exc))
    return {"ok": not errors, "path": str(path), "size": path.stat().st_size, "sha256": _file_sha(path), "file_count": len(names), "sample": names[:30], "errors": errors}


def _restore_plan(paths: Any, archive_path: Path) -> dict[str, Any]:
    verify = _verify_archive(archive_path)
    if not verify.get("ok"):
        return {"ok": False, "path": str(archive_path), "errors": verify.get("errors") or ["备份不可用。"], "verify": verify}
    root = Path(paths.root)
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
    collisions = [name for name in names if (root / name).exists()]
    return {"ok": True, "path": str(archive_path), "file_count": len(names), "would_restore_to": str(root), "collisions": collisions[:200], "collision_count": len(collisions), "note": "为避免误覆盖，当前命令只生成恢复预案；需要恢复时先手动解压到临时目录核对。"}


def _backup_mgmt_md(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('command', 'backup')} {report.get('action', '')}", "", f"- ok: {report.get('ok')}", f"- time: {report.get('generated_at', '')}"]
    if report.get("path"):
        lines.append(f"- path: {report.get('path')}")
    if report.get("archive"):
        lines.append(f"- archive: {report.get('archive')}")
    if report.get("count") is not None:
        lines.append(f"- count: {report.get('count')}")
    errors = report.get("errors") or []
    if errors:
        lines += ["", "## Errors"] + [f"- {e}" for e in errors]
    items = report.get("items") or []
    if items:
        lines += ["", "## Items"]
        for item in items[:100]:
            lines.append(f"- {item.get('name')} ({item.get('size')} bytes) {item.get('modified_at')}")
    return "\n".join(lines).rstrip() + "\n"


def _issue(level: str, typ: str, message: str) -> dict[str, str]:
    return {"level": level, "type": typ, "message": message}


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _safe(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value or "manual")[:80]


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = json.loads(json.dumps(payload or {}, ensure_ascii=False, default=str))
    def clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                key = str(k)
                if any(token in key.lower() for token in ["key", "token", "secret", "password", "authorization"]):
                    out[key] = "***"
                else:
                    out[key] = clean(v)
            return out
        if isinstance(obj, list):
            return [clean(x) for x in obj]
        return obj
    return clean(raw)


def _resume_advice(storage: Any, project_id: str, chapter_no: int, ledger: dict[str, Any]) -> list[str]:
    paths = storage.paths(project_id)
    advice = []
    if chapter_no and not storage.load_blueprint_json(project_id, chapter_no):
        advice.append("缺少蓝图：先运行 plan --plan-type blueprint。")
    if chapter_no and not (Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json").exists():
        advice.append("缺少上下文包：运行 context 或 contract。")
    if chapter_no and not storage.load_chapter(project_id, chapter_no)[1]:
        advice.append("缺少正文：可从 write 步骤继续。")
    if chapter_no and not (Path(paths.commits) / f"第{chapter_no:04d}章_commit.json").exists():
        advice.append("缺少 commit：运行 review/heal 或重新 write。")
    if not advice:
        advice.append("可信产物齐全，不建议重复覆盖；如需重写请走 rewrite/invalidate。")
    return advice


def _counter(rows: list[Any], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if isinstance(row, dict):
            v = str(row.get(key) or "unknown")
            out[v] = out.get(v, 0) + 1
    return out


def _where_md(r: dict[str, Any]) -> str:
    return f"# 项目路径\n\n- root: `{r.get('root')}`\n- exists: {r.get('exists')}\n"


def _gate_md(r: dict[str, Any]) -> str:
    lines = [f"# Write Gate {r.get('stage')} 第{r.get('chapter_no')}章", "", f"ok: {r.get('ok')}", "", "## Issues"]
    for item in r.get("issues") or []:
        lines.append(f"- [{item.get('level')}] {item.get('type')}: {item.get('message')}")
    return "\n".join(lines) + "\n"


def _events_md(r: dict[str, Any]) -> str:
    lines = ["# Story Events", "", f"ok: {r.get('ok')}", f"event_count: {r.get('event_count')}", "", "## Issues"]
    for i in r.get("issues") or []:
        lines.append(f"- [{i.get('level')}] {i.get('message')}")
    lines += ["", "## Events"]
    for e in r.get("events") or []:
        lines.append(f"- #{e.get('index')} {e.get('type')} ch={e.get('chapter_no')} at={e.get('at')}")
    return "\n".join(lines) + "\n"


def _ledger_md(r: dict[str, Any]) -> str:
    ledger = r.get("ledger") or {}
    lines = ["# Run Ledger", "", f"action: {r.get('action')}", f"path: `{r.get('path')}`", "", "## Steps"]
    for s in ledger.get("steps") or []:
        lines.append(f"- {s.get('at')} {s.get('step')} => {s.get('status')}")
    if ledger.get("resume_advice"):
        lines += ["", "## Resume Advice"] + [f"- {x}" for x in ledger.get("resume_advice")]
    return "\n".join(lines) + "\n"


def _user_report_md(r: dict[str, Any]) -> str:
    return "\n".join(["# 最终报告", "", f"状态：**{r.get('status')}**", "", "## 产物", *[f"- {x}" for x in r.get("produced") or []], "", "## 问题", *[f"- {x}" for x in r.get("problems") or []], "", "## 下一步", *[f"- {x}" for x in r.get("next_steps") or []]]) + "\n"


def _state_md(r: dict[str, Any]) -> str:
    return f"# State Updated\n\n- reason: {r.get('reason')}\n- before: {r.get('before_hash')}\n- after: {r.get('after_hash')}\n"


def _archive_md(r: dict[str, Any]) -> str:
    return f"# Archive\n\n- reason: {r.get('reason')}\n- archive: `{r.get('archive')}`\n"


def _extract_context_md(r: dict[str, Any]) -> str:
    return f"# Extract Context 第{r.get('chapter_no')}章\n\n```json\n{json.dumps(r.get('context') or {}, ensure_ascii=False, indent=2)}\n```\n"


def _memory_cmd_md(r: dict[str, Any]) -> str:
    return f"# Memory {r.get('action')}\n\n```json\n{json.dumps(r.get('data') or {}, ensure_ascii=False, indent=2)}\n```\n"
