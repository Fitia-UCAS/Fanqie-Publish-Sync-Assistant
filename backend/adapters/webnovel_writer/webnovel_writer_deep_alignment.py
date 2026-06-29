from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, read_jsonl, write_json, append_jsonl
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _report_path(storage: Any, project_id: str, group: str, name: str) -> Path:
    p = Path(storage.paths(project_id).control) / "reports" / group / f"{name}.json"
    ensure_dir(p.parent)
    return p


def _slug(text: str) -> str:
    raw = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(text or "").strip())
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw or "item"


def _chapter_file(storage: Any, project_id: str, chapter_no: int) -> tuple[Path | None, str]:
    try:
        return storage.load_chapter(project_id, chapter_no)
    except Exception:
        return None, ""


def _tokens(text: str) -> list[str]:
    text = str(text or "")
    words = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,4}", text)
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    out = [w.lower() for w in words]
    # Add short Chinese shingles. This gives usable local recall without an external vector service.
    for n in (2, 3):
        for i in range(0, max(0, len(chars) - n + 1)):
            out.append("".join(chars[i:i+n]))
    return out


def _estimate_tokens(text: str) -> int:
    # Chinese prose is usually closer to char/1.7 than char/4; keep this deterministic.
    return max(1, int(len(str(text or "")) / 1.7))


def _hash_vector(text: str, dims: int = 256) -> list[float]:
    vec = [0.0] * dims
    counts = Counter(_tokens(text))
    if not counts:
        return vec
    for tok, freq in counts.items():
        h = hashlib.blake2b(tok.encode("utf-8", errors="ignore"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dims
        sign = -1.0 if (h[4] & 1) else 1.0
        vec[idx] += sign * (1.0 + math.log1p(freq))
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(a[i] * b[i] for i in range(n))


def _first_nonempty(text: str, limit: int = 300) -> str:
    for line in str(text or "").splitlines():
        s = line.strip()
        if s:
            return s[:limit]
    return str(text or "").strip()[:limit]


def _read_commit(path: Path) -> dict[str, Any]:
    data = read_json(path, {}) or {}
    return data if isinstance(data, dict) else {}


def _commit_files(storage: Any, project_id: str) -> list[Path]:
    return sorted(Path(storage.paths(project_id).commits).glob("第*章_commit.json"))


def _artifact_path(storage: Any, project_id: str, chapter_no: int, name: str) -> Path:
    return Path(storage.paths(project_id).artifacts) / f"第{chapter_no:04d}章" / f"{name}.json"


def _entity_buckets() -> list[str]:
    return ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]


def _flatten_entities(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in _entity_buckets():
        data = state.get(bucket) or {}
        if isinstance(data, dict):
            for name, value in data.items():
                info = value if isinstance(value, dict) else {"value": value}
                rows.append({
                    "bucket": bucket,
                    "name": str(name),
                    "id": str(info.get("id") or info.get("key") or name),
                    "status": str(info.get("status") or info.get("state") or ""),
                    "location": str(info.get("location") or ""),
                    "faction": str(info.get("faction") or ""),
                    "updated_chapter": info.get("updated_chapter") or info.get("last_chapter") or 0,
                    "data": info,
                })
    return rows


def workflow_command(storage: Any, project_id: str, action: str, chapter_no: int, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Reference-style workflow checkpoint/orchestrator layer.

    This is intentionally file based: it does not hide LLM failures.  It records trusted
    artifacts and tells the caller exactly which stage is safe to resume from.
    """
    payload = payload or {}
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or payload.get("chapterNo") or 1)
    wf_dir = ensure_dir(Path(paths.control) / "workflows" / f"chapter_{chapter_no:04d}")
    checkpoint_path = wf_dir / "checkpoint.json"
    ledger_path = wf_dir / "step_ledger.jsonl"
    checkpoint = read_json(checkpoint_path, {}) or {}
    if not isinstance(checkpoint, dict):
        checkpoint = {}

    stages = [
        ("prewrite", _artifact_path(storage, project_id, chapter_no, "00_prewrite_gate")),
        ("context", Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json"),
        ("contract", Path(paths.control) / "contracts" / f"chapter_{chapter_no:04d}_contract.json"),
        ("draft", Path(paths.drafts) / f"第{chapter_no:04d}章_*_latest.txt"),
        ("review", Path(paths.reviews) / f"第{chapter_no:04d}章_review.json"),
        ("fulfillment", _artifact_path(storage, project_id, chapter_no, "fulfillment_result")),
        ("disambiguation", _artifact_path(storage, project_id, chapter_no, "disambiguation_result")),
        ("extraction", _artifact_path(storage, project_id, chapter_no, "extraction_result")),
        ("commit", Path(paths.commits) / f"第{chapter_no:04d}章_commit.json"),
        ("projection", Path(paths.state)),
        ("quality", _artifact_path(storage, project_id, chapter_no, "06_quality_gate")),
        ("user_report", Path(paths.control) / "reports" / "user" / f"chapter_{chapter_no:04d}_write_report.json"),
    ]

    def stage_status(name: str, path: Path) -> dict[str, Any]:
        if "*" in str(path):
            matches = list(path.parent.glob(path.name)) if path.parent.exists() else []
            chosen = max(matches, key=lambda p: p.stat().st_mtime) if matches else None
        else:
            chosen = path if path.exists() else None
        return {
            "stage": name,
            "ok": bool(chosen and chosen.exists()),
            "path": str(chosen) if chosen else str(path),
            "mtime": datetime.fromtimestamp(chosen.stat().st_mtime).isoformat(timespec="seconds") if chosen and chosen.exists() else "",
        }

    statuses = [stage_status(name, path) for name, path in stages]
    next_stage = next((row["stage"] for row in statuses if not row["ok"]), "done")

    if action in {"record", "step"}:
        step = str(payload.get("step") or payload.get("stage") or "manual")
        status = str(payload.get("status") or "ok")
        entry = {"at": _now(), "chapter_no": chapter_no, "step": step, "status": status, "payload": payload.get("ledgerPayload") or payload}
        append_jsonl(ledger_path, entry)
        checkpoint.setdefault("manual_steps", []).append(entry)

    if action in {"orchestrate", "refresh", "status", "resume", "record", "step", "checkpoint"}:
        checkpoint.update({
            "schema_version": 2,
            "updated_at": _now(),
            "project_id": project_id,
            "chapter_no": chapter_no,
            "workflow": "context -> contract -> draft -> review -> fulfillment -> disambiguation -> extraction -> commit -> projection -> user_report",
            "stages": statuses,
            "next_stage": next_stage,
            "resume": {
                "can_resume": next_stage != "done",
                "from_stage": next_stage,
                "safe_to_skip_completed": [s["stage"] for s in statuses if s["ok"]],
                "advice": "从 next_stage 开始续跑；不要覆盖 safe_to_skip_completed 中已有可信产物。" if next_stage != "done" else "本章主链产物齐全。",
            },
            "ledger_path": str(ledger_path),
        })
        write_json(checkpoint_path, checkpoint)

    report = {"ok": True, "action": action or "status", "chapter_no": chapter_no, "checkpoint": checkpoint, "paths_written": {"json": str(checkpoint_path)}}
    write_json(_report_path(storage, project_id, "workflow", f"chapter_{chapter_no:04d}_{action or 'status'}"), report)
    return report


def memory_deep_command(storage: Any, project_id: str, action: str, query: str = "", budget: int = 24000) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    mem_dir = ensure_dir(Path(paths.control) / "memory")
    store_path = mem_dir / "memory_store.json"
    compact_path = mem_dir / "memory_compacted.json"
    budget_path = mem_dir / "memory_budget.json"
    schema_path = mem_dir / "memory_schema.json"

    state = storage.load_state(project_id)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(category: str, subject: str, content: str, *, status: str = "active", priority: int = 50, chapter: int = 0, source: str = "state") -> None:
        subject = str(subject or "").strip()
        content = str(content or "").strip()
        if not subject or not content:
            return
        fid = hashlib.sha1(f"{category}|{subject}|{content}|{chapter}".encode("utf-8", errors="ignore")).hexdigest()[:16]
        if fid in seen:
            return
        seen.add(fid)
        rows.append({
            "memory_id": fid,
            "category": category,
            "subject": subject,
            "content": content[:2000],
            "status": status or "active",
            "priority": int(priority),
            "source": source,
            "source_chapter": int(chapter or 0),
            "tokens_est": _estimate_tokens(content),
            "updated_at": _now(),
        })

    for ent in _flatten_entities(state):
        info = ent.get("data") or {}
        content = json.dumps({k: v for k, v in info.items() if k not in {"id"}}, ensure_ascii=False, sort_keys=True)
        pr = 90 if ent["bucket"] in {"characters", "foreshadows", "conflicts"} else 70
        add(ent["bucket"], ent["name"], content, status=ent.get("status") or "active", priority=pr, chapter=int(ent.get("updated_chapter") or 0), source="state")

    for key, summary in (state.get("chapter_summaries") or {}).items():
        add("chapter_summary", f"chapter_{int(key):04d}" if str(key).isdigit() else str(key), str(summary), priority=55, chapter=int(key) if str(key).isdigit() else 0, source="summary")

    for cpath in _commit_files(storage, project_id):
        commit = _read_commit(cpath)
        ch = int(commit.get("chapter_no") or 0)
        if commit.get("summary"):
            add("commit_summary", f"chapter_{ch:04d}", str(commit.get("summary")), priority=65, chapter=ch, source=str(cpath))
        for k in ["foreshadows", "conflicts", "secrets", "deadlines"]:
            data = commit.get(k) or {}
            if isinstance(data, dict):
                for name, value in data.items():
                    add(k, str(name), json.dumps(value, ensure_ascii=False), priority=85, chapter=ch, source=str(cpath))

    schema = {
        "schema_version": 1,
        "required_fields": ["memory_id", "category", "subject", "content", "status", "priority", "source_chapter", "tokens_est"],
        "categories": sorted(set(row["category"] for row in rows)),
        "status_values": sorted(set(row["status"] for row in rows)),
    }
    write_json(schema_path, schema)

    rows.sort(key=lambda r: (int(r.get("priority") or 0), int(r.get("source_chapter") or 0)), reverse=True)
    store = {"schema_version": 1, "updated_at": _now(), "count": len(rows), "items": rows}
    write_json(store_path, store)

    total_tokens = sum(int(r.get("tokens_est") or 0) for r in rows)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    used = 0
    for row in rows:
        cost = int(row.get("tokens_est") or 0)
        if used + cost <= budget or not kept:
            kept.append(row)
            used += cost
        else:
            dropped.append(row)
    compacted = {
        "schema_version": 1,
        "updated_at": _now(),
        "budget": budget,
        "total_tokens_est": total_tokens,
        "kept_tokens_est": used,
        "kept_count": len(kept),
        "compacted_count": len(dropped),
        "kept": kept,
        "compacted_summary": _compact_memory_summary(dropped),
    }
    write_json(compact_path, compacted)
    write_json(budget_path, {"schema_version": 1, "budget": budget, "used": used, "total": total_tokens, "kept_count": len(kept), "dropped_count": len(dropped)})

    conflicts = _memory_conflicts(rows)
    if action in {"query", "search"}:
        q = str(query or "").lower().strip()
        result_rows = [r for r in rows if not q or q in json.dumps(r, ensure_ascii=False).lower()]
    elif action == "conflicts":
        result_rows = conflicts
    elif action == "compact":
        result_rows = compacted.get("kept", [])
    else:
        result_rows = rows[:50]

    report = {
        "ok": True,
        "action": action or "rebuild",
        "count": len(rows),
        "total_tokens_est": total_tokens,
        "budget": budget,
        "conflict_count": len(conflicts),
        "results": result_rows[: max(20, 100 if action in {"dump", "rebuild"} else 50)],
        "paths_written": {"store": str(store_path), "compacted": str(compact_path), "budget": str(budget_path), "schema": str(schema_path)},
    }
    write_json(_report_path(storage, project_id, "memory", f"deep_memory_{action or 'rebuild'}"), report)
    return report


def _compact_memory_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_cat[str(row.get("category") or "other")].append(f"{row.get('subject')}: {str(row.get('content') or '')[:80]}")
    return {cat: vals[:20] for cat, vals in by_cat.items()}


def _memory_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[(str(row.get("category") or ""), str(row.get("subject") or ""))].append(row)
    conflicts: list[dict[str, Any]] = []
    for (category, subject), items in buckets.items():
        statuses = {str(i.get("status") or "") for i in items if i.get("status")}
        contents = {hashlib.sha1(str(i.get("content") or "").encode("utf-8")).hexdigest() for i in items}
        if len(statuses) > 1 or len(contents) > 3:
            conflicts.append({"category": category, "subject": subject, "status_values": sorted(statuses), "item_count": len(items), "sample": items[:3]})
    return conflicts


def rag_vector_command(storage: Any, project_id: str, action: str, query: str = "", top_k: int = 8, dims: int = 256) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    index_path = Path(paths.indexes) / "vector_index.json"
    if action in {"build", "rebuild", "index", "stats", "query", "search", ""}:
        docs = []
        for row in storage.list_chapters(project_id):
            p = Path(row["path"])
            text = read_text_auto(p) if p.exists() else ""
            # chunk by paragraphs but keep deterministic size for long chapters
            paras = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
            chunks: list[str] = []
            buf = ""
            for para in paras or [text]:
                if len(buf) + len(para) > 900 and buf:
                    chunks.append(buf)
                    buf = para
                else:
                    buf = (buf + "\n" + para).strip()
            if buf:
                chunks.append(buf)
            for idx, chunk in enumerate(chunks):
                docs.append({
                    "doc_id": f"chapter_{int(row['chapterNo']):04d}_chunk_{idx:03d}",
                    "chapter_no": int(row["chapterNo"]),
                    "title": row.get("title") or "",
                    "chunk_index": idx,
                    "path": str(p),
                    "snippet": _first_nonempty(chunk, 360),
                    "tokens_est": _estimate_tokens(chunk),
                    "vector": _hash_vector(chunk, dims),
                })
        index = {"schema_version": 1, "updated_at": _now(), "dims": dims, "doc_count": len(docs), "docs": docs}
        if action in {"build", "rebuild", "index", "", "query", "search", "stats"}:
            write_json(index_path, index)
    else:
        index = read_json(index_path, {}) or {}
    if action in {"query", "search"}:
        if not index.get("docs"):
            index = read_json(index_path, {}) or {}
        qv = _hash_vector(query, int(index.get("dims") or dims))
        rows = []
        q_terms = set(_tokens(query))
        for doc in index.get("docs") or []:
            score = _cosine(qv, doc.get("vector") or [])
            lex = 0.0
            snip = str(doc.get("snippet") or "")
            for t in q_terms:
                if t and t in snip:
                    lex += 0.03
            final = score + lex
            if final > 0:
                rows.append({k: v for k, v in doc.items() if k != "vector"} | {"score": round(final, 6)})
        rows.sort(key=lambda r: r["score"], reverse=True)
        results = rows[: max(0, top_k)]
    else:
        results = []
    report = {"ok": True, "action": action or "build", "doc_count": int(index.get("doc_count") or 0), "dims": int(index.get("dims") or dims), "results": results, "paths_written": {"vector_index": str(index_path)}}
    write_json(_report_path(storage, project_id, "rag", f"vector_{action or 'build'}"), report)
    return report


def review_deep_command(storage: Any, project_id: str, chapter_no: int, action: str = "run", max_rounds: int = 3) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    chapter_path, text = _chapter_file(storage, project_id, chapter_no)
    blueprint = storage.load_blueprint_json(project_id, chapter_no)
    state = storage.load_state(project_id)
    entities = _flatten_entities(state)
    lower_text = text.lower()
    issues: list[dict[str, Any]] = []

    required_nodes = blueprint.get("must_cover_nodes") or blueprint.get("required_beats") or []
    fulfilled_nodes = []
    missing_nodes = []
    for node in required_nodes if isinstance(required_nodes, list) else []:
        phrase = str(node or "").strip()
        if not phrase:
            continue
        score = _phrase_evidence_score(text, phrase)
        row = {"node": phrase, "score": score, "evidence": score >= 0.45}
        fulfilled_nodes.append(row)
        if score < 0.45:
            missing_nodes.append(row)
            issues.append({"type": "fulfillment_missing", "severity": "major", "message": f"蓝图必达节点证据不足：{phrase}", "score": score})

    mentions = []
    ambiguous = []
    for ent in entities:
        name = ent["name"]
        aliases = [name]
        data = ent.get("data") or {}
        if isinstance(data.get("aliases"), list):
            aliases += [str(x) for x in data["aliases"]]
        count = sum(text.count(alias) for alias in set(aliases) if alias)
        if count:
            mentions.append({"bucket": ent["bucket"], "name": name, "count": count, "id": ent.get("id")})
    by_name = defaultdict(list)
    for ent in entities:
        by_name[ent["name"]].append(ent)
    for name, vals in by_name.items():
        if len(vals) > 1 and text.count(name) > 0:
            ambiguous.append({"name": name, "candidates": [{"bucket": v["bucket"], "id": v.get("id")} for v in vals]})
            issues.append({"type": "entity_ambiguous", "severity": "minor", "message": f"实体名存在多个候选：{name}"})

    word_count = len(text)
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    dialogue_lines = [l for l in text.splitlines() if re.search(r"[“\"].+[”\"]|^\s*[A-Za-z\u4e00-\u9fff]{1,8}[：:]", l)]
    ai_phrases = ["不禁", "与此同时", "显然", "然而", "他知道", "一种难以言喻", "空气仿佛凝固"]
    ai_hits = [p for p in ai_phrases if p in text]
    repeated = _repeated_phrases(text)
    if not text.strip():
        issues.append({"type": "missing_chapter", "severity": "fatal", "message": "正文不存在或为空。"})
    if word_count and word_count < 1200:
        issues.append({"type": "short_chapter", "severity": "minor", "message": f"章节偏短：{word_count} 字。"})
    if len(ai_hits) >= 3:
        issues.append({"type": "ai_style", "severity": "minor", "message": f"疑似模板化表达较多：{', '.join(ai_hits[:6])}"})
    if repeated:
        issues.append({"type": "repeat_phrase", "severity": "minor", "message": f"重复短语：{', '.join([x['phrase'] for x in repeated[:5]])}"})

    review_result = {
        "schema_version": 2,
        "chapter_no": chapter_no,
        "status": "fail" if any(i["severity"] in {"fatal", "major"} for i in issues) else "pass_with_warnings" if issues else "pass",
        "dimensions": {
            "fulfillment": 100 - min(100, len(missing_nodes) * 25),
            "continuity": 90 - min(60, len(ambiguous) * 10),
            "language": 88 - min(60, len(ai_hits) * 5 + len(repeated) * 3),
            "structure": 82 if paragraphs else 0,
            "hook": 80 if _has_hook(text) else 45,
        },
        "issues": issues,
        "rounds": [{"round": 1, "status": "local_review", "issue_count": len(issues)}],
    }
    fulfillment_result = {"schema_version": 1, "chapter_no": chapter_no, "blueprint_title": blueprint.get("title") or "", "required_nodes": fulfilled_nodes, "missing_count": len(missing_nodes), "ok": len(missing_nodes) == 0}
    disambiguation_result = {"schema_version": 1, "chapter_no": chapter_no, "ambiguous": ambiguous, "mentions": mentions, "ok": not ambiguous}
    extraction_result = {"schema_version": 1, "chapter_no": chapter_no, "mentions": mentions, "facts": _extract_light_facts(text, mentions), "ok": bool(text.strip())}
    all_artifacts = {
        "review_result": review_result,
        "fulfillment_result": fulfillment_result,
        "disambiguation_result": disambiguation_result,
        "extraction_result": extraction_result,
    }
    written = {}
    for name, data in all_artifacts.items():
        path = _artifact_path(storage, project_id, chapter_no, name)
        write_json(path, data)
        written[name] = str(path)
    combined_path = _artifact_path(storage, project_id, chapter_no, "review_pipeline_full")
    write_json(combined_path, {"schema_version": 2, "chapter_no": chapter_no, "artifacts": all_artifacts})
    report = {"ok": review_result["status"] != "fail", "action": action, "chapter_no": chapter_no, "status": review_result["status"], "issue_count": len(issues), "paths_written": written | {"combined": str(combined_path)}, "artifacts": all_artifacts}
    write_json(_report_path(storage, project_id, "review", f"chapter_{chapter_no:04d}_deep_review"), report)
    return report


def _phrase_evidence_score(text: str, phrase: str) -> float:
    tks = set(_tokens(phrase))
    if not tks:
        return 0.0
    body = set(_tokens(text))
    return round(len(tks & body) / max(1, len(tks)), 4)


def _repeated_phrases(text: str) -> list[dict[str, Any]]:
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    c = Counter("".join(chars[i:i+4]) for i in range(max(0, len(chars) - 3)))
    return [{"phrase": k, "count": v} for k, v in c.most_common(20) if v >= 5 and len(set(k)) > 1]


def _has_hook(text: str) -> bool:
    tail = str(text or "").strip()[-280:]
    return bool(re.search(r"？|!|！|忽然|突然|没想到|血|门外|身后|真相|秘密|下一刻|声音|信|令牌|名字", tail))


def _extract_light_facts(text: str, mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts = []
    sentences = re.split(r"[。！？!?\n]", text)
    for m in mentions[:50]:
        name = str(m.get("name") or "")
        if not name:
            continue
        for sent in sentences:
            if name in sent and len(sent.strip()) >= 8:
                facts.append({"subject": name, "bucket": m.get("bucket"), "sentence": sent.strip()[:240]})
                break
    return facts[:80]


def schema_validate_command(storage: Any, project_id: str, deep: bool = True) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    issues: list[dict[str, Any]] = []
    state = storage.load_state(project_id)
    for key in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "chapter_summaries", "chapter_titles"]:
        if not isinstance(state.get(key), dict):
            issues.append({"type": "state_schema", "severity": "major", "path": f"story_state.{key}", "message": "应为对象。"})
    events = storage.read_events(project_id)
    seen_events = set()
    prev = ""
    for idx, ev in enumerate(events):
        if not isinstance(ev, dict):
            issues.append({"type": "event_schema", "severity": "major", "index": idx, "message": "事件不是对象。"})
            continue
        eid = ev.get("event_id")
        if not eid:
            issues.append({"type": "event_schema", "severity": "major", "index": idx, "message": "缺 event_id。"})
        if eid in seen_events:
            issues.append({"type": "event_duplicate", "severity": "major", "event_id": eid})
        seen_events.add(eid)
        if idx and ev.get("prev_fingerprint") != prev:
            issues.append({"type": "event_chain", "severity": "major", "index": idx, "message": "事件链 prev_fingerprint 不连续。"})
        prev = str(ev.get("fingerprint") or prev)
    for cpath in _commit_files(storage, project_id):
        c = _read_commit(cpath)
        for req in ["chapter_no", "commit_id", "summary"]:
            if req not in c:
                issues.append({"type": "commit_schema", "severity": "minor", "path": str(cpath), "message": f"缺字段 {req}"})
        if c.get("status") and c.get("status") not in {"accepted", "rejected", "draft", "committed"}:
            issues.append({"type": "commit_status", "severity": "minor", "path": str(cpath), "status": c.get("status")})
    mem = read_json(Path(paths.control) / "memory" / "memory_store.json", {}) or {}
    if mem and isinstance(mem, dict):
        for idx, row in enumerate(mem.get("items") or []):
            missing = [k for k in ["memory_id", "category", "subject", "content", "priority"] if k not in row]
            if missing:
                issues.append({"type": "memory_schema", "severity": "minor", "index": idx, "missing": missing})
    report = {"ok": not any(i.get("severity") in {"fatal", "major"} for i in issues), "issue_count": len(issues), "issues": issues, "checked": {"state": True, "events": len(events), "commits": len(_commit_files(storage, project_id)), "memory": bool(mem)}, "paths": {"state": paths.state}}
    out = _report_path(storage, project_id, "schema", "last_schema_validation")
    write_json(out, report)
    report["paths_written"] = {"json": str(out)}
    return report


def sqlite_command(storage: Any, project_id: str, action: str = "build", query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    db_path = Path(paths.indexes) / "webnovel_state.db"
    ensure_dir(db_path.parent)
    if action in {"build", "rebuild", "", "stats", "query"}:
        con = sqlite3.connect(db_path)
        try:
            cur = con.cursor()
            cur.executescript("""
            CREATE TABLE IF NOT EXISTS chapters (chapter_no INTEGER PRIMARY KEY, title TEXT, path TEXT, size INTEGER, summary TEXT);
            CREATE TABLE IF NOT EXISTS entities (bucket TEXT, name TEXT, entity_id TEXT, status TEXT, location TEXT, faction TEXT, updated_chapter INTEGER, data_json TEXT, PRIMARY KEY(bucket, name));
            CREATE TABLE IF NOT EXISTS events (rowid_pk INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, type TEXT, at TEXT, fingerprint TEXT, payload_json TEXT);
            CREATE TABLE IF NOT EXISTS commits (chapter_no INTEGER PRIMARY KEY, commit_id TEXT, status TEXT, summary TEXT, path TEXT, data_json TEXT);
            CREATE TABLE IF NOT EXISTS memories (memory_id TEXT PRIMARY KEY, category TEXT, subject TEXT, status TEXT, priority INTEGER, source_chapter INTEGER, tokens_est INTEGER, content TEXT, data_json TEXT);
            """)
            cur.execute("DELETE FROM chapters")
            cur.execute("DELETE FROM entities")
            cur.execute("DELETE FROM events")
            cur.execute("DELETE FROM commits")
            cur.execute("DELETE FROM memories")
            state = storage.load_state(project_id)
            summaries = state.get("chapter_summaries") or {}
            for ch in storage.list_chapters(project_id):
                cur.execute("INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?)", (int(ch.get("chapterNo") or 0), ch.get("title") or "", ch.get("path") or "", int(ch.get("size") or 0), str(summaries.get(str(ch.get("chapterNo"))) or "")))
            for ent in _flatten_entities(state):
                cur.execute("INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?)", (ent["bucket"], ent["name"], ent.get("id") or "", ent.get("status") or "", ent.get("location") or "", ent.get("faction") or "", int(ent.get("updated_chapter") or 0), json.dumps(ent.get("data") or {}, ensure_ascii=False)))
            for ev in storage.read_events(project_id):
                if isinstance(ev, dict):
                    cur.execute("INSERT INTO events(event_id,type,at,fingerprint,payload_json) VALUES (?,?,?,?,?)", (ev.get("event_id") or "", ev.get("type") or "", ev.get("at") or "", ev.get("fingerprint") or "", json.dumps(ev.get("payload") or {}, ensure_ascii=False)))
            for cpath in _commit_files(storage, project_id):
                c = _read_commit(cpath)
                cur.execute("INSERT OR REPLACE INTO commits VALUES (?,?,?,?,?,?)", (int(c.get("chapter_no") or 0), c.get("commit_id") or "", c.get("status") or "", c.get("summary") or "", str(cpath), json.dumps(c, ensure_ascii=False)))
            mem = read_json(Path(paths.control) / "memory" / "memory_store.json", {}) or {}
            for row in mem.get("items") or []:
                cur.execute("INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?,?,?,?,?)", (row.get("memory_id") or "", row.get("category") or "", row.get("subject") or "", row.get("status") or "", int(row.get("priority") or 0), int(row.get("source_chapter") or 0), int(row.get("tokens_est") or 0), row.get("content") or "", json.dumps(row, ensure_ascii=False)))
            con.commit()
            stats = {table: cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["chapters", "entities", "events", "commits", "memories"]}
            results: list[dict[str, Any]] = []
            if action == "query" and query:
                q = f"%{query}%"
                for table, cols in [("chapters", "chapter_no,title,summary,path"), ("entities", "bucket,name,status,location,faction"), ("memories", "category,subject,status,content")]:
                    if table == "chapters":
                        rows = cur.execute(f"SELECT {cols} FROM {table} WHERE title LIKE ? OR summary LIKE ? LIMIT 20", (q, q)).fetchall()
                    elif table == "entities":
                        rows = cur.execute(f"SELECT {cols} FROM {table} WHERE name LIKE ? OR status LIKE ? OR location LIKE ? OR faction LIKE ? LIMIT 20", (q, q, q, q)).fetchall()
                    else:
                        rows = cur.execute(f"SELECT {cols} FROM {table} WHERE subject LIKE ? OR content LIKE ? LIMIT 20", (q, q)).fetchall()
                    for row in rows:
                        results.append({"table": table, "values": list(row)})
        finally:
            con.close()
    else:
        stats = {}
        results = []
    report = {"ok": True, "action": action or "build", "db_path": str(db_path), "stats": stats, "results": results, "paths_written": {"sqlite": str(db_path)}}
    write_json(_report_path(storage, project_id, "sqlite", f"sqlite_{action or 'build'}"), report)
    return report


def publisher_bridge_command(storage: Any, project_id: str, action: str = "plan", start: int = 0, end: int = 0, platform: str = "fanqie") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    pub_dir = ensure_dir(Path(paths.control) / "publisher")
    state = storage.load_state(project_id)
    publication = state.setdefault("publication", {}) if isinstance(state, dict) else {}
    pub_chapters = publication.setdefault("chapters", {}) if isinstance(publication, dict) else {}
    chapters = storage.list_chapters(project_id)
    jobs = []
    for ch in chapters:
        no = int(ch.get("chapterNo") or 0)
        if start and no < start:
            continue
        if end and no > end:
            continue
        status = (pub_chapters.get(str(no)) or {}).get("status") if isinstance(pub_chapters.get(str(no)), dict) else ""
        commit_path = Path(paths.commits) / f"第{no:04d}章_commit.json"
        ready = commit_path.exists() and status not in {"published", "publishing"}
        if ready:
            jobs.append({"chapter_no": no, "title": ch.get("title") or "", "chapter_path": ch.get("path"), "commit_path": str(commit_path), "platform": platform or "fanqie", "status": "ready"})
    plan = {"schema_version": 1, "updated_at": _now(), "platform": platform or "fanqie", "start": start, "end": end, "job_count": len(jobs), "jobs": jobs}
    plan_path = write_json(pub_dir / "publisher_jobs.json", plan)
    if action in {"mark-queued", "queue"}:
        for job in jobs:
            pub_chapters[str(job["chapter_no"])] = {"status": "queued", "platform": job["platform"], "updated_at": _now()}
        storage.save_state(project_id, state)
        storage.append_event(project_id, "publisher_jobs_queued", {"platform": platform, "jobs": jobs})
    if action in {"export", "prepare", "plan", "queue", "mark-queued"}:
        txt = storage.export_txt(project_id)
        zip_path = Path(paths.exports) / f"publisher_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(plan_path, plan_path.relative_to(paths.root))
            if txt and Path(txt).exists():
                zf.write(txt, Path(txt).relative_to(paths.root))
            for job in jobs:
                p = Path(job["chapter_path"])
                if p.exists():
                    zf.write(p, p.relative_to(paths.root))
        out_zip = str(zip_path)
    else:
        out_zip = ""
    report = {"ok": True, "action": action or "plan", "platform": platform or "fanqie", "job_count": len(jobs), "jobs": jobs, "paths_written": {"jobs": str(plan_path), "zip": out_zip}}
    write_json(_report_path(storage, project_id, "publisher", f"publisher_bridge_{action or 'plan'}"), report)
    return report


def deep_alignment_command(storage: Any, project_id: str) -> dict[str, Any]:
    """One command to refresh the deep back-end counterparts of the reference projects."""
    paths = _paths(storage, project_id)
    outputs = {}
    outputs["memory"] = memory_deep_command(storage, project_id, "rebuild")
    outputs["rag_vector"] = rag_vector_command(storage, project_id, "build")
    outputs["schema"] = schema_validate_command(storage, project_id)
    outputs["sqlite"] = sqlite_command(storage, project_id, "build")
    outputs["publisher"] = publisher_bridge_command(storage, project_id, "plan")
    # Refresh workflow checkpoints for the visible chapter range without invoking LLM.
    workflow_reports = []
    for ch in storage.list_chapters(project_id)[:200]:
        workflow_reports.append(workflow_command(storage, project_id, "status", int(ch.get("chapterNo") or 0)))
    outputs["workflows"] = {"count": len(workflow_reports), "chapters": [r.get("chapter_no") for r in workflow_reports]}
    report = {"ok": True, "updated_at": _now(), "outputs": outputs}
    out = _report_path(storage, project_id, "deep_alignment", "last_deep_alignment")
    write_json(out, report)
    report["paths_written"] = {"json": str(out)}
    return report
