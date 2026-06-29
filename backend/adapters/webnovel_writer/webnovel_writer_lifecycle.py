from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import read_text_auto, write_text

PUBLISH_FINAL_STATES = {"published", "synced", "uploaded", "发布成功", "已发布"}


def lifecycle_report(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    chapters = {int(row.get("chapterNo") or 0): row for row in storage.list_chapters(project_id)}
    blueprints = {int(row.get("chapterNo") or 0): row for row in storage.list_blueprints(project_id)}
    rejected = _rejected_by_chapter(storage.list_rejected(project_id))
    commits = _commit_map(Path(paths.commits))
    reviews = _review_map(Path(paths.reviews))
    quality = _quality_map(Path(paths.artifacts))
    publication = _publication_map(state)
    max_no = max([0, int(state.get("latest_chapter") or 0), *chapters.keys(), *blueprints.keys(), *rejected.keys(), *commits.keys(), *reviews.keys()])
    rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    for no in range(1, max_no + 1):
        row = _chapter_lifecycle_row(no, chapters, blueprints, rejected, commits, reviews, quality, publication, state)
        rows.append(row)
        issues.extend(_row_issues(row))
    queues = {
        "ready_to_write": [r["chapter_no"] for r in rows if r["stage"] == "ready_to_write"],
        "needs_repair": [r["chapter_no"] for r in rows if r["stage"] == "needs_repair"],
        "needs_review": [r["chapter_no"] for r in rows if r["stage"] == "needs_review"],
        "ready_to_publish": [r["chapter_no"] for r in rows if r["publish_ready"]],
        "published": [r["chapter_no"] for r in rows if r["publish_status"] in PUBLISH_FINAL_STATES],
    }
    report = {
        "ok": not any(i["level"] == "error" for i in issues),
        "schema_version": 1,
        "generated_at": _now(),
        "project_id": project_id,
        "summary": {
            "chapters_seen": len(rows),
            "committed": sum(1 for r in rows if r["has_commit"]),
            "rejected": sum(1 for r in rows if r["has_rejected"]),
            "ready_to_publish": len(queues["ready_to_publish"]),
            "published": len(queues["published"]),
            "issue_count": len(issues),
        },
        "queues": queues,
        "issues": issues,
        "chapters": rows,
    }
    out_dir = Path(paths.control) / "reports" / "lifecycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(out_dir / "last_lifecycle_report.json", report)
    md_path = write_text(out_dir / "last_lifecycle_report.md", _lifecycle_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def publish_queue(storage: Any, project_id: str, *, start: int | None = None, end: int | None = None, include_warnings: bool = False) -> dict[str, Any]:
    report = lifecycle_report(storage, project_id)
    rows = report.get("chapters") or []
    queue: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        no = int(row.get("chapter_no") or 0)
        if start is not None and no < start:
            continue
        if end is not None and no > end:
            continue
        if row.get("publish_status") in PUBLISH_FINAL_STATES:
            skipped.append({"chapter_no": no, "reason": "already_published"})
            continue
        if not row.get("has_chapter") or not row.get("has_commit"):
            skipped.append({"chapter_no": no, "reason": "not_committed"})
            continue
        warnings = list(row.get("warnings") or [])
        if warnings and not include_warnings:
            skipped.append({"chapter_no": no, "reason": "quality_or_review_warning", "warnings": warnings})
            continue
        queue.append({
            "chapter_no": no,
            "title": row.get("title") or f"第{no}章",
            "path": row.get("chapter_path") or "",
            "word_count": row.get("word_count") or 0,
            "quality_score": row.get("quality_score"),
            "commit_id": row.get("commit_id") or "",
            "publish_status": row.get("publish_status") or "pending",
        })
    paths = storage.ensure_project_dirs(project_id)
    result = {
        "ok": True,
        "schema_version": 1,
        "generated_at": _now(),
        "project_id": project_id,
        "include_warnings": include_warnings,
        "range": {"start": start, "end": end},
        "count": len(queue),
        "queue": queue,
        "skipped": skipped,
    }
    out_dir = Path(paths.control) / "reports" / "publication"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(out_dir / "publish_queue.json", result)
    md_path = write_text(out_dir / "publish_queue.md", _publish_queue_markdown(result))
    result["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return result


def update_publish_status(storage: Any, project_id: str, chapter_no: int, *, status: str, platform: str = "fanqie", external_id: str = "", note: str = "") -> dict[str, Any]:
    if chapter_no <= 0:
        raise ValueError("chapter_no must be greater than zero")
    status = (status or "").strip() or "pending"
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    publication = state.setdefault("publication", {})
    chapters = publication.setdefault("chapters", {})
    old = chapters.get(str(chapter_no)) if isinstance(chapters.get(str(chapter_no)), dict) else {}
    item = dict(old or {})
    item.update({
        "chapter_no": chapter_no,
        "status": status,
        "platform": platform or item.get("platform") or "fanqie",
        "external_id": external_id or item.get("external_id") or "",
        "note": note,
        "updated_at": _now(),
    })
    chapters[str(chapter_no)] = item
    storage.save_state(project_id, state)
    storage.append_event(project_id, "publication_status_changed", item)
    report = {
        "ok": True,
        "project_id": project_id,
        "chapter_no": chapter_no,
        "old": old,
        "current": item,
    }
    out_dir = Path(paths.control) / "reports" / "publication"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = write_json(out_dir / f"chapter_{chapter_no:04d}_publish_status.json", report)
    report["path"] = str(path)
    return report


def chapter_trace(storage: Any, project_id: str, chapter_no: int) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    chapter_path, chapter_text = storage.load_chapter(project_id, chapter_no)
    rejected = [x for x in storage.list_rejected(project_id) if int(x.get("chapterNo") or 0) == chapter_no]
    events = [e for e in storage.read_events(project_id) if _event_chapter_no(e) == chapter_no]
    art_dir = Path(paths.artifacts) / f"第{chapter_no:04d}章"
    artifacts = []
    if art_dir.exists():
        for path in sorted(art_dir.glob("*.json")):
            artifacts.append({"name": path.stem, "path": str(path), "ok": _artifact_ok(path)})
    report = {
        "ok": True,
        "schema_version": 1,
        "generated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "title": (state.get("chapter_titles") or {}).get(str(chapter_no)) or _chapter_title_from_path(chapter_path) or f"第{chapter_no}章",
        "state_status": (state.get("chapter_status") or {}).get(str(chapter_no)) or "",
        "publish_status": (_publication_map(state).get(chapter_no) or {}).get("status") or "pending",
        "files": {
            "blueprint_md": str(Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.md"),
            "blueprint_json": str(Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.json"),
            "chapter": str(chapter_path or ""),
            "review": str(Path(paths.reviews) / f"第{chapter_no:04d}章_review.json"),
            "commit": str(Path(paths.commits) / f"第{chapter_no:04d}章_commit.json"),
            "context_md": str(Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.md"),
            "context_json": str(Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json"),
        },
        "has": {
            "blueprint": (Path(paths.blueprints) / f"第{chapter_no:04d}章_蓝图.json").exists(),
            "chapter": bool(chapter_text.strip()),
            "review": (Path(paths.reviews) / f"第{chapter_no:04d}章_review.json").exists(),
            "commit": (Path(paths.commits) / f"第{chapter_no:04d}章_commit.json").exists(),
            "context": (Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json").exists(),
            "rejected": bool(rejected),
        },
        "word_count": len(re.sub(r"\s+", "", chapter_text or "")),
        "rejected": rejected[:5],
        "artifacts": artifacts,
        "events": events,
    }
    out_dir = Path(paths.control) / "reports" / "trace"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(out_dir / f"chapter_{chapter_no:04d}_trace.json", report)
    md_path = write_text(out_dir / f"chapter_{chapter_no:04d}_trace.md", _trace_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def _chapter_lifecycle_row(no: int, chapters: dict[int, dict[str, Any]], blueprints: dict[int, dict[str, Any]], rejected: dict[int, list[dict[str, Any]]], commits: dict[int, dict[str, Any]], reviews: dict[int, dict[str, Any]], quality: dict[int, dict[str, Any]], publication: dict[int, dict[str, Any]], state: dict[str, Any]) -> dict[str, Any]:
    chapter = chapters.get(no) or {}
    commit = commits.get(no) or {}
    review = reviews.get(no) or {}
    q = quality.get(no) or {}
    pub = publication.get(no) or {}
    has_chapter = bool(chapter)
    has_commit = bool(commit)
    has_blueprint = bool(blueprints.get(no))
    has_rejected = bool(rejected.get(no))
    warnings: list[str] = []
    blocking = review.get("blocking_issues") or []
    if blocking:
        warnings.append("review_blocking_issues")
    if isinstance(q, dict) and q and q.get("ok") is False:
        warnings.append("quality_warning")
    if has_chapter and not has_commit:
        warnings.append("chapter_without_commit")
    if has_commit and not has_chapter:
        warnings.append("commit_without_chapter")
    if not has_blueprint:
        warnings.append("missing_blueprint")
    if has_rejected and not has_commit:
        stage = "needs_repair"
    elif has_commit and has_chapter:
        stage = "committed"
    elif has_blueprint:
        stage = "ready_to_write"
    else:
        stage = "needs_blueprint"
    publish_status = str(pub.get("status") or "pending")
    publish_ready = bool(has_chapter and has_commit and publish_status not in PUBLISH_FINAL_STATES and (not warnings or warnings == ["missing_blueprint"]))
    return {
        "chapter_no": no,
        "title": chapter.get("title") or commit.get("chapter_title") or (state.get("chapter_titles") or {}).get(str(no)) or f"第{no}章",
        "stage": stage,
        "has_blueprint": has_blueprint,
        "has_chapter": has_chapter,
        "has_commit": has_commit,
        "has_review": bool(review),
        "has_rejected": has_rejected,
        "state_status": (state.get("chapter_status") or {}).get(str(no)) or "",
        "publish_status": publish_status,
        "publish_ready": publish_ready,
        "chapter_path": chapter.get("path") or "",
        "commit_id": commit.get("commit_id") or "",
        "word_count": _word_count(chapter.get("path") or ""),
        "quality_score": q.get("score") if isinstance(q, dict) else None,
        "warnings": warnings,
    }


def _row_issues(row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    no = row["chapter_no"]
    for warning in row.get("warnings") or []:
        level = "error" if warning in {"chapter_without_commit", "commit_without_chapter", "review_blocking_issues"} else "warning"
        out.append({"level": level, "type": warning, "chapter_no": no, "message": f"第 {no} 章：{warning}"})
    return out


def _commit_map(root: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    if not root.exists():
        return rows
    for path in sorted(root.glob("第*章_commit.json")):
        match = re.match(r"第(\d+)章_commit\.json$", path.name)
        if match:
            data = read_json(path, {}) or {}
            if isinstance(data, dict):
                rows[int(match.group(1))] = data
    return rows


def _review_map(root: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    if not root.exists():
        return rows
    for path in sorted(root.glob("第*章_review.json")):
        match = re.match(r"第(\d+)章_review\.json$", path.name)
        if match:
            data = read_json(path, {}) or {}
            if isinstance(data, dict):
                rows[int(match.group(1))] = data
    return rows


def _quality_map(root: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    if not root.exists():
        return rows
    for folder in root.glob("第*章"):
        match = re.match(r"第(\d+)章$", folder.name)
        if not match:
            continue
        candidates = [folder / "06_quality_gate.json", folder / "local_quality_review.json"]
        for path in candidates:
            if path.exists():
                data = read_json(path, {}) or {}
                if isinstance(data, dict):
                    rows[int(match.group(1))] = data
                    break
    return rows


def _rejected_by_chapter(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        no = int(row.get("chapterNo") or 0)
        if no:
            out.setdefault(no, []).append(row)
    return out


def _publication_map(state: dict[str, Any]) -> dict[int, dict[str, Any]]:
    raw = ((state.get("publication") or {}).get("chapters") or {}) if isinstance(state.get("publication"), dict) else {}
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        if str(key).isdigit() and isinstance(value, dict):
            out[int(key)] = value
    return out


def _word_count(path: str) -> int:
    try:
        if path and Path(path).exists():
            return len(re.sub(r"\s+", "", read_text_auto(Path(path))))
    except Exception:
        return 0
    return 0


def _chapter_title_from_path(path: Path | None) -> str:
    if not path:
        return ""
    match = re.match(r"第\d+章_(.+)\.txt$", path.name)
    return match.group(1) if match else path.stem


def _artifact_ok(path: Path) -> Any:
    data = read_json(path, None)
    if isinstance(data, dict):
        return data.get("ok")
    return None


def _event_chapter_no(event: dict[str, Any]) -> int:
    payload = event.get("payload") if isinstance(event, dict) else {}
    if isinstance(payload, dict):
        for key in ["chapter_no", "chapterNo"]:
            if str(payload.get(key) or "").isdigit():
                return int(payload[key])
    return 0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _lifecycle_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    lines = ["# 章节生命周期报告", "", f"生成时间：{report.get('generated_at')}", "", "## 摘要"]
    for key, value in summary.items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## 队列"]
    for key, value in (report.get("queues") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## 章节", "", "| 章 | 阶段 | 正文 | Commit | Rejected | 发布 | 警告 |", "|---:|---|---|---|---|---|---|"]
    for row in report.get("chapters") or []:
        lines.append(f"| {row.get('chapter_no')} | {row.get('stage')} | {row.get('has_chapter')} | {row.get('has_commit')} | {row.get('has_rejected')} | {row.get('publish_status')} | {', '.join(row.get('warnings') or [])} |")
    return "\n".join(lines) + "\n"


def _publish_queue_markdown(result: dict[str, Any]) -> str:
    lines = ["# 发布队列", "", f"生成时间：{result.get('generated_at')}", f"待发布章节数：{result.get('count')}", "", "| 章 | 标题 | 字数 | 质量分 | 状态 |", "|---:|---|---:|---:|---|"]
    for row in result.get("queue") or []:
        lines.append(f"| {row.get('chapter_no')} | {row.get('title')} | {row.get('word_count')} | {row.get('quality_score')} | {row.get('publish_status')} |")
    if result.get("skipped"):
        lines += ["", "## 跳过"]
        for item in result.get("skipped") or []:
            lines.append(f"- 第 {item.get('chapter_no')} 章：{item.get('reason')}")
    return "\n".join(lines) + "\n"


def _trace_markdown(report: dict[str, Any]) -> str:
    lines = ["# 章节追踪", "", f"第 {report.get('chapter_no')} 章：{report.get('title')}", "", "## 状态", f"- 章节状态：{report.get('state_status')}", f"- 发布状态：{report.get('publish_status')}", f"- 字数：{report.get('word_count')}", "", "## 文件"]
    for key, value in (report.get("files") or {}).items():
        lines.append(f"- {key}: {value}")
    lines += ["", "## Artifacts"]
    for item in report.get("artifacts") or []:
        lines.append(f"- {item.get('name')} ok={item.get('ok')} {item.get('path')}")
    lines += ["", "## Events"]
    for event in report.get("events") or []:
        lines.append(f"- {event.get('type')} {event.get('at')} {event.get('event_id')}")
    return "\n".join(lines) + "\n"
