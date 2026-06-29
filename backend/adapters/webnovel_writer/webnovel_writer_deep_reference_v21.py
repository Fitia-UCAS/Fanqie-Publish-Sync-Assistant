from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import append_jsonl, read_json, read_jsonl, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


ENTITY_BUCKETS = ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]
STAGE_ORDER = [
    "prewrite", "context", "contract", "task_book", "draft", "review", "fulfillment",
    "disambiguation", "extraction", "commit", "projection", "quality", "user_report",
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except Exception:
        return str(value)


def _write_report(storage: Any, project_id: str, group: str, name: str, data: dict[str, Any]) -> Path:
    p = Path(storage.paths(project_id).control) / "reports" / group / f"{name}.json"
    ensure_dir(p.parent)
    write_json(p, data)
    return p


def _tokens(text: str) -> list[str]:
    text = str(text or "")
    words = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,4}", text)
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    out = [w.lower() for w in words]
    for n in (2, 3, 4):
        for i in range(0, max(0, len(chars) - n + 1)):
            out.append("".join(chars[i:i + n]))
    return out


def _token_counter(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _hash_vector(text: str, dims: int = 384) -> list[float]:
    vec = [0.0] * dims
    for tok, freq in _token_counter(text).items():
        h = hashlib.blake2b(tok.encode("utf-8", errors="ignore"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "little") % dims
        sign = -1.0 if h[4] & 1 else 1.0
        vec[idx] += sign * (1.0 + math.log1p(freq))
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n <= 0:
        return 0.0
    return float(sum(a[i] * b[i] for i in range(n)))


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(str(text or "")) / 1.7))


def _fingerprint(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _chapter_file(storage: Any, project_id: str, chapter_no: int) -> tuple[Path | None, str]:
    try:
        return storage.load_chapter(project_id, chapter_no)
    except Exception:
        return None, ""


def _chapter_paths(paths: Any, chapter_no: int) -> dict[str, Path]:
    art_dir = Path(paths.artifacts) / f"第{chapter_no:04d}章"
    return {
        "prewrite": art_dir / "00_prewrite_gate.json",
        "context": Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json",
        "contract": Path(paths.control) / "contracts" / f"chapter_{chapter_no:04d}_contract.json",
        "task_book": Path(paths.control) / "workflows" / f"chapter_{chapter_no:04d}" / "task_book.json",
        "draft": Path(paths.drafts) / f"第{chapter_no:04d}章_draft_latest.txt",
        "review": Path(paths.reviews) / f"第{chapter_no:04d}章_review.json",
        "fulfillment": art_dir / "fulfillment_result.json",
        "disambiguation": art_dir / "disambiguation_result.json",
        "extraction": art_dir / "extraction_result.json",
        "commit": Path(paths.commits) / f"第{chapter_no:04d}章_commit.json",
        "projection": Path(paths.state),
        "quality": art_dir / "06_quality_gate.json",
        "user_report": Path(paths.control) / "reports" / "user" / f"chapter_{chapter_no:04d}_write_report.json",
    }


def _load_blueprint(paths: Any, chapter_no: int) -> dict[str, Any]:
    candidates = [
        Path(paths.control) / "blueprints" / f"chapter_{chapter_no:04d}.json",
        Path(paths.blueprints) / f"chapter_{chapter_no:04d}.json",
    ]
    for p in candidates:
        data = read_json(p, None)
        if isinstance(data, dict):
            return data
    return {}


def _flatten_state_entities(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in ENTITY_BUCKETS:
        data = state.get(bucket) or {}
        if isinstance(data, dict):
            for name, value in data.items():
                info = value if isinstance(value, dict) else {"value": value}
                aliases = info.get("aliases") or []
                if isinstance(aliases, str):
                    aliases = [a.strip() for a in re.split(r"[,，、;；\s]+", aliases) if a.strip()]
                rows.append({
                    "bucket": bucket,
                    "name": str(name),
                    "id": str(info.get("id") or info.get("key") or name),
                    "aliases": aliases if isinstance(aliases, list) else [],
                    "status": str(info.get("status") or info.get("state") or ""),
                    "location": str(info.get("location") or ""),
                    "faction": str(info.get("faction") or ""),
                    "priority": _safe_int(info.get("priority"), 50),
                    "data": info,
                })
    return rows


def _split_changes(text: str) -> tuple[str, str]:
    raw = str(text or "")
    patterns = [
        r"(?is)<\s*(?:chapter_changes|changes)\s*>(.*?)</\s*(?:chapter_changes|changes)\s*>",
        r"(?is)^\s*[-—–]{3}\s*CHANGES\s*[-—–]{3}\s*(.*)$",
        r"(?is)^\s*#{1,4}\s*(?:CHANGES|事实回写|变更记录|状态变更)\s*\n(.*)$",
    ]
    for pat in patterns:
        m = re.search(pat, raw, flags=re.MULTILINE)
        if m:
            return raw[:m.start()].strip(), m.group(1).strip()
    return raw, ""


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    # A conservative repair pass for common LLM output.
    fixed = re.sub(r"//.*?$|/\*.*?\*/", "", raw, flags=re.S | re.M)
    fixed = fixed.replace("True", "true").replace("False", "false").replace("None", "null")
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    fixed = re.sub(r"([{,]\s*)([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff-]*)(\s*:)", r'\1"\2"\3', fixed)
    try:
        data = json.loads(fixed)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _extract_mentioned_entities(text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    body = str(text or "")
    hits: list[dict[str, Any]] = []
    for ent in entities:
        names = [ent.get("name", ""), ent.get("id", "")] + list(ent.get("aliases") or [])
        names = [str(n).strip() for n in names if str(n).strip() and len(str(n).strip()) >= 2]
        count = sum(body.count(n) for n in set(names))
        if count:
            hits.append({"bucket": ent.get("bucket"), "name": ent.get("name"), "id": ent.get("id"), "mention_count": count})
    return hits


def _read_reference_files(paths: Any) -> list[dict[str, Any]]:
    root = Path(paths.control) / "references"
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".txt", ".md", ".json", ".csv"}:
            continue
        try:
            if p.suffix.lower() == ".csv":
                with open(p, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader, 1):
                        text = "\n".join(f"{k}: {v}" for k, v in row.items() if v)
                        rows.append({"source": "reference_csv", "path": str(p), "row": i, "title": row.get("title") or row.get("name") or p.stem, "text": text})
            elif p.suffix.lower() == ".json":
                data = read_json(p, {})
                text = json.dumps(data, ensure_ascii=False)[:8000]
                rows.append({"source": "reference_json", "path": str(p), "title": p.stem, "text": text})
            else:
                text = read_text_auto(p)
                rows.append({"source": "reference_text", "path": str(p), "title": p.stem, "text": text[:12000]})
        except Exception:
            continue
    return rows


def orchestrate_deep_command(storage: Any, project_id: str, chapter_no: int, action: str = "status", max_rounds: int = 3) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    action = action or "status"
    wf_dir = ensure_dir(Path(paths.control) / "workflows" / f"chapter_{chapter_no:04d}")
    checkpoint_path = wf_dir / "checkpoint.json"
    ledger_path = wf_dir / "step_ledger.jsonl"
    task_path = wf_dir / "task_book.json"
    resume_path = wf_dir / "resume_plan.json"
    stage_paths = _chapter_paths(paths, chapter_no)

    def trusted(stage: str, path: Path) -> dict[str, Any]:
        exists = path.exists() if "*" not in str(path) else bool(list(path.parent.glob(path.name)))
        chosen = path
        if "*" in str(path):
            matches = list(path.parent.glob(path.name)) if path.parent.exists() else []
            chosen = max(matches, key=lambda p: p.stat().st_mtime) if matches else path
        sig = _fingerprint(chosen) if chosen.exists() and chosen.is_file() else ""
        size = chosen.stat().st_size if chosen.exists() and chosen.is_file() else 0
        ok = bool(exists and (stage in {"projection"} or size > 0))
        return {"stage": stage, "ok": ok, "path": str(chosen), "signature": sig, "size": size}

    if action in {"run", "resume", "prepare", "orchestrate"}:
        state = storage.load_state(project_id)
        blueprint = _load_blueprint(paths, chapter_no)
        _, chapter_text = _chapter_file(storage, project_id, chapter_no)
        body, changes_raw = _split_changes(chapter_text)
        task_book = {
            "schema_version": 3,
            "created_at": _now(),
            "chapter_no": chapter_no,
            "chapter_title": blueprint.get("title") or f"第{chapter_no}章",
            "workflow_contract": {
                "required_output": ["正文", "CHANGES"],
                "required_artifacts": STAGE_ORDER,
                "max_review_rounds": max_rounds,
                "never_overwrite_trusted_artifacts": True,
            },
            "blueprint": blueprint,
            "state_summary": {
                bucket: len((state.get(bucket) or {}) if isinstance(state.get(bucket), dict) else {}) for bucket in ENTITY_BUCKETS
            },
            "existing_chapter": {"has_body": bool(body.strip()), "has_changes": bool(changes_raw.strip())},
            "resume_policy": "按 checkpoint.next_stage 续跑；已签名可信产物只读不覆盖。",
        }
        write_json(task_path, task_book)
        append_jsonl(ledger_path, {"at": _now(), "event": "task_book_prepared", "chapter_no": chapter_no, "path": str(task_path)})

    statuses = [trusted(stage, stage_paths[stage]) for stage in STAGE_ORDER]
    done = [s["stage"] for s in statuses if s["ok"]]
    next_stage = next((s["stage"] for s in statuses if not s["ok"]), "done")
    blocking = []
    if next_stage == "draft":
        blocking.append("缺少草稿/正文，需要调用写作模型或手工补入 draft。")
    if next_stage == "commit" and not stage_paths["extraction"].exists():
        blocking.append("缺少 extraction artifact，不能安全 commit。")
    resume = {
        "can_resume": next_stage != "done",
        "from_stage": next_stage,
        "trusted_completed_stages": done,
        "blocking": blocking,
        "commands": [
            f"python -m backend.adapters.webnovel_writer.webnovel_writer_cli workflow-resume --project {project_id!r} --chapter {chapter_no}",
            f"python -m backend.adapters.webnovel_writer.webnovel_writer_cli review-pipeline-deep --project {project_id!r} --chapter {chapter_no}",
        ],
    }
    write_json(resume_path, resume)
    checkpoint = {
        "schema_version": 3,
        "updated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "action": action,
        "stages": statuses,
        "next_stage": next_stage,
        "resume": resume,
        "ledger_path": str(ledger_path),
        "task_book_path": str(task_path),
        "resume_path": str(resume_path),
    }
    write_json(checkpoint_path, checkpoint)
    report = {"ok": True, "kind": "workflow_orchestrator_v2", "checkpoint": checkpoint, "paths_written": {"checkpoint": str(checkpoint_path), "resume": str(resume_path), "task_book": str(task_path)}}
    _write_report(storage, project_id, "workflow_v2", f"chapter_{chapter_no:04d}_{action}", report)
    return report


def memory_orchestrate_command(storage: Any, project_id: str, action: str = "rebuild", query: str = "", budget: int = 24000) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    mem_dir = ensure_dir(Path(paths.control) / "memory_v2")
    store_path = mem_dir / "store.json"
    compact_path = mem_dir / "compacted.json"
    budget_path = mem_dir / "budget.json"
    conflicts_path = mem_dir / "conflicts.json"
    schema_path = mem_dir / "schema.json"
    state = storage.load_state(project_id)

    schema = {
        "schema_version": 2,
        "fields": ["memory_id", "category", "subject", "content", "status", "priority", "source", "source_chapter", "tokens_est", "updated_at"],
        "categories": ["character_state", "location_state", "faction_state", "item_state", "foreshadow", "conflict", "secret", "deadline", "chapter_summary", "reference_knowledge"],
    }
    write_json(schema_path, schema)

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(category: str, subject: str, content: str, status: str = "active", priority: int = 50, source: str = "state", chapter: int = 0) -> None:
        subject = str(subject or "").strip()
        content = str(content or "").strip()
        if not subject or not content:
            return
        raw_id = f"{category}|{subject}|{content}|{source}|{chapter}"
        memory_id = hashlib.sha1(raw_id.encode("utf-8", errors="ignore")).hexdigest()[:18]
        if memory_id in seen:
            return
        seen.add(memory_id)
        entries.append({
            "memory_id": memory_id,
            "category": category,
            "subject": subject,
            "content": content[:2500],
            "status": status or "active",
            "priority": int(priority),
            "source": source,
            "source_chapter": int(chapter or 0),
            "tokens_est": _estimate_tokens(content),
            "updated_at": _now(),
        })

    for ent in _flatten_state_entities(state):
        bucket = ent["bucket"]
        cat = {
            "characters": "character_state", "locations": "location_state", "factions": "faction_state", "items": "item_state",
            "foreshadows": "foreshadow", "conflicts": "conflict", "secrets": "secret", "deadlines": "deadline",
        }.get(bucket, bucket)
        content = json.dumps(ent.get("data") or {}, ensure_ascii=False)
        priority = 85 if bucket in {"foreshadows", "conflicts", "deadlines"} else 60
        add(cat, ent["name"], content, ent.get("status") or "active", priority, "state", 0)

    for commit_path in sorted(Path(paths.commits).glob("第*章_commit.json")):
        data = read_json(commit_path, {}) or {}
        chapter = _safe_int(data.get("chapter_no") or data.get("chapterNo"), 0)
        summary = str(data.get("summary") or data.get("chapter_summary") or "")
        if summary:
            add("chapter_summary", f"chapter_{chapter:04d}", summary, "active", 55 + min(chapter, 20), "commit", chapter)
        changes = data.get("changes") or data.get("parsed_changes") or {}
        if isinstance(changes, dict):
            for key in ["characters", "foreshadows", "conflicts", "locations", "factions", "items"]:
                value = changes.get(key)
                if value:
                    add(f"change_{key}", f"chapter_{chapter:04d}_{key}", json.dumps(value, ensure_ascii=False), "active", 50, "commit_changes", chapter)

    for ref in _read_reference_files(paths):
        add("reference_knowledge", ref.get("title") or Path(str(ref.get("path", ""))).stem, ref.get("text") or "", "active", 45, ref.get("source") or "reference", 0)

    # detect conflicts by subject/category dimensions.
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_key[(e["category"], e["subject"])].append(e)
    conflicts: list[dict[str, Any]] = []
    for (cat, subject), group in by_key.items():
        statuses = {str(g.get("status") or "") for g in group if str(g.get("status") or "")}
        if len(statuses) > 1:
            conflicts.append({"type": "status_conflict", "category": cat, "subject": subject, "statuses": sorted(statuses), "memory_ids": [g["memory_id"] for g in group]})
        contents = [g.get("content", "") for g in group]
        if len(group) > 4 and len(set(c[:120] for c in contents)) > 3:
            conflicts.append({"type": "too_many_active_records", "category": cat, "subject": subject, "count": len(group), "memory_ids": [g["memory_id"] for g in group[:20]]})

    entries.sort(key=lambda e: (int(e.get("priority", 0)), int(e.get("source_chapter", 0))), reverse=True)
    spent = 0
    selected = []
    overflow = []
    for e in entries:
        cost = _safe_int(e.get("tokens_est"), 1)
        if spent + cost <= int(budget):
            selected.append(e)
            spent += cost
        else:
            overflow.append(e)

    compacted: list[dict[str, Any]] = []
    for (cat, subject), group in by_key.items():
        group_sorted = sorted(group, key=lambda e: (e.get("priority", 0), e.get("source_chapter", 0)), reverse=True)
        merged = "\n".join(f"- {g['content']}" for g in group_sorted[:8])
        compacted.append({
            "category": cat,
            "subject": subject,
            "summary": merged[:3000],
            "source_count": len(group_sorted),
            "priority": max(_safe_int(g.get("priority"), 0) for g in group_sorted),
            "tokens_est": _estimate_tokens(merged),
        })
    compacted.sort(key=lambda e: (e["priority"], e["source_count"]), reverse=True)

    write_json(store_path, {"schema_version": 2, "updated_at": _now(), "entries": entries})
    write_json(compact_path, {"schema_version": 2, "updated_at": _now(), "entries": compacted})
    write_json(budget_path, {"budget": budget, "spent": spent, "selected_count": len(selected), "overflow_count": len(overflow), "selected": selected, "overflow_memory_ids": [e["memory_id"] for e in overflow]})
    write_json(conflicts_path, {"schema_version": 2, "updated_at": _now(), "conflicts": conflicts})

    if action in {"query", "search"} and query:
        q = _token_counter(query)
        results = []
        for e in entries:
            c = _token_counter(f"{e.get('subject','')} {e.get('content','')}")
            overlap = sum(min(c[t], q[t]) for t in q)
            if overlap:
                results.append({"score": overlap + _safe_int(e.get("priority"), 0) / 100.0, **e})
        results.sort(key=lambda x: x["score"], reverse=True)
        report = {"ok": True, "action": action, "query": query, "results": results[:20], "paths_written": {"store": str(store_path), "budget": str(budget_path), "conflicts": str(conflicts_path)}}
    else:
        report = {"ok": True, "action": action, "entry_count": len(entries), "compacted_count": len(compacted), "conflict_count": len(conflicts), "budget": {"spent": spent, "limit": budget}, "paths_written": {"store": str(store_path), "compacted": str(compact_path), "budget": str(budget_path), "conflicts": str(conflicts_path), "schema": str(schema_path)}}
    _write_report(storage, project_id, "memory_v2", f"memory_{action or 'rebuild'}", report)
    return report


def rag_router_command(storage: Any, project_id: str, action: str = "build", query: str = "", top_k: int = 8) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    index_path = Path(paths.indexes) / "hybrid_rag_index.json"
    ensure_dir(index_path.parent)
    state = storage.load_state(project_id)
    entities = _flatten_state_entities(state)
    records: list[dict[str, Any]] = []

    def add(source: str, title: str, text: str, path: str = "", chapter: int = 0, weight: float = 1.0, meta: dict[str, Any] | None = None) -> None:
        text = str(text or "").strip()
        if not text:
            return
        rid = hashlib.sha1(f"{source}|{title}|{path}|{chapter}|{text[:240]}".encode("utf-8", errors="ignore")).hexdigest()[:20]
        toks = _token_counter(f"{title}\n{text}")
        records.append({
            "id": rid,
            "source": source,
            "title": title,
            "text": text[:3000],
            "path": path,
            "chapter_no": int(chapter or 0),
            "weight": float(weight),
            "tokens": dict(toks.most_common(300)),
            "vector": _hash_vector(f"{title}\n{text}"),
            "meta": meta or {},
        })

    # chapters split into paragraph windows
    for p in sorted(Path(paths.chapters).glob("*.txt")) + sorted(Path(paths.chapters).glob("*.md")):
        m = re.search(r"第\s*(\d+)\s*章", p.stem)
        chapter = _safe_int(m.group(1), 0) if m else 0
        text = read_text_auto(p)
        paragraphs = [x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()]
        if not paragraphs:
            paragraphs = [text]
        for i in range(0, len(paragraphs), 3):
            chunk = "\n".join(paragraphs[i:i + 4])
            add("chapter", f"{p.stem}#{i//3+1}", chunk, str(p), chapter, 1.2, {"paragraph_window": [i, i + 4]})

    for ent in entities:
        add(f"entity:{ent['bucket']}", ent["name"], json.dumps(ent.get("data") or {}, ensure_ascii=False), "story_state.json", 0, 1.15, {"entity_id": ent["id"], "aliases": ent.get("aliases")})

    mem_store = read_json(Path(paths.control) / "memory_v2" / "store.json", {}) or {}
    for e in mem_store.get("entries") or []:
        if isinstance(e, dict):
            add("memory", str(e.get("subject") or e.get("memory_id")), str(e.get("content") or ""), "writer_control/memory_v2/store.json", _safe_int(e.get("source_chapter"), 0), 1.05, {"category": e.get("category"), "memory_id": e.get("memory_id")})

    for ref in _read_reference_files(paths):
        add("reference", str(ref.get("title") or "reference"), str(ref.get("text") or ""), str(ref.get("path") or ""), 0, 0.95, {"ref_source": ref.get("source")})

    write_json(index_path, {"schema_version": 2, "updated_at": _now(), "records": records})

    def route(q: str) -> dict[str, Any]:
        q = str(q or "")
        wants = []
        if re.search(r"角色|人物|主角|反派|谁|关系", q):
            wants.append("entity:characters")
        if re.search(r"伏笔|回收|坑|债务", q):
            wants.extend(["entity:foreshadows", "memory"])
        if re.search(r"设定|知识|模板|套路|题材", q):
            wants.append("reference")
        if re.search(r"章节|正文|片段|发生", q):
            wants.append("chapter")
        if not wants:
            wants = ["chapter", "entity:characters", "memory", "reference"]
        return {"query_type": wants[0], "preferred_sources": wants, "budget_tokens": 6000}

    def search(q: str, k: int) -> list[dict[str, Any]]:
        q_tokens = _token_counter(q)
        q_vec = _hash_vector(q)
        r = route(q)
        out = []
        for rec in records:
            toks = Counter(rec.get("tokens") or {})
            lexical = sum(min(toks[t], q_tokens[t]) for t in q_tokens)
            jaccard = lexical / max(1, len(set(toks) | set(q_tokens)))
            vector = _cosine(q_vec, rec.get("vector") or [])
            source_boost = 0.35 if rec.get("source") in r["preferred_sources"] or any(str(rec.get("source", "")).startswith(s) for s in r["preferred_sources"] if s.startswith("entity:")) else 0.0
            chapter = _safe_int(rec.get("chapter_no"), 0)
            recency = min(0.2, chapter / 500.0) if chapter else 0.0
            score = (lexical * 0.7) + (jaccard * 4.0) + (vector * 2.0) + source_boost + recency
            if score > 0:
                out.append({"score": round(score, 6), "lexical": lexical, "vector": round(vector, 6), "source_boost": source_boost, "record": {k: v for k, v in rec.items() if k not in {"tokens", "vector"}}})
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:k]

    if action in {"query", "search"} and query:
        results = search(query, top_k)
        report = {"ok": True, "action": action, "route": route(query), "query": query, "results": results, "paths_written": {"index": str(index_path)}}
    else:
        by_source = Counter(r["source"] for r in records)
        report = {"ok": True, "action": action, "record_count": len(records), "by_source": dict(by_source), "paths_written": {"index": str(index_path)}}
    _write_report(storage, project_id, "rag_router", f"rag_{action or 'build'}", report)
    return report


def review_pipeline_deep_command(storage: Any, project_id: str, chapter_no: int, max_rounds: int = 3) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    art_dir = ensure_dir(Path(paths.artifacts) / f"第{chapter_no:04d}章")
    state = storage.load_state(project_id)
    entities = _flatten_state_entities(state)
    blueprint = _load_blueprint(paths, chapter_no)
    chapter_path, text = _chapter_file(storage, project_id, chapter_no)
    body, changes_raw = _split_changes(text)
    changes = _extract_json_object(changes_raw)
    mentioned = _extract_mentioned_entities(body, entities)

    def list_field(name: str) -> list[str]:
        v = blueprint.get(name) or []
        if isinstance(v, str):
            return [x.strip() for x in re.split(r"[,，、;；\n]+", v) if x.strip()]
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    required_names = list_field("required_characters") + list_field("required_locations") + list_field("required_factions")
    required_nodes = list_field("must_cover_nodes") or list_field("required_beats")
    missing_entities = [n for n in required_names if n and n not in body]
    missing_nodes = []
    for node in required_nodes:
        pieces = [p for p in re.split(r"[，,。；;、\s]+", node) if len(p) >= 2]
        if not pieces or not any(p in body for p in pieces[:5]):
            missing_nodes.append(node)

    declared_text = json.dumps(changes, ensure_ascii=False)
    omissions = [m for m in mentioned if m["name"] not in declared_text and m["id"] not in declared_text]

    # Simple disambiguation by duplicate aliases/names.
    aliases: dict[str, list[str]] = defaultdict(list)
    for ent in entities:
        for n in [ent["name"], ent["id"], *(ent.get("aliases") or [])]:
            n = str(n).strip()
            if len(n) >= 2:
                aliases[n].append(f"{ent['bucket']}:{ent['name']}")
    ambiguous = [{"surface": k, "candidates": v} for k, v in aliases.items() if len(set(v)) > 1 and k in body]

    extraction = {
        "schema_version": 2,
        "chapter_no": chapter_no,
        "summary": (body.strip().splitlines()[0] if body.strip().splitlines() else "")[:300],
        "has_changes": bool(changes),
        "changes_fields": sorted(changes.keys()) if isinstance(changes, dict) else [],
        "mentioned_entities": mentioned,
        "unreported_entities": omissions,
    }
    fulfillment = {"schema_version": 2, "chapter_no": chapter_no, "missing_entities": missing_entities, "missing_nodes": missing_nodes, "ok": not missing_entities and not missing_nodes}
    disambiguation = {"schema_version": 2, "chapter_no": chapter_no, "ambiguous": ambiguous, "pending": ambiguous, "ok": not ambiguous}

    dimensions = []
    def dim(name: str, ok: bool, score: int, issues: list[str]) -> None:
        dimensions.append({"name": name, "ok": ok, "score": score if ok else min(score, 60), "issues": issues})

    dim("blueprint_fulfillment", fulfillment["ok"], 90, missing_entities + missing_nodes)
    dim("changes_alignment", not omissions and bool(changes), 88, [f"正文出现但 CHANGES 未申报：{o['name']}" for o in omissions] + ([] if changes else ["缺少可解析 CHANGES"]))
    dim("entity_disambiguation", disambiguation["ok"], 92, [f"{a['surface']} 候选 {len(a['candidates'])} 个" for a in ambiguous])
    ai_phrases = [p for p in ["不禁", "与此同时", "命运的齿轮", "一股暖流", "眼神坚定"] if p in body]
    dim("anti_ai_language", len(ai_phrases) <= 2, 84, [f"疑似套话：{p}" for p in ai_phrases])
    paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    dim("readability", 5 <= len(paragraphs) <= 160, 80, [] if paragraphs else ["正文段落为空"])

    blocking = []
    for d in dimensions:
        if not d["ok"] and d["name"] in {"blueprint_fulfillment", "changes_alignment", "entity_disambiguation"}:
            blocking.extend(d["issues"])
    rounds = []
    current = blocking[:]
    for round_no in range(1, max(1, int(max_rounds)) + 1):
        if not current:
            break
        rounds.append({
            "round": round_no,
            "status": "needs_model_or_manual_repair",
            "target_issues": current[:12],
            "repair_prompt": "只修复 target_issues 对应问题；保持正文主情节不变；输出完整正文和 CHANGES。",
        })
        # Local pipeline can only plan repairs, not hallucinate a new chapter. Keep issues explicit.
        break

    review_schema = {
        "schema_version": 2,
        "dimensions": ["blueprint_fulfillment", "changes_alignment", "entity_disambiguation", "anti_ai_language", "readability"],
        "blocking_dimensions": ["blueprint_fulfillment", "changes_alignment", "entity_disambiguation"],
        "max_rounds": max_rounds,
    }
    combined = {
        "schema_version": 2,
        "chapter_no": chapter_no,
        "ok": not blocking,
        "chapter_path": str(chapter_path) if chapter_path else "",
        "dimensions": dimensions,
        "blocking_issues": blocking,
        "rounds": rounds,
        "artifacts": {
            "review_schema": str(art_dir / "review_schema.json"),
            "fulfillment": str(art_dir / "fulfillment_result.json"),
            "disambiguation": str(art_dir / "disambiguation_result.json"),
            "extraction": str(art_dir / "extraction_result.json"),
            "combined": str(art_dir / "review_deep_v2.json"),
        },
    }
    write_json(art_dir / "review_schema.json", review_schema)
    write_json(art_dir / "fulfillment_result.json", fulfillment)
    write_json(art_dir / "disambiguation_result.json", disambiguation)
    write_json(art_dir / "extraction_result.json", extraction)
    write_json(art_dir / "review_deep_v2.json", combined)
    _write_report(storage, project_id, "review_deep_v2", f"chapter_{chapter_no:04d}", combined)
    return {"ok": not blocking, "report": combined, "paths_written": combined["artifacts"]}


def sqlite_schema_command(storage: Any, project_id: str, action: str = "migrate", query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    db_path = Path(paths.control) / "index.db"
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS entities(bucket TEXT, entity_id TEXT, name TEXT, status TEXT, payload_json TEXT, PRIMARY KEY(bucket, entity_id));
    CREATE TABLE IF NOT EXISTS chapters(chapter_no INTEGER PRIMARY KEY, title TEXT, path TEXT, words INTEGER, body TEXT);
    CREATE TABLE IF NOT EXISTS commits(chapter_no INTEGER PRIMARY KEY, commit_id TEXT, summary TEXT, payload_json TEXT);
    CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, event_type TEXT, chapter_no INTEGER, at TEXT, payload_json TEXT);
    CREATE TABLE IF NOT EXISTS memory(memory_id TEXT PRIMARY KEY, category TEXT, subject TEXT, priority INTEGER, source_chapter INTEGER, content TEXT);
    CREATE TABLE IF NOT EXISTS rag_records(record_id TEXT PRIMARY KEY, source TEXT, title TEXT, chapter_no INTEGER, payload_json TEXT);
    CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
    CREATE INDEX IF NOT EXISTS idx_memory_subject ON memory(subject);
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_chapters USING fts5(title, body, content='');
    CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory USING fts5(subject, content, content='');
    """)
    if action in {"migrate", "rebuild", "build", "refresh"}:
        state = storage.load_state(project_id)
        cur.execute("DELETE FROM entities")
        for ent in _flatten_state_entities(state):
            cur.execute("INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?)", (ent["bucket"], ent["id"], ent["name"], ent.get("status", ""), json.dumps(ent.get("data") or {}, ensure_ascii=False)))
        cur.execute("DELETE FROM chapters")
        cur.execute("DELETE FROM fts_chapters")
        for p in sorted(Path(paths.chapters).glob("*.txt")) + sorted(Path(paths.chapters).glob("*.md")):
            m = re.search(r"第\s*(\d+)\s*章", p.stem)
            no = _safe_int(m.group(1), 0) if m else 0
            text = read_text_auto(p)
            cur.execute("INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?)", (no, p.stem, str(p), len(text), text))
            cur.execute("INSERT INTO fts_chapters(rowid,title,body) VALUES (?,?,?)", (no or None, p.stem, text))
        cur.execute("DELETE FROM commits")
        for p in sorted(Path(paths.commits).glob("第*章_commit.json")):
            data = read_json(p, {}) or {}
            no = _safe_int(data.get("chapter_no") or data.get("chapterNo"), 0)
            cur.execute("INSERT OR REPLACE INTO commits VALUES (?,?,?,?)", (no, str(data.get("commit_id") or data.get("commitId") or p.stem), str(data.get("summary") or ""), json.dumps(data, ensure_ascii=False)))
        cur.execute("DELETE FROM events")
        for p in sorted((Path(paths.root) / "events").glob("*.jsonl")) + sorted((Path(paths.root) / "writer_control" / "events").glob("*.jsonl")):
            for e in read_jsonl(p):
                if not isinstance(e, dict):
                    continue
                eid = str(e.get("event_id") or e.get("id") or hashlib.sha1(json.dumps(e, ensure_ascii=False).encode()).hexdigest()[:20])
                cur.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", (eid, str(e.get("event_type") or e.get("type") or e.get("event") or ""), _safe_int(e.get("chapter_no") or e.get("chapterNo"), 0), str(e.get("at") or e.get("time") or ""), json.dumps(e, ensure_ascii=False)))
        cur.execute("DELETE FROM memory")
        cur.execute("DELETE FROM fts_memory")
        mem = read_json(Path(paths.control) / "memory_v2" / "store.json", {}) or read_json(Path(paths.control) / "memory" / "memory_store.json", {}) or {}
        for e in mem.get("entries") or []:
            if isinstance(e, dict):
                mid = str(e.get("memory_id") or hashlib.sha1(json.dumps(e, ensure_ascii=False).encode()).hexdigest()[:20])
                cur.execute("INSERT OR REPLACE INTO memory VALUES (?,?,?,?,?,?)", (mid, str(e.get("category") or ""), str(e.get("subject") or ""), _safe_int(e.get("priority"), 0), _safe_int(e.get("source_chapter"), 0), str(e.get("content") or "")))
                cur.execute("INSERT INTO fts_memory(subject,content) VALUES (?,?)", (str(e.get("subject") or ""), str(e.get("content") or "")))
        rag = read_json(Path(paths.indexes) / "hybrid_rag_index.json", {}) or {}
        cur.execute("DELETE FROM rag_records")
        for r in rag.get("records") or []:
            if isinstance(r, dict):
                cur.execute("INSERT OR REPLACE INTO rag_records VALUES (?,?,?,?,?)", (str(r.get("id") or ""), str(r.get("source") or ""), str(r.get("title") or ""), _safe_int(r.get("chapter_no"), 0), json.dumps({k: v for k, v in r.items() if k not in {"vector"}}, ensure_ascii=False)))
        conn.commit()
    if action in {"query", "search"} and query:
        try:
            rows = [dict(r) for r in cur.execute("SELECT rowid,title,body FROM fts_chapters WHERE fts_chapters MATCH ? LIMIT 20", (query,)).fetchall()]
        except Exception:
            rows = [dict(r) for r in cur.execute("SELECT chapter_no AS rowid,title,body FROM chapters WHERE body LIKE ? LIMIT 20", (f"%{query}%",)).fetchall()]
        report = {"ok": True, "action": action, "query": query, "results": rows, "paths_written": {"sqlite": str(db_path)}}
    else:
        stats = {}
        for table in ["entities", "chapters", "commits", "events", "memory", "rag_records"]:
            stats[table] = cur.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        report = {"ok": True, "action": action, "stats": stats, "paths_written": {"sqlite": str(db_path)}}
    conn.close()
    _write_report(storage, project_id, "sqlite_v2", f"sqlite_{action or 'stats'}", report)
    return report


def publisher_sync_command(storage: Any, project_id: str, action: str = "plan", platform: str = "fanqie", start: int = 0, end: int = 0) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    pub_dir = ensure_dir(Path(paths.control) / "publisher_bridge_v2")
    config_path = pub_dir / "platform_config.json"
    jobs_path = pub_dir / "jobs.json"
    state_path = pub_dir / "state.json"
    platforms = {
        "fanqie": {"title_limit": 30, "chapter_min_words": 1000, "chapter_max_words": 6000, "newline_policy": "blank_line_between_paragraphs", "adapter": "existing_fanqie_publisher"},
        "qimao": {"title_limit": 30, "chapter_min_words": 1000, "chapter_max_words": 8000, "newline_policy": "blank_line_between_paragraphs", "adapter": "qimao_placeholder"},
    }
    write_json(config_path, {"schema_version": 2, "platforms": platforms, "updated_at": _now()})
    platform_cfg = platforms.get(platform, platforms["fanqie"])
    jobs = []
    for p in sorted(Path(paths.chapters).glob("*.txt")) + sorted(Path(paths.chapters).glob("*.md")):
        m = re.search(r"第\s*(\d+)\s*章", p.stem)
        no = _safe_int(m.group(1), 0) if m else 0
        if start and no and no < start:
            continue
        if end and no and no > end:
            continue
        text = read_text_auto(p)
        title = p.stem[: int(platform_cfg["title_limit"])]
        formatted = "\n\n".join(x.strip() for x in text.splitlines() if x.strip())
        job = {
            "job_id": hashlib.sha1(f"{platform}|{no}|{p}".encode()).hexdigest()[:16],
            "platform": platform,
            "chapter_no": no,
            "title": title,
            "source_path": str(p),
            "words": len(text),
            "status": "ready" if len(text) >= int(platform_cfg["chapter_min_words"]) else "needs_review",
            "warnings": [] if len(text) >= int(platform_cfg["chapter_min_words"]) else ["字数低于平台建议阈值"],
            "formatted_preview": formatted[:1000],
        }
        jobs.append(job)
    write_json(jobs_path, {"schema_version": 2, "updated_at": _now(), "jobs": jobs})
    old_state = read_json(state_path, {}) or {}
    by_id = {j["job_id"]: {**old_state.get("jobs", {}).get(j["job_id"], {}), **j} for j in jobs}
    write_json(state_path, {"schema_version": 2, "updated_at": _now(), "platform": platform, "jobs": by_id})
    report = {"ok": True, "action": action, "platform": platform, "job_count": len(jobs), "ready_count": sum(1 for j in jobs if j["status"] == "ready"), "paths_written": {"config": str(config_path), "jobs": str(jobs_path), "state": str(state_path)}}
    _write_report(storage, project_id, "publisher_bridge_v2", f"publisher_{platform}_{action or 'plan'}", report)
    return report


def alignment_gap_command(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    expected = [
        ("workflow_checkpoint", "workflow_orchestrate", Path(paths.control) / "workflows"),
        ("memory_store_budget_compactor", "memory_orchestrate", Path(paths.control) / "memory_v2" / "store.json"),
        ("hybrid_rag_router", "rag_router", Path(paths.indexes) / "hybrid_rag_index.json"),
        ("review_pipeline_artifacts", "review_pipeline_deep", Path(paths.artifacts)),
        ("sqlite_schema_index", "sqlite_schema", Path(paths.control) / "index.db"),
        ("publisher_bridge", "publisher_sync", Path(paths.control) / "publisher_bridge_v2" / "jobs.json"),
    ]
    rows = []
    for capability, command, path in expected:
        rows.append({"capability": capability, "command": command, "implemented": path.exists(), "evidence_path": str(path), "status": "aligned" if path.exists() else "needs_run"})
    report = {"ok": True, "checked_at": _now(), "rows": rows, "remaining_unimplemented": [r for r in rows if not r["implemented"]]}
    p = _write_report(storage, project_id, "alignment", "last_alignment_gap", report)
    report["paths_written"] = {"json": str(p)}
    return report
