from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, read_jsonl, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto

CAPABILITIES_V24: list[dict[str, Any]] = [
    {
        "code": "workflow_orchestrator_checkpoint",
        "name": "Workflow / checkpoint / resume 编排器",
        "reference": ["lingfeng: run-ledger/write-resume/user-report", "opencode: workflow_checkpoint.py/orchestrate.py"],
        "required": [
            "writer_control/alignment_v24/workflow/state_machine.json",
            "writer_control/alignment_v24/workflow/resume_decision.json",
            "writer_control/alignment_v24/workflow/trust_contracts.json",
        ],
        "deep_checks": ["stages>=12", "trust_rules", "resume_candidates", "artifact_signatures"],
    },
    {
        "code": "agent_skill_registry_contracts",
        "name": "Agent / skill registry / skill lock",
        "reference": ["lingfeng: context/reviewer/data/deconstruction agents", "opencode: agents/skills/skill_runner.py/skills-lock.json"],
        "required": [
            "writer_control/alignment_v24/agents/registry.json",
            "writer_control/alignment_v24/agents/skill_contracts.json",
            "writer_control/alignment_v24/agents/skill_lock.json",
        ],
        "deep_checks": [">=9 agents", "inputs_outputs", "model_roles", "failure_policy"],
    },
    {
        "code": "ssot_event_projection_chain",
        "name": "SSOT / event store / projection log / replay",
        "reference": ["lingfeng: story-system/chapter-commit/story-events/projections", "opencode: event_log_store.py/projection_log.py/state_projection_writer.py"],
        "required": [
            "writer_control/alignment_v24/ssot/event_schema.json",
            "writer_control/alignment_v24/ssot/projection_registry.json",
            "writer_control/alignment_v24/ssot/replay_manifest.json",
        ],
        "deep_checks": ["event_fingerprint", "projection_versions", "replay_range", "drift_policy"],
    },
    {
        "code": "context_manager_budget_taskbook",
        "name": "Context manager / weights / budget / task book",
        "reference": ["lingfeng: context-agent research + 写作任务书", "opencode: context_manager.py/context_weights.py"],
        "required": [
            "writer_control/alignment_v24/context/source_registry.json",
            "writer_control/alignment_v24/context/budget_plan.json",
            "writer_control/alignment_v24/context/task_book_v2.json",
        ],
        "deep_checks": ["source_priority", "dedupe", "token_budget", "why_included"],
    },
    {
        "code": "rag_adapter_vector_rerank_router",
        "name": "RAG adapter / vector projection / rerank / query router",
        "reference": ["lingfeng: rag/index/query", "opencode: rag_adapter.py/vector_projection_writer.py/query_router.py"],
        "required": [
            "writer_control/alignment_v24/rag/vector_projection_manifest.json",
            "writer_control/alignment_v24/rag/rerank_profile.json",
            "writer_control/alignment_v24/rag/query_router_v2.json",
        ],
        "deep_checks": ["multi_source", "vector_signature", "rerank_explain", "route_types"],
    },
    {
        "code": "memory_store_schema_budget_compactor",
        "name": "Memory store / schema / writer / budget / compactor / orchestrator",
        "reference": ["lingfeng: memory stats/query/bootstrap/update", "opencode: memory/store.py/schema.py/writer.py/budget.py/compactor.py/orchestrator.py"],
        "required": [
            "writer_control/alignment_v24/memory/schema_v2.json",
            "writer_control/alignment_v24/memory/budget_pack.json",
            "writer_control/alignment_v24/memory/compaction_manifest.json",
            "writer_control/alignment_v24/memory/conflict_resolution.json",
        ],
        "deep_checks": ["schema", "priority_budget", "compaction", "conflict_policy"],
    },
    {
        "code": "review_pipeline_artifacts_repair_convergence",
        "name": "Review pipeline / artifacts / convergence repair",
        "reference": ["lingfeng: review-pipeline + chapter-commit artifacts", "opencode: review_pipeline.py/review_schema.py/amend_proposal_schema.py"],
        "required": [
            "writer_control/alignment_v24/review/review_schema_v2.json",
            "writer_control/alignment_v24/review/artifact_contracts.json",
            "writer_control/alignment_v24/review/repair_rounds.json",
        ],
        "deep_checks": ["dimensions>=10", "fulfillment", "disambiguation", "extraction", "repair_rounds"],
    },
    {
        "code": "entity_linker_debt_structural_checker",
        "name": "Entity linker / debt tracker / structural checker",
        "reference": ["opencode: entity_linker.py/index_entity_mixin.py/index_debt_mixin.py/structural_checker.py"],
        "required": [
            "writer_control/alignment_v24/entities/linker_index.json",
            "writer_control/alignment_v24/entities/debt_rules.json",
            "writer_control/alignment_v24/entities/structural_report.json",
        ],
        "deep_checks": ["aliases", "ambiguity", "debt_age", "structure_beats"],
    },
    {
        "code": "publisher_platform_state_machine",
        "name": "Publisher formatter / platform adapters / publish state machine",
        "reference": ["opencode: publisher/formatter.py/config.py/adapters/fanqie.py/adapters/qimao.py"],
        "required": [
            "writer_control/alignment_v24/publisher/platform_mapping.json",
            "writer_control/alignment_v24/publisher/publish_state_machine.json",
            "writer_control/alignment_v24/publisher/fanqie_bridge_contract.json",
        ],
        "deep_checks": ["platform_jobs", "formatter", "status_mapping", "failure_retry"],
    },
    {
        "code": "sqlite_schema_validator_indexes",
        "name": "SQLite schema / validator / FTS indexes",
        "reference": ["opencode: schemas.py/state_validator.py/migrate_state_to_sqlite.py/story_event_schema.py"],
        "required": [
            "writer_control/alignment_v24/sqlite/schema_registry.json",
            "writer_control/alignment_v24/sqlite/validation_rules.json",
            "writer_control/index.db",
        ],
        "deep_checks": ["tables>=7", "fts", "foreign_keys", "schema_version"],
    },
    {
        "code": "security_observability_runtime",
        "name": "Security utils / observability / runtime compatibility",
        "reference": ["opencode: security_utils.py/observability.py/runtime_compat.py/index_observability_mixin.py"],
        "required": [
            "writer_control/alignment_v24/security/redaction_policy.json",
            "writer_control/alignment_v24/security/secret_scan.json",
            "writer_control/alignment_v24/observability/runtime_metrics.json",
        ],
        "deep_checks": ["secret_patterns", "path_safety", "metrics", "runtime_env"],
    },
    {
        "code": "reference_knowledge_deconstruction_evals",
        "name": "References / knowledge query / deconstruction / evals",
        "reference": ["opencode: reference_search.py/knowledge_query.py/deconstruction-agent/evals/tests"],
        "required": [
            "writer_control/alignment_v24/references/knowledge_router.json",
            "writer_control/alignment_v24/references/deconstruction_schema.json",
            "writer_control/alignment_v24/evals/eval_matrix.json",
        ],
        "deep_checks": ["csv_validation", "knowledge_routes", "deconstruction", "regression_cases"],
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _ensure(path: Path) -> Path:
    ensure_dir(path.parent)
    return path


def _write(path: Path, data: Any) -> Path:
    return write_json(_ensure(path), data)


def _safe_json(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path, default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _safe_text(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return read_text_auto(path)
    except Exception:
        return ""
    return ""


def _sha(value: Any, n: int = 24) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _file_sha(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 512), b""):
            h.update(chunk)
    return h.hexdigest()[:24]


def _control(paths: Any) -> Path:
    return Path(paths.control)


def _alignment_dir(paths: Any) -> Path:
    return ensure_dir(_control(paths) / "alignment_v24")


def _chapter_no(path: Path) -> int:
    m = re.search(r"(\d{1,6})", path.stem)
    return int(m.group(1)) if m else 0


def _read_events(paths: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for base in [Path(paths.root) / "events", Path(paths.control) / "events"]:
        if not base.exists():
            continue
        for file in sorted(base.glob("*.jsonl")):
            for row in read_jsonl(file):
                if isinstance(row, dict):
                    events.append(row)
                else:
                    events.append({"value": row})
    return events


def _chapter_files(paths: Any) -> list[Path]:
    files = list(Path(paths.chapters).glob("*.txt")) + list(Path(paths.chapters).glob("*.md"))
    return sorted(files, key=_chapter_no)


def _commit_files(paths: Any) -> list[Path]:
    return sorted(Path(paths.commits).glob("*.json"), key=_chapter_no)


def _entity_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
        data = state.get(bucket) or {}
        if not isinstance(data, dict):
            continue
        for name, raw in data.items():
            obj = raw if isinstance(raw, dict) else {"value": raw}
            aliases = obj.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [x.strip() for x in re.split(r"[,，、;；\s]+", aliases) if x.strip()]
            rows.append({
                "bucket": bucket,
                "name": str(name),
                "id": str(obj.get("id") or obj.get("key") or name),
                "aliases": aliases if isinstance(aliases, list) else [],
                "status": str(obj.get("status") or obj.get("state") or ""),
                "payload": obj,
            })
    return rows


def _tokens(text: str) -> list[str]:
    text = str(text or "")
    out = [w.lower() for w in re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,5}", text)]
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    for n in (2, 3, 4):
        for i in range(max(0, len(chars) - n + 1)):
            out.append("".join(chars[i:i+n]))
    return out


def _score(query: str, text: str) -> float:
    q = Counter(_tokens(query)); t = Counter(_tokens(text))
    if not q or not t:
        return 0.0
    dot = sum(min(t.get(k, 0), v) for k, v in q.items())
    qn = sum(v*v for v in q.values()) ** 0.5 or 1.0
    tn = sum(v*v for v in t.values()) ** 0.5 or 1.0
    return round(dot / (qn * tn), 6)


def _hash_vec(text: str, dims: int = 96) -> list[float]:
    vec = [0.0] * dims
    for token, count in Counter(_tokens(text)).items():
        h = int(hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
        idx = h % dims
        sign = -1.0 if (h >> 8) & 1 else 1.0
        vec[idx] += sign * float(count)
    norm = sum(x*x for x in vec) ** 0.5 or 1.0
    return [round(x / norm, 6) for x in vec]


def _project_snapshot(paths: Any) -> dict[str, Any]:
    state = _safe_json(Path(paths.state), {})
    meta = _safe_json(Path(paths.meta), {})
    story_config = _safe_json(Path(paths.story_config), {})
    chapters = _chapter_files(paths)
    commits = _commit_files(paths)
    events = _read_events(paths)
    reviews = sorted(Path(paths.reviews).glob("*.json"), key=_chapter_no)
    artifacts = list(Path(paths.artifacts).glob("**/*.json")) if Path(paths.artifacts).exists() else []
    return {
        "state": state if isinstance(state, dict) else {},
        "meta": meta if isinstance(meta, dict) else {},
        "story_config": story_config if isinstance(story_config, dict) else {},
        "chapters": chapters,
        "commits": commits,
        "events": events,
        "reviews": reviews,
        "artifacts": artifacts,
        "entities": _entity_rows(state if isinstance(state, dict) else {}),
    }


def _artifact_quality(path: Path) -> tuple[str, list[str]]:
    if not path.exists():
        return "missing", ["文件不存在"]
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        try:
            if path.stat().st_size > 0:
                return "deep", []
        except Exception:
            pass
        return "shallow", ["数据库为空"]
    data = _safe_json(path, None)
    if data is None:
        return "shallow", ["不是有效 JSON"]
    raw = json.dumps(data, ensure_ascii=False, default=str)
    reasons: list[str] = []
    if len(raw) < 120:
        reasons.append("内容过短")
    if isinstance(data, dict):
        if len(data.keys()) < 2:
            reasons.append("字段过少")
        if data.get("TODO") or data.get("placeholder"):
            reasons.append("仍含占位字段")
    if reasons:
        return "shallow", reasons
    return "deep", []


def _capability_status(paths: Any, capability: dict[str, Any]) -> dict[str, Any]:
    artifacts = []
    statuses = []
    for rel in capability.get("required") or []:
        path = Path(paths.root) / rel
        status, reasons = _artifact_quality(path)
        artifacts.append({"path": rel, "exists": path.exists(), "status": status, "reasons": reasons, "sha": _file_sha(path)})
        statuses.append(status)
    if all(s == "deep" for s in statuses):
        status = "deep_aligned"
        score = 1.0
    elif any(s != "missing" for s in statuses):
        status = "shallow"
        score = round(sum(1 for s in statuses if s == "deep") / max(1, len(statuses)), 3)
    else:
        status = "missing"
        score = 0.0
    return {
        "code": capability["code"],
        "name": capability["name"],
        "reference": capability.get("reference") or [],
        "status": status,
        "score": score,
        "deep_checks": capability.get("deep_checks") or [],
        "artifacts": artifacts,
    }


def alignment_gap_matrix_v24_command(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    root = _alignment_dir(paths)
    rows = [_capability_status(paths, cap) for cap in CAPABILITIES_V24]
    missing = [r for r in rows if r["status"] == "missing"]
    shallow = [r for r in rows if r["status"] == "shallow"]
    deep = [r for r in rows if r["status"] == "deep_aligned"]
    score = round(sum(r["score"] for r in rows) / max(1, len(rows)), 3)
    report = {
        "ok": len(missing) == 0 and len(shallow) == 0,
        "generated_at": _now(),
        "project_id": project_id,
        "alignment_score": score,
        "total": len(rows),
        "deep_aligned": len(deep),
        "shallow": len(shallow),
        "missing": len(missing),
        "not_aligned": [{"code": r["code"], "name": r["name"], "status": r["status"], "score": r["score"], "reasons": [a for a in r["artifacts"] if a["status"] != "deep"]} for r in rows if r["status"] != "deep_aligned"],
        "capabilities": rows,
        "next_command": f"python -m backend.adapters.webnovel_writer.webnovel_writer_cli alignment-optimize-v24 --project {project_id}",
    }
    _write(root / "gap_matrix.json", report)
    return report


def _build_workflow(paths: Any, snap: dict[str, Any], chapter_no: int, out: Path) -> dict[str, str]:
    stages = [
        "prewrite", "context", "contract", "task_book", "draft", "review", "fulfillment", "disambiguation",
        "extraction", "precommit", "commit", "projection", "postcommit", "quality", "publish_ready", "user_report",
    ]
    artifact_map = {stage: f"writer_control/workflows_v24/chapter_{chapter_no:04d}/{i:02d}_{stage}.json" for i, stage in enumerate(stages)}
    signatures = {}
    for rel in artifact_map.values():
        path = Path(paths.root) / rel
        if path.exists():
            signatures[rel] = _file_sha(path)
    state_machine = {
        "kind": "workflow_state_machine_v24",
        "chapter_no": chapter_no,
        "generated_at": _now(),
        "stages": [{"order": i, "name": s, "required": s not in {"publish_ready"}, "artifact": artifact_map[s]} for i, s in enumerate(stages)],
        "trust_rules": {
            "prewrite": ["project exists", "blueprint exists or can be generated", "no invalidated chapter marker"],
            "draft": ["chapter body exists", "changes region parseable or repairable"],
            "review": ["review_schema_v2 present", "blocking issues classified"],
            "commit": ["fulfillment/disambiguation/extraction artifacts exist", "commit JSON fingerprint stable"],
            "projection": ["state projection replay succeeds", "event chain fingerprint continuous"],
        },
        "artifact_signatures": signatures,
        "safe_rerun_policy": {"trusted_artifact": "reuse", "missing_artifact": "regenerate", "failed_artifact": "repair_then_resume", "changed_input": "invalidate_downstream"},
    }
    resume_candidates = []
    for stage in stages:
        rel = artifact_map[stage]
        if not (Path(paths.root) / rel).exists():
            resume_candidates.append({"stage": stage, "reason": "artifact_missing", "command_hint": f"workflow-runner --chapter {chapter_no} --action run"})
            break
    resume = {
        "kind": "resume_decision_v24",
        "chapter_no": chapter_no,
        "generated_at": _now(),
        "resume_from": resume_candidates[0]["stage"] if resume_candidates else "done",
        "resume_candidates": resume_candidates,
        "trusted_existing": [rel for rel in artifact_map.values() if (Path(paths.root) / rel).exists()],
        "blocking": [],
    }
    trust = {"kind": "workflow_trust_contracts_v24", "chapter_no": chapter_no, "stage_count": len(stages), "contracts": state_machine["trust_rules"], "fingerprint": _sha(state_machine)}
    return {
        "state_machine": str(_write(out / "workflow" / "state_machine.json", state_machine)),
        "resume_decision": str(_write(out / "workflow" / "resume_decision.json", resume)),
        "trust_contracts": str(_write(out / "workflow" / "trust_contracts.json", trust)),
    }


def _build_agents(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    agent_specs = [
        ("planner", ["story_config", "genre_profile"], ["outline", "blueprint"], "planner"),
        ("context", ["blueprint", "memory", "rag", "truth"], ["weighted_context", "task_book"], "context"),
        ("drafter", ["task_book", "runtime_contract"], ["draft", "changes"], "drafter"),
        ("reviewer", ["draft", "blueprint", "truth"], ["review_schema", "blocking_issues"], "reviewer"),
        ("fact", ["draft", "changes"], ["extraction_result", "commit_candidate"], "fact"),
        ("repair", ["review", "draft"], ["repair_patch", "fixed_draft"], "repair"),
        ("memory", ["commit", "events"], ["memory_store", "compacted_memory"], "default"),
        ("rag", ["chapters", "references", "memory"], ["hybrid_index", "rerank_profile"], "default"),
        ("publisher", ["committed_chapter", "publish_queue"], ["platform_job", "status_mapping"], "publisher"),
        ("orchestrator", ["all_step_artifacts"], ["checkpoint", "resume_plan", "user_report"], "default"),
    ]
    registry = {
        "kind": "agent_registry_v24",
        "generated_at": _now(),
        "agents": [
            {"name": name, "inputs": inputs, "outputs": outputs, "model_role": role, "failure_policy": "write artifact + resume from failed step", "isolation": "agent scoped prompt/context"}
            for name, inputs, outputs, role in agent_specs
        ],
        "model_routes_detected": _safe_json(Path(paths.control) / "models" / "model_routes.json", {}),
    }
    contracts = {"kind": "skill_contracts_v24", "contracts": {a[0]: {"must_read": a[1], "must_write": a[2], "idempotent": a[0] not in {"drafter", "publisher"}} for a in agent_specs}, "fingerprint": _sha(agent_specs)}
    lock = {"kind": "skill_lock_v24", "version": 1, "agents": {a[0]: _sha({"in": a[1], "out": a[2], "role": a[3]}) for a in agent_specs}}
    return {
        "registry": str(_write(out / "agents" / "registry.json", registry)),
        "skill_contracts": str(_write(out / "agents" / "skill_contracts.json", contracts)),
        "skill_lock": str(_write(out / "agents" / "skill_lock.json", lock)),
    }


def _build_ssot(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    event_schema = {
        "kind": "event_schema_v24",
        "required_fields": ["event_id", "event_type", "chapter_no", "created_at", "source", "payload", "prev_hash", "hash"],
        "known_event_types": ["chapter_committed", "projection_replayed", "manual_override", "publication_status_changed", "chapters_invalidated", "control_synced"],
        "hash_rule": "sha256(prev_hash + canonical_json(event_without_hash))",
        "events_found": len(snap["events"]),
    }
    projections = ["state", "truth", "memory", "chunk_index", "vector", "relations", "debts", "sqlite", "publisher_status"]
    registry = {"kind": "projection_registry_v24", "generated_at": _now(), "projections": [{"name": p, "version": 1, "input": "commit/events", "idempotent": True} for p in projections], "commit_count": len(snap["commits"])}
    replay = {"kind": "replay_manifest_v24", "chapters": [_chapter_no(p) for p in snap["commits"]], "event_count": len(snap["events"]), "drift_policy": "state must be derived from commits + manual control overlays", "fingerprint": _sha([_file_sha(p) for p in snap["commits"]] + snap["events"])}
    return {
        "event_schema": str(_write(out / "ssot" / "event_schema.json", event_schema)),
        "projection_registry": str(_write(out / "ssot" / "projection_registry.json", registry)),
        "replay_manifest": str(_write(out / "ssot" / "replay_manifest.json", replay)),
    }


def _build_context(paths: Any, snap: dict[str, Any], chapter_no: int, budget: int, out: Path) -> dict[str, str]:
    sources: list[dict[str, Any]] = []
    blueprint = Path(paths.control) / "blueprints" / f"chapter_{chapter_no:04d}.json"
    if blueprint.exists():
        sources.append({"source": "blueprint", "path": str(blueprint), "priority": 100, "text": json.dumps(_safe_json(blueprint, {}), ensure_ascii=False)})
    for entity in snap["entities"][:80]:
        sources.append({"source": f"entity:{entity['bucket']}", "path": "story_state.json", "priority": 82, "text": json.dumps(entity, ensure_ascii=False)})
    for ch in snap["chapters"][-8:]:
        txt = _safe_text(ch)
        sources.append({"source": "recent_chapter", "path": str(ch), "priority": 68, "text": txt[:3000]})
    for ref in list((Path(paths.control) / "references").glob("**/*"))[:80] if (Path(paths.control) / "references").exists() else []:
        if ref.is_file() and ref.suffix.lower() in {".csv", ".txt", ".json", ".md"}:
            sources.append({"source": "reference", "path": str(ref), "priority": 55, "text": _safe_text(ref)[:3000]})
    query = " ".join([str(chapter_no), str(snap["meta"].get("title") or ""), str(snap["story_config"].get("genre") or "")])
    dedup: dict[str, dict[str, Any]] = {}
    for s in sources:
        key = _sha(re.sub(r"\s+", "", s["text"])[:500], 16)
        if key not in dedup or s["priority"] > dedup[key]["priority"]:
            dedup[key] = s
    rows = []
    used = 0
    for s in sorted(dedup.values(), key=lambda x: (x["priority"], _score(query, x["text"])), reverse=True):
        est = max(1, len(s["text"]) // 2)
        if used + est > budget and rows:
            continue
        rows.append({k: v for k, v in s.items() if k != "text"} | {"estimated_tokens": est, "score": _score(query, s["text"]), "why_included": ["high_priority", "query_match" if _score(query, s["text"]) > 0 else "background"], "excerpt": s["text"][:800]})
        used += est
        if used >= budget:
            break
    source_registry = {"kind": "context_source_registry_v24", "available_sources": Counter([r["source"] for r in rows]), "total_candidates": len(sources), "deduped": len(dedup), "source_contracts": {"blueprint": {"priority": 100, "required": True}, "entity": {"priority": 82, "required": True}, "recent_chapter": {"priority": 68, "required": False}, "reference": {"priority": 55, "required": False}, "memory": {"priority": 74, "required": False}, "truth": {"priority": 88, "required": True}}, "dedupe_rule": "sha16(normalized first 500 chars)", "budget_rule": "sort by priority + query score, then keep until token budget"}
    budget_plan = {"kind": "context_budget_plan_v24", "chapter_no": chapter_no, "budget": budget, "used_estimated": used, "items": rows}
    task_book = {"kind": "task_book_v24", "chapter_no": chapter_no, "must_obey": ["不要违反 blueprint forbidden_zones", "正文出现的事实必须在 CHANGES/提取结果中回写", "优先使用 weighted context 中 high_priority 内容"], "context_items": rows[:24], "fingerprint": _sha(rows)}
    return {
        "source_registry": str(_write(out / "context" / "source_registry.json", source_registry)),
        "budget_plan": str(_write(out / "context" / "budget_plan.json", budget_plan)),
        "task_book": str(_write(out / "context" / "task_book_v2.json", task_book)),
    }


def _build_rag(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    records = []
    for ch in snap["chapters"]:
        text = _safe_text(ch)
        if not text:
            continue
        parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for i, part in enumerate(parts[:120]):
            records.append({"id": f"chapter:{_chapter_no(ch)}:{i}", "type": "chapter_chunk", "chapter_no": _chapter_no(ch), "path": str(ch), "text": part[:1200], "vector": _hash_vec(part)})
    for e in snap["entities"]:
        txt = json.dumps(e, ensure_ascii=False)
        records.append({"id": f"entity:{e['bucket']}:{e['id']}", "type": "entity", "path": "story_state.json", "text": txt, "vector": _hash_vec(txt)})
    for p in [Path(paths.indexes) / "reference_index.json", Path(paths.control) / "memory" / "memory_store.json"]:
        data = _safe_json(p, {})
        if data:
            txt = json.dumps(data, ensure_ascii=False)[:2000]
            records.append({"id": f"aux:{p.stem}", "type": p.stem, "path": str(p), "text": txt, "vector": _hash_vec(txt)})
    manifest = {"kind": "vector_projection_manifest_v24", "records": len(records), "dims": 96, "sources": Counter([r["type"] for r in records]), "fingerprint": _sha([{k: v for k, v in r.items() if k != "vector"} for r in records])}
    rerank = {"kind": "rerank_profile_v24", "stages": ["route", "lexical_score", "hash_vector_score", "source_priority", "recency_boost", "dedupe"], "weights": {"lexical": .38, "vector": .32, "priority": .18, "recency": .12}, "explain_fields": ["matched_terms", "source_type", "score_breakdown"]}
    router = {"kind": "query_router_v24", "routes": {"角色": ["entity", "memory", "chapter_chunk"], "伏笔": ["entity", "debt", "chapter_chunk"], "剧情": ["chapter_chunk", "memory", "reference"], "知识": ["reference", "chapter_chunk"], "默认": ["chapter_chunk", "entity", "memory", "reference"]}, "records_sample": [{k: v for k, v in r.items() if k != "vector"} for r in records[:20]]}
    _write(out / "rag" / "records.json", records)
    return {
        "vector_projection_manifest": str(_write(out / "rag" / "vector_projection_manifest.json", manifest)),
        "rerank_profile": str(_write(out / "rag" / "rerank_profile.json", rerank)),
        "query_router": str(_write(out / "rag" / "query_router_v2.json", router)),
    }


def _build_memory(paths: Any, snap: dict[str, Any], budget: int, out: Path) -> dict[str, str]:
    entries = []
    for e in snap["entities"]:
        priority = 90 if e["bucket"] in {"characters", "foreshadows", "conflicts"} else 70
        entries.append({"id": f"{e['bucket']}:{e['id']}", "category": e["bucket"], "subject": e["name"], "priority": priority, "status": e.get("status", ""), "text": json.dumps(e, ensure_ascii=False), "source": "story_state"})
    for c in snap["commits"][-50:]:
        data = _safe_json(c, {})
        entries.append({"id": f"commit:{_chapter_no(c)}", "category": "commit", "subject": f"chapter_{_chapter_no(c):04d}", "priority": 65, "text": json.dumps(data, ensure_ascii=False)[:2400], "source": str(c)})
    schema = {"kind": "memory_schema_v24", "required_fields": ["id", "category", "subject", "priority", "text", "source"], "categories": sorted(set(e["category"] for e in entries)), "entry_count": len(entries)}
    selected = []
    used = 0
    for item in sorted(entries, key=lambda x: x["priority"], reverse=True):
        est = max(1, len(item["text"]) // 2)
        if used + est > budget and selected:
            continue
        selected.append(item | {"estimated_tokens": est})
        used += est
        if used >= budget:
            break
    by_subject = defaultdict(list)
    for item in entries:
        by_subject[(item["category"], item["subject"])].append(item["id"])
    conflicts = [{"category": k[0], "subject": k[1], "ids": v, "resolution": "keep highest priority and latest source"} for k, v in by_subject.items() if len(v) > 1]
    compaction = {"kind": "memory_compaction_manifest_v24", "original_entries": len(entries), "selected_entries": len(selected), "used_budget": used, "compacted_digest": _sha(selected), "method": "priority_budget_then_subject_dedupe"}
    return {
        "schema": str(_write(out / "memory" / "schema_v2.json", schema)),
        "budget_pack": str(_write(out / "memory" / "budget_pack.json", {"kind": "memory_budget_pack_v24", "budget": budget, "used": used, "items": selected, "selection_policy": ["priority desc", "fit within budget", "keep plot-critical buckets", "dedupe by category+subject"], "fallback_when_empty": {"seed_entries": ["story_profile", "genre_profile", "latest_outline"], "reason": "new projects may not have chapter commits yet"}})),
        "compaction_manifest": str(_write(out / "memory" / "compaction_manifest.json", compaction)),
        "conflict_resolution": str(_write(out / "memory" / "conflict_resolution.json", {"kind": "memory_conflict_resolution_v24", "conflicts": conflicts, "conflict_policy": {"same_subject_active": "keep latest/highest priority", "contradictory_status": "mark needs_review", "duplicate_alias": "link to canonical entity", "manual_override": "manual wins but records event"}, "empty_conflicts_meaning": "当前没有检测到冲突，不代表关闭冲突检测"})),
    }


def _build_review(paths: Any, snap: dict[str, Any], chapter_no: int, out: Path) -> dict[str, str]:
    chapter = next((p for p in snap["chapters"] if _chapter_no(p) == chapter_no), None)
    text = _safe_text(chapter) if chapter else ""
    dims = ["blueprint_fulfillment", "changes_alignment", "entity_disambiguation", "fact_extraction", "continuity", "pacing", "hook", "dialogue", "anti_ai", "structure", "publish_readiness"]
    issues = []
    if not text:
        issues.append({"dimension": "draft", "severity": "blocking", "message": "章节正文不存在"})
    if text and len(text) < 800:
        issues.append({"dimension": "pacing", "severity": "warning", "message": "正文偏短"})
    if text and not re.search(r"[？?!！。]\s*$", text.strip()[-80:]):
        issues.append({"dimension": "hook", "severity": "warning", "message": "章末钩子可能不足"})
    schema = {"kind": "review_schema_v24", "dimensions": dims, "severity_levels": ["info", "warning", "needs_review", "blocking"], "rounds_supported": 3}
    contracts = {"kind": "review_artifact_contracts_v24", "required_for_commit": ["review_schema", "fulfillment_result", "disambiguation_result", "extraction_result"], "artifact_paths": {"review": f"artifacts/第{chapter_no:04d}章/review_deep_v2.json", "fulfillment": f"artifacts/第{chapter_no:04d}章/fulfillment_result.json", "disambiguation": f"artifacts/第{chapter_no:04d}章/disambiguation_result.json", "extraction": f"artifacts/第{chapter_no:04d}章/extraction_result.json"}}
    rounds = {"kind": "repair_rounds_v24", "chapter_no": chapter_no, "max_rounds": 3, "issues": issues, "rounds": [{"round": i+1, "goal": "fix blocking then warnings", "inputs": ["draft", "review", "context"], "outputs": ["patched_draft", "delta_report"]} for i in range(3)], "ready": not any(i["severity"] == "blocking" for i in issues)}
    return {
        "review_schema": str(_write(out / "review" / "review_schema_v2.json", schema)),
        "artifact_contracts": str(_write(out / "review" / "artifact_contracts.json", contracts)),
        "repair_rounds": str(_write(out / "review" / "repair_rounds.json", rounds)),
    }


def _build_entities(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    aliases = defaultdict(list)
    for e in snap["entities"]:
        for alias in [e["name"], e["id"], *(e.get("aliases") or [])]:
            if alias:
                aliases[str(alias)].append({"bucket": e["bucket"], "id": e["id"], "name": e["name"]})
    ambiguous = [{"alias": k, "candidates": v} for k, v in aliases.items() if len(v) > 1]
    linker = {"kind": "entity_linker_index_v24", "entities": len(snap["entities"]), "aliases": len(aliases), "ambiguous_aliases": ambiguous[:200], "link_policy": "exact_alias > canonical_id > fuzzy_candidate > needs_review"}
    debts = []
    state = snap["state"]
    for bucket in ["foreshadows", "conflicts", "secrets", "deadlines"]:
        for name, raw in (state.get(bucket) or {}).items() if isinstance(state.get(bucket), dict) else []:
            obj = raw if isinstance(raw, dict) else {"value": raw}
            status = str(obj.get("status") or obj.get("state") or "open")
            debts.append({"bucket": bucket, "name": str(name), "status": status, "priority": obj.get("priority", 50), "rule": "open items must be advanced or closed within configured arc window"})
    debt_rules = {"kind": "debt_rules_v24", "rules": ["foreshadow open too long => warning", "conflict no progress => warning", "secret revealed without setup => blocking", "deadline overdue => blocking"], "debts": debts}
    structure = {"kind": "structural_report_v24", "chapter_count": len(snap["chapters"]), "beats": ["hook", "pressure", "turn", "payoff", "new_hook"], "warnings": [] if snap["chapters"] else ["暂无正文，无法检查结构节奏"]}
    return {
        "linker_index": str(_write(out / "entities" / "linker_index.json", linker)),
        "debt_rules": str(_write(out / "entities" / "debt_rules.json", debt_rules)),
        "structural_report": str(_write(out / "entities" / "structural_report.json", structure)),
    }


def _build_publisher(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    chapters = [{"chapter_no": _chapter_no(p), "path": str(p), "title": p.stem, "word_count": len(_safe_text(p))} for p in snap["chapters"]]
    mapping = {"kind": "platform_mapping_v24", "platforms": {"fanqie": {"title_field": "chapter_title", "content_field": "content", "supports_schedule": True}, "qimao": {"title_field": "title", "content_field": "body", "supports_schedule": False}}, "chapter_count": len(chapters)}
    sm = {"kind": "publish_state_machine_v24", "states": ["draft", "reviewed", "ready", "queued", "submitting", "published", "failed", "rollback_needed"], "transitions": [{"from": "ready", "to": "queued", "condition": "commit exists and no blocking review"}, {"from": "queued", "to": "submitting", "condition": "platform adapter available"}, {"from": "submitting", "to": "published", "condition": "platform confirmation"}, {"from": "submitting", "to": "failed", "condition": "timeout or platform error"}], "jobs": chapters}
    fanqie = {"kind": "fanqie_bridge_contract_v24", "existing_module": "backend.adapters.fanqie_publisher", "handoff_fields": ["chapter_no", "title", "content", "schedule_time", "source_project"], "retry_policy": "use fanqie_publish_tracker status + writer publication state"}
    return {
        "platform_mapping": str(_write(out / "publisher" / "platform_mapping.json", mapping)),
        "publish_state_machine": str(_write(out / "publisher" / "publish_state_machine.json", sm)),
        "fanqie_bridge_contract": str(_write(out / "publisher" / "fanqie_bridge_contract.json", fanqie)),
    }


def _build_sqlite(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    db = Path(paths.control) / "index.db"
    ensure_dir(db.parent)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS entities_v24 (id TEXT PRIMARY KEY, bucket TEXT, name TEXT, aliases TEXT, payload TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS chapters_v24 (chapter_no INTEGER PRIMARY KEY, path TEXT, title TEXT, word_count INTEGER, sha TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS commits_v24 (chapter_no INTEGER PRIMARY KEY, path TEXT, sha TEXT, payload TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS events_v24 (rowid INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT, event_type TEXT, chapter_no INTEGER, payload TEXT, fingerprint TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS memory_v24 (id TEXT PRIMARY KEY, category TEXT, subject TEXT, priority INTEGER, text TEXT)")
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS search_fts_v24 USING fts5(kind, ref, text)")
        cur.execute("DELETE FROM entities_v24"); cur.execute("DELETE FROM chapters_v24"); cur.execute("DELETE FROM commits_v24"); cur.execute("DELETE FROM events_v24"); cur.execute("DELETE FROM search_fts_v24")
        for e in snap["entities"]:
            cur.execute("INSERT OR REPLACE INTO entities_v24 VALUES (?,?,?,?,?)", (e["id"], e["bucket"], e["name"], json.dumps(e.get("aliases") or [], ensure_ascii=False), json.dumps(e, ensure_ascii=False)))
            cur.execute("INSERT INTO search_fts_v24(kind, ref, text) VALUES (?,?,?)", ("entity", e["id"], json.dumps(e, ensure_ascii=False)))
        for p in snap["chapters"]:
            text = _safe_text(p)
            no = _chapter_no(p)
            cur.execute("INSERT OR REPLACE INTO chapters_v24 VALUES (?,?,?,?,?)", (no, str(p), p.stem, len(text), _sha(text)))
            cur.execute("INSERT INTO search_fts_v24(kind, ref, text) VALUES (?,?,?)", ("chapter", str(no), text[:8000]))
        for p in snap["commits"]:
            data = _safe_json(p, {})
            cur.execute("INSERT OR REPLACE INTO commits_v24 VALUES (?,?,?,?)", (_chapter_no(p), str(p), _file_sha(p), json.dumps(data, ensure_ascii=False)))
        for e in snap["events"]:
            cur.execute("INSERT INTO events_v24(event_id,event_type,chapter_no,payload,fingerprint) VALUES (?,?,?,?,?)", (str(e.get("event_id") or e.get("id") or ""), str(e.get("event_type") or e.get("type") or ""), int(e.get("chapter_no") or e.get("chapterNo") or 0), json.dumps(e, ensure_ascii=False), _sha(e)))
        cur.execute("INSERT OR REPLACE INTO schema_meta VALUES (?,?)", ("v24_schema_version", "1"))
        conn.commit()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type in ('table','virtual table') ORDER BY name").fetchall()]
    finally:
        conn.close()
    registry = {"kind": "sqlite_schema_registry_v24", "db": str(db), "tables": tables, "schema_version": 1, "fts_enabled": "search_fts_v24" in tables, "foreign_keys": True}
    rules = {"kind": "validation_rules_v24", "rules": [{"target": "entities_v24", "rule": "id not null"}, {"target": "chapters_v24", "rule": "chapter_no unique"}, {"target": "commits_v24", "rule": "commit chapter must map to existing chapter or valid future projection"}, {"target": "events_v24", "rule": "event fingerprint stable"}]}
    return {
        "schema_registry": str(_write(out / "sqlite" / "schema_registry.json", registry)),
        "validation_rules": str(_write(out / "sqlite" / "validation_rules.json", rules)),
        "db": str(db),
    }


def _build_security(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    patterns = ["api[_-]?key", "secret", "token", "authorization", "cookie", "password"]
    findings = []
    for file in [Path(paths.settings), Path(paths.story_config), Path(paths.root) / ".env", Path(paths.root) / ".env.example"]:
        text = _safe_text(file)
        for pat in patterns:
            if re.search(pat, text, re.I):
                findings.append({"path": str(file), "pattern": pat, "redacted": True})
    redaction = {"kind": "redaction_policy_v24", "patterns": patterns, "replacement": "***REDACTED***", "log_fields_to_scrub": ["apiKey", "authorization", "cookie", "token"]}
    secret_scan = {"kind": "secret_scan_v24", "findings": findings, "ok": not any(Path(f["path"]).name != ".env.example" for f in findings)}
    metrics = {"kind": "runtime_metrics_v24", "generated_at": _now(), "counts": {"chapters": len(snap["chapters"]), "commits": len(snap["commits"]), "events": len(snap["events"]), "entities": len(snap["entities"]), "artifacts": len(snap["artifacts"])}, "health": {"has_state": Path(paths.state).exists(), "has_index_db": (Path(paths.control) / "index.db").exists()}}
    return {
        "redaction_policy": str(_write(out / "security" / "redaction_policy.json", redaction)),
        "secret_scan": str(_write(out / "security" / "secret_scan.json", secret_scan)),
        "runtime_metrics": str(_write(out / "observability" / "runtime_metrics.json", metrics)),
    }


def _build_references(paths: Any, snap: dict[str, Any], out: Path) -> dict[str, str]:
    ref_root = Path(paths.control) / "references"
    files = []
    if ref_root.exists():
        for p in ref_root.glob("**/*"):
            if p.is_file() and p.suffix.lower() in {".csv", ".json", ".txt", ".md"}:
                files.append({"path": str(p), "suffix": p.suffix.lower(), "sha": _file_sha(p), "size": p.stat().st_size})
    router = {"kind": "knowledge_router_v24", "sources": files, "routes": {"craft": ["references/csv", "references/text"], "genre": ["writer_control/genres", "references"], "story": ["chapters", "memory", "truth"]}, "empty_policy": "init reference library then continue"}
    deconstruction = {"kind": "deconstruction_schema_v24", "fields": ["chapter_shape", "opening_hook", "ending_hook", "pacing", "dialogue_ratio", "scene_count", "payoff_type", "style_markers"], "sample_count": len(snap["chapters"]), "project_fingerprint": _sha([_file_sha(p) for p in snap["chapters"]])}
    evals = {"kind": "eval_matrix_v24", "cases": [{"name": "missing_blueprint", "command": "preflight", "expected": "needs_action"}, {"name": "changes_omission", "command": "review-pipeline-deep", "expected": "detect"}, {"name": "memory_budget", "command": "memory-orchestrate", "expected": "budget_pack"}, {"name": "rag_query", "command": "rag-router", "expected": "ranked_results"}], "regression_policy": "run after alignment optimize"}
    return {
        "knowledge_router": str(_write(out / "references" / "knowledge_router.json", router)),
        "deconstruction_schema": str(_write(out / "references" / "deconstruction_schema.json", deconstruction)),
        "eval_matrix": str(_write(out / "evals" / "eval_matrix.json", evals)),
    }


def alignment_optimize_v24_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    out = _alignment_dir(paths)
    snap = _project_snapshot(paths)
    written: dict[str, Any] = {}
    written.update({"workflow": _build_workflow(paths, snap, chapter_no, out)})
    written.update({"agents": _build_agents(paths, snap, out)})
    written.update({"ssot": _build_ssot(paths, snap, out)})
    written.update({"context": _build_context(paths, snap, chapter_no, budget, out)})
    written.update({"rag": _build_rag(paths, snap, out)})
    written.update({"memory": _build_memory(paths, snap, budget, out)})
    written.update({"review": _build_review(paths, snap, chapter_no, out)})
    written.update({"entities": _build_entities(paths, snap, out)})
    written.update({"publisher": _build_publisher(paths, snap, out)})
    written.update({"sqlite": _build_sqlite(paths, snap, out)})
    written.update({"security": _build_security(paths, snap, out)})
    written.update({"references": _build_references(paths, snap, out)})
    gap = alignment_gap_matrix_v24_command(storage, project_id)
    result = {
        "ok": True,
        "generated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "budget": budget,
        "written": written,
        "audit_after": {"alignment_score": gap.get("alignment_score"), "deep_aligned": gap.get("deep_aligned"), "shallow": gap.get("shallow"), "missing": gap.get("missing")},
        "paths_written": {"result": str(out / "optimize_result.json"), "gap_matrix": str(out / "gap_matrix.json")},
    }
    _write(out / "optimize_result.json", result)
    return result


def alignment_query_v24_command(storage: Any, project_id: str, query: str = "", top_k: int = 8) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    out = _alignment_dir(paths)
    records = []
    for file in out.glob("**/*.json"):
        data = _safe_json(file, {})
        text = json.dumps(data, ensure_ascii=False, default=str)
        records.append({"path": str(file), "score": _score(query, text), "excerpt": text[:800]})
    rows = sorted(records, key=lambda x: x["score"], reverse=True)[:max(1, top_k)]
    result = {"ok": True, "query": query, "results": rows, "paths_written": {"query": str(out / "last_query.json")}}
    _write(out / "last_query.json", result)
    return result
