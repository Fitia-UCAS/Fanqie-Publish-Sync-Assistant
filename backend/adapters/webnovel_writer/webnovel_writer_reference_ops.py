from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import append_jsonl, read_json, read_jsonl, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.adapters.webnovel_writer.webnovel_writer_indexing import rebuild_chunk_index, search_chunks, build_entity_occurrence_index
from backend.adapters.webnovel_writer.webnovel_writer_language import anti_ai_report
from backend.adapters.webnovel_writer.webnovel_writer_learning import learn_style_profile
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def _reports_dir(storage: Any, project_id: str, *parts: str) -> Path:
    root = Path(storage.paths(project_id).control) / "reports" / "reference"
    for part in parts:
        root = root / str(part)
    return ensure_dir(root)


def _rel(root: Path, path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _safe_action(action: str, default: str = "stats") -> str:
    return str(action or default).strip().lower().replace("_", "-")


def _write_report(storage: Any, project_id: str, name: str, data: dict[str, Any]) -> dict[str, Any]:
    report_dir = _reports_dir(storage, project_id, name)
    json_path = write_json(report_dir / f"last_{name}.json", data)
    data.setdefault("paths_written", {})["json"] = str(json_path)
    return data


def index_command(storage: Any, project_id: str, action: str = "stats", chapter_no: int = 0, query: str = "", top_k: int = 8) -> dict[str, Any]:
    """Reference-compatible index subcommands: stats, rebuild, process-chapter, query."""
    storage.ensure_project_dirs(project_id)
    action = _safe_action(action)
    paths = storage.paths(project_id)
    root = Path(paths.root)
    if action in {"rebuild", "process-chapter", "process", "index-chapter"}:
        chapter_index = storage.rebuild_chapter_index(project_id)
        chunk = rebuild_chunk_index(storage, project_id)
        entity = build_entity_occurrence_index(storage, project_id)
        report = {
            "ok": True,
            "command": "index",
            "action": action,
            "chapter_no": chapter_no or None,
            "chapter_index": _rel(root, chapter_index),
            "chunk_index": (chunk.get("paths_written") or {}).get("json"),
            "entity_occurrences": (entity.get("paths_written") or {}).get("json"),
            "stats": storage.index_summary(project_id),
        }
        return _write_report(storage, project_id, "index", report)
    if action in {"query", "search"}:
        hits = storage.recall(project_id, query, top_k=top_k, exclude_chapter=chapter_no or None)
        chunks = search_chunks(storage, project_id, query, top_k=top_k, exclude_chapter=chapter_no or None)
        report = {"ok": True, "command": "index", "action": action, "query": query, "chapter_hits": hits, "chunk_hits": chunks.get("hits") or []}
        return _write_report(storage, project_id, "index", report)
    index_path = Path(paths.indexes) / "chapter_index.json"
    chunk_path = Path(paths.indexes) / "chunk_index.json"
    chapter_index = read_json(index_path, {}) or {}
    chunk_index = read_json(chunk_path, {}) or {}
    report = {
        "ok": True,
        "command": "index",
        "action": "stats",
        "chapter_index_exists": index_path.exists(),
        "chunk_index_exists": chunk_path.exists(),
        "chapter_doc_count": chapter_index.get("doc_count") or 0,
        "chunk_count": chunk_index.get("chunk_count") or len(chunk_index.get("chunks") or []),
        "updated_at": chapter_index.get("updated_at") or chunk_index.get("updated_at") or "",
        "paths": {"chapter_index": str(index_path), "chunk_index": str(chunk_path)},
    }
    return _write_report(storage, project_id, "index", report)


def state_command(storage: Any, project_id: str, action: str = "summary", patch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reference-compatible state subcommands: summary, dump, rebuild, patch."""
    storage.ensure_project_dirs(project_id)
    action = _safe_action(action, "summary")
    if action in {"rebuild", "replay"}:
        state_path = storage.rebuild_state_from_commits(project_id)
        state = storage.load_state(project_id)
    else:
        state_path = Path(storage.paths(project_id).state)
        state = storage.load_state(project_id)
    if action in {"patch", "update"} and isinstance(patch, dict) and patch:
        _deep_merge(state, patch)
        state_path = storage.save_state(project_id, state)
    summary = _state_summary(state)
    report = {
        "ok": True,
        "command": "state",
        "action": action,
        "state_path": str(state_path),
        "summary": summary,
        "state": state if action in {"dump", "show"} else None,
    }
    if report["state"] is None:
        report.pop("state", None)
    return _write_report(storage, project_id, "state", report)


def rag_command(storage: Any, project_id: str, action: str = "stats", chapter_no: int = 0, query: str = "", top_k: int = 8) -> dict[str, Any]:
    """Reference-compatible RAG command. Uses local BM25/chunk index when vector service is not configured."""
    action = _safe_action(action, "stats")
    paths = storage.paths(project_id)
    if action in {"index-chapter", "index", "rebuild"}:
        chunk = rebuild_chunk_index(storage, project_id)
        report = {"ok": True, "command": "rag", "action": action, "backend": "local_chunk_bm25", "chapter_no": chapter_no or None, "index": chunk}
        return _write_report(storage, project_id, "rag", report)
    if action in {"query", "search"}:
        result = search_chunks(storage, project_id, query, top_k=top_k, exclude_chapter=chapter_no or None)
        report = {"ok": True, "command": "rag", "action": action, "backend": "local_chunk_bm25", "query": query, "hits": result.get("hits") or []}
        return _write_report(storage, project_id, "rag", report)
    chunk_path = Path(paths.indexes) / "chunk_index.json"
    data = read_json(chunk_path, {}) or {}
    report = {
        "ok": True,
        "command": "rag",
        "action": "stats",
        "backend": "local_chunk_bm25",
        "vector_backend_configured": False,
        "chunk_index_exists": chunk_path.exists(),
        "chunk_count": data.get("chunk_count") or len(data.get("chunks") or []),
        "updated_at": data.get("updated_at") or "",
        "note": "当前后端提供本地分块召回；如需外部 embedding/rerank，可在模型路由与后续向量适配层接入。",
    }
    return _write_report(storage, project_id, "rag", report)


def entity_command(storage: Any, project_id: str, action: str = "stats", query: str = "") -> dict[str, Any]:
    """Reference-compatible entity subcommands: stats, link, occurrences."""
    action = _safe_action(action, "stats")
    storage.sync_control_files(project_id)
    state = storage.load_state(project_id)
    if action in {"occurrences", "rebuild"}:
        occ = build_entity_occurrence_index(storage, project_id)
        report = {"ok": True, "command": "entity", "action": action, "occurrences": occ}
        return _write_report(storage, project_id, "entity", report)
    rows = []
    for bucket, data in state.items():
        if not isinstance(data, dict) or bucket not in {"characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"}:
            continue
        for name, record in data.items():
            record = record if isinstance(record, dict) else {"value": record}
            text = " ".join([str(name), str(record.get("id") or ""), " ".join(map(str, record.get("aliases") or [])), json.dumps(record, ensure_ascii=False)])
            if query and query not in text:
                continue
            rows.append({"bucket": bucket, "name": str(name), "id": record.get("id") or "", "status": record.get("status") or "", "aliases": record.get("aliases") or []})
    if action in {"link", "query", "search"}:
        report = {"ok": True, "command": "entity", "action": action, "query": query, "matches": rows[:80], "match_count": len(rows)}
    else:
        by_bucket = Counter(r["bucket"] for r in rows)
        report = {"ok": True, "command": "entity", "action": "stats", "total": len(rows), "by_bucket": dict(by_bucket), "samples": rows[:20]}
    return _write_report(storage, project_id, "entity", report)


def style_command(storage: Any, project_id: str, action: str = "sample", chapter_no: int = 0, sample_limit: int = 80) -> dict[str, Any]:
    """Reference-compatible style sampling. Wraps local learning profile plus optional chapter language report."""
    action = _safe_action(action, "sample")
    profile = learn_style_profile(storage, project_id, sample_limit=sample_limit, update_config=action in {"sample", "profile", "learn"})
    report: dict[str, Any] = {"ok": True, "command": "style", "action": action, "profile": profile}
    if chapter_no:
        report["chapter_language"] = anti_ai_report(storage, project_id, chapter_no)
    return _write_report(storage, project_id, "style", report)


def migrate_command(storage: Any, project_id: str, action: str = "state-sqlite") -> dict[str, Any]:
    """Reference-compatible migration: state.json -> SQLite read model."""
    action = _safe_action(action, "state-sqlite")
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    db_path = Path(paths.indexes) / "webnovel_state.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS entities (bucket TEXT, name TEXT, entity_id TEXT, status TEXT, payload TEXT, PRIMARY KEY(bucket, name))")
        cur.execute("CREATE TABLE IF NOT EXISTS chapter_summaries (chapter_no INTEGER PRIMARY KEY, title TEXT, summary TEXT)")
        cur.execute("DELETE FROM entities")
        cur.execute("DELETE FROM chapter_summaries")
        for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
            data = state.get(bucket) or {}
            if not isinstance(data, dict):
                continue
            for name, record in data.items():
                record = record if isinstance(record, dict) else {"value": record}
                cur.execute(
                    "INSERT OR REPLACE INTO entities(bucket, name, entity_id, status, payload) VALUES (?, ?, ?, ?, ?)",
                    (bucket, str(name), str(record.get("id") or ""), str(record.get("status") or ""), json.dumps(record, ensure_ascii=False)),
                )
        titles = state.get("chapter_titles") or {}
        summaries = state.get("chapter_summaries") or {}
        if isinstance(summaries, dict):
            for chapter_no, summary in summaries.items():
                try:
                    no = int(chapter_no)
                except Exception:
                    continue
                cur.execute("INSERT OR REPLACE INTO chapter_summaries(chapter_no, title, summary) VALUES (?, ?, ?)", (no, str(titles.get(str(chapter_no)) or ""), str(summary or "")))
        cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("updated_at", now_iso()))
        cur.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("source", str(paths.state)))
        conn.commit()
        entity_count = cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        summary_count = cur.execute("SELECT COUNT(*) FROM chapter_summaries").fetchone()[0]
    finally:
        conn.close()
    report = {"ok": True, "command": "migrate", "action": action, "db_path": str(db_path), "entity_count": entity_count, "summary_count": summary_count}
    return _write_report(storage, project_id, "migrate", report)


def projections_command(storage: Any, project_id: str, action: str = "status", start: int = 0, end: int = 0, chapter_no: int = 0) -> dict[str, Any]:
    """Reference-compatible projection retry/replay/status."""
    action = _safe_action(action, "status")
    if action in {"retry", "replay", "rebuild"}:
        if chapter_no and not start:
            start = chapter_no
        # Current projection engine is deterministic and cheap enough to replay all commits.
        state_path = storage.rebuild_state_from_commits(project_id)
        chapter_index = storage.rebuild_chapter_index(project_id)
        chunk = rebuild_chunk_index(storage, project_id)
        entity = build_entity_occurrence_index(storage, project_id)
        report = {
            "ok": True,
            "command": "projections",
            "action": action,
            "requested_range": {"from": start or None, "to": end or None},
            "state_path": str(state_path),
            "chapter_index": str(chapter_index),
            "chunk_index": (chunk.get("paths_written") or {}).get("json"),
            "entity_occurrences": (entity.get("paths_written") or {}).get("json"),
        }
    else:
        paths = storage.paths(project_id)
        report = {
            "ok": True,
            "command": "projections",
            "action": "status",
            "state_exists": Path(paths.state).exists(),
            "chapter_index_exists": (Path(paths.indexes) / "chapter_index.json").exists(),
            "chunk_index_exists": (Path(paths.indexes) / "chunk_index.json").exists(),
            "relation_index_exists": (Path(paths.control) / "relations" / "relation_index.json").exists(),
        }
    return _write_report(storage, project_id, "projections", report)


def story_system_command(storage: Any, project_id: str, action: str = "persist", genre: str = "", chapter_no: int = 0) -> dict[str, Any]:
    """Reference-compatible story-system contract seed/runtime contract."""
    action = _safe_action(action, "persist")
    paths = storage.ensure_project_dirs(project_id)
    story_dir = ensure_dir(Path(paths.root) / ".story-system")
    meta = storage.load_meta(project_id)
    story_config = storage.load_story_config(project_id)
    state = storage.load_state(project_id)
    if genre:
        meta["genre"] = genre
        story_config.setdefault("story_profile", {})["genre"] = genre
        write_json(paths.meta, meta)
        write_json(paths.story_config, story_config)
    master = {
        "schema_version": 1,
        "project_id": project_id,
        "title": meta.get("title") or "",
        "genre": genre or meta.get("genre") or (story_config.get("story_profile") or {}).get("genre") or "",
        "premise": meta.get("premise") or (story_config.get("story_profile") or {}).get("premise") or "",
        "hard_rules": (story_config.get("generation_policy") or {}).get("hard_rules") or [],
        "forbidden": (story_config.get("generation_policy") or {}).get("forbidden") or [],
        "state_summary": _state_summary(state),
        "updated_at": now_iso(),
    }
    master_path = write_json(story_dir / "MASTER_SETTING.json", master)
    report: dict[str, Any] = {"ok": True, "command": "story-system", "action": action, "master_setting": str(master_path), "master": master}
    if action in {"emit-runtime-contracts", "runtime", "contract"} or chapter_no:
        from backend.adapters.webnovel_writer.webnovel_writer_contract import build_runtime_contract

        contract = build_runtime_contract(storage, project_id, chapter_no or 1)
        report["runtime_contract"] = contract
    return _write_report(storage, project_id, "story_system", report)


def chapter_commit_command(storage: Any, project_id: str, chapter_no: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reference-compatible chapter-commit wrapper from existing artifacts."""
    paths = storage.ensure_project_dirs(project_id)
    payload = payload or {}
    chapter_path, chapter_text = storage.load_chapter(project_id, chapter_no)
    if not chapter_text:
        return _write_report(storage, project_id, "chapter_commit", {"ok": False, "command": "chapter-commit", "chapter_no": chapter_no, "errors": ["未找到章节正文，无法提交。"]})
    existing_path = Path(paths.commits) / f"第{chapter_no:04d}章_commit.json"
    existing = read_json(existing_path, {}) if existing_path.exists() else {}
    if existing:
        report = {"ok": True, "command": "chapter-commit", "chapter_no": chapter_no, "status": "existing", "commit": existing, "commit_path": str(existing_path)}
        return _write_report(storage, project_id, "chapter_commit", report)
    review = _load_optional_json(payload.get("reviewResult") or payload.get("review_result")) or {}
    extraction = _load_optional_json(payload.get("extractionResult") or payload.get("extraction_result")) or {}
    commit = {
        "schema_version": 1,
        "chapter_no": chapter_no,
        "title": chapter_path.stem if chapter_path else f"第{chapter_no}章",
        "status": "accepted",
        "created_at": now_iso(),
        "summary": str(review.get("summary") or extraction.get("summary") or ""),
        "source": "chapter-commit",
        "review_result": review,
        "extraction_result": extraction,
        "characters": extraction.get("characters") if isinstance(extraction, dict) else {},
        "locations": extraction.get("locations") if isinstance(extraction, dict) else {},
        "factions": extraction.get("factions") if isinstance(extraction, dict) else {},
        "items": extraction.get("items") if isinstance(extraction, dict) else {},
        "foreshadows": extraction.get("foreshadows") if isinstance(extraction, dict) else {},
        "conflicts": extraction.get("conflicts") if isinstance(extraction, dict) else {},
    }
    path = storage.save_commit(project_id, chapter_no, commit)
    state = storage.load_state(project_id)
    storage.apply_commit_to_state(state, commit)
    storage.save_state(project_id, state)
    append_jsonl(Path(paths.root) / "events" / "event_log.jsonl", {"event_id": _sha(json.dumps(commit, ensure_ascii=False))[:16], "type": "chapter_committed", "chapter_no": chapter_no, "ts": now_iso(), "source": "chapter-commit"})
    report = {"ok": True, "command": "chapter-commit", "chapter_no": chapter_no, "commit_path": str(path), "commit": commit}
    return _write_report(storage, project_id, "chapter_commit", report)


def review_pipeline_command(storage: Any, project_id: str, chapter_no: int, review_results_path: str = "") -> dict[str, Any]:
    """Reference-compatible review-pipeline. Combines existing review, local quality, language and blueprint evidence."""
    chapter_path, chapter_text = storage.load_chapter(project_id, chapter_no)
    if not chapter_text:
        return _write_report(storage, project_id, "review_pipeline", {"ok": False, "command": "review-pipeline", "chapter_no": chapter_no, "errors": ["未找到章节正文。"]})
    external = _load_optional_json(review_results_path) if review_results_path else {}
    quality = anti_ai_report(storage, project_id, chapter_no)
    local_quality = None
    try:
        from backend.adapters.webnovel_writer.webnovel_writer_quality import local_quality_review

        local_quality = local_quality_review(storage, project_id, chapter_no)
    except Exception as exc:
        local_quality = {"ok": False, "error": str(exc)}
    report = {
        "ok": True,
        "command": "review-pipeline",
        "chapter_no": chapter_no,
        "external_review": external,
        "local_quality": local_quality,
        "language": quality,
        "blocking": _collect_blocking_review(local_quality, quality, external),
    }
    return _write_report(storage, project_id, "review_pipeline", report)


def memory_contract_command(storage: Any, project_id: str, action: str = "status", query: str = "") -> dict[str, Any]:
    """Reference-compatible memory-contract command."""
    action = _safe_action(action, "status")
    from backend.adapters.webnovel_writer.webnovel_writer_memory import build_memory_projection, load_or_build_memory

    if action in {"bootstrap", "rebuild", "update"}:
        memory = build_memory_projection(storage, project_id)
    else:
        memory = load_or_build_memory(storage, project_id)
    issues = []
    scratchpad = memory.get("scratchpad") or memory.get("memory_scratchpad") or []
    if isinstance(scratchpad, list):
        seen = set()
        for item in scratchpad:
            if not isinstance(item, dict):
                continue
            key = (item.get("category"), item.get("subject"), item.get("status"))
            if key in seen:
                issues.append({"type": "duplicate_memory_key", "key": list(key)})
            seen.add(key)
    report = {"ok": True, "command": "memory-contract", "action": action, "query": query, "memory": memory, "issues": issues, "issue_count": len(issues)}
    return _write_report(storage, project_id, "memory_contract", report)


def _load_optional_json(path: Any) -> dict[str, Any]:
    raw = str(path or "").strip()
    if not raw:
        return {}
    data = read_json(raw, {}) or {}
    return data if isinstance(data, dict) else {"value": data}


def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def _state_summary(state: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines", "chapter_summaries"]:
        value = state.get(key)
        out[key] = len(value) if isinstance(value, dict) else len(value) if isinstance(value, list) else 0
    return out


def _collect_blocking_review(*parts: Any) -> list[dict[str, Any]]:
    blocking = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        for key in ["errors", "blocking", "fatal", "issues"]:
            value = part.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        severity = str(item.get("severity") or item.get("level") or "").lower()
                        if severity in {"error", "fatal", "blocking"} or key in {"errors", "blocking", "fatal"}:
                            blocking.append(item)
                    elif key in {"errors", "blocking", "fatal"}:
                        blocking.append({"message": str(item)})
    return blocking

# ---- Additional reference-compatible ops from webnovel-writer-opencode scripts ----

def validate_csv_command(storage: Any, project_id: str) -> dict[str, Any]:
    """Reference-compatible validate_csv.py: validate structured reference CSV files."""
    import csv

    paths = storage.ensure_project_dirs(project_id)
    root = Path(paths.control) / "references" / "csv"
    ensure_dir(root)
    files = sorted(root.glob("*.csv"))
    issues: list[dict[str, Any]] = []
    rows_total = 0
    summaries: list[dict[str, Any]] = []
    for path in files:
        rel = _rel(Path(paths.root), path)
        try:
            text = read_text_auto(path)
            sample = text.splitlines()
            if not sample:
                issues.append({"level": "warning", "code": "empty_csv", "file": rel, "message": "CSV 文件为空。"})
                summaries.append({"file": rel, "ok": False, "rows": 0, "columns": []})
                continue
            dialect = csv.Sniffer().sniff("\n".join(sample[:10])) if len(sample) > 1 else csv.excel
            reader = csv.DictReader(text.splitlines(), dialect=dialect)
            columns = list(reader.fieldnames or [])
            if not columns:
                issues.append({"level": "error", "code": "missing_header", "file": rel, "message": "CSV 缺少表头。"})
            dup_cols = [c for c, n in Counter(columns).items() if n > 1]
            if dup_cols:
                issues.append({"level": "error", "code": "duplicate_header", "file": rel, "columns": dup_cols, "message": "CSV 表头重复。"})
            rows = list(reader)
            rows_total += len(rows)
            blank_rows = 0
            for i, row in enumerate(rows, start=2):
                if not any(str(v or "").strip() for v in row.values()):
                    blank_rows += 1
                    continue
                if columns and not any(str(row.get(c) or "").strip() for c in columns[: min(2, len(columns))]):
                    issues.append({"level": "warning", "code": "weak_key", "file": rel, "row": i, "message": "前两列均为空，知识条目缺少可检索主键。"})
            if blank_rows:
                issues.append({"level": "warning", "code": "blank_rows", "file": rel, "count": blank_rows, "message": "CSV 存在空行。"})
            summaries.append({"file": rel, "ok": not any(x.get("file") == rel and x.get("level") == "error" for x in issues), "rows": len(rows), "columns": columns})
        except Exception as exc:
            issues.append({"level": "error", "code": "read_failed", "file": rel, "message": str(exc)})
            summaries.append({"file": rel, "ok": False, "rows": 0, "columns": [], "error": str(exc)})
    report = {"ok": not any(i.get("level") == "error" for i in issues), "command": "validate-csv", "file_count": len(files), "row_count": rows_total, "files": summaries, "issues": issues, "issue_count": len(issues), "generated_at": now_iso()}
    return _write_report(storage, project_id, "validate_csv", report)


def quality_trend_command(storage: Any, project_id: str) -> dict[str, Any]:
    """Reference-compatible quality_trend_report.py: trend report across reviews/chapters."""
    paths = storage.ensure_project_dirs(project_id)
    rows: list[dict[str, Any]] = []
    for ch in storage.list_chapters(project_id):
        no = int(ch.get("chapterNo") or 0)
        _, text = storage.load_chapter(project_id, no)
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
        dialogue = sum(1 for p in paragraphs if "“" in p or '"' in p or "：" in p)
        review = read_json(Path(paths.reviews) / f"第{no:04d}章_review.json", {}) or {}
        quality = read_json(Path(paths.artifacts) / f"第{no:04d}章" / "06_quality_gate.json", {}) or {}
        lang = read_json(Path(paths.control) / "reports" / "language" / f"chapter_{no:04d}_anti_ai.json", {}) or {}
        issues = []
        for item in [review, quality, lang]:
            if isinstance(item, dict):
                for key in ["issues", "warnings", "errors", "blocking"]:
                    val = item.get(key)
                    if isinstance(val, list):
                        issues.extend(val)
        rows.append({
            "chapter_no": no,
            "title": ch.get("title") or "",
            "chars": len(text),
            "paragraphs": len(paragraphs),
            "dialogue_ratio": round(dialogue / max(len(paragraphs), 1), 4),
            "issue_count": len(issues),
            "has_review": bool(review),
            "has_quality_gate": bool(quality),
        })
    avg_chars = round(sum(r["chars"] for r in rows) / max(len(rows), 1), 2) if rows else 0
    avg_dialogue = round(sum(r["dialogue_ratio"] for r in rows) / max(len(rows), 1), 4) if rows else 0
    report = {"ok": True, "command": "quality-trend", "chapter_count": len(rows), "averages": {"chars": avg_chars, "dialogue_ratio": avg_dialogue}, "chapters": rows, "generated_at": now_iso()}
    return _write_report(storage, project_id, "quality_trend", report)


def rename_chapter_command(storage: Any, project_id: str, chapter_no: int, new_title: str, apply: bool = False) -> dict[str, Any]:
    """Reference-compatible chapter_rename.py: safely rename chapter title/file."""
    paths = storage.ensure_project_dirs(project_id)
    chapter_path, text = storage.load_chapter(project_id, chapter_no)
    if not chapter_path:
        return _write_report(storage, project_id, "rename_chapter", {"ok": False, "command": "rename-chapter", "chapter_no": chapter_no, "errors": ["未找到章节正文。"]})
    title = str(new_title or "").strip()
    if not title:
        return _write_report(storage, project_id, "rename_chapter", {"ok": False, "command": "rename-chapter", "chapter_no": chapter_no, "errors": ["缺少新标题。"]})
    safe = re.sub(r"[\\/:*?\"<>|\r\n]+", "_", title).strip() or f"第{chapter_no}章"
    target = Path(paths.chapters) / f"第{chapter_no:04d}章_{safe}.txt"
    report = {"ok": True, "command": "rename-chapter", "chapter_no": chapter_no, "old_path": str(chapter_path), "new_path": str(target), "new_title": title, "apply": apply, "generated_at": now_iso()}
    if apply:
        if target != chapter_path:
            if target.exists():
                backup_file = target.with_suffix(target.suffix + f".bak_{datetime.now().strftime('%Y%m%d%H%M%S')}")
                target.rename(backup_file)
                report["overwritten_backup"] = str(backup_file)
            chapter_path.rename(target)
        state = storage.load_state(project_id)
        titles = state.setdefault("chapter_titles", {})
        titles[str(chapter_no)] = title
        storage.save_state(project_id, state)
        storage.rebuild_chapter_index(project_id)
        storage.sync_novel_file(project_id)
        append_jsonl(Path(paths.root) / "events" / "event_log.jsonl", {"event_id": _sha(json.dumps(report, ensure_ascii=False))[:16], "type": "chapter_renamed", "chapter_no": chapter_no, "title": title, "ts": now_iso(), "source": "rename-chapter"})
    return _write_report(storage, project_id, "rename_chapter", report)


def update_master_outline_command(storage: Any, project_id: str, apply: bool = True) -> dict[str, Any]:
    """Reference-compatible update_master_outline.py: rebuild master outline from state, blueprints and chapters."""
    paths = storage.ensure_project_dirs(project_id)
    meta = storage.load_meta(project_id)
    state = storage.load_state(project_id)
    chapters = storage.list_chapters(project_id)
    blueprints = {int(x.get("chapterNo") or 0): x for x in storage.list_blueprints(project_id)}
    lines = [f"# {meta.get('title') or Path(paths.root).name} 总纲", "", "## 项目概况", "", f"- 题材：{meta.get('genre') or ''}", f"- 最新章节：{state.get('latest_chapter') or 0}", f"- 角色数：{len(state.get('characters') or {})}", f"- 伏笔数：{len(state.get('foreshadows') or {})}", "", "## 章节目录", ""]
    for ch in chapters:
        no = int(ch.get("chapterNo") or 0)
        bp = storage.load_blueprint_json(project_id, no)
        goal = bp.get("goal") or bp.get("章节目标") or ""
        lines.append(f"- 第{no:04d}章：{ch.get('title') or ''}" + (f"｜目标：{goal}" if goal else "") + ("｜有蓝图" if no in blueprints else ""))
    lines += ["", "## 开放伏笔", ""]
    for name, item in (state.get("foreshadows") or {}).items():
        if isinstance(item, dict) and str(item.get("status") or "").lower() not in {"closed", "resolved", "已回收", "完成"}:
            lines.append(f"- {name}：{item.get('status') or ''} {item.get('note') or item.get('notes') or ''}")
    text = "\n".join(lines).strip() + "\n"
    out = Path(paths.outlines) / "总纲.md"
    if apply:
        write_text(out, text)
    report = {"ok": True, "command": "update-master-outline", "apply": apply, "path": str(out), "chapter_count": len(chapters), "generated_at": now_iso()}
    return _write_report(storage, project_id, "update_master_outline", report)


def runtime_health_command(storage: Any, project_id: str) -> dict[str, Any]:
    """Reference-compatible story_runtime_health.py: runtime health summary."""
    paths = storage.ensure_project_dirs(project_id)
    checks: list[dict[str, Any]] = []
    def check(name: str, ok: bool, detail: Any = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    check("state", Path(paths.state).exists(), paths.state)
    check("story_config", Path(paths.story_config).exists(), paths.story_config)
    check("chapter_index", (Path(paths.indexes) / "chapter_index.json").exists())
    check("chunk_index", (Path(paths.indexes) / "chunk_index.json").exists())
    check("event_log", (Path(paths.root) / "events" / "event_log.jsonl").exists())
    check("memory", (Path(paths.control) / "memory" / "project_memory.json").exists())
    check("truth", (Path(paths.control) / "truth" / "truth_index.json").exists())
    check("model_routes", (Path(paths.control) / "models" / "model_routes.json").exists())
    check("genre_profile", (Path(paths.control) / "genres" / "genre_profile.json").exists())
    check("references", (Path(paths.indexes) / "reference_index.json").exists())
    errors = [c for c in checks if not c["ok"]]
    report = {"ok": len(errors) == 0, "command": "runtime-health", "checks": checks, "missing_count": len(errors), "generated_at": now_iso()}
    return _write_report(storage, project_id, "runtime_health", report)


def amend_proposal_command(storage: Any, project_id: str, chapter_no: int = 0, query: str = "") -> dict[str, Any]:
    """Reference-compatible amend proposal: propose safe project amendments from query/rejected/doctor reports."""
    paths = storage.ensure_project_dirs(project_id)
    proposals: list[dict[str, Any]] = []
    if chapter_no:
        repair = read_json(Path(paths.control) / "reports" / "repair" / f"chapter_{chapter_no:04d}_repair_plan.json", {}) or {}
        if repair:
            proposals.append({"type": "repair_chapter", "chapter_no": chapter_no, "source": "repair_plan", "proposal": repair.get("actions") or repair.get("summary") or repair})
    if query:
        proposals.append({"type": "manual_note", "query": query, "proposal": "请审阅该人工修订意图，并通过 update-state 或 rewrite/heal 执行。"})
    if not proposals:
        lifecycle = read_json(Path(paths.control) / "reports" / "lifecycle" / "last_lifecycle_report.json", {}) or {}
        for no in (lifecycle.get("queues") or {}).get("needs_repair", [])[:10] if isinstance(lifecycle, dict) else []:
            proposals.append({"type": "repair_chapter", "chapter_no": no, "source": "lifecycle.needs_repair"})
    report = {"ok": True, "command": "amend-proposal", "chapter_no": chapter_no or None, "query": query, "proposal_count": len(proposals), "proposals": proposals, "generated_at": now_iso()}
    return _write_report(storage, project_id, "amend_proposal", report)


def override_ledger_command(storage: Any, project_id: str, chapter_no: int, reason: str = "manual", patch: dict[str, Any] | None = None, apply: bool = False) -> dict[str, Any]:
    """Reference-compatible override_ledger_service.py: record/apply explicit override entries."""
    paths = storage.ensure_project_dirs(project_id)
    ledger_path = Path(paths.control) / "override_ledger.jsonl"
    entry = {"event_id": _sha(json.dumps({"chapter": chapter_no, "reason": reason, "patch": patch, "ts": now_iso()}, ensure_ascii=False))[:16], "type": "override_ledger", "chapter_no": chapter_no or None, "reason": reason, "patch": patch or {}, "apply": apply, "ts": now_iso()}
    append_jsonl(ledger_path, entry)
    if apply and isinstance(patch, dict) and patch:
        state = storage.load_state(project_id)
        _deep_merge(state, patch)
        storage.save_state(project_id, state)
        append_jsonl(Path(paths.root) / "events" / "event_log.jsonl", entry)
    report = {"ok": True, "command": "override-ledger", "ledger_path": str(ledger_path), "entry": entry, "generated_at": now_iso()}
    return _write_report(storage, project_id, "override_ledger", report)
