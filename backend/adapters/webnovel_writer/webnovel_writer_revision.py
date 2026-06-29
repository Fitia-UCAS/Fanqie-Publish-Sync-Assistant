from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_auditor import make_snapshot
from backend.adapters.webnovel_writer.webnovel_writer_json import write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, write_text


def revision_plan(storage: Any, project_id: str, start_chapter: int) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.paths(project_id)
    affected = _affected_files(paths, start_chapter)
    chapters = _affected_chapter_numbers(affected)
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "project_id": project_id,
        "start_chapter": start_chapter,
        "affected_chapters": chapters,
        "affected_count": sum(len(v) for v in affected.values()),
        "affected": affected,
        "message": "这是预演报告；真正归档/失效章节请运行 invalidate --apply。",
    }
    out_dir = ensure_dir(Path(paths.control) / "reports" / "revision")
    json_path = write_json(out_dir / f"revision_plan_from_{start_chapter:04d}.json", report)
    md_path = write_text(out_dir / f"revision_plan_from_{start_chapter:04d}.md", revision_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(out_dir / f"revision_plan_from_{start_chapter:04d}.json", report)
    return report


def invalidate_from_chapter(storage: Any, project_id: str, start_chapter: int, *, reason: str = "rewrite", apply: bool = False) -> dict[str, Any]:
    paths = storage.paths(project_id)
    plan = revision_plan(storage, project_id, start_chapter)
    if not apply:
        plan["dry_run"] = True
        return plan
    snapshot = make_snapshot(storage, project_id, f"before_invalidate_from_{start_chapter:04d}_{reason}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = ensure_dir(Path(paths.control) / "revisions" / f"invalidated_from_{start_chapter:04d}_{stamp}")
    moved = []
    for group, files in (plan.get("affected") or {}).items():
        for f in files:
            src = Path(f)
            if not src.exists() or not src.is_file():
                continue
            rel = src.relative_to(Path(paths.root)) if src.is_relative_to(Path(paths.root)) else Path(src.name)
            dst = archive_root / rel
            ensure_dir(dst.parent)
            shutil.move(str(src), str(dst))
            moved.append({"from": str(src), "to": str(dst), "group": group})
    affected_chapters = [int(x) for x in (plan.get("affected_chapters") or []) if int(x) >= start_chapter]
    storage.rebuild_state_from_commits(project_id)
    state = storage.load_state(project_id)
    for no in affected_chapters or [start_chapter]:
        state.setdefault("chapter_status", {})[str(no)] = "invalidated"
    storage.save_state(project_id, state)
    storage.rebuild_chapter_index(project_id)
    storage.sync_novel_file(project_id)
    try:
        storage.append_event(project_id, "chapters_invalidated", {"start_chapter": start_chapter, "reason": reason, "moved": moved, "snapshot": snapshot})
    except Exception:
        pass
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "project_id": project_id,
        "start_chapter": start_chapter,
        "reason": reason,
        "snapshot": snapshot,
        "archive": str(archive_root),
        "moved_count": len(moved),
        "moved": moved,
    }
    out_dir = ensure_dir(Path(paths.control) / "reports" / "revision")
    json_path = write_json(out_dir / f"invalidated_from_{start_chapter:04d}_{stamp}.json", report)
    md_path = write_text(out_dir / f"invalidated_from_{start_chapter:04d}_{stamp}.md", invalidation_markdown(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(out_dir / f"invalidated_from_{start_chapter:04d}_{stamp}.json", report)
    return report


def revision_markdown(report: dict[str, Any]) -> str:
    lines = ["# 重写影响预演", "", f"- 起始章节：第{report.get('start_chapter')}章", f"- 受影响文件数：{report.get('affected_count')}", "", "## 受影响文件", ""]
    for group, files in (report.get("affected") or {}).items():
        lines.append(f"### {group}")
        if not files:
            lines.append("暂无。")
        for f in files[:200]:
            lines.append(f"- `{f}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def invalidation_markdown(report: dict[str, Any]) -> str:
    lines = ["# 章节失效归档报告", "", f"- 起始章节：第{report.get('start_chapter')}章", f"- 原因：{report.get('reason')}", f"- 移动文件数：{report.get('moved_count')}", f"- 归档目录：`{report.get('archive')}`", f"- 快照：`{(report.get('snapshot') or {}).get('path')}`", ""]
    for row in (report.get("moved") or [])[:300]:
        lines.append(f"- {row.get('group')}: `{row.get('from')}` → `{row.get('to')}`")
    return "\n".join(lines).rstrip() + "\n"


def _affected_files(paths: Any, start_chapter: int) -> dict[str, list[str]]:
    root = Path(paths.root)
    patterns = {
        "chapters": (Path(paths.chapters), "第*章_*.txt"),
        "drafts": (Path(paths.drafts), "第*章_*.txt"),
        "rejected": (Path(paths.rejected), "第*章_*.txt"),
        "reviews": (Path(paths.reviews), "第*章_review.json"),
        "commits": (Path(paths.commits), "第*章_commit.json"),
        "runs": (Path(paths.runs), "第*章_*.json"),
        "runtime": (Path(paths.runtime), "第*章"),
        "artifacts": (Path(paths.artifacts), "第*章"),
    }
    out: dict[str, list[str]] = {}
    for group, (folder, pattern) in patterns.items():
        rows = []
        if folder.exists():
            for path in sorted(folder.glob(pattern)):
                no = _chapter_no(path.name)
                if no >= start_chapter:
                    if path.is_dir():
                        for sub in sorted(path.rglob("*")):
                            if sub.is_file():
                                rows.append(str(sub))
                    elif path.is_file():
                        rows.append(str(path))
        out[group] = rows
    return out


def _affected_chapter_numbers(affected: dict[str, list[str]]) -> list[int]:
    nums: set[int] = set()
    for files in affected.values():
        for f in files:
            no = _chapter_no(Path(f).name)
            if no:
                nums.add(no)
            else:
                for part in Path(f).parts:
                    no = _chapter_no(part)
                    if no:
                        nums.add(no)
                        break
    return sorted(nums)


def _chapter_no(name: str) -> int:
    import re
    m = re.search(r"第(\d+)章", name)
    return int(m.group(1)) if m else 0
