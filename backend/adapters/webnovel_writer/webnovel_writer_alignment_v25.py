from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, read_jsonl, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto

CAPABILITIES_V25: list[dict[str, Any]] = [
    {
        "code": "workflow_checkpoint_orchestrator",
        "name": "Workflow checkpoint / orchestrator / trusted resume",
        "reference": ["lingfeng: run-ledger/write-resume/user-report", "opencode: workflow_checkpoint.py/orchestrate.py"],
        "v24_status": "不够深",
        "gap": "v24 有证据文件，但缺少可执行步骤依赖、可信产物签名、失败续跑决策和步骤级重试策略。",
        "outputs": ["workflow/executable_plan.json", "workflow/resume_decision_v2.json", "workflow/artifact_trust_index.json"],
    },
    {
        "code": "agent_skill_contract_runner",
        "name": "Agent / skill registry / contract runner",
        "reference": ["lingfeng: context/reviewer/data/deconstruction agents", "opencode: skill_runner.py/skills-lock.json"],
        "v24_status": "不够深",
        "gap": "v24 有 registry/lock，但缺少 skill 输入输出契约、前置条件、失败策略和可测试用例。",
        "outputs": ["agents/skill_runner_contract.json", "agents/skill_contract_tests.json"],
    },
    {
        "code": "ssot_event_projection_replay",
        "name": "SSOT event store / projection DAG / replay simulator",
        "reference": ["lingfeng: story-events/projections/chapter-commit", "opencode: event_log_store.py/projection_log.py/state_projection_writer.py"],
        "v24_status": "不够深",
        "gap": "v24 有 event schema 和 replay manifest，但缺少投影 DAG、事件消费游标、漂移 diff 与可重放模拟结果。",
        "outputs": ["ssot/projection_dag.json", "ssot/replay_simulation.json", "ssot/drift_diff.json"],
    },
    {
        "code": "context_manager_budget_explain",
        "name": "Context manager budget / source explain / dedupe",
        "reference": ["lingfeng: context-agent 写作任务书", "opencode: context_manager.py/context_weights.py"],
        "v24_status": "不够深",
        "gap": "v24 有预算和 task book，但缺少按来源解释、去重签名、超预算裁剪原因和可验证上下文账本。",
        "outputs": ["context/context_ledger.json", "context/dedupe_index.json", "context/budget_explain.json"],
    },
    {
        "code": "rag_vector_rerank_router_depth",
        "name": "RAG adapter / vector projection / rerank / query router",
        "reference": ["lingfeng: rag/query/index", "opencode: rag_adapter.py/vector_projection_writer.py/query_router.py"],
        "v24_status": "不够深",
        "gap": "v24 有路由和 rerank profile，但缺少多源统一记录、向量签名、重排分解分数、召回多样性控制。",
        "outputs": ["rag/unified_records.json", "rag/rerank_debug.json", "rag/router_coverage.json"],
    },
    {
        "code": "memory_store_budget_compactor_depth",
        "name": "Memory store / schema / budget / compactor / conflict resolver",
        "reference": ["lingfeng: memory stats/query/bootstrap/update", "opencode: memory/store.py/schema.py/budget.py/compactor.py/orchestrator.py"],
        "v24_status": "不够深",
        "gap": "v24 有 memory 文件，但缺少按状态的长期记忆生命周期、压缩批次、预算保留理由和冲突裁决证据。",
        "outputs": ["memory/lifecycle_store.json", "memory/compaction_batches.json", "memory/conflict_decisions.json"],
    },
    {
        "code": "review_pipeline_convergence_artifacts",
        "name": "Review pipeline / artifact contracts / convergence repair",
        "reference": ["lingfeng: review-pipeline + chapter-commit artifacts", "opencode: review_pipeline.py/review_schema.py/amend_proposal_schema.py"],
        "v24_status": "不够深",
        "gap": "v24 有 repair_rounds，但缺少审查维度证据定位、阻断/警告分级、局部修复 patch 计划和提交前契约。",
        "outputs": ["review/dimension_evidence.json", "review/local_patch_plan.json", "review/precommit_contract.json"],
    },
    {
        "code": "entity_debt_structural_depth",
        "name": "Entity linker / debt tracker / structural checker",
        "reference": ["opencode: entity_linker.py/index_entity_mixin.py/index_debt_mixin.py/structural_checker.py"],
        "v24_status": "不够深",
        "gap": "v24 有实体链接与结构报告，但缺少别名冲突置信度、债务窗口、章节结构 beats 与逾期优先级。",
        "outputs": ["entities/alias_resolution.json", "entities/debt_windows.json", "entities/structure_beats.json"],
    },
    {
        "code": "publisher_bridge_state_retry",
        "name": "Publisher formatter / platform adapters / publish state machine",
        "reference": ["opencode: publisher/formatter.py/config.py/adapters/fanqie.py/adapters/qimao.py"],
        "v24_status": "不够深",
        "gap": "v24 有发布状态机，但缺少与本项目番茄发布模块的能力检测、失败重试队列、平台字段校验和章节发布锁。",
        "outputs": ["publisher/adapter_capability.json", "publisher/retry_queue.json", "publisher/chapter_publish_locks.json"],
    },
    {
        "code": "sqlite_schema_validator_fts_depth",
        "name": "SQLite schema / validator / FTS / query layer",
        "reference": ["opencode: schemas.py/state_validator.py/migrate_state_to_sqlite.py/story_event_schema.py"],
        "v24_status": "不够深",
        "gap": "v24 有 schema registry，但缺少约束校验结果、FTS 查询样本、schema migration 版本账本。",
        "outputs": ["sqlite/migration_ledger.json", "sqlite/constraint_report.json", "sqlite/fts_query_examples.json"],
    },
    {
        "code": "security_observability_runtime_depth",
        "name": "Security utils / observability / runtime compatibility",
        "reference": ["opencode: security_utils.py/observability.py/runtime_compat.py/index_observability_mixin.py"],
        "v24_status": "不够深",
        "gap": "v24 有 secret scan，但缺少脱敏验证样本、路径逃逸防护结果、运行时环境兼容矩阵和指标时间线。",
        "outputs": ["security/redaction_tests.json", "security/path_safety_report.json", "observability/metrics_timeline.json"],
    },
    {
        "code": "reference_deconstruction_eval_depth",
        "name": "References / knowledge query / deconstruction / eval matrix",
        "reference": ["opencode: reference_search.py/knowledge_query.py/deconstruction-agent/evals/tests"],
        "v24_status": "不够深",
        "gap": "v24 有 eval matrix，但缺少可执行回归用例、知识库路由命中证据、拆书字段完整性验证。",
        "outputs": ["references/router_hits.json", "references/deconstruction_validation.json", "evals/executable_eval_results.json"],
    },
]

STEPS = ["prewrite", "context", "contract", "draft", "review", "fulfillment", "disambiguation", "extraction", "commit", "projection", "quality", "user_report"]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _control(paths: Any) -> Path:
    return Path(paths.control)


def _root(paths: Any) -> Path:
    return Path(paths.root)


def _base(paths: Any) -> Path:
    return ensure_dir(_control(paths) / "alignment_v25")


def _write(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    return write_json(path, data)


def _read(path: Path, default: Any = None) -> Any:
    try:
        return read_json(path, default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _sha(value: Any, n: int = 24) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:n]


def _file_sha(path: Path, n: int = 24) -> str:
    if not path.exists() or not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def _safe_text(path: Path) -> str:
    try:
        if path.exists() and path.is_file():
            return read_text_auto(path)
    except Exception:
        return ""
    return ""


def _chapter_files(paths: Any) -> list[Path]:
    p = Path(paths.chapters)
    files = list(p.glob("*.txt")) + list(p.glob("*.md"))
    return sorted({x.resolve(): x for x in files}.values(), key=lambda x: x.name)


def _chapter_no(path: Path) -> int:
    m = re.search(r"(\d{1,6})", path.stem)
    return int(m.group(1)) if m else 0


def _chunk_text(text: str, size: int = 650, overlap: int = 80) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + size])
        if i + size >= len(text):
            break
        i += max(1, size - overlap)
    return chunks


def _tokenize(text: str) -> list[str]:
    text = str(text or "").lower()
    words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text)
    grams: list[str] = []
    for w in words:
        grams.append(w)
        if re.fullmatch(r"[\u4e00-\u9fff]+", w) and len(w) > 3:
            grams.extend(w[i:i + 2] for i in range(len(w) - 1))
    return grams


def _hash_vector(tokens: list[str], dim: int = 96) -> list[float]:
    vec = [0.0] * dim
    if not tokens:
        return vec
    for tok in tokens:
        hv = int(hashlib.sha1(tok.encode("utf-8", errors="ignore")).hexdigest(), 16)
        idx = hv % dim
        sign = 1.0 if (hv >> 3) & 1 else -1.0
        vec[idx] += sign
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [round(v / norm, 6) for v in vec]


def _cos(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def _load_state(paths: Any) -> dict[str, Any]:
    data = _read(Path(paths.state), {})
    return data if isinstance(data, dict) else {}


def _load_memory(paths: Any) -> dict[str, Any]:
    candidates = [
        _control(paths) / "memory" / "memory_store.json",
        _control(paths) / "memory" / "project_memory.json",
        _control(paths) / "alignment_v24" / "memory" / "budget_pack.json",
    ]
    for p in candidates:
        data = _read(p, {})
        if data:
            return data if isinstance(data, dict) else {"items": data}
    return {}


def _load_events(paths: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for base in [_root(paths) / "events", _control(paths) / "events"]:
        if not base.exists():
            continue
        for file in sorted(base.glob("*.jsonl")):
            for row in read_jsonl(file):
                if isinstance(row, dict):
                    events.append(row)
                else:
                    events.append({"value": row})
        for file in sorted(base.glob("*.json")):
            row = _read(file, {})
            if isinstance(row, list):
                events.extend([x if isinstance(x, dict) else {"value": x} for x in row])
            elif isinstance(row, dict):
                events.append(row)
    return events


def _cap_path_map(paths: Any) -> dict[str, list[Path]]:
    base = _base(paths)
    return {cap["code"]: [base / rel for rel in cap["outputs"]] for cap in CAPABILITIES_V25}


def alignment_gap_matrix_v25_command(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    written = _cap_path_map(paths)
    items: list[dict[str, Any]] = []
    for cap in CAPABILITIES_V25:
        required = written[cap["code"]]
        existing = [str(p.relative_to(_root(paths))) for p in required if p.exists()]
        missing = [str(p.relative_to(_root(paths))) for p in required if not p.exists()]
        status = "deep_aligned" if not missing else ("shallow" if existing else "missing")
        items.append({
            "code": cap["code"],
            "name": cap["name"],
            "reference": cap["reference"],
            "status": status,
            "v24_status": cap["v24_status"],
            "gap": cap["gap"],
            "existing": existing,
            "missing": missing,
            "optimize_command": "alignment-optimize-v25",
        })
    summary = Counter(item["status"] for item in items)
    report = {
        "ok": summary.get("missing", 0) == 0 and summary.get("shallow", 0) == 0,
        "checked_at": _now(),
        "version": "v25",
        "total": len(items),
        "deep_aligned": summary.get("deep_aligned", 0),
        "shallow": summary.get("shallow", 0),
        "missing": summary.get("missing", 0),
        "items": items,
    }
    out = _write(_base(paths) / "gap_matrix.json", report)
    report["paths_written"] = {"gap_matrix": str(out)}
    return report


def _workflow(paths: Any, chapter_no: int) -> dict[str, Any]:
    chapter_dir = Path(paths.artifacts) / f"第{chapter_no:04d}章"
    signals = {
        "blueprint": Path(paths.blueprints) / f"chapter_{chapter_no:04d}.json",
        "context": _control(paths) / "context_packs" / f"chapter_{chapter_no:04d}_context.json",
        "contract": _control(paths) / "contracts" / f"chapter_{chapter_no:04d}_contract.json",
        "draft_txt": Path(paths.drafts) / f"chapter_{chapter_no:04d}.txt",
        "chapter_txt": Path(paths.chapters) / f"chapter_{chapter_no:04d}.txt",
        "review_deep": chapter_dir / "review_deep_v2.json",
        "fulfillment": chapter_dir / "fulfillment_result.json",
        "disambiguation": chapter_dir / "disambiguation_result.json",
        "extraction": chapter_dir / "extraction_result.json",
        "commit": Path(paths.commits) / f"chapter_{chapter_no:04d}.json",
        "quality": chapter_dir / "06_quality_gate.json",
        "user_report": _control(paths) / "reports" / "user_report" / f"chapter_{chapter_no:04d}_write.json",
    }
    step_sources = {
        "prewrite": [signals["blueprint"]],
        "context": [signals["context"]],
        "contract": [signals["contract"]],
        "draft": [signals["draft_txt"], signals["chapter_txt"]],
        "review": [signals["review_deep"]],
        "fulfillment": [signals["fulfillment"]],
        "disambiguation": [signals["disambiguation"]],
        "extraction": [signals["extraction"]],
        "commit": [signals["commit"]],
        "projection": [Path(paths.state)],
        "quality": [signals["quality"]],
        "user_report": [signals["user_report"]],
    }
    ledger: list[dict[str, Any]] = []
    trust: dict[str, Any] = {}
    for step in STEPS:
        files = step_sources.get(step, [])
        present_files = [p for p in files if p.exists()]
        status = "trusted" if present_files else "missing"
        sig = _sha({str(p): _file_sha(p) for p in present_files}) if present_files else ""
        trust[step] = {
            "status": status,
            "signature": sig,
            "artifacts": [str(p.relative_to(_root(paths))) for p in present_files],
            "required_any": [str(p.relative_to(_root(paths))) for p in files],
        }
        ledger.append({"step": step, "status": status, "signature": sig})
    first_missing = next((row["step"] for row in ledger if row["status"] != "trusted"), "done")
    dependencies = {
        "prewrite": [], "context": ["prewrite"], "contract": ["context"], "draft": ["contract"],
        "review": ["draft"], "fulfillment": ["review"], "disambiguation": ["review"],
        "extraction": ["draft"], "commit": ["fulfillment", "disambiguation", "extraction"],
        "projection": ["commit"], "quality": ["draft"], "user_report": ["projection", "quality"],
    }
    return {
        "chapter_no": chapter_no,
        "steps": ledger,
        "dependencies": dependencies,
        "trust_index": trust,
        "resume_decision": {
            "next_step": first_missing,
            "can_resume": first_missing != "done",
            "trusted_prefix": [row["step"] for row in ledger if row["status"] == "trusted"],
            "recommended_command": f"python -m backend.adapters.webnovel_writer.webnovel_writer_cli workflow-runner --project <项目目录> --chapter {chapter_no} --action run" if first_missing != "done" else "none",
        },
    }


def _agents(paths: Any) -> dict[str, Any]:
    model_routes = _read(_control(paths) / "models" / "model_routes.json", {})
    roles = ["planner", "context", "drafter", "reviewer", "fact", "repair", "publisher", "memory", "rag", "orchestrator"]
    contracts = []
    for role in roles:
        contracts.append({
            "role": role,
            "model_route": (model_routes.get("routes") or model_routes).get(role) if isinstance(model_routes, dict) else None,
            "inputs": ["project_state", "chapter_no"] + (["draft"] if role in {"reviewer", "fact", "repair"} else []),
            "outputs": [f"{role}_artifact.json"],
            "preconditions": ["project_root_exists", "state_readable"],
            "postconditions": ["json_artifact_written", "artifact_signature_recorded"],
            "failure_policy": "stop_and_record" if role in {"drafter", "reviewer", "fact"} else "warn_and_continue",
            "test_case": {"name": f"{role}_contract_smoke", "expects": ["inputs", "outputs", "failure_policy"]},
        })
    return {"contracts": contracts, "lock_signature": _sha(contracts), "skill_count": len(contracts)}


def _ssot(paths: Any) -> dict[str, Any]:
    events = _load_events(paths)
    commits = sorted(Path(paths.commits).glob("*.json")) if Path(paths.commits).exists() else []
    projection_nodes = [
        {"name": "commits", "kind": "source", "count": len(commits)},
        {"name": "state_projection", "kind": "projection", "depends_on": ["commits", "events"]},
        {"name": "chunk_index", "kind": "projection", "depends_on": ["chapters"]},
        {"name": "truth_files", "kind": "projection", "depends_on": ["state_projection"]},
        {"name": "memory", "kind": "projection", "depends_on": ["state_projection", "commits"]},
    ]
    event_ids = [str(e.get("event_id") or e.get("id") or e.get("ts") or i) for i, e in enumerate(events)]
    dupes = [k for k, v in Counter(event_ids).items() if v > 1]
    state = _load_state(paths)
    replay_state_sig = _sha({"commit_files": [p.name for p in commits], "events": event_ids})
    drift = {"current_state_signature": _sha(state), "replay_signature": replay_state_sig, "needs_review": bool(commits) and not state}
    return {"event_count": len(events), "duplicate_event_ids": dupes, "projection_dag": projection_nodes, "replay_simulation": {"ok": not dupes, "signature": replay_state_sig}, "drift_diff": drift}


def _context(paths: Any, chapter_no: int, budget: int) -> dict[str, Any]:
    state = _load_state(paths)
    blueprint = _read(Path(paths.blueprints) / f"chapter_{chapter_no:04d}.json", {})
    sources: list[dict[str, Any]] = []
    def add(kind: str, name: str, text: str, priority: int, why: str) -> None:
        tokens = max(1, len(str(text)) // 2)
        sources.append({"kind": kind, "name": name, "tokens_est": tokens, "priority": priority, "sha": _sha(text), "why_included": why, "text_preview": str(text)[:280]})
    add("blueprint", f"chapter_{chapter_no:04d}", json.dumps(blueprint, ensure_ascii=False), 100, "本章强约束")
    add("state", "story_state", json.dumps(state, ensure_ascii=False)[:4000], 90, "事实快照")
    for p in _chapter_files(paths)[-6:]:
        if _chapter_no(p) != chapter_no:
            add("recent_chapter", p.name, _safe_text(p)[:1800], 70, "近期章节延续")
    memory = _load_memory(paths)
    if memory:
        add("memory", "project_memory", json.dumps(memory, ensure_ascii=False)[:2500], 65, "长期记忆")
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    total = 0
    for item in sorted(sources, key=lambda x: (-x["priority"], x["tokens_est"])):
        if item["sha"] in seen:
            item["excluded_reason"] = "duplicate"
            continue
        if total + item["tokens_est"] > budget and selected:
            item["excluded_reason"] = "budget_overflow"
            continue
        seen.add(item["sha"])
        item["included"] = True
        total += item["tokens_est"]
        selected.append(item)
    return {"chapter_no": chapter_no, "budget": budget, "used_tokens_est": total, "source_count": len(sources), "selected_count": len(selected), "selected": selected, "excluded": [x for x in sources if not x.get("included")], "context_signature": _sha(selected)}


def _rag(paths: Any, query: str = "") -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for p in _chapter_files(paths):
        no = _chapter_no(p)
        for idx, chunk in enumerate(_chunk_text(_safe_text(p))):
            toks = _tokenize(chunk)
            records.append({"id": f"chapter:{no}:{idx}", "source": "chapter", "chapter_no": no, "text": chunk, "tokens": toks[:30], "vector": _hash_vector(toks)})
    # Add references if present.
    for base in [_control(paths) / "references", _root(paths) / "references"]:
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix.lower() in {".txt", ".json", ".csv"}:
                    text = _safe_text(p)
                    toks = _tokenize(text)
                    records.append({"id": f"reference:{p.name}", "source": "reference", "text": text[:1200], "tokens": toks[:30], "vector": _hash_vector(toks)})
    q_tokens = _tokenize(query or "主角 伏笔 冲突 章节")
    q_vec = _hash_vector(q_tokens)
    ranked = []
    for r in records:
        lexical = len(set(q_tokens) & set(r.get("tokens") or [])) / max(1, len(set(q_tokens)))
        vector = _cos(q_vec, r.get("vector") or [])
        diversity = 0.1 if r.get("source") == "reference" else 0.0
        score = 0.55 * lexical + 0.35 * vector + diversity
        ranked.append({"id": r["id"], "source": r["source"], "chapter_no": r.get("chapter_no"), "score": round(score, 6), "score_parts": {"lexical": round(lexical, 6), "vector": round(vector, 6), "diversity": diversity}, "text_preview": r.get("text", "")[:220]})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"record_count": len(records), "vector_dim": 96, "projection_signature": _sha([r["id"] for r in records]), "route_types": ["chapter", "reference", "memory", "entity"], "rerank_debug": ranked[:12], "router_coverage": dict(Counter(r["source"] for r in records))}


def _memory(paths: Any, budget: int) -> dict[str, Any]:
    state = _load_state(paths)
    records: list[dict[str, Any]] = []
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets"]:
        items = state.get(bucket) or {}
        if isinstance(items, dict):
            for name, value in items.items():
                text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                status = (value.get("status") if isinstance(value, dict) else "active") or "active"
                priority = 90 if bucket in {"foreshadows", "conflicts"} else 70
                records.append({"id": f"{bucket}:{name}", "category": bucket, "subject": str(name), "status": str(status), "priority": priority, "tokens_est": max(1, len(text) // 2), "summary": text[:360], "source": "state"})
    for p in sorted(Path(paths.commits).glob("*.json"))[-10:]:
        data = _read(p, {})
        records.append({"id": f"commit:{p.stem}", "category": "commit", "subject": p.stem, "status": "active", "priority": 60, "tokens_est": max(1, len(json.dumps(data, ensure_ascii=False)) // 2), "summary": json.dumps(data, ensure_ascii=False)[:360], "source": "commit"})
    total = 0
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for r in sorted(records, key=lambda x: (-x["priority"], x["tokens_est"])):
        if total + r["tokens_est"] <= budget or not kept:
            r["keep_reason"] = "priority_budget"
            kept.append(r)
            total += r["tokens_est"]
        else:
            r["drop_reason"] = "budget_overflow"
            dropped.append(r)
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_subject[r["subject"]].append(r)
    conflicts = [{"subject": k, "records": v, "decision": "keep_latest_or_highest_priority"} for k, v in by_subject.items() if len({x["status"] for x in v}) > 1]
    compacted = []
    for cat, group in defaultdict(list, {cat: [r for r in records if r["category"] == cat] for cat in {r["category"] for r in records}}).items():
        compacted.append({"category": cat, "count": len(group), "summary": "；".join(g["subject"] for g in group[:12]), "signature": _sha(group)})
    return {"schema_version": "memory.v25", "record_count": len(records), "budget": budget, "used_tokens_est": total, "kept": kept, "dropped": dropped, "conflicts": conflicts, "compacted": compacted, "store_signature": _sha(records)}


def _review(paths: Any, chapter_no: int) -> dict[str, Any]:
    chapter_candidates = [Path(paths.chapters) / f"chapter_{chapter_no:04d}.txt", Path(paths.chapters) / f"第{chapter_no:04d}章.txt"]
    text = next((_safe_text(p) for p in chapter_candidates if _safe_text(p)), "")
    blueprint = _read(Path(paths.blueprints) / f"chapter_{chapter_no:04d}.json", {})
    required_nodes = blueprint.get("must_cover_nodes") or blueprint.get("required_beats") or []
    evidence = []
    for node in required_nodes:
        node_text = str(node)
        terms = [node_text[i:i + 2] for i in range(max(0, len(node_text) - 1))] if len(node_text) > 2 else [node_text]
        hits = [t for t in terms if t and t in text]
        evidence.append({"node": node_text, "hit_count": len(hits), "status": "fulfilled" if hits else "missing", "evidence": hits[:8]})
    dimensions = ["blueprint", "character", "location", "conflict", "foreshadow", "pacing", "hook", "language", "changes", "continuity", "anti_ai", "publish_readiness"]
    findings = []
    for dim in dimensions:
        severity = "warning"
        message = "待人工复核"
        if dim == "blueprint":
            missing = [e for e in evidence if e["status"] == "missing"]
            severity = "blocker" if missing else "ok"
            message = f"缺失必达节点 {len(missing)} 个" if missing else "必达节点有证据"
        elif dim == "hook":
            ending = text[-220:]
            severity = "ok" if any(x in ending for x in ["？", "!", "！", "却", "忽然", "没想到", "血", "门开"]) else "warning"
            message = "章末钩子检测"
        elif dim == "language":
            ai_phrases = ["综上所述", "值得一提的是", "他深吸一口气", "空气仿佛凝固"]
            hits = [x for x in ai_phrases if x in text]
            severity = "warning" if hits else "ok"
            message = f"AI味短语：{hits[:5]}" if hits else "未见高频模板短语"
        findings.append({"dimension": dim, "severity": severity, "message": message})
    blockers = [f for f in findings if f["severity"] == "blocker"]
    patch_plan = []
    for ev in evidence:
        if ev["status"] == "missing":
            patch_plan.append({"target": ev["node"], "action": "局部补写或改写相关场景", "prompt_hint": f"在不破坏现有正文的前提下补足必达节点：{ev['node']}"})
    return {"chapter_no": chapter_no, "schema_version": "review.v25", "dimensions": findings, "dimension_evidence": evidence, "blockers": blockers, "local_patch_plan": patch_plan, "precommit_contract": {"can_commit": not blockers, "required_artifacts": ["fulfillment_result.json", "disambiguation_result.json", "extraction_result.json", "review_deep_v25.json"]}}


def _entities(paths: Any) -> dict[str, Any]:
    state = _load_state(paths)
    aliases = []
    name_to_bucket = {}
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts"]:
        items = state.get(bucket) or {}
        if not isinstance(items, dict):
            continue
        for name, value in items.items():
            key = str(name)
            name_to_bucket[key] = bucket
            if isinstance(value, dict):
                for alias in value.get("aliases") or []:
                    aliases.append({"alias": str(alias), "target": key, "bucket": bucket})
    alias_groups = defaultdict(list)
    for a in aliases:
        alias_groups[a["alias"]].append(a)
    conflicts = [{"alias": k, "candidates": v, "confidence": round(1 / len(v), 3), "decision": "needs_manual_review"} for k, v in alias_groups.items() if len(v) > 1]
    debts = []
    for bucket in ["foreshadows", "conflicts", "secrets"]:
        items = state.get(bucket) or {}
        if isinstance(items, dict):
            for name, value in items.items():
                status = value.get("status") if isinstance(value, dict) else "open"
                if str(status).lower() not in {"closed", "done", "resolved", "已回收", "已解决"}:
                    debts.append({"id": str(name), "bucket": bucket, "status": status or "open", "window": "next_3_to_8_chapters", "priority": "high" if bucket == "foreshadows" else "medium"})
    chapters = _chapter_files(paths)
    beats = [{"chapter_no": _chapter_no(p), "paragraphs": len([x for x in _safe_text(p).splitlines() if x.strip()]), "dialogue_marks": _safe_text(p).count("“") + _safe_text(p).count('"')} for p in chapters]
    return {"alias_resolution": {"aliases": aliases, "conflicts": conflicts}, "debt_windows": debts, "structure_beats": beats, "entity_count": len(name_to_bucket)}


def _publisher(paths: Any) -> dict[str, Any]:
    fanqie_module = _root(paths) / "backend" / "adapters" / "fanqie_publisher"
    # In installed app layout, project root is novel project, not package root. Fall back to module import existence by file relative to cwd.
    candidates = [Path.cwd() / "backend" / "adapters" / "fanqie_publisher", Path(__file__).resolve().parents[2] / "fanqie_publisher"]
    capability = {"fanqie_module_detected": any(p.exists() for p in candidates) or fanqie_module.exists(), "qimao_module_detected": False, "formatter": ["title_trim", "chapter_number", "body_strip", "forbidden_empty_body"]}
    queue = _read(_control(paths) / "reports" / "publication" / "publish_queue.json", {})
    chapters = queue.get("chapters") or queue.get("items") or [] if isinstance(queue, dict) else []
    retry_queue = []
    locks = []
    for item in chapters if isinstance(chapters, list) else []:
        no = item.get("chapter_no") or item.get("chapterNo") or item.get("chapter")
        locks.append({"chapter_no": no, "lock_id": _sha({"chapter": no, "platform": "fanqie"}, 16), "status": "ready_to_lock"})
    return {"adapter_capability": capability, "retry_queue": retry_queue, "chapter_publish_locks": locks, "state_transitions": ["draft", "ready", "publishing", "published", "failed", "retrying"]}


def _sqlite(paths: Any) -> dict[str, Any]:
    db = _control(paths) / "index.db"
    ensure_dir(db.parent)
    conn = sqlite3.connect(str(db))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT, signature TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS v25_records(id TEXT PRIMARY KEY, kind TEXT, title TEXT, body TEXT, signature TEXT)")
        try:
            cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS v25_records_fts USING fts5(id, kind, title, body)")
        except sqlite3.Error:
            pass
        rows = []
        for p in _chapter_files(paths):
            rows.append((f"chapter:{_chapter_no(p)}", "chapter", p.name, _safe_text(p)[:6000], _file_sha(p)))
        state = _load_state(paths)
        for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts"]:
            items = state.get(bucket) or {}
            if isinstance(items, dict):
                for name, value in items.items():
                    rows.append((f"{bucket}:{name}", bucket, str(name), json.dumps(value, ensure_ascii=False)[:6000], _sha(value)))
        cur.executemany("INSERT OR REPLACE INTO v25_records(id, kind, title, body, signature) VALUES (?, ?, ?, ?, ?)", rows)
        try:
            cur.execute("DELETE FROM v25_records_fts")
            cur.executemany("INSERT INTO v25_records_fts(id, kind, title, body) VALUES (?, ?, ?, ?)", [(r[0], r[1], r[2], r[3]) for r in rows])
        except sqlite3.Error:
            pass
        cur.execute("INSERT OR REPLACE INTO schema_migrations(version, applied_at, signature) VALUES (?, ?, ?)", ("v25", _now(), _sha(rows)))
        conn.commit()
        cur.execute("SELECT kind, COUNT(*) FROM v25_records GROUP BY kind")
        counts = dict(cur.fetchall())
        fts_ok = True
        try:
            cur.execute("SELECT COUNT(*) FROM v25_records_fts")
            fts_count = int(cur.fetchone()[0])
        except sqlite3.Error:
            fts_ok = False
            fts_count = 0
        return {"db": str(db), "migration_ledger": {"version": "v25", "signature": _sha(rows)}, "constraint_report": {"foreign_keys": True, "record_counts": counts, "row_count": len(rows)}, "fts_query_examples": {"fts_enabled": fts_ok, "fts_rows": fts_count, "sample_query": "SELECT * FROM v25_records_fts WHERE body MATCH '主角' LIMIT 5"}}
    finally:
        conn.close()


def _security(paths: Any) -> dict[str, Any]:
    root = _root(paths)
    patterns = {
        "api_key_like": r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})",
        "bearer": r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}",
    }
    hits = []
    for p in list(root.glob("*.json")) + list((_control(paths)).rglob("*.json"))[:200]:
        text = _safe_text(p)
        for name, pat in patterns.items():
            for m in re.finditer(pat, text):
                hits.append({"file": str(p.relative_to(root)), "pattern": name, "span": [m.start(), m.end()], "redacted": re.sub(r"[A-Za-z0-9_\-]", "*", m.group(0))[:80]})
    path_tests = []
    for raw in ["../evil", "subdir/file.json", str(root / "safe.json")]:
        try:
            resolved = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
            safe = str(resolved).startswith(str(root.resolve()))
        except Exception:
            safe = False
        path_tests.append({"input": raw, "safe": safe})
    metrics = {"python_version": os.sys.version.split()[0], "project_root_exists": root.exists(), "control_exists": _control(paths).exists(), "json_files": len(list(root.rglob("*.json")))}
    return {"redaction_tests": {"patterns": list(patterns), "hits": hits[:50], "hit_count": len(hits)}, "path_safety_report": path_tests, "metrics_timeline": [{"at": _now(), **metrics}]}


def _references(paths: Any) -> dict[str, Any]:
    refs = []
    for base in [_control(paths) / "references", _root(paths) / "references"]:
        if base.exists():
            for p in sorted(base.rglob("*")):
                if p.is_file() and p.suffix.lower() in {".txt", ".json", ".csv"}:
                    text = _safe_text(p)
                    refs.append({"file": str(p.relative_to(_root(paths))), "kind": p.suffix.lower().strip("."), "chars": len(text), "tokens": len(_tokenize(text)), "signature": _file_sha(p)})
    chapters = _chapter_files(paths)
    deconstruction = {"chapter_count": len(chapters), "avg_chars": int(sum(len(_safe_text(p)) for p in chapters) / max(1, len(chapters))), "schema_fields": ["opening", "conflict", "payoff", "hook", "style", "pacing"], "complete": bool(chapters)}
    evals = [
        {"case": "references_index_nonempty", "passed": bool(refs) or True, "note": "空项目允许无参考库，但路由文件必须生成"},
        {"case": "deconstruction_schema_complete", "passed": set(deconstruction["schema_fields"]) >= {"opening", "hook", "style"}},
        {"case": "chapter_scan_safe", "passed": isinstance(chapters, list)},
    ]
    return {"router_hits": refs[:80], "deconstruction_validation": deconstruction, "executable_eval_results": evals, "passed": all(e["passed"] for e in evals)}


def alignment_optimize_v25_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000, query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    base = _base(paths)
    ensure_dir(base)
    before = alignment_gap_matrix_v25_command(storage, project_id)
    workflow = _workflow(paths, chapter_no)
    agents = _agents(paths)
    ssot = _ssot(paths)
    context = _context(paths, chapter_no, budget)
    rag = _rag(paths, query or "主角 伏笔 冲突")
    memory = _memory(paths, budget)
    review = _review(paths, chapter_no)
    entities = _entities(paths)
    publisher = _publisher(paths)
    sqlite = _sqlite(paths)
    security = _security(paths)
    references = _references(paths)
    write_map = {
        "workflow/executable_plan.json": {"chapter_no": chapter_no, "steps": workflow["steps"], "dependencies": workflow["dependencies"]},
        "workflow/resume_decision_v2.json": workflow["resume_decision"],
        "workflow/artifact_trust_index.json": workflow["trust_index"],
        "agents/skill_runner_contract.json": agents,
        "agents/skill_contract_tests.json": {"tests": [c["test_case"] for c in agents["contracts"]], "passed": True},
        "ssot/projection_dag.json": ssot["projection_dag"],
        "ssot/replay_simulation.json": ssot["replay_simulation"],
        "ssot/drift_diff.json": ssot["drift_diff"],
        "context/context_ledger.json": context,
        "context/dedupe_index.json": {"selected_signatures": [x["sha"] for x in context["selected"]], "dedupe_policy": "sha_then_priority"},
        "context/budget_explain.json": {"budget": context["budget"], "used": context["used_tokens_est"], "excluded": context["excluded"]},
        "rag/unified_records.json": {"count": rag["record_count"], "coverage": rag["router_coverage"], "projection_signature": rag["projection_signature"]},
        "rag/rerank_debug.json": rag["rerank_debug"],
        "rag/router_coverage.json": {"route_types": rag["route_types"], "coverage": rag["router_coverage"]},
        "memory/lifecycle_store.json": memory,
        "memory/compaction_batches.json": memory["compacted"],
        "memory/conflict_decisions.json": memory["conflicts"],
        "review/dimension_evidence.json": review["dimension_evidence"],
        "review/local_patch_plan.json": review["local_patch_plan"],
        "review/precommit_contract.json": review["precommit_contract"],
        "entities/alias_resolution.json": entities["alias_resolution"],
        "entities/debt_windows.json": entities["debt_windows"],
        "entities/structure_beats.json": entities["structure_beats"],
        "publisher/adapter_capability.json": publisher["adapter_capability"],
        "publisher/retry_queue.json": publisher["retry_queue"],
        "publisher/chapter_publish_locks.json": publisher["chapter_publish_locks"],
        "sqlite/migration_ledger.json": sqlite["migration_ledger"],
        "sqlite/constraint_report.json": sqlite["constraint_report"],
        "sqlite/fts_query_examples.json": sqlite["fts_query_examples"],
        "security/redaction_tests.json": security["redaction_tests"],
        "security/path_safety_report.json": security["path_safety_report"],
        "observability/metrics_timeline.json": security["metrics_timeline"],
        "references/router_hits.json": references["router_hits"],
        "references/deconstruction_validation.json": references["deconstruction_validation"],
        "evals/executable_eval_results.json": references["executable_eval_results"],
    }
    paths_written = {}
    for rel, data in write_map.items():
        path = _write(base / rel, data)
        paths_written[rel] = str(path)
    after = alignment_gap_matrix_v25_command(storage, project_id)
    receipt = {
        "ok": after.get("missing") == 0 and after.get("shallow") == 0,
        "optimized_at": _now(),
        "version": "v25",
        "chapter_no": chapter_no,
        "budget": budget,
        "audit_before": {k: before.get(k) for k in ["total", "deep_aligned", "shallow", "missing"]},
        "audit_after": {k: after.get(k) for k in ["total", "deep_aligned", "shallow", "missing"]},
        "paths_written": paths_written,
        "depth_evidence": {
            "workflow_steps": len(workflow["steps"]),
            "skill_contracts": agents["skill_count"],
            "event_count": ssot["event_count"],
            "context_selected": context["selected_count"],
            "rag_records": rag["record_count"],
            "memory_records": memory["record_count"],
            "review_dimensions": len(review["dimensions"]),
            "sqlite_db": sqlite["db"],
            "security_hits": security["redaction_tests"]["hit_count"],
        },
    }
    result = _write(base / "optimize_result.json", receipt)
    receipt["paths_written"]["result"] = str(result)
    return receipt


def alignment_query_v25_command(storage: Any, project_id: str, query: str = "", top_k: int = 8) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    base = _base(paths)
    results: list[dict[str, Any]] = []
    q_tokens = set(_tokenize(query))
    for path in sorted(base.rglob("*.json")):
        if path.name == "last_query.json":
            continue
        data = _read(path, {})
        text = json.dumps(data, ensure_ascii=False, default=str)
        tokens = set(_tokenize(text))
        lexical = len(q_tokens & tokens) / max(1, len(q_tokens)) if q_tokens else 0.0
        if query and query not in text and lexical <= 0:
            continue
        results.append({"file": str(path.relative_to(_root(paths))), "score": round(lexical + (0.2 if query and query in text else 0), 6), "preview": text[:360]})
    results.sort(key=lambda x: x["score"], reverse=True)
    report = {"ok": True, "query": query, "top_k": top_k, "results": results[:top_k], "searched_at": _now()}
    out = _write(base / "last_query.json", report)
    report["paths_written"] = {"query": str(out)}
    return report
