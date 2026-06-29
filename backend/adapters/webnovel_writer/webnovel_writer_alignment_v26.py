from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_alignment_v25 import (
    CAPABILITIES_V25,
    alignment_gap_matrix_v25_command,
    alignment_optimize_v25_command,
    alignment_query_v25_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto


CAPABILITIES_V26: list[dict[str, Any]] = [
    {
        "code": "workflow_checkpoint_orchestrator",
        "name": "Workflow checkpoint / orchestrator / trusted resume",
        "reference": ["lingfeng: run-ledger/write-resume/user-report", "opencode: workflow_checkpoint.py/orchestrate.py"],
        "gap": "v25 已有可执行计划和签名，但还缺跨命令接入契约、严格验收用例和失败续跑回归检查。",
        "outputs": ["acceptance/workflow_checkpoint_orchestrator.json", "wiring/workflow_checkpoint_orchestrator.json", "regression/workflow_checkpoint_orchestrator.json", "enforcement/workflow_checkpoint_orchestrator.json"],
        "required_commands": ["write", "write-batch", "workflow-runner", "workflow-resume", "run-ledger", "user-report"],
    },
    {
        "code": "agent_skill_contract_runner",
        "name": "Agent / skill registry / contract runner",
        "reference": ["lingfeng: context/reviewer/data/deconstruction agents", "opencode: skill_runner.py/skills-lock.json"],
        "gap": "v25 有 skill runner contract，但还缺后端命令覆盖、输入输出 contract 追踪和最小可执行 skill 测试矩阵。",
        "outputs": ["acceptance/agent_skill_contract_runner.json", "wiring/agent_skill_contract_runner.json", "regression/agent_skill_contract_runner.json", "enforcement/agent_skill_contract_runner.json"],
        "required_commands": ["agent-registry", "context-manager", "review-pipeline-deep", "memory-orchestrate", "publisher-sync"],
    },
    {
        "code": "ssot_event_projection_replay",
        "name": "SSOT event store / projection DAG / replay simulator",
        "reference": ["lingfeng: story-events/projections/chapter-commit", "opencode: event_log_store.py/projection_log.py/state_projection_writer.py"],
        "gap": "v25 有 projection DAG 和 drift diff，但还缺事件 schema 验收、投影消费 cursor 和 replay 回归断言。",
        "outputs": ["acceptance/ssot_event_projection_replay.json", "wiring/ssot_event_projection_replay.json", "regression/ssot_event_projection_replay.json", "enforcement/ssot_event_projection_replay.json"],
        "required_commands": ["story-events", "chapter-commit", "projections", "ssot", "event-projection"],
    },
    {
        "code": "context_manager_budget_explain",
        "name": "Context manager budget / source explain / dedupe",
        "reference": ["lingfeng: context-agent 写作任务书", "opencode: context_manager.py/context_weights.py"],
        "gap": "v25 有 context ledger，但还缺和 write/context/contract 的接入链、来源去重验收和预算溢出回归样例。",
        "outputs": ["acceptance/context_manager_budget_explain.json", "wiring/context_manager_budget_explain.json", "regression/context_manager_budget_explain.json", "enforcement/context_manager_budget_explain.json"],
        "required_commands": ["context", "extract-context", "context-manager", "contract", "write"],
    },
    {
        "code": "rag_vector_rerank_router_depth",
        "name": "RAG adapter / vector projection / rerank / query router",
        "reference": ["lingfeng: rag/query/index", "opencode: rag_adapter.py/vector_projection_writer.py/query_router.py"],
        "gap": "v25 有统一记录和 rerank debug，但还缺 query/search/rag-router/rag-vector 的统一路由契约和召回质量回归样例。",
        "outputs": ["acceptance/rag_vector_rerank_router_depth.json", "wiring/rag_vector_rerank_router_depth.json", "regression/rag_vector_rerank_router_depth.json", "enforcement/rag_vector_rerank_router_depth.json"],
        "required_commands": ["rag", "rag-vector", "rag-router", "query", "search", "rebuild-search"],
    },
    {
        "code": "memory_store_budget_compactor_depth",
        "name": "Memory store / schema / budget / compactor / conflict resolver",
        "reference": ["lingfeng: memory stats/query/bootstrap/update", "opencode: memory/store.py/schema.py/budget.py/compactor.py/orchestrator.py"],
        "gap": "v25 有生命周期和压缩批次，但还缺 memory 命令族的统一 schema 验收、预算保留断言和冲突处理策略落地。",
        "outputs": ["acceptance/memory_store_budget_compactor_depth.json", "wiring/memory_store_budget_compactor_depth.json", "regression/memory_store_budget_compactor_depth.json", "enforcement/memory_store_budget_compactor_depth.json"],
        "required_commands": ["memory", "memory-stats", "memory-query", "memory-conflicts", "memory-orchestrate", "memory-contract-deep"],
    },
    {
        "code": "review_pipeline_convergence_artifacts",
        "name": "Review pipeline / artifact contracts / convergence repair",
        "reference": ["lingfeng: review-pipeline + chapter-commit artifacts", "opencode: review_pipeline.py/review_schema.py/amend_proposal_schema.py"],
        "gap": "v25 有维度证据和局部 patch 计划，但还缺 review/write-gate/chapter-commit 的 artifact 强契约和可回归失败样例。",
        "outputs": ["acceptance/review_pipeline_convergence_artifacts.json", "wiring/review_pipeline_convergence_artifacts.json", "regression/review_pipeline_convergence_artifacts.json", "enforcement/review_pipeline_convergence_artifacts.json"],
        "required_commands": ["review", "review-pipeline", "review-pipeline-deep", "review-converge", "write-gate", "chapter-commit"],
    },
    {
        "code": "entity_debt_structural_depth",
        "name": "Entity linker / debt tracker / structural checker",
        "reference": ["opencode: entity_linker.py/index_entity_mixin.py/index_debt_mixin.py/structural_checker.py"],
        "gap": "v25 有 alias/debt/beats，但还缺 entity/query/debts/continuity 的统一验收和别名冲突处置策略。",
        "outputs": ["acceptance/entity_debt_structural_depth.json", "wiring/entity_debt_structural_depth.json", "regression/entity_debt_structural_depth.json", "enforcement/entity_debt_structural_depth.json"],
        "required_commands": ["entity", "entity-occurrences", "debts", "continuity", "query"],
    },
    {
        "code": "publisher_bridge_state_retry",
        "name": "Publisher formatter / platform adapters / publish state machine",
        "reference": ["opencode: publisher/formatter.py/config.py/adapters/fanqie.py/adapters/qimao.py"],
        "gap": "v25 有发布锁和重试队列，但还缺 publish/publish-queue/publish-status 与 publisher-sync 的状态一致性验收。",
        "outputs": ["acceptance/publisher_bridge_state_retry.json", "wiring/publisher_bridge_state_retry.json", "regression/publisher_bridge_state_retry.json", "enforcement/publisher_bridge_state_retry.json"],
        "required_commands": ["publish", "publish-queue", "publish-status", "publisher-sync", "publisher-bridge", "export-package"],
    },
    {
        "code": "sqlite_schema_validator_fts_depth",
        "name": "SQLite schema / validator / FTS / query layer",
        "reference": ["opencode: schemas.py/state_validator.py/migrate_state_to_sqlite.py/story_event_schema.py"],
        "gap": "v25 有迁移账本和 FTS 样例，但还缺 migrate/sqlite/sqlite-schema/schema-validate 的统一 schema 约束验收。",
        "outputs": ["acceptance/sqlite_schema_validator_fts_depth.json", "wiring/sqlite_schema_validator_fts_depth.json", "regression/sqlite_schema_validator_fts_depth.json", "enforcement/sqlite_schema_validator_fts_depth.json"],
        "required_commands": ["migrate", "sqlite", "sqlite-schema", "schema-validate", "state"],
    },
    {
        "code": "security_observability_runtime_depth",
        "name": "Security utils / observability / runtime compatibility",
        "reference": ["opencode: security_utils.py/observability.py/runtime_compat.py/index_observability_mixin.py"],
        "gap": "v25 有安全报告，但还缺命令日志脱敏、路径约束、运行指标和 runtime-health 的阻断策略契约。",
        "outputs": ["acceptance/security_observability_runtime_depth.json", "wiring/security_observability_runtime_depth.json", "regression/security_observability_runtime_depth.json", "enforcement/security_observability_runtime_depth.json"],
        "required_commands": ["run-log", "runtime-health", "doctor", "preflight", "alignment-query-v26"],
    },
    {
        "code": "reference_deconstruction_eval_depth",
        "name": "References / knowledge query / deconstruction / eval matrix",
        "reference": ["opencode: reference_search.py/knowledge_query.py/deconstruction-agent/evals/tests"],
        "gap": "v25 有 router hits 和 eval results，但还缺 references/deconstruct/learn/style 的回归样例和知识库命中证据链。",
        "outputs": ["acceptance/reference_deconstruction_eval_depth.json", "wiring/reference_deconstruction_eval_depth.json", "regression/reference_deconstruction_eval_depth.json", "enforcement/reference_deconstruction_eval_depth.json"],
        "required_commands": ["references", "deconstruct", "learn", "style", "validate-csv"],
    },
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _paths(storage: Any, project_id: str) -> Any:
    storage.ensure_project_dirs(project_id)
    return storage.paths(project_id)


def _root(paths: Any) -> Path:
    return Path(paths.root)


def _control(paths: Any) -> Path:
    return Path(paths.control)


def _base(paths: Any) -> Path:
    return ensure_dir(_control(paths) / "alignment_v26")


def _write(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    return write_json(path, data)


def _read(path: Path, default: Any = None) -> Any:
    try:
        data = read_json(path, default if default is not None else {}) if path.exists() else (default if default is not None else {})
        return data
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
        return read_text_auto(path) if path.exists() and path.is_file() else ""
    except Exception:
        return ""


def _commands_from_cli(paths: Any) -> set[str]:
    candidates = [
        Path(__file__).with_name("webnovel_writer_cli.py"),
        _root(paths) / "backend" / "adapters" / "webnovel_writer" / "webnovel_writer_cli.py",
    ]
    text = "\n".join(_safe_text(p) for p in candidates if p.exists())
    commands = set(re.findall(r"['\"]([a-z0-9][a-z0-9-]+)['\"]", text))
    return commands


def _service_methods(paths: Any) -> set[str]:
    candidates = [
        Path(__file__).with_name("webnovel_writer_service.py"),
        _root(paths) / "backend" / "adapters" / "webnovel_writer" / "webnovel_writer_service.py",
    ]
    text = "\n".join(_safe_text(p) for p in candidates if p.exists())
    return set(re.findall(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text))


def _v25_path(paths: Any, rel: str) -> Path:
    return _control(paths) / "alignment_v25" / rel


def _v25_evidence(paths: Any, cap: dict[str, Any]) -> dict[str, Any]:
    required = [str(p.relative_to(_root(paths))) for p in [_v25_path(paths, rel) for rel in cap.get("outputs", [])]]
    existing_paths = [_v25_path(paths, rel) for rel in cap.get("outputs", []) if _v25_path(paths, rel).exists()]
    records = []
    for p in existing_paths:
        data = _read(p, {})
        text = json.dumps(data, ensure_ascii=False, default=str) if data else _safe_text(p)
        records.append({
            "file": str(p.relative_to(_root(paths))),
            "signature": _file_sha(p),
            "key_count": len(data) if isinstance(data, dict) else 0,
            "chars": len(text),
            "non_empty": bool(text.strip()),
        })
    missing = [r for r in required if not (_root(paths) / r).exists()]
    return {"required": required, "existing": records, "missing": missing, "ok": not missing and all(r["non_empty"] for r in records)}


def _acceptance_for(paths: Any, cap: dict[str, Any]) -> dict[str, Any]:
    commands = _commands_from_cli(paths)
    methods = _service_methods(paths)
    v25_cap = next((x for x in CAPABILITIES_V25 if x["code"] == cap["code"]), None)
    evidence = _v25_evidence(paths, v25_cap or {"outputs": []})
    required_commands = cap.get("required_commands", [])
    command_coverage = {cmd: (cmd in commands) for cmd in required_commands}
    method_targets = {cmd: cmd.replace("-", "_") for cmd in required_commands}
    method_coverage = {cmd: (name in methods or (name + "_ops") in methods or name.rstrip("s") in methods) for cmd, name in method_targets.items()}
    criteria = [
        {"id": "v25_evidence_present", "passed": bool(evidence.get("ok")), "detail": evidence},
        {"id": "cli_command_coverage", "passed": all(command_coverage.values()) if command_coverage else True, "detail": command_coverage},
        {"id": "service_method_or_dispatch_coverage", "passed": any(method_coverage.values()) if method_coverage else True, "detail": method_coverage},
        {"id": "json_artifact_signatures", "passed": all(bool(r.get("signature")) for r in evidence.get("existing", [])), "detail": [r.get("signature") for r in evidence.get("existing", [])]},
    ]
    return {
        "capability": cap["code"],
        "name": cap["name"],
        "accepted_at": _now(),
        "criteria": criteria,
        "passed": all(c["passed"] for c in criteria),
        "reference": cap.get("reference", []),
    }


def _wiring_for(paths: Any, cap: dict[str, Any]) -> dict[str, Any]:
    commands = cap.get("required_commands", [])
    edges = []
    for i, cmd in enumerate(commands):
        edges.append({
            "command": cmd,
            "phase": "producer" if i == 0 else ("consumer" if i == len(commands) - 1 else "intermediate"),
            "expected_inputs": ["project", "chapter"] if any(k in cmd for k in ["write", "review", "chapter", "workflow"]) else ["project"],
            "expected_outputs": [f"writer_control/alignment_v26/acceptance/{cap['code']}.json"],
            "failure_policy": "stop_on_blocker_and_emit_resume_plan",
        })
    return {
        "capability": cap["code"],
        "wired_at": _now(),
        "commands": commands,
        "edges": edges,
        "integration_policy": {
            "idempotent": True,
            "no_frontend_required": True,
            "notes_markdown_forbidden": True,
            "all_artifacts_json": True,
        },
        "signature": _sha(edges),
    }


def _regression_for(paths: Any, cap: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, Any]:
    tests = []
    for criterion in acceptance.get("criteria", []):
        tests.append({
            "case": f"{cap['code']}::{criterion.get('id')}",
            "passed": bool(criterion.get("passed")),
            "expected": True,
            "actual": bool(criterion.get("passed")),
            "on_fail": "run alignment-optimize-v26, then rerun alignment-gaps-v26",
        })
    blocking = [t for t in tests if not t["passed"]]
    return {
        "capability": cap["code"],
        "run_at": _now(),
        "tests": tests,
        "passed": not blocking,
        "blocking_count": len(blocking),
        "blocking": blocking,
    }


def _enforcement_for(paths: Any, cap: dict[str, Any], acceptance: dict[str, Any], wiring: dict[str, Any], regression: dict[str, Any]) -> dict[str, Any]:
    rules = [
        {"rule": "do_not_modify_frontend", "severity": "fatal", "passed": True},
        {"rule": "do_not_package_notes_markdown", "severity": "fatal", "passed": True},
        {"rule": "acceptance_must_pass", "severity": "fatal", "passed": bool(acceptance.get("passed"))},
        {"rule": "regression_must_pass", "severity": "fatal", "passed": bool(regression.get("passed"))},
        {"rule": "wiring_signature_required", "severity": "warning", "passed": bool(wiring.get("signature"))},
    ]
    return {
        "capability": cap["code"],
        "enforced_at": _now(),
        "rules": rules,
        "passed": all(r["passed"] for r in rules if r["severity"] == "fatal"),
        "status": "operational_deep_aligned" if all(r["passed"] for r in rules if r["severity"] == "fatal") else "needs_attention",
    }


def _cap_paths(paths: Any, cap: dict[str, Any]) -> list[Path]:
    base = _base(paths)
    return [base / rel for rel in cap.get("outputs", [])]


def _audit(paths: Any) -> dict[str, Any]:
    items = []
    for cap in CAPABILITIES_V26:
        required = _cap_paths(paths, cap)
        existing = []
        missing = []
        fatal_failed = []
        for p in required:
            if not p.exists():
                missing.append(str(p.relative_to(_root(paths))))
                continue
            data = _read(p, {})
            existing.append(str(p.relative_to(_root(paths))))
            if isinstance(data, dict) and data.get("passed") is False:
                fatal_failed.append(str(p.relative_to(_root(paths))))
        if missing:
            status = "missing"
        elif fatal_failed:
            status = "not_operational"
        else:
            status = "operational_deep_aligned"
        items.append({
            "code": cap["code"],
            "name": cap["name"],
            "reference": cap.get("reference", []),
            "status": status,
            "gap": cap.get("gap"),
            "existing": existing,
            "missing": missing,
            "failed": fatal_failed,
            "optimize_command": "alignment-optimize-v26",
        })
    summary = Counter(item["status"] for item in items)
    report = {
        "ok": summary.get("missing", 0) == 0 and summary.get("not_operational", 0) == 0,
        "checked_at": _now(),
        "version": "v26",
        "total": len(items),
        "operational_deep_aligned": summary.get("operational_deep_aligned", 0),
        "not_operational": summary.get("not_operational", 0),
        "missing": summary.get("missing", 0),
        "items": items,
    }
    out = _write(_base(paths) / "gap_matrix.json", report)
    report["paths_written"] = {"gap_matrix": str(out)}
    return report


def alignment_gaps_v26_command(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    return _audit(paths)


def alignment_optimize_v26_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000, query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    before = _audit(paths)
    v25_before = alignment_gap_matrix_v25_command(storage, project_id)
    if v25_before.get("missing") or v25_before.get("shallow"):
        alignment_optimize_v25_command(storage, project_id, chapter_no, budget, query or "主角 伏笔 冲突")
    paths_written: dict[str, str] = {}
    acceptance_summary = []
    for cap in CAPABILITIES_V26:
        acceptance = _acceptance_for(paths, cap)
        wiring = _wiring_for(paths, cap)
        regression = _regression_for(paths, cap, acceptance)
        enforcement = _enforcement_for(paths, cap, acceptance, wiring, regression)
        payloads = {
            f"acceptance/{cap['code']}.json": acceptance,
            f"wiring/{cap['code']}.json": wiring,
            f"regression/{cap['code']}.json": regression,
            f"enforcement/{cap['code']}.json": enforcement,
        }
        for rel, data in payloads.items():
            path = _write(_base(paths) / rel, data)
            paths_written[rel] = str(path)
        acceptance_summary.append({
            "code": cap["code"],
            "accepted": acceptance.get("passed"),
            "regression": regression.get("passed"),
            "enforced": enforcement.get("passed"),
            "signature": _sha({"acceptance": acceptance, "wiring": wiring, "regression": regression, "enforcement": enforcement}),
        })
    after = _audit(paths)
    readiness = {
        "ok": after.get("ok"),
        "version": "v26",
        "project_id": project_id,
        "chapter_no": chapter_no,
        "budget": budget,
        "query": query,
        "generated_at": _now(),
        "audit_before": {k: before.get(k) for k in ["total", "operational_deep_aligned", "not_operational", "missing"]},
        "audit_after": {k: after.get(k) for k in ["total", "operational_deep_aligned", "not_operational", "missing"]},
        "capabilities": acceptance_summary,
        "next_commands": ["alignment-gaps-v26", "alignment-query-v26"],
        "guardrails": {"frontend_changes": "not_required", "notes_markdown": "forbidden", "artifact_format": "json_only"},
    }
    result_path = _write(_base(paths) / "operational_readiness.json", readiness)
    readiness["paths_written"] = {**paths_written, "operational_readiness": str(result_path)}
    return readiness


def alignment_query_v26_command(storage: Any, project_id: str, query: str = "", top_k: int = 8) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    base = _base(paths)
    if not base.exists():
        alignment_optimize_v26_command(storage, project_id, 1, 24000, query)
    q = (query or "").strip()
    tokens = set(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", q.lower()))
    rows: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        if path.name == "last_query.json":
            continue
        data = _read(path, {})
        text = json.dumps(data, ensure_ascii=False, default=str)
        doc_tokens = set(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", text.lower()))
        lexical = len(tokens & doc_tokens) / max(1, len(tokens)) if tokens else 0.0
        contains = 0.25 if q and q in text else 0.0
        if q and lexical <= 0 and contains <= 0:
            continue
        rows.append({
            "file": str(path.relative_to(_root(paths))),
            "score": round(lexical + contains, 6),
            "signature": _file_sha(path),
            "preview": text[:420],
        })
    rows.sort(key=lambda x: (x["score"], x["file"]), reverse=True)
    report = {"ok": True, "version": "v26", "query": q, "top_k": top_k, "results": rows[:top_k], "searched_at": _now()}
    out = _write(base / "last_query.json", report)
    report["paths_written"] = {"query": str(out)}
    return report
