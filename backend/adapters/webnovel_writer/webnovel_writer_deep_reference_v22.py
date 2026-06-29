from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import append_jsonl, read_json, read_jsonl, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text

ENTITY_BUCKETS = ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]
PIPELINE_STAGES = [
    "prewrite", "context", "contract", "task_book", "draft", "review", "fulfillment",
    "disambiguation", "extraction", "commit", "projection", "quality", "user_report",
]
AGENT_ROLES = ["planner", "context", "drafter", "reviewer", "fact", "repair", "publisher", "memory", "rag", "orchestrator"]


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


def _json_dumps(data: Any) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(data)


def _sha(data: Any, n: int = 24) -> str:
    return hashlib.sha256(_json_dumps(data).encode("utf-8", errors="ignore")).hexdigest()[:n]


def _fingerprint_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _write_report(storage: Any, project_id: str, group: str, name: str, data: dict[str, Any]) -> Path:
    p = Path(storage.paths(project_id).control) / "reports" / group / f"{name}.json"
    ensure_dir(p.parent)
    write_json(p, data)
    return p


def _tokens(text: str) -> list[str]:
    text = str(text or "")
    words = re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,5}", text)
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    out = [w.lower() for w in words]
    for n in (2, 3, 4):
        for i in range(0, max(0, len(chars) - n + 1)):
            out.append("".join(chars[i:i + n]))
    return out


def _counter(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _score(query: str, text: str) -> float:
    qt = _counter(query)
    tt = _counter(text)
    if not qt or not tt:
        return 0.0
    overlap = sum(min(tt.get(k, 0), v) for k, v in qt.items())
    return overlap / (math.sqrt(sum(v * v for v in qt.values())) * math.sqrt(sum(v * v for v in tt.values())) or 1.0)


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(str(text or "")) / 1.7))


def _read_state_entities(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket in ENTITY_BUCKETS:
        data = state.get(bucket) or {}
        if not isinstance(data, dict):
            continue
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
                "priority": _safe_int(info.get("priority"), 50),
                "payload": info,
                "text": _json_dumps(info),
            })
    return rows


def _chapter_no_from_path(path: Path) -> int:
    m = re.search(r"第\s*(\d+)\s*章|chapter[_-]?(\d+)", path.stem, flags=re.I)
    if not m:
        return 0
    return _safe_int(next((g for g in m.groups() if g), "0"), 0)


def _chapter_files(paths: Any) -> list[Path]:
    root = Path(paths.chapters)
    files = []
    if root.exists():
        for p in sorted(root.glob("*.txt")) + sorted(root.glob("*.md")):
            if p.is_file():
                files.append(p)
    return files


def _load_blueprint(paths: Any, chapter_no: int) -> dict[str, Any]:
    for p in [Path(paths.control) / "blueprints" / f"chapter_{chapter_no:04d}.json", Path(paths.blueprints) / f"chapter_{chapter_no:04d}.json"]:
        data = read_json(p, None)
        if isinstance(data, dict):
            return data
    return {}


def _artifact_paths(paths: Any, chapter_no: int) -> dict[str, Path]:
    art = Path(paths.artifacts) / f"第{chapter_no:04d}章"
    return {
        "prewrite": art / "00_prewrite_gate.json",
        "context": Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json",
        "contract": Path(paths.control) / "contracts" / f"chapter_{chapter_no:04d}_contract.json",
        "task_book": Path(paths.control) / "workflows" / f"chapter_{chapter_no:04d}" / "task_book.json",
        "draft": Path(paths.drafts) / f"第{chapter_no:04d}章_draft_latest.txt",
        "review": Path(paths.reviews) / f"第{chapter_no:04d}章_review.json",
        "fulfillment": art / "fulfillment_result.json",
        "disambiguation": art / "disambiguation_result.json",
        "extraction": art / "extraction_result.json",
        "commit": Path(paths.commits) / f"第{chapter_no:04d}章_commit.json",
        "projection": Path(paths.state),
        "quality": art / "06_quality_gate.json",
        "user_report": Path(paths.control) / "reports" / "user" / f"chapter_{chapter_no:04d}_write_report.json",
    }


def _load_chapter_text(storage: Any, project_id: str, chapter_no: int) -> tuple[Path | None, str]:
    try:
        return storage.load_chapter(project_id, chapter_no)
    except Exception:
        return None, ""


def _split_changes(text: str) -> tuple[str, dict[str, Any]]:
    raw = str(text or "")
    match = re.search(r"(?is)<\s*(?:chapter_changes|changes)\s*>(.*?)</\s*(?:chapter_changes|changes)\s*>", raw)
    if not match:
        match = re.search(r"(?is)(?:^|\n)\s*[-—–]{3}\s*CHANGES\s*[-—–]{3}\s*(.*)$", raw)
    if not match:
        match = re.search(r"(?is)(?:^|\n)\s*#{1,4}\s*(?:CHANGES|事实回写|变更记录|状态变更)\s*\n(.*)$", raw)
    if not match:
        return raw, {}
    changes_raw = match.group(1).strip()
    start, end = changes_raw.find("{"), changes_raw.rfind("}")
    if start >= 0 and end > start:
        changes_raw = changes_raw[start:end + 1]
    try:
        data = json.loads(changes_raw)
        return raw[:match.start()].strip(), data if isinstance(data, dict) else {}
    except Exception:
        fixed = re.sub(r"//.*?$|/\*.*?\*/", "", changes_raw, flags=re.S | re.M)
        fixed = fixed.replace("True", "true").replace("False", "false").replace("None", "null")
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        fixed = re.sub(r"([{,]\s*)([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff-]*)(\s*:)", r'\1"\2"\3', fixed)
        try:
            data = json.loads(fixed)
            return raw[:match.start()].strip(), data if isinstance(data, dict) else {}
        except Exception:
            return raw[:match.start()].strip(), {}


def agent_registry_command(storage: Any, project_id: str, action: str = "build") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    root = ensure_dir(Path(paths.control) / "agents")
    routes = read_json(Path(paths.control) / "models" / "model_routes.json", {}) or {}
    genre = read_json(Path(paths.control) / "genres" / "genre_profile.json", {}) or {}
    role_specs = {
        "planner": ["full_outline", "volume_outline", "chapter_blueprint"],
        "context": ["context_pack", "runtime_contract", "weighted_context"],
        "drafter": ["chapter_draft", "changes_protocol"],
        "reviewer": ["quality_review", "fulfillment", "anti_ai", "repair_verdict"],
        "fact": ["extraction", "disambiguation", "state_projection"],
        "repair": ["repair_plan", "localized_rewrite", "convergence_round"],
        "publisher": ["format", "publish_queue", "platform_payload"],
        "memory": ["store", "budget", "compact", "conflict_resolution"],
        "rag": ["hybrid_search", "rerank", "reference_knowledge"],
        "orchestrator": ["checkpoint", "resume", "step_ledger"],
    }
    agents = []
    for role in AGENT_ROLES:
        route = routes.get(role) if isinstance(routes, dict) else None
        if isinstance(route, dict):
            model = route.get("model") or route.get("model_name") or route.get("name") or ""
        else:
            model = str(route or "")
        agents.append({
            "role": role,
            "capabilities": role_specs[role],
            "model_configured": bool(model),
            "model": model,
            "inputs": ["project_state", "story_config", "runtime_contract"] if role != "publisher" else ["chapters", "publish_queue"],
            "outputs": [f"writer_control/{role}", "artifacts"],
        })
    registry = {
        "schema_version": 1,
        "updated_at": _now(),
        "project_id": project_id,
        "genre": genre.get("genre") or genre.get("name") or "",
        "agents": agents,
        "ready_count": sum(1 for a in agents if a["model_configured"]),
        "missing_routes": [a["role"] for a in agents if not a["model_configured"] and a["role"] in {"planner", "drafter", "reviewer", "fact", "repair"}],
        "fallback_policy": "未配置模型时沿用现有界面/环境变量传入的模型参数；本地校验 agent 继续可用。",
    }
    registry_path = root / "registry.json"
    write_json(registry_path, registry)
    skill_plan = {
        "schema_version": 1,
        "updated_at": _now(),
        "tasks": [
            {"task": "plan", "agent": "planner", "requires": ["genre", "story_config"], "produces": ["outline", "blueprint"]},
            {"task": "write", "agent_chain": ["orchestrator", "context", "drafter", "reviewer", "fact"], "produces": ["chapter", "commit", "projection"]},
            {"task": "heal", "agent_chain": ["reviewer", "repair", "fact"], "produces": ["fixed_draft", "repair_verdict"]},
            {"task": "publish", "agent_chain": ["publisher"], "produces": ["publish_job", "platform_payload"]},
        ],
    }
    skill_path = root / "skill_plan.json"
    write_json(skill_path, skill_plan)
    report = {"ok": True, "action": action, "registry": registry, "paths_written": {"registry": str(registry_path), "skill_plan": str(skill_path)}}
    p = _write_report(storage, project_id, "agents", "agent_registry", report)
    report["paths_written"]["report"] = str(p)
    return report


def context_manager_deep_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000, query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    out_dir = ensure_dir(Path(paths.control) / "context_manager" / f"chapter_{chapter_no:04d}")
    state = storage.load_state(project_id)
    blueprint = _load_blueprint(paths, chapter_no)
    query = query or " ".join(str(x) for x in [blueprint.get("title"), blueprint.get("goal"), " ".join(blueprint.get("must_cover_nodes") or [])] if x)
    sources: list[dict[str, Any]] = []

    def add(source: str, title: str, text: str, priority: int, metadata: dict[str, Any] | None = None) -> None:
        text = str(text or "").strip()
        if not text:
            return
        sources.append({
            "id": hashlib.sha1(f"{source}|{title}|{text[:200]}".encode("utf-8", errors="ignore")).hexdigest()[:16],
            "source": source,
            "title": title,
            "text": text[:12000],
            "priority": int(priority),
            "tokens_est": _estimate_tokens(text),
            "query_score": round(_score(query, text), 6),
            "metadata": metadata or {},
        })

    add("blueprint", f"chapter_{chapter_no:04d}_blueprint", _json_dumps(blueprint), 100, {"chapter_no": chapter_no})
    for ent in _read_state_entities(state):
        names = [ent["name"], ent["id"]] + ent.get("aliases", [])
        if not query or any(n and n in query for n in names) or ent["bucket"] in {"foreshadows", "conflicts", "deadlines"}:
            add(f"entity:{ent['bucket']}", ent["name"], ent["text"], ent.get("priority", 50), {"bucket": ent["bucket"], "id": ent["id"]})
    for mem_file in [Path(paths.control) / "memory_v2" / "store.json", Path(paths.control) / "memory" / "memory_store.json"]:
        mem = read_json(mem_file, {}) or {}
        for e in (mem.get("entries") or [])[:1000]:
            if isinstance(e, dict):
                add("memory", str(e.get("subject") or e.get("memory_id") or "memory"), str(e.get("content") or ""), _safe_int(e.get("priority"), 55), {"category": e.get("category"), "source_chapter": e.get("source_chapter")})
    for idx_file in [Path(paths.indexes) / "hybrid_rag_index.json", Path(paths.indexes) / "chunk_index.json", Path(paths.indexes) / "reference_index.json"]:
        idx = read_json(idx_file, {}) or {}
        rows = idx.get("records") or idx.get("chunks") or idx.get("entries") or []
        if isinstance(rows, list):
            for r in rows[:2000]:
                if isinstance(r, dict):
                    text = str(r.get("text") or r.get("body") or r.get("content") or "")
                    add(str(r.get("source") or idx_file.stem), str(r.get("title") or r.get("chapter_no") or r.get("id") or idx_file.stem), text, 45, {"path": r.get("path"), "chapter_no": r.get("chapter_no")})
    for p in _chapter_files(paths):
        no = _chapter_no_from_path(p)
        if no and no >= chapter_no:
            continue
        text = read_text_auto(p)
        add("recent_chapter" if no >= chapter_no - 3 else "history_chapter", p.stem, text[-3000:], 70 if no >= chapter_no - 3 else 35, {"chapter_no": no, "path": str(p)})

    for s in sources:
        s["weighted_score"] = round((s["priority"] / 100.0) * 0.65 + s["query_score"] * 0.35, 6)
    ranked = sorted(sources, key=lambda x: (x["weighted_score"], x["priority"]), reverse=True)
    selected = []
    used = 0
    for s in ranked:
        cost = int(s.get("tokens_est") or 1)
        if used + cost > budget and selected:
            continue
        selected.append(s)
        used += cost
        if used >= budget:
            break
    plan = {
        "schema_version": 2,
        "updated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "budget": budget,
        "query": query,
        "source_count": len(sources),
        "selected_count": len(selected),
        "tokens_est": used,
        "selected_sources": selected,
        "dropped_sources": [{"source": s["source"], "title": s["title"], "tokens_est": s["tokens_est"], "weighted_score": s["weighted_score"]} for s in ranked[len(selected):len(selected)+200]],
    }
    plan_path = out_dir / "weighted_context.json"
    write_json(plan_path, plan)
    md_lines = [f"# Chapter {chapter_no:04d} Weighted Context", ""]
    for i, s in enumerate(selected, 1):
        md_lines += [f"## {i}. [{s['source']}] {s['title']}", f"- score: {s['weighted_score']} / tokens: {s['tokens_est']}", "", s["text"][:1800], ""]
    md_path = out_dir / "weighted_context.txt"
    write_text(md_path, "\n".join(md_lines))
    report = {"ok": True, "kind": "context_manager_v2", "chapter_no": chapter_no, "paths_written": {"json": str(plan_path), "text": str(md_path)}, "summary": {"sources": len(sources), "selected": len(selected), "tokens_est": used}}
    p = _write_report(storage, project_id, "context_manager", f"chapter_{chapter_no:04d}", report)
    report["paths_written"]["report"] = str(p)
    return report


def workflow_runner_v2_command(storage: Any, project_id: str, chapter_no: int = 1, action: str = "run", max_rounds: int = 3) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    wf_dir = ensure_dir(Path(paths.control) / "workflows_v2" / f"chapter_{chapter_no:04d}")
    ledger_path = wf_dir / "step_ledger.jsonl"
    checkpoint_path = wf_dir / "checkpoint.json"
    artifacts = _artifact_paths(paths, chapter_no)
    _, chapter_text = _load_chapter_text(storage, project_id, chapter_no)
    body, changes = _split_changes(chapter_text)
    blueprint = _load_blueprint(paths, chapter_no)
    state = storage.load_state(project_id)

    def record(stage: str, status: str, path: Path | None = None, data: dict[str, Any] | None = None) -> None:
        append_jsonl(ledger_path, {"at": _now(), "chapter_no": chapter_no, "stage": stage, "status": status, "path": str(path or ""), "data": data or {}})

    generated: dict[str, str] = {}
    if action in {"run", "prepare", "resume"}:
        ensure_dir(artifacts["prewrite"].parent)
        if not artifacts["prewrite"].exists():
            prewrite = {"ok": bool(blueprint), "chapter_no": chapter_no, "checks": {"has_blueprint": bool(blueprint), "has_state": bool(state)}, "created_at": _now()}
            write_json(artifacts["prewrite"], prewrite)
            generated["prewrite"] = str(artifacts["prewrite"])
            record("prewrite", "generated", artifacts["prewrite"], {"ok": prewrite["ok"]})
        ctx = context_manager_deep_command(storage, project_id, chapter_no, 24000)
        generated["context_manager"] = ctx["paths_written"]["json"]
        if not artifacts["task_book"].exists():
            ensure_dir(artifacts["task_book"].parent)
            task = {"schema_version": 2, "chapter_no": chapter_no, "created_at": _now(), "blueprint": blueprint, "context_manager": ctx["paths_written"], "required_artifacts": PIPELINE_STAGES, "max_rounds": max_rounds}
            write_json(artifacts["task_book"], task)
            generated["task_book"] = str(artifacts["task_book"])
            record("task_book", "generated", artifacts["task_book"])
        if chapter_text.strip():
            ents = _read_state_entities(state)
            mentions = []
            for ent in ents:
                names = [ent["name"], ent["id"]] + ent.get("aliases", [])
                cnt = sum(body.count(str(n)) for n in set(names) if str(n).strip())
                if cnt:
                    mentions.append({"bucket": ent["bucket"], "id": ent["id"], "name": ent["name"], "count": cnt})
            nodes = blueprint.get("must_cover_nodes") or blueprint.get("required_beats") or []
            completed, missed = [], []
            for node in nodes:
                pieces = [x for x in re.split(r"[，,。；;、\s]+", str(node)) if len(x) >= 2]
                (completed if any(x in body for x in pieces[:5]) else missed).append(node)
            if not artifacts["fulfillment"].exists():
                write_json(artifacts["fulfillment"], {"ok": not missed, "chapter_no": chapter_no, "completed_nodes": completed, "missed_nodes": missed, "created_at": _now()})
                generated["fulfillment"] = str(artifacts["fulfillment"])
                record("fulfillment", "generated", artifacts["fulfillment"], {"missed": len(missed)})
            if not artifacts["disambiguation"].exists():
                write_json(artifacts["disambiguation"], {"ok": True, "chapter_no": chapter_no, "mentions": mentions, "ambiguous": [], "created_at": _now()})
                generated["disambiguation"] = str(artifacts["disambiguation"])
                record("disambiguation", "generated", artifacts["disambiguation"], {"mentions": len(mentions)})
            if not artifacts["extraction"].exists():
                write_json(artifacts["extraction"], {"ok": bool(changes), "chapter_no": chapter_no, "changes": changes, "mentioned_entities": mentions, "created_at": _now()})
                generated["extraction"] = str(artifacts["extraction"])
                record("extraction", "generated", artifacts["extraction"], {"has_changes": bool(changes)})
    statuses = []
    for stage in PIPELINE_STAGES:
        p = artifacts[stage]
        ok = p.exists() and (stage == "projection" or (p.is_file() and p.stat().st_size > 0) or p.is_dir())
        statuses.append({"stage": stage, "ok": ok, "path": str(p), "signature": _fingerprint_file(p) if p.is_file() else ""})
    next_stage = next((s["stage"] for s in statuses if not s["ok"]), "done")
    checkpoint = {"schema_version": 4, "updated_at": _now(), "chapter_no": chapter_no, "action": action, "stages": statuses, "generated": generated, "next_stage": next_stage, "can_resume": next_stage != "done", "ledger_path": str(ledger_path)}
    write_json(checkpoint_path, checkpoint)
    report = {"ok": True, "kind": "workflow_runner_v2", "chapter_no": chapter_no, "next_stage": next_stage, "checkpoint": checkpoint, "paths_written": {"checkpoint": str(checkpoint_path), "ledger": str(ledger_path)}}
    p = _write_report(storage, project_id, "workflow_runner", f"chapter_{chapter_no:04d}_{action}", report)
    report["paths_written"]["report"] = str(p)
    return report


def memory_contract_deep_command(storage: Any, project_id: str, action: str = "validate", budget: int = 24000) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    root = ensure_dir(Path(paths.control) / "memory_contract_v2")
    store = read_json(Path(paths.control) / "memory_v2" / "store.json", {}) or read_json(Path(paths.control) / "memory" / "memory_store.json", {}) or {}
    entries = store.get("entries") or []
    schema = {"required": ["memory_id", "category", "subject", "content", "priority"], "statuses": ["active", "archived", "candidate", "deprecated", "resolved"]}
    issues = []
    total_tokens = 0
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            issues.append({"level": "error", "code": "not_object", "index": i})
            continue
        for req in schema["required"]:
            if not e.get(req):
                issues.append({"level": "error", "code": "missing_field", "index": i, "field": req})
        total_tokens += _safe_int(e.get("tokens_est"), _estimate_tokens(e.get("content", "")))
        by_key[(str(e.get("category") or ""), str(e.get("subject") or ""))].append(e)
    conflicts = []
    for (cat, subject), group in by_key.items():
        statuses = {str(x.get("status") or "active") for x in group}
        payloads = {_sha(x.get("content") or x, 10) for x in group}
        if len(statuses) > 1 or len(payloads) > 3:
            conflicts.append({"category": cat, "subject": subject, "count": len(group), "statuses": sorted(statuses), "content_variants": len(payloads)})
    budget_plan = sorted(entries, key=lambda e: (_safe_int(e.get("priority"), 0), -_safe_int(e.get("tokens_est"), 0)), reverse=True)
    selected, used = [], 0
    for e in budget_plan:
        cost = _safe_int(e.get("tokens_est"), _estimate_tokens(e.get("content", "")))
        if used + cost > budget and selected:
            continue
        selected.append(e.get("memory_id"))
        used += cost
    contract = {"schema_version": 2, "updated_at": _now(), "action": action, "entry_count": len(entries), "issue_count": len(issues), "conflict_count": len(conflicts), "token_budget": budget, "tokens_total": total_tokens, "selected_memory_ids": selected, "issues": issues, "conflicts": conflicts, "contract_status": "ok" if not issues else "needs_fix"}
    path = root / "memory_contract.json"
    write_json(path, contract)
    report = {"ok": not any(i.get("level") == "error" for i in issues), "contract": contract, "paths_written": {"contract": str(path)}}
    p = _write_report(storage, project_id, "memory_contract_v2", "memory_contract", report)
    report["paths_written"]["report"] = str(p)
    return report


def event_projection_deep_command(storage: Any, project_id: str, action: str = "health") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    out_dir = ensure_dir(Path(paths.control) / "projection_v2")
    event_files = sorted(Path(paths.root).glob("events/*.jsonl")) + sorted((Path(paths.control) / "events").glob("*.jsonl"))
    events = []
    seen = set()
    duplicates = []
    prev_hash = "GENESIS"
    chain = []
    for p in event_files:
        for row in read_jsonl(p):
            if not isinstance(row, dict):
                continue
            eid = str(row.get("event_id") or row.get("id") or _sha(row, 16))
            if eid in seen:
                duplicates.append(eid)
            seen.add(eid)
            event_type = str(row.get("event_type") or row.get("type") or row.get("event") or "unknown")
            event_hash = _sha({"prev": prev_hash, "event": row}, 24)
            chain.append({"event_id": eid, "event_type": event_type, "prev": prev_hash, "hash": event_hash, "chapter_no": _safe_int(row.get("chapter_no") or row.get("chapterNo"), 0)})
            prev_hash = event_hash
            events.append(row)
    projections = []
    for name, path in [
        ("state", Path(paths.state)),
        ("chunk_index", Path(paths.indexes) / "chunk_index.json"),
        ("hybrid_rag", Path(paths.indexes) / "hybrid_rag_index.json"),
        ("memory_v2", Path(paths.control) / "memory_v2" / "store.json"),
        ("truth", Path(paths.control) / "truth" / "truth_index.md"),
    ]:
        projections.append({"name": name, "path": str(path), "exists": path.exists(), "signature": _fingerprint_file(path), "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else ""})
    log = {"schema_version": 2, "updated_at": _now(), "action": action, "event_count": len(events), "event_files": [str(p) for p in event_files], "duplicates": duplicates, "chain_head": prev_hash, "chain": chain[-500:], "projections": projections, "health": "ok" if not duplicates else "warning"}
    path = out_dir / "projection_log.json"
    write_json(path, log)
    replay = {"from_event": chain[0]["event_id"] if chain else "", "to_event": chain[-1]["event_id"] if chain else "", "commands": ["rebuild-projections", "sqlite-schema --action migrate", "alignment-gaps"]}
    replay_path = out_dir / "replay_plan.json"
    write_json(replay_path, replay)
    report = {"ok": not duplicates, "projection_log": log, "paths_written": {"projection_log": str(path), "replay_plan": str(replay_path)}}
    p = _write_report(storage, project_id, "projection_v2", "event_projection", report)
    report["paths_written"]["report"] = str(p)
    return report


def review_converge_command(storage: Any, project_id: str, chapter_no: int = 1, max_rounds: int = 3) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    chapter_no = int(chapter_no or 1)
    art_dir = ensure_dir(Path(paths.artifacts) / f"第{chapter_no:04d}章")
    review_files = [art_dir / "review_deep_v2.json", art_dir / "review_deep.json", Path(paths.reviews) / f"第{chapter_no:04d}章_review.json"]
    issues = []
    evidence = []
    for p in review_files:
        data = read_json(p, None)
        if isinstance(data, dict):
            evidence.append(str(p))
            if isinstance(data.get("issues"), list):
                issues.extend(data.get("issues") or [])
            if isinstance(data.get("report"), dict) and isinstance(data["report"].get("issues"), list):
                issues.extend(data["report"].get("issues") or [])
            if data.get("ok") is False and not data.get("issues"):
                issues.append({"code": "review_not_ok", "message": data.get("message") or p.name})
    fulfillment = read_json(art_dir / "fulfillment_result.json", {}) or {}
    if fulfillment.get("missed_nodes"):
        for node in fulfillment.get("missed_nodes") or []:
            issues.append({"code": "missed_blueprint_node", "message": f"必达节点未落地：{node}", "target": node})
    extraction = read_json(art_dir / "extraction_result.json", {}) or {}
    if extraction and not extraction.get("changes") and not extraction.get("ok"):
        issues.append({"code": "missing_changes", "message": "事实抽取没有可信 CHANGES。"})
    rounds = []
    open_issues = list(issues)
    for i in range(1, max(1, max_rounds) + 1):
        if not open_issues:
            break
        round_issues = open_issues[:10]
        actions = []
        for issue in round_issues:
            msg = str(issue.get("message") or issue.get("code") or issue)
            if "必达" in msg or "blueprint" in msg:
                actions.append({"type": "add_or_rewrite_scene", "instruction": msg})
            elif "CHANGES" in msg or "事实" in msg:
                actions.append({"type": "repair_changes_protocol", "instruction": msg})
            elif "实体" in msg or "消歧" in msg:
                actions.append({"type": "clarify_entity", "instruction": msg})
            else:
                actions.append({"type": "local_polish", "instruction": msg})
        rounds.append({"round": i, "issue_count": len(round_issues), "actions": actions, "status": "proposal_only"})
        open_issues = open_issues[10:]
    prompt = "\n".join(["请按以下修复动作局部修订本章，不要重写无关段落："] + [f"- R{r['round']}: {a['type']}：{a['instruction']}" for r in rounds for a in r["actions"]])
    result = {"schema_version": 2, "created_at": _now(), "chapter_no": chapter_no, "evidence": evidence, "initial_issue_count": len(issues), "rounds": rounds, "converged": not issues, "repair_prompt": prompt, "next_action": "accept" if not issues else "repair_and_rerun_review"}
    path = art_dir / "review_convergence.json"
    write_json(path, result)
    report = {"ok": True, "chapter_no": chapter_no, "result": result, "paths_written": {"convergence": str(path)}}
    p = _write_report(storage, project_id, "review_convergence", f"chapter_{chapter_no:04d}", report)
    report["paths_written"]["report"] = str(p)
    return report


def deep_alignment_v22_command(storage: Any, project_id: str, chapter_no: int = 1) -> dict[str, Any]:
    outputs = {
        "agents": agent_registry_command(storage, project_id),
        "context_manager": context_manager_deep_command(storage, project_id, chapter_no),
        "workflow_runner": workflow_runner_v2_command(storage, project_id, chapter_no, "run"),
        "memory_contract": memory_contract_deep_command(storage, project_id),
        "event_projection": event_projection_deep_command(storage, project_id),
        "review_converge": review_converge_command(storage, project_id, chapter_no),
    }
    remaining = []
    for name, out in outputs.items():
        if not out.get("ok", True):
            remaining.append({"module": name, "status": "needs_attention"})
    report = {"ok": not remaining, "updated_at": _now(), "project_id": project_id, "chapter_no": chapter_no, "outputs": outputs, "remaining": remaining}
    p = _write_report(storage, project_id, "deep_alignment_v22", "last_deep_alignment_v22", report)
    report["paths_written"] = {"json": str(p)}
    return report
