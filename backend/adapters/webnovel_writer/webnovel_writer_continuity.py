from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, write_text


def continuity_report(storage: Any, project_id: str) -> dict[str, Any]:
    """Check continuity drift that is not covered by shape/audit checks."""
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    paths = storage.paths(project_id)
    commits = _load_commits(paths)
    issues: list[dict[str, Any]] = []

    _check_character_location_history(commits, issues)
    _check_item_owner_history(commits, issues)
    _check_chapter_order(commits, issues)
    _check_open_debts(state, issues)
    _check_status_values(state, issues)

    report = {
        "ok": not any(i.get("level") == "error" for i in issues),
        "generated_at": now_iso(),
        "project_id": project_id,
        "issue_count": len(issues),
        "issues": issues,
    }
    out_dir = ensure_dir(Path(paths.control) / "reports" / "continuity")
    json_path = write_json(out_dir / "last_continuity_report.json", report)
    md_path = write_text(out_dir / "last_continuity_report.md", continuity_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(out_dir / "last_continuity_report.json", report)
    return report


def continuity_markdown(report: dict[str, Any]) -> str:
    lines = ["# 连贯性检查报告", "", f"- 时间：{report.get('generated_at')}", f"- 问题数：{report.get('issue_count')}", ""]
    issues = report.get("issues") or []
    if not issues:
        lines.append("暂无明显连贯性问题。")
    for item in issues:
        chapter = f"第{item.get('chapter_no')}章 " if item.get("chapter_no") else ""
        lines.append(f"- [{item.get('level')}] {chapter}{item.get('type')}: {item.get('message')}")
    return "\n".join(lines).rstrip() + "\n"


def _load_commits(paths: Any) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(Path(paths.commits).glob("第*章_commit.json")):
        data = read_json(path, {}) or {}
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _check_character_location_history(commits: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    per_chapter: dict[tuple[int, str], set[str]] = defaultdict(set)
    last_location: dict[str, tuple[int, str]] = {}
    for commit in commits:
        no = int(commit.get("chapter_no") or 0)
        for name, item in (commit.get("characters") or {}).items():
            if not isinstance(item, dict):
                continue
            loc = str(item.get("location") or item.get("位置") or "").strip()
            if not loc:
                continue
            per_chapter[(no, str(name))].add(loc)
            prev = last_location.get(str(name))
            if prev and prev[1] != loc and no == prev[0]:
                issues.append(_issue("warning", "same_chapter_location_jump", f"角色《{name}》同章内位置从《{prev[1]}》变为《{loc}》，请确认是否有过场。", no))
            last_location[str(name)] = (no, loc)
    for (no, name), locs in per_chapter.items():
        if len(locs) > 2:
            issues.append(_issue("warning", "too_many_locations_in_chapter", f"角色《{name}》同章出现多个位置：{', '.join(sorted(locs))}。", no))


def _check_item_owner_history(commits: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    last_owner: dict[str, tuple[int, str]] = {}
    for commit in commits:
        no = int(commit.get("chapter_no") or 0)
        for name, item in (commit.get("items") or {}).items():
            if not isinstance(item, dict):
                continue
            owner = str(item.get("owner") or item.get("持有者") or "").strip()
            if not owner:
                continue
            prev = last_owner.get(str(name))
            transfer_note = str(item.get("transfer") or item.get("event") or item.get("note") or "")
            if prev and prev[1] != owner and not transfer_note:
                issues.append(_issue("warning", "item_owner_changed_without_event", f"物品《{name}》持有者从《{prev[1]}》变为《{owner}》，但缺少流转说明。", no))
            last_owner[str(name)] = (no, owner)


def _check_chapter_order(commits: list[dict[str, Any]], issues: list[dict[str, Any]]) -> None:
    nums = [int(c.get("chapter_no") or 0) for c in commits if int(c.get("chapter_no") or 0) > 0]
    for prev, cur in zip(nums, nums[1:]):
        if cur <= prev:
            issues.append(_issue("error", "commit_order", f"commit 章节顺序异常：第{prev}章后接第{cur}章。", cur))
        elif cur > prev + 1:
            issues.append(_issue("warning", "commit_gap", f"commit 存在缺口：第{prev}章后接第{cur}章。", cur))


def _check_open_debts(state: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    latest = int(state.get("latest_chapter") or 0)
    for name, item in (state.get("foreshadow_debts") or {}).items():
        if not isinstance(item, dict):
            continue
        first = _to_int(item.get("introduced_chapter") or item.get("first_seen_chapter"), latest)
        if latest and first and latest - first > 60:
            issues.append(_issue("warning", "very_long_foreshadow_debt", f"伏笔《{name}》开放超过 60 章，建议回收、推进或降级。"))


def _check_status_values(state: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
        for name, item in (state.get(bucket) or {}).items():
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or item.get("state") or "").strip()
            if status and re.search(r"未知|待定|TODO|todo|\?\?", status):
                issues.append(_issue("info", "uncertain_status", f"{bucket}《{name}》状态仍是占位/不确定：{status}"))


def _issue(level: str, typ: str, message: str, chapter_no: int | None = None) -> dict[str, Any]:
    row = {"level": level, "type": typ, "message": message}
    if chapter_no:
        row["chapter_no"] = chapter_no
    return row


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
