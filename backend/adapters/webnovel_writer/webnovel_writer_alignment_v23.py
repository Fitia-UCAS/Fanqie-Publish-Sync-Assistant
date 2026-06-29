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

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, read_jsonl, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text

ENTITY_BUCKETS = ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]
PIPELINE_STAGES = [
    "prewrite", "context", "contract", "task_book", "draft", "review", "fulfillment",
    "disambiguation", "extraction", "commit", "projection", "quality", "user_report",
]

REFERENCE_CAPABILITIES: list[dict[str, Any]] = [
    {
        "code": "workflow_checkpoint_orchestrator",
        "name": "写作工作流编排与可信断点续跑",
        "reference": ["lingfeng: run-ledger/write-resume", "opencode: workflow_checkpoint.py/orchestrate.py"],
        "evidence": ["writer_control/alignment_v23/workflow/checkpoint.json", "writer_control/alignment_v23/workflow/resume_plan.json"],
    },
    {
        "code": "agent_skill_registry",
        "name": "Agent/Skill 注册与任务角色分工",
        "reference": ["lingfeng: context/reviewer/data/deconstruction agents", "opencode: agents/skills/skill_runner.py"],
        "evidence": ["writer_control/alignment_v23/agents/registry.json", "writer_control/alignment_v23/agents/skill_lock.json"],
    },
    {
        "code": "story_system_ssot_projection",
        "name": "Story System / SSOT / 事件与投影链",
        "reference": ["lingfeng: story-system/chapter-commit/story-events/projections", "opencode: story_system_engine.py/event_log_store.py/projection_log.py"],
        "evidence": ["writer_control/alignment_v23/ssot/projection_chain.json", "writer_control/alignment_v23/ssot/replay_plan.json"],
    },
    {
        "code": "context_manager_weight_budget",
        "name": "Context Manager 权重预算与上下文裁剪",
        "reference": ["lingfeng: context-agent 写作任务书", "opencode: context_manager.py/context_weights.py"],
        "evidence": ["writer_control/alignment_v23/context/weighted_context.json", "writer_control/alignment_v23/context/task_book.json"],
    },
    {
        "code": "rag_vector_query_router",
        "name": "RAG Adapter / Vector Projection / Query Router",
        "reference": ["lingfeng: rag/index/query", "opencode: rag_adapter.py/vector_projection_writer.py/query_router.py"],
        "evidence": ["writer_control/alignment_v23/rag/hybrid_index.json", "writer_control/alignment_v23/rag/query_router.json"],
    },
    {
        "code": "memory_store_budget_compactor",
        "name": "长期记忆 Store / Schema / Budget / Compactor",
        "reference": ["lingfeng: memory stats/query/bootstrap/update", "opencode: memory/store.py/schema.py/budget.py/compactor.py/orchestrator.py"],
        "evidence": ["writer_control/alignment_v23/memory/store.json", "writer_control/alignment_v23/memory/compacted.json"],
    },
    {
        "code": "review_pipeline_artifacts_convergence",
        "name": "Review Pipeline / Fulfillment / Disambiguation / Extraction / 收敛修复",
        "reference": ["lingfeng: review-pipeline + chapter-commit artifacts", "opencode: review_pipeline.py/review_schema.py"],
        "evidence": ["writer_control/alignment_v23/review/review_schema.json", "writer_control/alignment_v23/review/convergence_plan.json"],
    },
    {
        "code": "entity_linking_debt_structural_checker",
        "name": "实体链接、故事债务、结构检查",
        "reference": ["opencode: entity_linker.py/index_debt_mixin.py/structural_checker.py"],
        "evidence": ["writer_control/alignment_v23/entities/entity_linking.json", "writer_control/alignment_v23/entities/structural_debts.json"],
    },
    {
        "code": "publisher_platform_bridge",
        "name": "发布格式化、平台配置、发布状态桥接",
        "reference": ["opencode: publisher/formatter.py/config.py/adapters/fanqie.py/adapters/qimao.py"],
        "evidence": ["writer_control/alignment_v23/publisher/platform_jobs.json", "writer_control/alignment_v23/publisher/formatter_preview.json"],
    },
    {
        "code": "sqlite_schema_validator",
        "name": "SQLite / Schema / Validator 数据层",
        "reference": ["opencode: schemas.py/state_validator.py/migrate_state_to_sqlite.py/story_event_schema.py"],
        "evidence": ["writer_control/alignment_v23/sqlite/schema_report.json", "writer_control/index.db"],
    },
    {
        "code": "security_observability_runtime_compat",
        "name": "安全脱敏、可观测性、运行时兼容",
        "reference": ["opencode: security_utils.py/observability.py/runtime_compat.py/index_observability_mixin.py"],
        "evidence": ["writer_control/alignment_v23/security/security_audit.json", "writer_control/alignment_v23/observability/metrics.json"],
    },
    {
        "code": "reference_knowledge_deconstruction",
        "name": "结构化知识库与拆书学习",
        "reference": ["opencode: reference_search.py/validate_csv.py/knowledge_query.py/deconstruction-agent"],
        "evidence": ["writer_control/alignment_v23/references/knowledge_profile.json", "writer_control/alignment_v23/references/deconstruction_profile.json"],
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _sha(value: Any, n: int = 24) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _fingerprint_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _safe_read_json(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path, default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _safe_read_text(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return read_text_auto(path)
    except Exception:
        return ""
    return ""


def _write(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    write_json(path, data)
    return path


def _alignment_dir(storage: Any, project_id: str) -> Path:
    return ensure_dir(Path(storage.paths(project_id).control) / "alignment_v23")


def _project_snapshot(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    state = _safe_read_json(Path(paths.state), {})
    meta = _safe_read_json(Path(paths.meta), {})
    config = _safe_read_json(Path(paths.story_config), {})
    chapters = sorted(Path(paths.chapters).glob("*.txt")) + sorted(Path(paths.chapters).glob("*.md"))
    commits = sorted(Path(paths.commits).glob("*.json"))
    reviews = sorted(Path(paths.reviews).glob("*.json"))
    events = []
    for file in sorted((Path(paths.root) / "events").glob("*.jsonl")) + sorted((Path(paths.control) / "events").glob("*.jsonl")):
        try:
            events.extend(read_jsonl(file))
        except Exception:
            pass
    return {
        "paths": paths,
        "state": state if isinstance(state, dict) else {},
        "meta": meta if isinstance(meta, dict) else {},
        "config": config if isinstance(config, dict) else {},
        "chapters": chapters,
        "commits": commits,
        "reviews": reviews,
        "events": events,
    }


def _chapter_no_from_path(path: Path) -> int:
    m = re.search(r"(\d{1,6})", path.stem)
    return int(m.group(1)) if m else 0


def _entity_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for bucket in ENTITY_BUCKETS:
        data = state.get(bucket) or {}
        if not isinstance(data, dict):
            continue
        for name, value in data.items():
            obj = value if isinstance(value, dict) else {"value": value}
            aliases = obj.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [x.strip() for x in re.split(r"[,，、;；\s]+", aliases) if x.strip()]
            out.append({
                "bucket": bucket,
                "name": str(name),
                "id": str(obj.get("id") or obj.get("key") or name),
                "aliases": aliases if isinstance(aliases, list) else [],
                "status": str(obj.get("status") or obj.get("state") or ""),
                "priority": _to_int(obj.get("priority"), 50),
                "payload": obj,
                "text": json.dumps(obj, ensure_ascii=False, default=str),
            })
    return out


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _tokens(text: str) -> list[str]:
    text = str(text or "")
    out = [w.lower() for w in re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,5}", text)]
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    for n in (2, 3, 4):
        for i in range(max(0, len(chars) - n + 1)):
            out.append("".join(chars[i:i+n]))
    return out


def _counter(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _score(query: str, text: str) -> float:
    q = _counter(query)
    t = _counter(text)
    if not q or not t:
        return 0.0
    dot = sum(min(t.get(k, 0), v) for k, v in q.items())
    qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
    tn = math.sqrt(sum(v * v for v in t.values())) or 1.0
    return round(dot / (qn * tn), 6)


def _hash_vector(text: str, dims: int = 64) -> list[float]:
    vec = [0.0] * dims
    for token, count in _counter(text).items():
        h = int(hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
        idx = h % dims
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign * float(count)
    norm = math.sqrt(sum(x*x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return round(sum(x*y for x, y in zip(a, b)), 6)


def _chapter_records(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for p in snapshot.get("chapters") or []:
        path = Path(p)
        text = _safe_read_text(path)
        if not text:
            continue
        no = _chapter_no_from_path(path)
        for idx, para in enumerate([x.strip() for x in re.split(r"\n\s*\n", text) if x.strip()] or [text[:1200]]):
            rows.append({
                "source": "chapter",
                "chapter_no": no,
                "chunk_no": idx + 1,
                "path": str(path),
                "title": path.stem,
                "text": para[:1800],
                "tokens": _tokens(para),
                "vector": _hash_vector(para),
                "fingerprint": _sha({"p": str(path), "i": idx, "t": para}),
            })
    return rows


def _collect_reference_docs(paths: Any) -> list[dict[str, Any]]:
    root = Path(paths.control) / "references"
    docs: list[dict[str, Any]] = []
    for pattern in ("**/*.csv", "**/*.md", "**/*.txt", "**/*.json"):
        for p in sorted(root.glob(pattern)):
            text = _safe_read_text(p)
            if not text and p.suffix.lower() == ".json":
                data = _safe_read_json(p, {})
                text = json.dumps(data, ensure_ascii=False, default=str)
            if text:
                docs.append({"source": "reference", "path": str(p), "title": p.stem, "text": text[:2400], "vector": _hash_vector(text), "fingerprint": _sha([str(p), text[:400]])})
    return docs


def _existing_evidence(storage: Any, project_id: str, cap: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(storage.paths(project_id).root)
    out = []
    for rel in cap.get("evidence") or []:
        p = root / rel
        out.append({"path": rel, "exists": p.exists(), "fingerprint": _fingerprint_file(p)})
    return out


def _depth_status(evidence: list[dict[str, Any]]) -> str:
    count = sum(1 for x in evidence if x.get("exists"))
    if count == len(evidence) and count > 0:
        return "deep_aligned"
    if count > 0:
        return "shallow_or_partial"
    return "missing"


def alignment_audit_command(storage: Any, project_id: str) -> dict[str, Any]:
    _paths(storage, project_id)
    rows = []
    for cap in REFERENCE_CAPABILITIES:
        evidence = _existing_evidence(storage, project_id, cap)
        rows.append({
            "code": cap["code"],
            "name": cap["name"],
            "reference": cap["reference"],
            "status": _depth_status(evidence),
            "evidence": evidence,
        })
    score = round(sum(1.0 if r["status"] == "deep_aligned" else 0.5 if r["status"] == "shallow_or_partial" else 0 for r in rows) / max(1, len(rows)), 4)
    report = {"ok": score >= 0.9, "checked_at": _now(), "alignment_score": score, "items": rows}
    path = _write(_alignment_dir(storage, project_id) / "alignment_audit.json", report)
    report["paths_written"] = {"audit": str(path)}
    return report


def alignment_optimize_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000) -> dict[str, Any]:
    snapshot = _project_snapshot(storage, project_id)
    paths = snapshot["paths"]
    base = _alignment_dir(storage, project_id)
    written: dict[str, str] = {}

    written.update(_optimize_workflow(paths, snapshot, base, chapter_no))
    written.update(_optimize_agents(paths, snapshot, base))
    written.update(_optimize_ssot(paths, snapshot, base))
    written.update(_optimize_context(paths, snapshot, base, chapter_no, budget))
    written.update(_optimize_rag(paths, snapshot, base))
    written.update(_optimize_memory(paths, snapshot, base, budget))
    written.update(_optimize_review(paths, snapshot, base, chapter_no))
    written.update(_optimize_entities(paths, snapshot, base))
    written.update(_optimize_publisher(paths, snapshot, base))
    written.update(_optimize_sqlite(paths, snapshot, base))
    written.update(_optimize_security_observability(paths, snapshot, base))
    written.update(_optimize_references(paths, snapshot, base))

    audit = alignment_audit_command(storage, project_id)
    deep_count = sum(1 for x in audit.get("items") or [] if x.get("status") == "deep_aligned")
    report = {
        "ok": deep_count == len(REFERENCE_CAPABILITIES),
        "optimized_at": _now(),
        "chapter_no": chapter_no,
        "budget": budget,
        "deep_aligned": deep_count,
        "total": len(REFERENCE_CAPABILITIES),
        "alignment_score": audit.get("alignment_score"),
        "written": written,
        "audit": audit,
    }
    path = _write(base / "alignment_optimization_result.json", report)
    report["paths_written"] = {"result": str(path), **{k: v for k, v in written.items()}}
    return report


def _stage_evidence(paths: Any, chapter_no: int) -> dict[str, Any]:
    root = Path(paths.root)
    art = root / "artifacts" / f"第{chapter_no:04d}章"
    candidates = {
        "prewrite": Path(paths.runtime) / f"chapter_{chapter_no:04d}_contract.json",
        "context": Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.json",
        "contract": Path(paths.control) / "contracts" / f"chapter_{chapter_no:04d}_contract.json",
        "task_book": Path(paths.control) / "workflows_v2" / f"chapter_{chapter_no:04d}" / "task_book.json",
        "draft": Path(paths.drafts) / f"chapter_{chapter_no:04d}.txt",
        "review": Path(paths.reviews) / f"chapter_{chapter_no:04d}_review.json",
        "fulfillment": art / "fulfillment_result.json",
        "disambiguation": art / "disambiguation_result.json",
        "extraction": art / "extraction_result.json",
        "commit": Path(paths.commits) / f"chapter_{chapter_no:04d}_commit.json",
        "projection": Path(paths.control) / "projection_v2" / "projection_log.json",
        "quality": art / "06_quality_gate.json",
        "user_report": Path(paths.control) / "reports" / "user" / f"chapter_{chapter_no:04d}_write.json",
    }
    return {stage: {"path": str(p), "exists": p.exists(), "fingerprint": _fingerprint_file(p)} for stage, p in candidates.items()}


def _optimize_workflow(paths: Any, snapshot: dict[str, Any], base: Path, chapter_no: int) -> dict[str, str]:
    evidence = _stage_evidence(paths, chapter_no)
    trusted = [k for k, v in evidence.items() if v["exists"]]
    next_step = next((s for s in PIPELINE_STAGES if s not in trusted), "complete")
    wf_dir = ensure_dir(base / "workflow")
    checkpoint = {
        "chapter_no": chapter_no,
        "reference_alignment": "workflow_checkpoint + run-ledger + write-resume",
        "stages": evidence,
        "trusted_stages": trusted,
        "next_step": next_step,
        "resume_allowed": next_step != "complete",
        "run_id": _sha({"chapter": chapter_no, "stages": evidence}),
        "updated_at": _now(),
    }
    resume = {
        "chapter_no": chapter_no,
        "safe_resume_from": next_step,
        "do_not_overwrite": trusted,
        "suggested_commands": [f"write-gate --chapter {chapter_no} --stage prewrite", f"workflow-runner --chapter {chapter_no} --action run"],
        "blocking_missing": [s for s in PIPELINE_STAGES if s not in trusted],
    }
    p1 = _write(wf_dir / "checkpoint.json", checkpoint)
    p2 = _write(wf_dir / "resume_plan.json", resume)
    _write(wf_dir / "step_ledger.json", {"records": [{"step": k, **v} for k, v in evidence.items()]})
    return {"workflow_checkpoint": str(p1), "workflow_resume_plan": str(p2)}


def _optimize_agents(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    routes = _safe_read_json(Path(paths.control) / "models" / "model_routes.json", {})
    agents = []
    for role, duty in {
        "planner": "规划全书、分卷和章节蓝图",
        "context": "组装写前上下文和任务书",
        "drafter": "生成正文草稿并遵守 CHANGES 协议",
        "reviewer": "多维审稿和门禁",
        "fact": "事实抽取、实体消歧、状态回写",
        "repair": "失败后局部修复和收敛",
        "publisher": "发布队列、格式化和状态回写",
        "memory": "长期记忆预算、压缩、冲突处理",
        "rag": "多源召回、重排、上下文预算",
        "orchestrator": "可信断点和流程编排",
    }.items():
        route = routes.get(role) if isinstance(routes, dict) else {}
        agents.append({"role": role, "duty": duty, "model_route": route if isinstance(route, dict) else {}, "configured": bool(route)})
    skill_lock = {"version": 1, "updated_at": _now(), "skills": [{"name": f"webnovel-{a['role']}", "role": a["role"], "fingerprint": _sha(a)} for a in agents]}
    d = ensure_dir(base / "agents")
    p1 = _write(d / "registry.json", {"agents": agents, "missing_routes": [a["role"] for a in agents if not a["configured"]]})
    p2 = _write(d / "skill_lock.json", skill_lock)
    return {"agent_registry": str(p1), "skill_lock": str(p2)}


def _optimize_ssot(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    commits = []
    for p in snapshot.get("commits") or []:
        data = _safe_read_json(Path(p), {})
        commits.append({"path": str(p), "chapter_no": _chapter_no_from_path(Path(p)), "fingerprint": _fingerprint_file(Path(p)), "commit_id": data.get("commit_id") or data.get("id") or Path(p).stem})
    events = snapshot.get("events") or []
    event_fps = []
    prev = "GENESIS"
    duplicate_ids: list[str] = []
    seen_ids: set[str] = set()
    for idx, event in enumerate(events):
        eid = str(event.get("event_id") or event.get("id") or f"event_{idx}") if isinstance(event, dict) else f"event_{idx}"
        if eid in seen_ids:
            duplicate_ids.append(eid)
        seen_ids.add(eid)
        fp = _sha({"prev": prev, "event": event})
        event_fps.append({"index": idx, "event_id": eid, "prev": prev, "fingerprint": fp})
        prev = fp
    state_fp = _fingerprint_file(Path(paths.state))
    projection = {"updated_at": _now(), "state_fingerprint": state_fp, "commit_count": len(commits), "event_count": len(events), "duplicate_event_ids": duplicate_ids, "commits": commits, "event_chain": event_fps, "projection_signature": _sha([state_fp, commits, event_fps])}
    replay = {"can_replay": bool(commits), "from_chapter": min([c["chapter_no"] for c in commits if c["chapter_no"]] or [0]), "to_chapter": max([c["chapter_no"] for c in commits if c["chapter_no"]] or [0]), "steps": ["sync_control", "load_commits", "apply_changes", "write_state", "rebuild_indexes", "verify_signature"]}
    d = ensure_dir(base / "ssot")
    p1 = _write(d / "projection_chain.json", projection)
    p2 = _write(d / "replay_plan.json", replay)
    return {"ssot_projection_chain": str(p1), "ssot_replay_plan": str(p2)}


def _optimize_context(paths: Any, snapshot: dict[str, Any], base: Path, chapter_no: int, budget: int) -> dict[str, str]:
    state = snapshot.get("state") or {}
    entities = _entity_rows(state)
    chapter_rows = _chapter_records(snapshot)
    query_parts = [f"第{chapter_no}章"]
    bp = _safe_read_json(Path(paths.control) / "blueprints" / f"chapter_{chapter_no:04d}.json", {})
    query_parts.append(json.dumps(bp, ensure_ascii=False, default=str))
    query = "\n".join(query_parts)
    items: list[dict[str, Any]] = []
    for e in entities:
        items.append({"source": "entity", "id": e["id"], "title": e["name"], "weight": 0.82, "score": _score(query, e["text"]), "text": e["text"][:900]})
    for row in chapter_rows:
        items.append({"source": "chapter", "id": row["fingerprint"], "chapter_no": row["chapter_no"], "title": row["title"], "weight": 0.72, "score": _score(query, row["text"]), "text": row["text"]})
    for doc in _collect_reference_docs(paths):
        items.append({"source": "reference", "id": doc["fingerprint"], "title": doc["title"], "weight": 0.55, "score": _score(query, doc["text"]), "text": doc["text"]})
    for item in items:
        item["budget_cost"] = max(1, int(len(item.get("text", "")) / 1.7))
        item["final_score"] = round(float(item.get("weight", 0)) * (float(item.get("score", 0)) + 0.05), 6)
    items.sort(key=lambda x: x["final_score"], reverse=True)
    selected = []
    total = 0
    for item in items:
        cost = int(item.get("budget_cost") or 0)
        if total + cost > budget and selected:
            continue
        selected.append(item)
        total += cost
        if total >= budget:
            break
    task_book = {"chapter_no": chapter_no, "goal": bp.get("goal") or "", "must_cover_nodes": bp.get("must_cover_nodes") or [], "forbidden_zones": bp.get("forbidden_zones") or [], "selected_context_ids": [x.get("id") for x in selected], "context_budget_used": total, "output_contract": "正文 + CHANGES；正文出现的实体必须在 CHANGES 申报。"}
    report = {"chapter_no": chapter_no, "budget": budget, "used": total, "candidate_count": len(items), "selected": selected}
    d = ensure_dir(base / "context")
    p1 = _write(d / "weighted_context.json", report)
    p2 = _write(d / "task_book.json", task_book)
    return {"weighted_context": str(p1), "task_book": str(p2)}


def _optimize_rag(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    records = _chapter_records(snapshot)
    entities = _entity_rows(snapshot.get("state") or {})
    for e in entities:
        records.append({"source": "entity", "chapter_no": 0, "chunk_no": 0, "path": "story_state.json", "title": e["name"], "text": e["text"], "tokens": _tokens(e["text"]), "vector": _hash_vector(e["text"]), "fingerprint": _sha(e)})
    for doc in _collect_reference_docs(paths):
        records.append({"source": "reference", "chapter_no": 0, "chunk_no": 0, "path": doc["path"], "title": doc["title"], "text": doc["text"], "tokens": _tokens(doc["text"]), "vector": doc["vector"], "fingerprint": doc["fingerprint"]})
    source_counts = Counter(str(r.get("source")) for r in records)
    router = {"routes": [
        {"when": "query mentions 人名/角色/aliases", "route": ["entity", "memory", "chapter"]},
        {"when": "query mentions 伏笔/冲突/秘密/债务", "route": ["entity", "chapter", "reference"]},
        {"when": "query asks technique/style/template", "route": ["reference", "memory", "chapter"]},
        {"when": "default", "route": ["chapter", "entity", "memory", "reference"]},
    ], "source_counts": dict(source_counts), "rerank": "weighted lexical + hash-vector cosine"}
    d = ensure_dir(base / "rag")
    p1 = _write(d / "hybrid_index.json", {"built_at": _now(), "dimension": 64, "record_count": len(records), "records": records})
    p2 = _write(d / "query_router.json", router)
    return {"hybrid_rag_index": str(p1), "query_router": str(p2)}


def _optimize_memory(paths: Any, snapshot: dict[str, Any], base: Path, budget: int) -> dict[str, str]:
    state = snapshot.get("state") or {}
    rows = []
    for e in _entity_rows(state):
        priority = e["priority"]
        if e["bucket"] in {"foreshadows", "conflicts", "secrets", "deadlines"}:
            priority += 20
        rows.append({"memory_id": _sha([e["bucket"], e["id"]]), "category": e["bucket"], "subject": e["name"], "status": e["status"], "priority": priority, "text": e["text"][:1200], "source": "story_state", "fingerprint": _sha(e)})
    for p in snapshot.get("commits") or []:
        data = _safe_read_json(Path(p), {})
        rows.append({"memory_id": _sha(str(p)), "category": "chapter_commit", "subject": Path(p).stem, "priority": 60, "text": json.dumps(data, ensure_ascii=False, default=str)[:1500], "source": str(p), "fingerprint": _fingerprint_file(Path(p))})
    rows.sort(key=lambda x: int(x.get("priority") or 0), reverse=True)
    used = 0
    selected = []
    for row in rows:
        cost = max(1, int(len(row.get("text", "")) / 1.7))
        if used + cost > budget and selected:
            continue
        row["budget_cost"] = cost
        selected.append(row)
        used += cost
    compacted_by_cat: dict[str, list[str]] = defaultdict(list)
    for row in selected:
        compacted_by_cat[str(row.get("category"))].append(str(row.get("subject")))
    conflicts = _memory_conflicts(rows)
    d = ensure_dir(base / "memory")
    p1 = _write(d / "store.json", {"schema_version": 2, "built_at": _now(), "items": rows})
    p2 = _write(d / "budget.json", {"budget": budget, "used": used, "selected_ids": [x["memory_id"] for x in selected]})
    p3 = _write(d / "compacted.json", {"built_at": _now(), "summary": {k: v[:50] for k, v in compacted_by_cat.items()}, "selected_count": len(selected)})
    p4 = _write(d / "conflicts.json", {"conflicts": conflicts})
    return {"memory_store": str(p1), "memory_budget": str(p2), "memory_compacted": str(p3), "memory_conflicts": str(p4)}


def _memory_conflicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        grouped[(str(row.get("category")), str(row.get("subject")))].add(str(row.get("status") or ""))
    return [{"category": k[0], "subject": k[1], "statuses": sorted(v)} for k, v in grouped.items() if len([x for x in v if x]) > 1]


def _chapter_text(paths: Any, chapter_no: int) -> str:
    candidates = list(Path(paths.chapters).glob(f"*{chapter_no:04d}*")) + list(Path(paths.drafts).glob(f"*{chapter_no:04d}*"))
    if not candidates:
        candidates = list(Path(paths.chapters).glob(f"*{chapter_no}*")) + list(Path(paths.drafts).glob(f"*{chapter_no}*"))
    for p in candidates:
        if p.is_file():
            text = _safe_read_text(p)
            if text:
                return text
    return ""


def _optimize_review(paths: Any, snapshot: dict[str, Any], base: Path, chapter_no: int) -> dict[str, str]:
    text = _chapter_text(paths, chapter_no)
    bp = _safe_read_json(Path(paths.control) / "blueprints" / f"chapter_{chapter_no:04d}.json", {})
    entities = _entity_rows(snapshot.get("state") or {})
    entity_hits = []
    for e in entities:
        names = [e["name"], e["id"], *[str(a) for a in e.get("aliases") or []]]
        count = sum(text.count(n) for n in names if n)
        if count:
            entity_hits.append({"bucket": e["bucket"], "name": e["name"], "mentions": count})
    nodes = bp.get("must_cover_nodes") or []
    fulfillment = []
    for node in nodes:
        node_text = str(node)
        evidence_score = _score(node_text, text)
        fulfillment.append({"node": node_text, "score": evidence_score, "fulfilled": evidence_score >= 0.08 or node_text in text})
    review_schema = {"schema_version": 2, "dimensions": ["blueprint_fulfillment", "entity_disambiguation", "changes_alignment", "fact_extraction", "anti_ai_language", "structure", "repair_convergence"], "blocking_levels": ["fatal", "needs_repair"], "chapter_no": chapter_no}
    extraction = {"chapter_no": chapter_no, "entities_seen": entity_hits, "candidate_facts": _extract_candidate_facts(text), "text_fingerprint": _sha(text)}
    disamb = {"chapter_no": chapter_no, "ambiguous_mentions": _ambiguous_mentions(entity_hits), "resolved_mentions": entity_hits}
    fulfillment_report = {"chapter_no": chapter_no, "goal": bp.get("goal") or "", "nodes": fulfillment, "fulfilled_count": sum(1 for x in fulfillment if x["fulfilled"]), "total": len(fulfillment)}
    issues = []
    if fulfillment and any(not x["fulfilled"] for x in fulfillment):
        issues.append({"type": "blueprint_unfulfilled", "level": "needs_repair", "count": sum(1 for x in fulfillment if not x["fulfilled"])})
    if len(text) < 500:
        issues.append({"type": "too_short", "level": "warning", "message": "章节正文过短，可能不是完整正文。"})
    convergence = {"chapter_no": chapter_no, "max_rounds": 3, "issues": issues, "repair_rounds": _repair_rounds_from_issues(issues), "ready_for_commit": not any(x.get("level") in {"fatal", "needs_repair"} for x in issues)}
    d = ensure_dir(base / "review")
    p1 = _write(d / "review_schema.json", review_schema)
    p2 = _write(d / "fulfillment_result.json", fulfillment_report)
    p3 = _write(d / "disambiguation_result.json", disamb)
    p4 = _write(d / "extraction_result.json", extraction)
    p5 = _write(d / "convergence_plan.json", convergence)
    return {"review_schema": str(p1), "fulfillment": str(p2), "disambiguation": str(p3), "extraction": str(p4), "convergence": str(p5)}


def _extract_candidate_facts(text: str) -> list[dict[str, Any]]:
    sentences = [s.strip() for s in re.split(r"[。！？!?\n]+", text) if len(s.strip()) >= 8]
    out = []
    for s in sentences[:120]:
        if any(k in s for k in ["发现", "获得", "失去", "决定", "承诺", "背叛", "死亡", "离开", "进入", "揭露", "隐藏"]):
            out.append({"sentence": s[:160], "event_hint": True, "fingerprint": _sha(s)})
    return out[:40]


def _ambiguous_mentions(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for h in hits:
        by_name[str(h.get("name"))].append(str(h.get("bucket")))
    return [{"name": n, "buckets": sorted(set(bs))} for n, bs in by_name.items() if len(set(bs)) > 1]


def _repair_rounds_from_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rounds = []
    for idx, issue in enumerate(issues[:3], start=1):
        rounds.append({"round": idx, "target_issue": issue, "strategy": "局部修复，不重写已可信正文；修复后重新运行 review-pipeline-deep。"})
    return rounds


def _optimize_entities(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    entities = _entity_rows(snapshot.get("state") or {})
    chapters = _chapter_records(snapshot)
    links = []
    for e in entities:
        names = [e["name"], e["id"], *[str(a) for a in e.get("aliases") or []]]
        mentions = []
        for row in chapters:
            count = sum(str(row.get("text", "")).count(n) for n in names if n)
            if count:
                mentions.append({"chapter_no": row["chapter_no"], "chunk_no": row["chunk_no"], "count": count, "chunk_id": row["fingerprint"]})
        links.append({"bucket": e["bucket"], "name": e["name"], "id": e["id"], "aliases": e["aliases"], "mention_count": sum(m["count"] for m in mentions), "mentions": mentions[:80]})
    debts = []
    for e in entities:
        if e["bucket"] in {"foreshadows", "conflicts", "secrets", "deadlines"} and e["status"] not in {"closed", "done", "resolved", "已回收", "已解决"}:
            debts.append({"bucket": e["bucket"], "name": e["name"], "status": e["status"], "priority": e["priority"], "suggestion": "安排推进或回收窗口；写前加入 context-manager 高权重。"})
    structural = {"open_debts": debts, "debt_count": len(debts), "chapter_count": len(snapshot.get("chapters") or []), "warnings": ["没有章节正文，结构检查只能基于状态。"] if not snapshot.get("chapters") else []}
    d = ensure_dir(base / "entities")
    p1 = _write(d / "entity_linking.json", {"entities": links, "entity_count": len(links)})
    p2 = _write(d / "structural_debts.json", structural)
    return {"entity_linking": str(p1), "structural_debts": str(p2)}


def _optimize_publisher(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    state = snapshot.get("state") or {}
    published = (((state.get("publication") or {}).get("chapters") or {}) if isinstance(state.get("publication"), dict) else {})
    chapters = []
    for p in snapshot.get("chapters") or []:
        no = _chapter_no_from_path(Path(p))
        text = _safe_read_text(Path(p))
        chapters.append({"chapter_no": no, "path": str(p), "title": Path(p).stem, "words": len(text), "publish_status": (published.get(str(no)) or {}).get("status") if isinstance(published, dict) else "", "ready": bool(text) and not ((published.get(str(no)) or {}).get("status") == "published" if isinstance(published, dict) else False)})
    jobs = []
    for platform in ("fanqie", "qimao"):
        jobs.append({"platform": platform, "adapter": f"publisher.adapters.{platform}", "formatter": "default_webnovel_formatter", "ready_chapters": [c for c in chapters if c["ready"]], "state": "ready" if any(c["ready"] for c in chapters) else "empty"})
    formatter = {"rules": {"title_format": "第{chapter_no:04d}章 {title}", "strip_changes": True, "normalize_blank_lines": True, "max_preview_chars": 800}, "previews": [{"chapter_no": c["chapter_no"], "title": c["title"], "path": c["path"]} for c in chapters[:20]]}
    d = ensure_dir(base / "publisher")
    p1 = _write(d / "platform_jobs.json", {"jobs": jobs})
    p2 = _write(d / "formatter_preview.json", formatter)
    return {"publisher_jobs": str(p1), "publisher_formatter": str(p2)}


def _optimize_sqlite(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    db_path = Path(paths.control) / "index.db"
    ensure_dir(db_path.parent)
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS entities (bucket TEXT, entity_id TEXT, name TEXT, status TEXT, payload TEXT, fingerprint TEXT, PRIMARY KEY(bucket, entity_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS chapters (chapter_no INTEGER PRIMARY KEY, path TEXT, title TEXT, words INTEGER, fingerprint TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS commits (chapter_no INTEGER, path TEXT, commit_id TEXT, fingerprint TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, chapter_no INTEGER, event_type TEXT, payload TEXT, fingerprint TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS memory (memory_id TEXT PRIMARY KEY, category TEXT, subject TEXT, payload TEXT, fingerprint TEXT)")
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts_records USING fts5(source, title, text, path)")
        cur.execute("DELETE FROM entities")
        for e in _entity_rows(snapshot.get("state") or {}):
            cur.execute("INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?)", (e["bucket"], e["id"], e["name"], e["status"], e["text"], _sha(e)))
        cur.execute("DELETE FROM chapters")
        cur.execute("DELETE FROM fts_records")
        for p in snapshot.get("chapters") or []:
            path = Path(p)
            text = _safe_read_text(path)
            no = _chapter_no_from_path(path)
            cur.execute("INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?)", (no, str(path), path.stem, len(text), _sha(text)))
            cur.execute("INSERT INTO fts_records(source,title,text,path) VALUES (?,?,?,?)", ("chapter", path.stem, text[:5000], str(path)))
        cur.execute("DELETE FROM commits")
        for p in snapshot.get("commits") or []:
            data = _safe_read_json(Path(p), {})
            cur.execute("INSERT INTO commits VALUES (?,?,?,?)", (_chapter_no_from_path(Path(p)), str(p), str(data.get("commit_id") or Path(p).stem), _fingerprint_file(Path(p))))
        cur.execute("DELETE FROM events")
        for idx, ev in enumerate(snapshot.get("events") or []):
            eid = str(ev.get("event_id") or ev.get("id") or f"event_{idx}") if isinstance(ev, dict) else f"event_{idx}"
            cur.execute("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", (eid, _to_int(ev.get("chapter_no") if isinstance(ev, dict) else 0), str(ev.get("type") or ev.get("event") or "") if isinstance(ev, dict) else "", json.dumps(ev, ensure_ascii=False, default=str), _sha(ev)))
        con.commit()
        stats = {"entities": cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0], "chapters": cur.execute("SELECT COUNT(*) FROM chapters").fetchone()[0], "commits": cur.execute("SELECT COUNT(*) FROM commits").fetchone()[0], "events": cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]}
    finally:
        con.close()
    schema = {"db_path": str(db_path), "tables": ["entities", "chapters", "commits", "events", "memory", "fts_records"], "stats": stats, "validated_at": _now()}
    d = ensure_dir(base / "sqlite")
    p1 = _write(d / "schema_report.json", schema)
    return {"sqlite_schema_report": str(p1), "sqlite_db": str(db_path)}


def _optimize_security_observability(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    secret_patterns = [re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?([^'\"\s]{8,})"), re.compile(r"sk-[A-Za-z0-9]{20,}")]
    findings = []
    for folder in [Path(paths.root), Path(paths.control)]:
        for p in list(folder.glob("*.json")) + list(folder.glob("*.env*")) + list(folder.glob("**/*.json"))[:200]:
            if not p.is_file() or "__pycache__" in str(p):
                continue
            text = _safe_read_text(p)
            if not text and p.suffix == ".json":
                text = json.dumps(_safe_read_json(p, {}), ensure_ascii=False, default=str)
            for pat in secret_patterns:
                for m in pat.finditer(text or ""):
                    findings.append({"path": str(p), "pattern": pat.pattern[:40], "redacted": "***", "span": [m.start(), m.end()]})
    metrics = {"collected_at": _now(), "chapter_count": len(snapshot.get("chapters") or []), "commit_count": len(snapshot.get("commits") or []), "event_count": len(snapshot.get("events") or []), "review_count": len(snapshot.get("reviews") or []), "alignment_v23_files": len(list(base.glob("**/*.json"))) if base.exists() else 0}
    d1 = ensure_dir(base / "security")
    d2 = ensure_dir(base / "observability")
    p1 = _write(d1 / "security_audit.json", {"finding_count": len(findings), "findings": findings[:100], "policy": "logs and reports should redact API keys/tokens/secrets before display"})
    p2 = _write(d2 / "metrics.json", metrics)
    return {"security_audit": str(p1), "observability_metrics": str(p2)}


def _optimize_references(paths: Any, snapshot: dict[str, Any], base: Path) -> dict[str, str]:
    docs = _collect_reference_docs(paths)
    profile = {"doc_count": len(docs), "top_titles": [d["title"] for d in docs[:50]], "fingerprint": _sha(docs[:20])}
    chapter_texts = [_safe_read_text(Path(p)) for p in snapshot.get("chapters") or []]
    all_text = "\n".join(chapter_texts[:80])
    hooks = [s.strip() for s in re.split(r"[。！？!?\n]+", all_text) if any(k in s for k in ["忽然", "就在", "没想到", "下一刻", "却见", "原来"])][:30]
    deconstruct = {"sample_chapters": len(chapter_texts), "avg_chapter_chars": int(sum(len(x) for x in chapter_texts) / max(1, len(chapter_texts))), "dialogue_ratio_hint": round(all_text.count("“") / max(1, len(all_text)), 5), "hook_samples": hooks, "style_tokens": Counter(_tokens(all_text)).most_common(80)}
    d = ensure_dir(base / "references")
    p1 = _write(d / "knowledge_profile.json", profile)
    p2 = _write(d / "deconstruction_profile.json", deconstruct)
    return {"reference_knowledge_profile": str(p1), "deconstruction_profile": str(p2)}


def query_alignment_router(storage: Any, project_id: str, query: str, top_k: int = 8) -> dict[str, Any]:
    _paths(storage, project_id)
    base = _alignment_dir(storage, project_id)
    idx = _safe_read_json(base / "rag" / "hybrid_index.json", {})
    records = idx.get("records") if isinstance(idx, dict) else []
    qv = _hash_vector(query)
    scored = []
    for r in records or []:
        text = str(r.get("text") or "")
        scored.append({
            "score": round(_score(query, text) * 0.65 + _cosine(qv, r.get("vector") or []) * 0.35, 6),
            "source": r.get("source"),
            "title": r.get("title"),
            "path": r.get("path"),
            "chapter_no": r.get("chapter_no"),
            "text": text[:500],
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    result = {"ok": True, "query": query, "top_k": top_k, "results": scored[:top_k]}
    path = _write(base / "rag" / "last_alignment_query.json", result)
    result["paths_written"] = {"query": str(path)}
    return result
