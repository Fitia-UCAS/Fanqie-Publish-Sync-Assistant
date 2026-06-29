from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import CONTROL_ENTITY_BUCKETS, fresh_state, now_iso
from backend.shared.text_file.text_file_storage import write_text


STATE_COUNT_KEYS = tuple(CONTROL_ENTITY_BUCKETS) + ("timeline", "milestones")


def project_ssot_report(storage: Any, project_id: str) -> dict[str, Any]:
    """Create a non-destructive SSOT/projection report.

    The commit log is treated as the machine source for generated chapter facts.
    writer_control Markdown is treated as the human overlay.  This report does
    not overwrite story_state; it only points out drift and event-log holes.
    """
    paths = storage.ensure_project_dirs(project_id)
    commit_rows = _load_commits(paths)
    projection = fresh_state()
    accepted_commits: list[dict[str, Any]] = []
    rejected_commits: list[dict[str, Any]] = []
    broken_commits: list[dict[str, Any]] = []

    for row in commit_rows:
        commit = row.get("commit")
        if not isinstance(commit, dict):
            broken_commits.append({"path": row.get("path"), "reason": "commit json is not object"})
            continue
        status = str(commit.get("status") or "").lower()
        if status == "accepted":
            accepted_commits.append(commit)
            storage.apply_commit_to_state(projection, commit)
        else:
            rejected_commits.append(commit)

    current = storage.load_state(project_id)
    events = storage.read_events(project_id)
    event_report = _event_integrity(events, accepted_commits)
    drift = _projection_drift(current, projection)
    report = {
        "ok": not broken_commits and not event_report["errors"] and not [d for d in drift if d.get("level") == "error"],
        "schema_version": 1,
        "checked_at": now_iso(),
        "project_id": project_id,
        "commit_count": len(commit_rows),
        "accepted_commit_count": len(accepted_commits),
        "rejected_commit_count": len(rejected_commits),
        "broken_commits": broken_commits,
        "event_log": event_report,
        "projection": _projection_summary(projection),
        "current_state": _projection_summary(current),
        "drift": drift,
        "notes": [
            "commits 是生成事实的机器来源；writer_control Markdown 是人工覆盖层。",
            "如果 drift 只来自人工 Markdown 新增实体，通常不是错误；如果 latest_chapter 或已提交章节摘要不同，需要 doctor/rebuild。",
        ],
    }
    report_dir = Path(paths.control) / "reports" / "ssot"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(report_dir / "last_ssot_report.json", report)
    md_path = write_text(report_dir / "last_ssot_report.md", ssot_report_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def ssot_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SSOT / 投影一致性报告",
        "",
        f"- 时间：{report.get('checked_at', '')}",
        f"- 状态：{'通过' if report.get('ok') else '需要处理'}",
        f"- accepted commits：{report.get('accepted_commit_count', 0)}",
        f"- rejected commits：{report.get('rejected_commit_count', 0)}",
        "",
        "## 投影摘要",
        "",
    ]
    proj = report.get("projection") or {}
    cur = report.get("current_state") or {}
    for key in sorted(set(proj) | set(cur)):
        lines.append(f"- {key}: projection={proj.get(key)} / current={cur.get(key)}")
    lines += ["", "## Drift", ""]
    drift = report.get("drift") or []
    if not drift:
        lines.append("暂无。")
    for item in drift:
        lines.append(f"- [{item.get('level', 'info')}] {item.get('type', '')}: {item.get('message', '')}")
    lines += ["", "## Event Log", ""]
    ev = report.get("event_log") or {}
    lines.append(f"- events: {ev.get('event_count', 0)}")
    lines.append(f"- duplicate event ids: {len(ev.get('duplicate_event_ids') or [])}")
    lines.append(f"- missing chapter_committed events: {len(ev.get('missing_commit_events') or [])}")
    for msg in ev.get("errors") or []:
        lines.append(f"- [error] {msg}")
    broken = report.get("broken_commits") or []
    if broken:
        lines += ["", "## Broken Commits", ""]
        for item in broken:
            lines.append(f"- `{item.get('path')}`: {item.get('reason')}")
    return "\n".join(lines).rstrip() + "\n"


def _load_commits(paths: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(paths.commits).glob("第*章_commit.json"), key=_commit_sort_key):
        try:
            commit = read_json(path, {}) or {}
        except Exception as exc:
            rows.append({"path": str(path), "commit": None, "error": str(exc)})
            continue
        rows.append({"path": str(path), "commit": commit})
    return rows


def _commit_sort_key(path: Path) -> tuple[int, str]:
    import re

    match = re.search(r"第(\d+)章", path.name)
    return (int(match.group(1)) if match else 0, path.name)


def _event_integrity(events: list[Any], accepted_commits: list[dict[str, Any]]) -> dict[str, Any]:
    ids: list[str] = []
    duplicate_ids: list[str] = []
    seen: set[str] = set()
    errors: list[str] = []
    committed_ids = {str(c.get("commit_id") or "") for c in accepted_commits if c.get("commit_id")}
    event_commit_ids: set[str] = set()
    prev_fingerprint = ""
    chain_breaks: list[dict[str, Any]] = []

    for idx, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"第 {idx + 1} 条事件不是 JSON object")
            continue
        event_id = str(event.get("event_id") or "")
        if event_id:
            if event_id in seen:
                duplicate_ids.append(event_id)
            seen.add(event_id)
            ids.append(event_id)
        payload = event.get("payload") or {}
        if event.get("type") == "chapter_committed" and isinstance(payload, dict):
            cid = str(payload.get("commit_id") or "")
            if cid:
                event_commit_ids.add(cid)
        if event.get("prev_fingerprint") and event.get("prev_fingerprint") != prev_fingerprint:
            chain_breaks.append({"index": idx + 1, "event_id": event_id, "expected_prev": prev_fingerprint, "actual_prev": event.get("prev_fingerprint")})
        stored_fingerprint = str(event.get("fingerprint") or "")
        calculated = _event_fingerprint(event, prev_fingerprint)
        prev_fingerprint = stored_fingerprint or calculated
    return {
        "event_count": len(events),
        "duplicate_event_ids": sorted(set(duplicate_ids)),
        "missing_commit_events": sorted(committed_ids - event_commit_ids),
        "extra_commit_events": sorted(event_commit_ids - committed_ids),
        "chain_breaks": chain_breaks,
        "errors": errors,
    }


def _event_fingerprint(event: dict[str, Any], prev: str = "") -> str:
    import json

    raw = json.dumps({"prev": prev, "event": event}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def _projection_drift(current: dict[str, Any], projection: dict[str, Any]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    if int(current.get("latest_chapter") or 0) != int(projection.get("latest_chapter") or 0):
        drift.append({"level": "error", "type": "latest_chapter", "message": f"latest_chapter current={current.get('latest_chapter')} projection={projection.get('latest_chapter')}"})
    for chapter, summary in (projection.get("chapter_summaries") or {}).items():
        cur = (current.get("chapter_summaries") or {}).get(str(chapter))
        if cur != summary:
            drift.append({"level": "warning", "type": "chapter_summary", "message": f"第 {chapter} 章摘要与 commit 投影不同。"})
    for bucket in CONTROL_ENTITY_BUCKETS:
        cur = current.get(bucket) or {}
        proj = projection.get(bucket) or {}
        if not isinstance(cur, dict) or not isinstance(proj, dict):
            continue
        missing = sorted(set(proj) - set(cur))
        if missing:
            drift.append({"level": "error", "type": "missing_projected_entity", "message": f"{bucket} 缺少 commit 投影实体：{', '.join(missing[:10])}"})
        extra = []
        for name in sorted(set(cur) - set(proj)):
            item = cur.get(name)
            if isinstance(item, dict) and item.get("_control_managed"):
                continue
            extra.append(name)
        if extra:
            drift.append({"level": "info", "type": "extra_state_entity", "message": f"{bucket} 存在非 commit 投影实体：{', '.join(extra[:10])}"})
    return drift


def _projection_summary(state: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {"latest_chapter": state.get("latest_chapter") or 0}
    for key in STATE_COUNT_KEYS:
        value = state.get(key)
        if isinstance(value, dict):
            summary[key] = len(value)
        elif isinstance(value, list):
            summary[key] = len(value)
        else:
            summary[key] = 0
    summary["chapter_summaries"] = len(state.get("chapter_summaries") or {})
    return summary
