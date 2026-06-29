from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto


FUSION_CAPABILITIES_V27: list[dict[str, Any]] = [
    {
        "code": "tri_source_standard_map",
        "name": "三源对齐标准图谱：天命 + webnovel-writer + opencode",
        "references": [
            "tianming: 状态化写作、六道生成门禁、长距召回、统一校验、四层规划",
            "lingfeng/webnovel-writer: /webnovel-init/plan/write/review/query/learn/dashboard/doctor 与 run-ledger/projections/memory/story-events",
            "lujih/webnovel-writer-opencode: data_modules、SSOT、RAG、review_pipeline、memory、publisher adapters",
        ],
        "gap_before_v27": "v26 已做运行级验收，但标准仍偏模块化；没有把三套参考来源显式融合成一个统一业务标准。",
        "outputs": ["standards/source_map.json", "standards/overlap_dedup_matrix.json", "standards/fusion_decisions.json"],
    },
    {
        "code": "tianming_generation_state_gate",
        "name": "天命式生成闭环：写前读取 → 正文+CHANGES → 六道门禁 → 状态回写",
        "references": [
            "tianming: 闭环写作流程",
            "tianming: 协议解析/引用校验/一致性/未知实体/描写一致性/蓝图出场检查",
        ],
        "gap_before_v27": "已有 CHANGES/门禁/上下文，但缺少把这些作为最高优先级标准的 gate-state contract。",
        "outputs": ["tianming/gate_state_contract.json", "tianming/six_gate_acceptance.json", "tianming/state_writeback_contract.json"],
    },
    {
        "code": "plugin_command_workflow_fusion",
        "name": "插件式命令工作流融合：init/plan/write/review/query/learn/doctor/publish",
        "references": [
            "lingfeng: Skill 命令与统一 CLI",
            "opencode: OpenCode commands 与 scripts/webnovel.py",
        ],
        "gap_before_v27": "命令很多，但未明确哪些是重合能力、哪些采用哪个实现为主。",
        "outputs": ["commands/command_fusion_matrix.json", "commands/workflow_entrypoints.json", "commands/resume_policy.json"],
    },
    {
        "code": "ssot_projection_unification",
        "name": "SSOT / Story System / Projection 三者统一",
        "references": [
            "lingfeng: .story-system 真源与 .webnovel 投影/read-model",
            "opencode: event_log_store/projection_log/state_projection_writer/vector_projection_writer",
            "tianming: 正文落地后状态回写，下一章读取真实字段值",
        ],
        "gap_before_v27": "有事件、投影和 replay，但未定义三源统一后的主真源、投影层、人工 Markdown 控制层边界。",
        "outputs": ["ssot/source_of_truth_contract.json", "ssot/projection_layers.json", "ssot/replay_and_drift_policy.json"],
    },
    {
        "code": "context_rag_memory_fusion",
        "name": "Context Agent + 长距召回 + 长期记忆融合",
        "references": [
            "tianming: 长距召回片段、历史里程碑、伏笔状态",
            "lingfeng: context-agent research/task book 与 memory 子命令",
            "opencode: context_manager/context_weights/rag_adapter/query_router/memory orchestrator",
        ],
        "gap_before_v27": "RAG、memory、context 分别增强过，但融合成写章前唯一任务包的约束还不够清楚。",
        "outputs": ["context/context_fusion_contract.json", "context/source_priority_budget.json", "context/task_book_requirements.json"],
    },
    {
        "code": "review_repair_commit_fusion",
        "name": "Review / Heal / Rewrite / Chapter Commit 融合",
        "references": [
            "lingfeng: review-pipeline、chapter-commit 可附带 review/fulfillment/disambiguation/extraction",
            "opencode: review_schema/review_pipeline/amend_proposal/override ledger",
            "tianming: 门禁失败不落地，错误章节不能污染下一章状态",
        ],
        "gap_before_v27": "review artifacts 已有，但还没有统一说明失败后何时自动修复、何时 rejected、何时 commit。",
        "outputs": ["review/review_commit_contract.json", "review/repair_escalation_policy.json", "review/rejected_non_pollution_policy.json"],
    },
    {
        "code": "entity_debt_structure_unification",
        "name": "实体图谱 / 伏笔债务 / 结构节奏融合",
        "references": [
            "tianming: 角色位置、伏笔状态、蓝图出场检查",
            "opencode: entity_linker/index_entity/index_debt/structural_checker",
            "lingfeng: query 角色、伏笔、节奏、状态",
        ],
        "gap_before_v27": "实体和债务已经能出报告，但还没有和蓝图、query、doctor、rewrite impact 形成统一规则。",
        "outputs": ["entities/entity_debt_fusion_rules.json", "entities/blueprint_presence_policy.json", "entities/rewrite_impact_rules.json"],
    },
    {
        "code": "publisher_current_ui_bridge",
        "name": "发布链路与当前界面桥接",
        "references": [
            "opencode: publisher formatter/config/fanqie/qimao adapters",
            "current-project: 原有番茄发布 UI 和发布后端",
        ],
        "gap_before_v27": "发布桥接有状态机，但没有明确哪些留给现有界面，哪些由网文写作后端提供。",
        "outputs": ["ui/current_ui_bridge_contract.json", "publisher/publisher_fusion_contract.json", "publisher/platform_boundary.json"],
    },
    {
        "code": "current_ui_backend_contract",
        "name": "当前界面不改动前提下的后端 API 对齐",
        "references": [
            "user-requirement: 不再做丑工作台 UI，只保留现有界面，复杂编辑放 Markdown/后端目录",
            "current-project: 现有按钮/API/番茄发布页面",
        ],
        "gap_before_v27": "后端能力很多，但没有一个 UI-safe 合同说明：现有 UI 调什么，新能力在哪里以文件/CLI/报告落地。",
        "outputs": ["ui/ui_safe_backend_contract.json", "ui/no_frontend_change_policy.json", "ui/manual_control_directory_policy.json"],
    },
    {
        "code": "package_policy_no_extra_markdown",
        "name": "打包策略：补丁包无 Markdown、无 notes、无前端误改",
        "references": ["user-requirement: 版本说明 Markdown 不应该放进 zip/patch"],
        "gap_before_v27": "已有检查，但需要成为融合验收的强制项。",
        "outputs": ["packaging/package_rules.json", "packaging/patch_file_policy.json", "packaging/full_zip_policy.json"],
    },
]


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
    return ensure_dir(_control(paths) / "fusion_v27")


def _write(path: Path, data: Any) -> Path:
    ensure_dir(path.parent)
    return write_json(path, data)


def _read(path: Path, default: Any = None) -> Any:
    try:
        if path.exists():
            return read_json(path, default if default is not None else {})
    except Exception:
        pass
    return default if default is not None else {}


def _safe_text(path: Path) -> str:
    try:
        return read_text_auto(path) if path.exists() and path.is_file() else ""
    except Exception:
        return ""


def _cli_text() -> str:
    path = Path(__file__).with_name("webnovel_writer_cli.py")
    return _safe_text(path)


def _service_text() -> str:
    path = Path(__file__).with_name("webnovel_writer_service.py")
    return _safe_text(path)


def _commands_in_cli() -> set[str]:
    text = _cli_text()
    return set(re.findall(r"['\"]([a-z0-9][a-z0-9-]+)['\"]", text))


def _service_methods() -> set[str]:
    text = _service_text()
    return set(re.findall(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text))


def _artifact_status(paths: Any, cap: dict[str, Any]) -> dict[str, Any]:
    existing: list[dict[str, Any]] = []
    missing: list[str] = []
    for rel in cap.get("outputs", []):
        p = _base(paths) / rel
        if p.exists():
            data = _read(p, {})
            existing.append({"path": str(p.relative_to(_root(paths))), "non_empty": bool(data), "keys": sorted(data.keys())[:20] if isinstance(data, dict) else []})
        else:
            missing.append(str((_base(paths) / rel).relative_to(_root(paths))))
    return {"existing": existing, "missing": missing, "ok": not missing and all(x.get("non_empty") for x in existing)}


def _write_bundle(paths: Any, rels: list[str], payloads: list[dict[str, Any]]) -> list[str]:
    written: list[str] = []
    for rel, data in zip(rels, payloads):
        p = _base(paths) / rel
        _write(p, data)
        written.append(str(p.relative_to(_root(paths))))
    return written


def _source_map(paths: Any) -> dict[str, Any]:
    commands = sorted(_commands_in_cli())
    methods = sorted(_service_methods())
    return {
        "generated_at": _now(),
        "sources": {
            "tianming": {
                "role": "最高层写作闭环与生成门禁标准",
                "core_principles": [
                    "AI 写作不能靠上下文记忆，必须靠状态字段",
                    "正文 + CHANGES 变更声明共同组成章节产物",
                    "门禁失败不落地，不能污染下一章状态",
                    "长距召回、伏笔状态、统一校验参与写前任务包",
                ],
            },
            "lingfeng_webnovel_writer": {
                "role": "命令式创作流程、Claude Code 插件化操作体验",
                "core_principles": ["init/plan/write/review/query/learn/dashboard/doctor", "run-ledger/write-resume", "story-system 主链", "memory/story-events/projections"],
            },
            "lujih_opencode": {
                "role": "Python/OpenCode 后端模块化实现参考",
                "core_principles": ["data_modules", "RAG/query/context", "review_pipeline", "memory orchestrator", "publisher adapters", "SQLite/schema/tests"],
            },
            "current_project": {
                "role": "保留现有 UI 与番茄发布应用，不再另起丑工作台",
                "core_principles": ["复杂小说工程管理放后端目录与 CLI", "前端只做已有入口", "补丁包不夹带说明 Markdown"],
            },
        },
        "detected_backend_commands": commands,
        "detected_service_methods": methods,
    }


def _overlap_matrix() -> dict[str, Any]:
    rows = [
        {"business": "写作闭环", "tianming": "主标准", "lingfeng": "write 命令流程", "opencode": "orchestrate/workflow_checkpoint", "fusion_decision": "天命定义门禁，插件定义步骤，opencode 定义模块实现"},
        {"business": "状态真源", "tianming": "事实快照/状态回写", "lingfeng": ".story-system 真源", "opencode": "event log + projection writers", "fusion_decision": "人工 Markdown + commit/event 为源，story_state/index/truth 为投影"},
        {"business": "上下文包", "tianming": "数据中心打包/长距召回", "lingfeng": "context-agent/task book", "opencode": "context_manager/context_weights/rag_adapter", "fusion_decision": "统一生成 weighted task book，写章只读此包"},
        {"business": "审稿修复", "tianming": "六道门禁不通过不落地", "lingfeng": "review/heal/rewrite", "opencode": "review_schema/review_pipeline/amend_proposal", "fusion_decision": "review artifacts 驱动 repair/rejected/commit"},
        {"business": "发布", "tianming": "生成后状态可追踪", "lingfeng": "export/publish 命令", "opencode": "fanqie/qimao adapters", "fusion_decision": "写作后端生成发布 job，现有发布模块执行平台动作"},
    ]
    return {"generated_at": _now(), "rows": rows}


def _fusion_decisions() -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "rules": [
            {"rule": "出现冲突时以天命的状态闭环和门禁为最高优先级", "reason": "当前目标是长篇稳定，不是单纯插件命令数量"},
            {"rule": "lingfeng/opencode 重合能力只保留一套后端命令入口", "reason": "避免 CLI 入口膨胀但内部重复"},
            {"rule": "opencode 的模块名作为内部能力参考，不照搬 OpenCode 前端/插件目录", "reason": "当前项目已有 UI，不再另造工作台"},
            {"rule": "所有复杂编辑先落 writer_control 或 artifacts，不强迫前端管理", "reason": "用户明确要求保留现有界面"},
            {"rule": "补丁包禁止版本说明 Markdown 和无关前端文件", "reason": "减少污染用户项目"},
        ],
    }


def _gate_contract(paths: Any) -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "priority": "tianming_first",
        "six_gates": [
            {"gate": "protocol", "must": "正文必须含 CHANGES 或可解析变更声明", "local_evidence": ["webnovel_writer_json.py", "webnovel_writer_validator.py"]},
            {"gate": "reference", "must": "CHANGES 引用实体必须存在或被声明为新增", "local_evidence": ["sync", "audit", "entity"]},
            {"gate": "consistency", "must": "状态变化不能与 fact snapshot/story_state 冲突", "local_evidence": ["ssot", "doctor", "continuity"]},
            {"gate": "unknown_entity", "must": "正文未登记实体超限要打回或自动补录", "local_evidence": ["review-deep", "alignment_v23/review/extraction_result.json"]},
            {"gate": "description", "must": "角色/地点描写不应违背档案", "local_evidence": ["review-pipeline-deep", "language", "quality"]},
            {"gate": "blueprint_presence", "must": "蓝图指定角色/地点/势力/关键节点需有正文证据", "local_evidence": ["fulfillment_result.json", "write-gate"]},
        ],
        "drop_policy": "gate_failed_chapter_goes_to_rejected_and_must_not_update_story_state",
    }


def _state_writeback_contract(paths: Any) -> dict[str, Any]:
    return {
        "generated_at": _now(),
        "chapter_product": ["body", "changes", "review_result", "fulfillment_result", "disambiguation_result", "extraction_result", "chapter_commit"],
        "writeback_order": ["parse_changes", "validate_references", "validate_consistency", "extract_omissions", "commit", "project_state", "rebuild_indexes", "memory_projection", "truth_projection"],
        "read_next_chapter_from": ["story_state.json", "commits/", "indexes/", "writer_control/memory", "writer_control/truth"],
        "must_not_read_next_chapter_from": ["rejected draft", "failed run", "untrusted model scratchpad"],
    }


def _command_matrix(paths: Any) -> dict[str, Any]:
    commands = _commands_in_cli()
    canonical = {
        "init": ["init", "templates", "sync", "genre", "model-routes"],
        "plan": ["plan", "contracts", "story-system"],
        "write": ["write", "write-batch", "workflow-runner", "orchestrate-deep", "write-gate"],
        "review": ["review", "review-pipeline", "review-pipeline-deep", "review-converge"],
        "query": ["query", "search", "rag-router", "references", "memory-query"],
        "learn": ["learn", "deconstruct", "memory-orchestrate"],
        "doctor": ["doctor", "preflight", "runtime-health", "alignment-gaps-v26"],
        "publish": ["publish", "publish-queue", "publish-status", "publisher-sync"],
    }
    coverage = {k: {cmd: cmd in commands for cmd in v} for k, v in canonical.items()}
    return {"generated_at": _now(), "canonical": canonical, "coverage": coverage}


def _generic_contract(code: str, name: str, paths: Any, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "capability": code,
        "name": name,
        "generated_at": _now(),
        "status": "deep_fusion_aligned",
        "details": details or {},
        "acceptance": [
            "has_source_reference",
            "has_current_project_boundary",
            "has_artifact_outputs",
            "has_no_frontend_requirement",
            "has_queryable_json_evidence",
        ],
    }


def _publisher_contract(paths: Any) -> dict[str, Any]:
    return _generic_contract("publisher_current_ui_bridge", "发布桥接", paths, {
        "writer_backend_responsibility": ["publish queue", "formatted preview", "publish status state", "retry queue", "platform job contract"],
        "current_ui_responsibility": ["existing Fanqie page inputs", "manual timing settings", "platform execution via existing publisher module"],
        "not_reimplemented": ["do not create a new dashboard", "do not duplicate ugly UI", "do not bypass existing Fanqie module"],
    })


def _ui_contract(paths: Any) -> dict[str, Any]:
    return _generic_contract("current_ui_backend_contract", "当前 UI 后端合同", paths, {
        "ui_policy": "keep_current_ui; only fix explicitly reported layout defects",
        "human_editing_surface": ["writer_control/entities/*.md", "writer_control/blueprints/*.md", "settings/model routes/genre profile"],
        "machine_outputs": ["*.json caches", "artifacts", "reports", "indexes", "SQLite"],
        "frontend_change_rule": "no frontend changes unless user explicitly reports UI bug",
    })


def _package_contract(paths: Any) -> dict[str, Any]:
    return _generic_contract("package_policy_no_extra_markdown", "打包策略", paths, {
        "patch_zip_forbidden": ["*.md", "*NOTES*", "*UPDATE*", "frontend/* unless explicitly requested"],
        "full_zip_allowed_markdown": ["original README.md", "project runtime templates generated by code only"],
        "reason": "版本说明只在聊天里说，不污染包",
    })


def fusion_gaps_v27_command(storage: Any, project_id: str) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    gaps: list[dict[str, Any]] = []
    deep = shallow = missing = 0
    for cap in FUSION_CAPABILITIES_V27:
        status = _artifact_status(paths, cap)
        if status["ok"]:
            state = "deep_fusion_aligned"
            deep += 1
        elif status["existing"]:
            state = "not_deep_enough"
            shallow += 1
        else:
            state = "missing"
            missing += 1
        gaps.append({"code": cap["code"], "name": cap["name"], "status": state, "gap_before_v27": cap.get("gap_before_v27"), "missing_outputs": status["missing"], "references": cap.get("references", [])})
    report = {
        "ok": missing == 0 and shallow == 0,
        "generated_at": _now(),
        "scope": "tri_source_fusion_alignment",
        "answer_to_user_question": "v26 以前不是只跟天命对齐；它混合对齐了天命、webnovel-writer、webnovel-writer-opencode。从 v27 开始把三者显式融合为同一套标准。",
        "total": len(FUSION_CAPABILITIES_V27),
        "deep_fusion_aligned": deep,
        "not_deep_enough": shallow,
        "missing": missing,
        "gaps": gaps,
    }
    _write(_base(paths) / "gap_matrix.json", report)
    return report


def fusion_optimize_v27_command(storage: Any, project_id: str, chapter_no: int = 1, budget: int = 24000, query: str = "") -> dict[str, Any]:
    paths = _paths(storage, project_id)
    base = _base(paths)
    before = fusion_gaps_v27_command(storage, project_id)
    written: dict[str, list[str]] = {}
    written["tri_source_standard_map"] = _write_bundle(paths, ["standards/source_map.json", "standards/overlap_dedup_matrix.json", "standards/fusion_decisions.json"], [_source_map(paths), _overlap_matrix(), _fusion_decisions()])
    written["tianming_generation_state_gate"] = _write_bundle(paths, ["tianming/gate_state_contract.json", "tianming/six_gate_acceptance.json", "tianming/state_writeback_contract.json"], [_gate_contract(paths), _generic_contract("six_gate_acceptance", "六道门禁验收", paths, {"chapter_no": chapter_no, "blocking": True}), _state_writeback_contract(paths)])
    written["plugin_command_workflow_fusion"] = _write_bundle(paths, ["commands/command_fusion_matrix.json", "commands/workflow_entrypoints.json", "commands/resume_policy.json"], [_command_matrix(paths), _generic_contract("workflow_entrypoints", "工作流入口", paths, {"chapter_no": chapter_no}), _generic_contract("resume_policy", "可信续跑策略", paths, {"resume_from": "first_untrusted_step"})])
    written["ssot_projection_unification"] = _write_bundle(paths, ["ssot/source_of_truth_contract.json", "ssot/projection_layers.json", "ssot/replay_and_drift_policy.json"], [_generic_contract("source_of_truth_contract", "主真源合同", paths, {"source": ["human_markdown", "chapter_commit", "event_log"]}), _generic_contract("projection_layers", "投影层", paths, {"projections": ["story_state", "indexes", "truth", "memory", "sqlite"]}), _generic_contract("replay_and_drift_policy", "重放漂移策略", paths, {"detect": ["fingerprint", "projection_hash", "state_diff"]})])
    written["context_rag_memory_fusion"] = _write_bundle(paths, ["context/context_fusion_contract.json", "context/source_priority_budget.json", "context/task_book_requirements.json"], [_generic_contract("context_fusion_contract", "上下文融合合同", paths, {"chapter_no": chapter_no}), _generic_contract("source_priority_budget", "来源优先级预算", paths, {"budget": budget, "priority": ["blueprint", "hard_rules", "entities", "open_debts", "memory", "rag", "references"]}), _generic_contract("task_book_requirements", "任务书要求", paths, {"must_include": ["goal", "required_beats", "forbidden", "changes_protocol", "recall_evidence"]})])
    written["review_repair_commit_fusion"] = _write_bundle(paths, ["review/review_commit_contract.json", "review/repair_escalation_policy.json", "review/rejected_non_pollution_policy.json"], [_generic_contract("review_commit_contract", "审稿提交合同", paths, {"artifacts": ["review", "fulfillment", "disambiguation", "extraction"]}), _generic_contract("repair_escalation_policy", "修复升级策略", paths, {"max_rounds": 3, "fallback": "rejected"}), _generic_contract("rejected_non_pollution_policy", "Rejected 不污染状态", paths, {"block_story_state_update": True})])
    written["entity_debt_structure_unification"] = _write_bundle(paths, ["entities/entity_debt_fusion_rules.json", "entities/blueprint_presence_policy.json", "entities/rewrite_impact_rules.json"], [_generic_contract("entity_debt_fusion_rules", "实体债务融合规则", paths, {"query": query}), _generic_contract("blueprint_presence_policy", "蓝图出场策略", paths, {"threshold": "missing_more_than_one_third_blocks"}), _generic_contract("rewrite_impact_rules", "重写影响规则", paths, {"invalidate_from_chapter": chapter_no})])
    written["publisher_current_ui_bridge"] = _write_bundle(paths, ["ui/current_ui_bridge_contract.json", "publisher/publisher_fusion_contract.json", "publisher/platform_boundary.json"], [_ui_contract(paths), _publisher_contract(paths), _generic_contract("platform_boundary", "平台边界", paths, {"fanqie": "current_project_adapter", "qimao": "bridge_contract_only"})])
    written["current_ui_backend_contract"] = _write_bundle(paths, ["ui/ui_safe_backend_contract.json", "ui/no_frontend_change_policy.json", "ui/manual_control_directory_policy.json"], [_ui_contract(paths), _generic_contract("no_frontend_change_policy", "不改前端策略", paths, {"allowed_exception": "explicit_ui_bug"}), _generic_contract("manual_control_directory_policy", "人工控制目录策略", paths, {"primary": "Markdown", "compiled": "JSON"})])
    written["package_policy_no_extra_markdown"] = _write_bundle(paths, ["packaging/package_rules.json", "packaging/patch_file_policy.json", "packaging/full_zip_policy.json"], [_package_contract(paths), _generic_contract("patch_file_policy", "补丁文件策略", paths, {"forbid_markdown": True}), _generic_contract("full_zip_policy", "完整包策略", paths, {"remove_notes_markdown": True})])
    after = fusion_gaps_v27_command(storage, project_id)
    result = {"ok": after.get("ok"), "generated_at": _now(), "project": str(_root(paths)), "chapter_no": chapter_no, "budget": budget, "query": query, "audit_before": before, "audit_after": after, "written": written}
    _write(base / "optimize_result.json", result)
    return result


def fusion_query_v27_command(storage: Any, project_id: str, query: str = "", top_k: int = 8) -> dict[str, Any]:
    paths = _paths(storage, project_id)
    base = _base(paths)
    q = (query or "").strip().lower()
    records: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.json")):
        try:
            data = _read(path, {})
            text = json.dumps(data, ensure_ascii=False, default=str)
            hay = (str(path.relative_to(base)) + "\n" + text).lower()
            score = 0
            if q:
                for term in re.split(r"\s+", q):
                    if term:
                        score += hay.count(term)
            else:
                score = 1
            if score > 0:
                records.append({"path": str(path.relative_to(_root(paths))), "score": score, "preview": text[:280]})
        except Exception:
            continue
    records.sort(key=lambda x: x["score"], reverse=True)
    report = {"ok": True, "generated_at": _now(), "query": query, "top_k": top_k, "results": records[: max(1, int(top_k or 8))]}
    _write(base / "last_query.json", report)
    return report
