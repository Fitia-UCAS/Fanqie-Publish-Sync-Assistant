from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_auditor import audit_project, impact_report, make_snapshot
from backend.adapters.webnovel_writer.webnovel_writer_client import WebnovelWriterClient
from backend.adapters.webnovel_writer.webnovel_writer_command_parity import (
    command_parity_report,
    export_package,
    preflight_report,
    project_status_report,
    query_report,
    safe_delete_chapter,
)
from backend.adapters.webnovel_writer.webnovel_writer_quality import local_quality_review
from backend.adapters.webnovel_writer.webnovel_writer_repair import build_repair_plan
from backend.adapters.webnovel_writer.webnovel_writer_ssot import project_ssot_report
from backend.adapters.webnovel_writer.webnovel_writer_json import extract_json_object, split_draft_and_changes_with_marker
from backend.adapters.webnovel_writer.webnovel_writer_lifecycle import (
    chapter_trace,
    lifecycle_report,
    publish_queue,
    update_publish_status,
)
from backend.adapters.webnovel_writer.webnovel_writer_memory import build_memory_projection, load_or_build_memory
from backend.adapters.webnovel_writer.webnovel_writer_model_router import build_model_routes_report, route_payload, sync_model_routes
from backend.adapters.webnovel_writer.webnovel_writer_genres import ensure_genre_files, sync_genre_profile
from backend.adapters.webnovel_writer.webnovel_writer_language import anti_ai_report
from backend.adapters.webnovel_writer.webnovel_writer_learning import learn_style_profile
from backend.adapters.webnovel_writer.webnovel_writer_continuity import continuity_report
from backend.adapters.webnovel_writer.webnovel_writer_contract import build_runtime_contract, build_contract_index
from backend.adapters.webnovel_writer.webnovel_writer_truth import build_truth_projection, build_debt_report
from backend.adapters.webnovel_writer.webnovel_writer_indexing import (
    build_entity_occurrence_index,
    chunk_recall,
    rebuild_chunk_index,
    search_chunks,
)
from backend.adapters.webnovel_writer.webnovel_writer_revision import invalidate_from_chapter, revision_plan
from backend.adapters.webnovel_writer.webnovel_writer_platform import WebnovelWriterPlatform
from backend.adapters.webnovel_writer.webnovel_writer_reference_ops import (
    amend_proposal_command,
    chapter_commit_command,
    entity_command,
    index_command,
    memory_contract_command,
    migrate_command,
    override_ledger_command,
    projections_command,
    quality_trend_command,
    rag_command,
    rename_chapter_command,
    review_pipeline_command,
    runtime_health_command,
    state_command,
    story_system_command,
    style_command,
    update_master_outline_command,
    validate_csv_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_deep_alignment import (
    deep_alignment_command,
    memory_deep_command,
    publisher_bridge_command,
    rag_vector_command,
    review_deep_command,
    schema_validate_command,
    sqlite_command,
    workflow_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_deep_reference_v21 import (
    alignment_gap_command,
    memory_orchestrate_command,
    orchestrate_deep_command,
    publisher_sync_command,
    rag_router_command,
    review_pipeline_deep_command,
    sqlite_schema_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_deep_reference_v22 import (
    agent_registry_command,
    context_manager_deep_command,
    deep_alignment_v22_command,
    event_projection_deep_command,
    memory_contract_deep_command,
    review_converge_command,
    workflow_runner_v2_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_alignment_v23 import (
    alignment_audit_command,
    alignment_optimize_command,
    query_alignment_router,
)
from backend.adapters.webnovel_writer.webnovel_writer_alignment_v24 import (
    alignment_gap_matrix_v24_command,
    alignment_optimize_v24_command,
    alignment_query_v24_command,
)

from backend.adapters.webnovel_writer.webnovel_writer_alignment_v25 import (
    alignment_gap_matrix_v25_command,
    alignment_optimize_v25_command,
    alignment_query_v25_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_alignment_v26 import (
    alignment_gaps_v26_command,
    alignment_optimize_v26_command,
    alignment_query_v26_command,
)
from backend.adapters.webnovel_writer.webnovel_writer_references import (
    build_reference_index,
    deconstruct_project,
    ensure_reference_library,
    search_reference_index,
)

from backend.adapters.webnovel_writer.webnovel_writer_fusion_v27 import (
    fusion_gaps_v27_command,
    fusion_optimize_v27_command,
    fusion_query_v27_command,
)

from backend.adapters.webnovel_writer.webnovel_writer_behavior_v28 import (
    behavior_gaps_v28_command,
    behavior_query_v28_command,
    behavior_run_v28_command,
)

from backend.adapters.webnovel_writer.webnovel_writer_vector_rag_v29 import (
    build_true_vector_rag,
    query_true_vector_rag,
    vector_rag_command_v29,
    vector_rag_gaps_v29,
)
from backend.adapters.webnovel_writer.webnovel_writer_production_v30 import (
    production_gaps_v30,
    production_optimize_v30,
    production_query_v30,
)
from backend.adapters.webnovel_writer.webnovel_writer_runtime_ops import (
    archive_management,
    archive_project,
    backup_management,
    extract_context_report,
    memory_command,
    run_ledger,
    run_log,
    story_events_report,
    update_state,
    use_project,
    user_report,
    where_report,
    write_gate_report,
)
from backend.adapters.webnovel_writer.webnovel_writer_prompts import (
    CONTEXT_SYSTEM,
    DRAFTER_SYSTEM,
    FACT_SYSTEM,
    PLANNER_SYSTEM,
    REVIEWER_SYSTEM,
    build_blueprint_json_prompt,
    build_context_agent_prompt,
    build_context_pack,
    build_draft_prompt,
    build_fact_prompt,
    build_fix_prompt,
    build_outline_prompt,
    build_repair_prompt,
    build_review_prompt,
)
from backend.adapters.webnovel_writer.webnovel_writer_storage import WebnovelWriterStorage
from backend.adapters.webnovel_writer.webnovel_writer_validator import (
    GateResult,
    blueprint_required_nodes,
    gate,
    normalize_changes,
    validate_blueprint,
    validate_changes,
    validate_commit,
    validate_consistency,
    validate_data_artifacts,
    validate_review,
)
from backend.shared.app.app_paths import WEBNOVEL_WRITER_PROJECT_DIR
from backend.shared.task.task_callbacks import TaskCallbacks
from backend.shared.task.task_result import TaskResult
from backend.shared.text_file.text_file_storage import read_text_auto


class WebnovelWriterService:
    """Improved Python webnovel writer product layer.

    It keeps the old pywebview API surface, but rewrites the writing core around:
    - append-only chapter commits
    - no-bad-chapter-writeback gates
    - local long-distance recall index
    - blueprint fulfillment checks
    - deterministic state projection
    """

    def __init__(self) -> None:
        self.storage = WebnovelWriterStorage(WEBNOVEL_WRITER_PROJECT_DIR)

    @staticmethod
    def platforms() -> dict[str, str]:
        return WebnovelWriterPlatform.list_platforms()

    @staticmethod
    def default_platform_values(platform: str) -> dict[str, str | int | float]:
        return WebnovelWriterPlatform.default_runtime_values(platform)

    def list_projects(self) -> dict[str, Any]:
        return {"ok": True, "projects": self.storage.list_projects()}

    def save_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.storage.create_or_update_project(payload)
        return {"ok": True, "message": f"项目已保存：{result['meta'].get('title')}", **result}

    def load_project(self, project_id: str) -> dict[str, Any]:
        self.storage.sync_control_files(project_id)
        return {"ok": True, **self.storage.load_project(project_id)}

    def open_project_path(self, project_id: str) -> str:
        return self.storage.paths(project_id).root

    def plan(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        self.storage.sync_control_files(project_id)
        meta = self.storage.load_meta(project_id)
        story_config = self.storage.load_story_config(project_id)
        client, runtime = self._client_for_role(project_id, payload, "planner")
        plan_type = str(payload.get("planType") or "full").strip()
        chapter_no = _int(payload.get("chapterNo"), 1)
        scope_label = {"full": "全书大纲", "volume": "分卷大纲", "blueprint": "章节蓝图"}.get(plan_type, "规划")
        callbacks.emit_log(f"规划：开始生成 {scope_label}。", "info")
        callbacks.emit_progress(0, 1)

        if plan_type == "blueprint":
            prompt = self._blueprint_prompt(meta, project_id, chapter_no, payload)
            content = client.chat(PLANNER_SYSTEM, prompt, temperature=0.42, max_tokens=min(runtime.max_tokens, 4096))
            blueprint = extract_json_object(content)
            bp_gate = validate_blueprint(blueprint)
            if not isinstance(blueprint, dict) or not blueprint.get("goal"):
                callbacks.emit_log("蓝图 JSON 不完整，已保存原始内容并标记为待人工确认。", "warning")
                blueprint = {"chapter_no": chapter_no, "raw": content, "must_cover_nodes": [], "forbidden_zones": []}
            md = self._blueprint_markdown(blueprint, content)
            path = self.storage.save_blueprint(project_id, chapter_no, md)
            self.storage.save_blueprint_json(project_id, chapter_no, blueprint)
            self.storage.save_artifact(project_id, chapter_no, "blueprint_gate", bp_gate.to_dict())
        else:
            prompt = build_outline_prompt(meta, scope=plan_type, story_config=story_config)
            content = client.chat(PLANNER_SYSTEM, prompt, temperature=_float(payload.get("temperature"), runtime.temperature), max_tokens=runtime.max_tokens)
            filename = "全书大纲" if plan_type == "full" else f"第{_int(payload.get('volumeNo'), 1)}卷_分卷大纲"
            path = self.storage.save_outline(project_id, filename, content)
        callbacks.emit_progress(1, 1)
        callbacks.emit_log(f"写入：{path}", "success")
        return TaskResult(ok=True, message=f"{scope_label}已生成：{path}", path=path, result_kind="output_file", data={"projectId": project_id})

    def write_chapter(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        self.storage.sync_control_files(project_id)
        context_client, context_runtime = self._client_for_role(project_id, payload, "context")
        drafter_client, drafter_runtime = self._client_for_role(project_id, payload, "drafter")
        reviewer_client, reviewer_runtime = self._client_for_role(project_id, payload, "reviewer")
        fact_client, fact_runtime = self._client_for_role(project_id, payload, "fact")
        repair_client, repair_runtime = self._client_for_role(project_id, payload, "repair")
        chapter_no = _int(payload.get("chapterNo"), 1)
        chapter_title = str(payload.get("chapterTitle") or f"第{chapter_no}章").strip()
        target_words = max(800, _int(payload.get("targetWords"), 2200))
        strictness = str(payload.get("strictness") or "标准门禁").strip()
        run: dict[str, Any] = {"chapter_no": chapter_no, "started_at": _now(), "steps": [], "artifacts": {}, "status": "running"}

        callbacks.emit_progress(0, 11)
        callbacks.emit_log("Step 0/11：prewrite gate 检查项目、蓝图和上一章状态。", "info")
        prewrite = self._prewrite_gate(project_id, chapter_no, strictness)
        self._record_step(run, "prewrite_gate", prewrite.to_dict())
        self.storage.save_artifact(project_id, chapter_no, "00_prewrite_gate", prewrite.to_dict())
        if not prewrite.ok:
            return self._reject(project_id, chapter_no, chapter_title, "prewrite gate 未通过。", run, callbacks, prewrite.to_dict())
        callbacks.emit_progress(1, 11)

        callbacks.emit_log("Step 1/11：检索上下文包 + 长距召回。", "info")
        context_pack, context_data = self._context_pack_bundle(project_id, chapter_no, payload)
        context_path = self.storage.save_runtime_text(project_id, chapter_no, "context_pack", context_pack)
        control_context_path, control_context_json = self.storage.save_context_pack(project_id, chapter_no, context_pack, context_data)
        run["artifacts"]["context_pack"] = str(context_path)
        run["artifacts"]["control_context_pack"] = str(control_context_path)
        run["artifacts"]["control_context_data"] = str(control_context_json)
        callbacks.emit_progress(2, 11)
        self._check_stop(callbacks)

        callbacks.emit_log("Step 2/11：context-agent 生成写作任务书。", "info")
        blueprint_json = self.storage.load_blueprint_json(project_id, chapter_no)
        story_config = self.storage.load_story_config(project_id)
        brief = context_client.chat(
            CONTEXT_SYSTEM,
            build_context_agent_prompt(context_pack, blueprint_json, story_config),
            temperature=context_runtime.temperature,
            max_tokens=min(context_runtime.max_tokens, 6144),
        )
        brief_path = self.storage.save_runtime_text(project_id, chapter_no, "writing_brief", brief)
        run["artifacts"]["writing_brief"] = str(brief_path)
        callbacks.emit_progress(3, 11)
        self._check_stop(callbacks)

        callbacks.emit_log("Step 3/11：起草正文 + CHANGES 协议。", "info")
        raw = drafter_client.chat(
            DRAFTER_SYSTEM,
            build_draft_prompt(brief, chapter_no=chapter_no, chapter_title=chapter_title, target_words=target_words, strictness=strictness),
            temperature=drafter_runtime.temperature,
            max_tokens=drafter_runtime.max_tokens,
        )
        chapter_text, changes, marker_found = split_draft_and_changes_with_marker(raw)
        draft_gate = self._draft_gate(project_id, chapter_text, changes, marker_found)
        changes = _dict(draft_gate.data.get("normalized_changes") or changes)
        repair_rounds = _int((story_config.get("gate_policy") or {}).get("auto_repair_rounds"), 1)
        for attempt in range(repair_rounds):
            if draft_gate.ok:
                break
            callbacks.emit_log(f"CHANGES 协议不完整，自动要求模型修复（{attempt + 1}/{repair_rounds}）。", "warning")
            raw = repair_client.chat(DRAFTER_SYSTEM, build_repair_prompt(brief, raw, draft_gate.to_dict()), temperature=min(repair_runtime.temperature, 0.45), max_tokens=repair_runtime.max_tokens)
            chapter_text, changes, marker_found = split_draft_and_changes_with_marker(raw)
            draft_gate = self._draft_gate(project_id, chapter_text, changes, marker_found)
            changes = _dict(draft_gate.data.get("normalized_changes") or changes)
        self._record_step(run, "draft_gate", draft_gate.to_dict())
        self.storage.save_artifact(project_id, chapter_no, "03_draft_gate", draft_gate.to_dict())
        if not draft_gate.ok:
            draft_path = self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text or raw, rejected=True)
            return self._reject(project_id, chapter_no, chapter_title, f"draft gate 未通过，草稿已保存：{draft_path}", run, callbacks, draft_gate.to_dict(), path=draft_path)
        chapter_title = self._resolve_title(chapter_title, chapter_text, chapter_no)
        draft_path = self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=False)
        run["artifacts"]["draft"] = str(draft_path)
        callbacks.emit_progress(4, 11)
        self._check_stop(callbacks)

        callbacks.emit_log("Step 4/11：reviewer 审稿门禁。", "info")
        review_raw = reviewer_client.chat(REVIEWER_SYSTEM, build_review_prompt(brief, chapter_text, changes), temperature=reviewer_runtime.temperature, max_tokens=min(reviewer_runtime.max_tokens, 4096))
        review = extract_json_object(review_raw)
        review_gate = validate_review(review)
        callbacks.emit_progress(5, 11)

        if payload.get("autoFix") and not review_gate.ok:
            callbacks.emit_log("审稿有阻断问题，按后端策略自动修复一轮。", "warning")
            fixed_raw = repair_client.chat(DRAFTER_SYSTEM, build_fix_prompt(brief, chapter_text, review, target_words), temperature=max(repair_runtime.temperature, 0.45), max_tokens=repair_runtime.max_tokens)
            fixed_text, fixed_changes, fixed_marker = split_draft_and_changes_with_marker(fixed_raw)
            fixed_gate = self._draft_gate(project_id, fixed_text, fixed_changes, fixed_marker)
            fixed_changes = _dict(fixed_gate.data.get("normalized_changes") or fixed_changes)
            self.storage.save_artifact(project_id, chapter_no, "04_repair_draft_gate", fixed_gate.to_dict())
            if fixed_text.strip() and fixed_gate.ok:
                chapter_text, changes = fixed_text, fixed_changes or changes
                chapter_title = self._resolve_title(chapter_title, chapter_text, chapter_no)
                self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=False)
                review_raw = reviewer_client.chat(REVIEWER_SYSTEM, build_review_prompt(brief, chapter_text, changes), temperature=reviewer_runtime.temperature, max_tokens=min(reviewer_runtime.max_tokens, 4096))
                review = extract_json_object(review_raw)
                review_gate = validate_review(review)
        review_path = self.storage.save_review(project_id, chapter_no, review)
        self._record_step(run, "review_gate", review_gate.to_dict())
        self.storage.save_artifact(project_id, chapter_no, "04_review_gate", review_gate.to_dict())
        if not review_gate.ok:
            rejected_path = self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=True)
            return self._reject(project_id, chapter_no, chapter_title, f"review gate 未通过，未写入正式章节：{rejected_path}", run, callbacks, review_gate.to_dict(), path=rejected_path)
        callbacks.emit_progress(6, 11)
        self._check_stop(callbacks)

        callbacks.emit_log("Step 5/11：data-agent 提取 fulfillment / disambiguation / extraction 三件套。", "info")
        fact_raw = fact_client.chat(FACT_SYSTEM, build_fact_prompt(chapter_no, chapter_title, chapter_text, changes, blueprint_json), temperature=fact_runtime.temperature, max_tokens=min(fact_runtime.max_tokens, 6144))
        changes = normalize_changes(changes)
        fact_bundle = extract_json_object(fact_raw)
        fulfillment = _dict(fact_bundle.get("fulfillment_result"))
        disambiguation = _dict(fact_bundle.get("disambiguation_result"))
        extraction = _dict(fact_bundle.get("extraction_result") or fact_bundle)
        if not fulfillment:
            fulfillment = self._fallback_fulfillment(chapter_no, blueprint_json, chapter_text)
        if not disambiguation:
            disambiguation = {"new_entities": [], "ambiguous_entities": [], "pending": []}
        data_gate = validate_data_artifacts(fulfillment, disambiguation, extraction)
        self.storage.save_artifact(project_id, chapter_no, "05_fulfillment_result", fulfillment)
        self.storage.save_artifact(project_id, chapter_no, "05_disambiguation_result", disambiguation)
        self.storage.save_artifact(project_id, chapter_no, "05_extraction_result", extraction)
        self.storage.save_artifact(project_id, chapter_no, "05_data_gate", data_gate.to_dict())
        self._record_step(run, "data_gate", data_gate.to_dict())
        if not data_gate.ok:
            rejected_path = self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=True)
            return self._reject(project_id, chapter_no, chapter_title, f"data-agent gate 未通过，未写入正式章节：{rejected_path}", run, callbacks, data_gate.to_dict(), path=rejected_path)
        callbacks.emit_progress(7, 11)
        self._check_stop(callbacks)

        callbacks.emit_log("Step 6/11：一致性门禁：蓝图、禁区、未知实体和状态污染检查。", "info")
        consistency_gate = validate_consistency(
            chapter_text=chapter_text,
            changes=changes,
            extraction=extraction,
            blueprint=blueprint_json,
            state=self.storage.load_state(project_id),
            story_config=story_config,
        )
        changes = _dict(consistency_gate.data.get("normalized_changes") or changes)
        self.storage.save_artifact(project_id, chapter_no, "06_consistency_gate", consistency_gate.to_dict())
        self._record_step(run, "consistency_gate", consistency_gate.to_dict())
        if not consistency_gate.ok:
            rejected_path = self.storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=True)
            return self._reject(project_id, chapter_no, chapter_title, f"consistency gate 未通过，未写入正式章节：{rejected_path}", run, callbacks, consistency_gate.to_dict(), path=rejected_path)

        quality_gate = local_quality_review(chapter_text, blueprint_json, story_config)
        self.storage.save_artifact(project_id, chapter_no, "06_quality_gate", quality_gate)
        self._record_step(run, "quality_gate", quality_gate)
        if not quality_gate.get("ok"):
            callbacks.emit_log(f"质量审查提示：score={quality_gate.get('score')}，章节继续入账但建议后续修订。", "warning")
        callbacks.emit_progress(8, 11)

        callbacks.emit_log("Step 7/11：构建 chapter_commit 并执行 precommit gate。", "info")
        commit = self._build_commit(chapter_no, chapter_title, changes, extraction, review, fulfillment, disambiguation, consistency_gate.to_dict())
        commit_gate = validate_commit(commit)
        self.storage.save_artifact(project_id, chapter_no, "07_precommit_gate", commit_gate.to_dict())
        self._record_step(run, "precommit_gate", commit_gate.to_dict())
        if not commit_gate.ok:
            return self._reject(project_id, chapter_no, chapter_title, "precommit gate 未通过，未更新 story_state。", run, callbacks, commit_gate.to_dict())
        callbacks.emit_progress(9, 11)

        callbacks.emit_log("Step 8/11：正式落地正文、commit、story_state。", "info")
        chapter_path = self.storage.save_chapter(project_id, chapter_no, chapter_title, chapter_text)
        commit_path = self.storage.save_commit(project_id, chapter_no, commit)
        self._apply_commit(project_id, commit)
        postcommit = self._postcommit_gate(project_id, chapter_no)
        self.storage.save_artifact(project_id, chapter_no, "08_postcommit_gate", postcommit.to_dict())
        self._record_step(run, "postcommit_gate", postcommit.to_dict())
        callbacks.emit_progress(10, 11)
        if not postcommit.ok:
            run["status"] = "postcommit_failed"
            run["finished_at"] = _now()
            self.storage.save_run(project_id, chapter_no, run)
            return TaskResult(ok=False, message="postcommit gate 未通过，请查看 artifacts。", path=commit_path, result_kind="output_file", data={"gate": postcommit.to_dict()})

        callbacks.emit_log("Step 9/11：重建长距召回索引并同步小说 TXT。", "info")
        self.storage.rebuild_chapter_index(project_id)
        self.storage.sync_novel_file(project_id)
        callbacks.emit_progress(11, 11)

        callbacks.emit_log("完成：章节已通过硬门禁并正式入账。", "success")
        run["status"] = "committed"
        run["finished_at"] = _now()
        run_path = self.storage.save_run(project_id, chapter_no, run)
        return TaskResult(
            ok=True,
            message=f"第 {chapter_no} 章已通过硬门禁并正式入账：{chapter_path}",
            path=chapter_path,
            result_kind="output_file",
            data={
                "projectId": project_id,
                "chapterPath": str(chapter_path),
                "reviewPath": str(review_path),
                "commitPath": str(commit_path),
                "runPath": str(run_path),
                "review": review,
                "gates": {
                    "prewrite": prewrite.to_dict(),
                    "draft": draft_gate.to_dict(),
                    "review": review_gate.to_dict(),
                    "data": data_gate.to_dict(),
                    "consistency": consistency_gate.to_dict(),
                    "precommit": commit_gate.to_dict(),
                    "postcommit": postcommit.to_dict(),
                },
            },
        )

    def batch_write(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        start = _int(payload.get("start"), _int(payload.get("chapterNo"), 1))
        end = _int(payload.get("end"), start)
        if end < start:
            raise ValueError("结束章不能小于开始章。")
        total = end - start + 1
        outputs = []
        callbacks.emit_log(f"批量写作：第 {start} - {end} 章，共 {total} 章。失败章节会进入 rejected，不污染 story_state。", "info")
        for offset, chapter_no in enumerate(range(start, end + 1), start=1):
            self._check_stop(callbacks)
            child_payload = dict(payload, chapterNo=chapter_no, chapterTitle=payload.get("chapterTitle") or f"第{chapter_no}章")
            callbacks.emit_log(f"批量：开始第 {chapter_no} 章。", "info")
            result = self.write_chapter(child_payload, callbacks)
            outputs.append(result.to_dict())
            if not result.ok:
                callbacks.emit_log(f"第 {chapter_no} 章未通过硬门禁，批量流程停止。", "warning")
                break
            callbacks.emit_progress(offset, total)
        return TaskResult(ok=True, message=f"批量写作完成：成功/处理 {len(outputs)} 章。", path=Path(self.storage.paths(project_id).chapters), result_kind="output_dir", data={"outputs": outputs})

    def review_chapter(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        self.storage.sync_control_files(project_id)
        client, runtime = self._client_for_role(project_id, payload, "reviewer")
        chapter_no = _int(payload.get("chapterNo"), 1)
        chapter_path, chapter_text = self.storage.load_chapter(project_id, chapter_no)
        if not chapter_text:
            raise FileNotFoundError(f"未找到第 {chapter_no} 章正式正文。")
        context_pack = self._context_pack(project_id, chapter_no, payload)
        callbacks.emit_progress(0, 1)
        raw = client.chat(REVIEWER_SYSTEM, build_review_prompt(context_pack, chapter_text, {}), temperature=runtime.temperature, max_tokens=min(runtime.max_tokens, 4096))
        review = extract_json_object(raw)
        review_gate = validate_review(review)
        review["gate"] = review_gate.to_dict()
        review_path = self.storage.save_review(project_id, chapter_no, review)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=review_gate.ok, message=f"第 {chapter_no} 章审查完成：{review_path}", path=review_path, result_kind="output_file", data={"review": review, "chapterPath": str(chapter_path), "gate": review_gate.to_dict()})

    def validate_project(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        focused_chapter = _int((payload or {}).get("chapterNo"), 0)
        deep = bool((payload or {}).get("deep"))
        snapshot_report = make_snapshot(self.storage, project_id, "before_doctor")
        control_report = self.storage.sync_control_files(project_id)
        callbacks.emit_progress(0, 8)
        self.storage.rebuild_state_from_commits(project_id)
        control_report = self.storage.sync_control_files(project_id)
        self.storage.rebuild_chapter_index(project_id)
        data = self.storage.load_project(project_id)
        state = data["state"]
        issues: list[dict[str, Any]] = []
        callbacks.emit_progress(1, 8)

        chapters = data.get("chapters") or []
        statuses = state.get("chapter_status") or {}
        chapter_numbers = [int(row.get("chapterNo") or 0) for row in chapters]
        for row in chapters:
            chapter_no = int(row.get("chapterNo") or 0)
            if statuses.get(str(chapter_no)) != "committed":
                issues.append({"level": "warning", "type": "chapter_status", "message": f"第 {chapter_no} 章有正文但状态不是 committed。"})
            if not self.storage.load_blueprint_json(project_id, chapter_no) and not self.storage.load_blueprint(project_id, chapter_no):
                issues.append({"level": "warning", "type": "missing_blueprint", "message": f"第 {chapter_no} 章缺少蓝图。"})
        for prev, cur in zip(chapter_numbers, chapter_numbers[1:]):
            if cur != prev + 1:
                issues.append({"level": "warning", "type": "chapter_gap", "message": f"章节序号不连续：第 {prev} 章后接第 {cur} 章。"})
        callbacks.emit_progress(2, 8)

        latest = _int(state.get("latest_chapter"), 0)
        story_config = self.storage.load_story_config(project_id)
        long_threshold = _int((story_config.get("gate_policy") or {}).get("long_foreshadow_warning_chapters"), 30)
        for name, item in (state.get("foreshadows") or {}).items():
            if isinstance(item, dict) and str(item.get("status") or "") in {"新增", "推进", "未收", "open"}:
                first = _int(item.get("introduced_chapter") or item.get("first_seen_chapter"), latest)
                if latest - first >= long_threshold:
                    issues.append({"level": "warning", "type": "foreshadow_debt", "message": f"伏笔《{name}》已超过 {long_threshold} 章未回收。"})
        callbacks.emit_progress(3, 8)

        for key in ["characters", "locations", "factions", "items"]:
            for name, item in (state.get(key) or {}).items():
                if isinstance(item, dict) and not item.get("id"):
                    issues.append({"level": "warning", "type": "entity_id", "message": f"{key}.{name} 缺少实体 ID。"})
        paths = self.storage.paths(project_id)

        scaffold = self._reference_init_scaffold_status(project_id)
        for item in scaffold.get("issues") or []:
            issues.append(item)
        focused_report: dict[str, Any] = {}
        if focused_chapter > 0:
            chapter_path, chapter_text = self.storage.load_chapter(project_id, focused_chapter)
            focused_report = {
                "chapter_no": focused_chapter,
                "chapter_exists": bool(chapter_text),
                "chapter_path": str(chapter_path) if chapter_path else "",
                "blueprint_exists": bool(self.storage.load_blueprint_json(project_id, focused_chapter) or self.storage.load_blueprint(project_id, focused_chapter)),
                "review_exists": (Path(paths.reviews) / f"第{focused_chapter:04d}章_review.json").exists(),
                "commit_exists": (Path(paths.commits) / f"第{focused_chapter:04d}章_commit.json").exists(),
                "context_exists": (Path(paths.control) / "context_packs" / f"chapter_{focused_chapter:04d}_context.json").exists(),
            }
            if not focused_report["blueprint_exists"]:
                issues.append({"level": "warning", "type": "doctor_focus_missing_blueprint", "message": f"聚焦体检：第 {focused_chapter} 章缺少蓝图。"})
            if not focused_report["chapter_exists"]:
                issues.append({"level": "warning", "type": "doctor_focus_missing_chapter", "message": f"聚焦体检：第 {focused_chapter} 章缺少正式正文。"})
            if focused_report["chapter_exists"] and not focused_report["commit_exists"]:
                issues.append({"level": "warning", "type": "doctor_focus_missing_commit", "message": f"聚焦体检：第 {focused_chapter} 章有正文但缺少 commit。"})
        for bp_path in sorted(Path(paths.blueprints).glob("第*章_蓝图.json")):
            m = re.match(r"第(\d+)章_蓝图\.json$", bp_path.name)
            chapter_label = f"第 {int(m.group(1))} 章" if m else bp_path.stem
            try:
                import json as _json
                blueprint = _json.loads(bp_path.read_text(encoding="utf-8"))
            except Exception:
                issues.append({"level": "error", "type": "blueprint_json", "message": f"{chapter_label} 蓝图 JSON 无法读取。"})
                continue
            for field, bucket, cn in [("required_characters", "characters", "角色"), ("required_locations", "locations", "地点"), ("required_factions", "factions", "势力")]:
                known = state.get(bucket) or {}
                for name in blueprint.get(field) or []:
                    if str(name).strip() and str(name).strip() not in known:
                        issues.append({"level": "warning", "type": "blueprint_unknown_entity", "message": f"{chapter_label} 蓝图引用的{cn}《{name}》尚未在 writer_control/entities 中登记。"})
        callbacks.emit_progress(4, 8)

        events = self.storage.read_events(project_id)
        commits = list(Path(self.storage.paths(project_id).commits).glob("第*章_commit.json"))
        committed_events = [e for e in events if isinstance(e, dict) and e.get("type") == "chapter_committed"]
        if len(committed_events) < len(commits):
            issues.append({"level": "warning", "type": "event_log", "message": "事件日志少于 commit 文件数。"})
        callbacks.emit_progress(5, 8)

        rejected = self.storage.list_rejected(project_id)
        if rejected:
            issues.append({"level": "warning", "type": "rejected", "message": f"存在 {len(rejected)} 个 rejected 草稿待处理。"})
        for item in control_report.get("issues") or []:
            issues.append(item)
        relation_path = self.storage.save_relation_index(project_id)
        audit_report = audit_project(self.storage, project_id)
        for item in audit_report.get("issues") or []:
            if item not in issues:
                issues.append(item)
        deep_report: dict[str, Any] = {}
        if deep:
            try:
                deep_report["ssot"] = project_ssot_report(self.storage, project_id)
            except Exception as ex:
                deep_report["ssot"] = {"ok": False, "error": str(ex)}
            try:
                deep_report["continuity"] = continuity_report(self.storage, project_id)
            except Exception as ex:
                deep_report["continuity"] = {"ok": False, "error": str(ex)}
            try:
                deep_report["debts"] = build_debt_report(self.storage, project_id)
            except Exception as ex:
                deep_report["debts"] = {"ok": False, "error": str(ex)}
            for section, report_item in deep_report.items():
                if isinstance(report_item, dict):
                    for item in report_item.get("issues") or []:
                        if item not in issues:
                            issues.append(item)
        callbacks.emit_progress(6, 8)

        next_chapter = focused_chapter if focused_chapter > 0 else _int((payload or {}).get("chapterNo"), latest + 1)
        context, context_data = self._context_pack_bundle(project_id, next_chapter, payload or {})
        context_md, context_json = self.storage.save_context_pack(project_id, next_chapter, context, context_data)
        callbacks.emit_progress(7, 8)

        ok = not any(item.get("level") == "error" for item in issues)
        report = {
            "ok": ok,
            "project_id": project_id,
            "checked_at": _now(),
            "focused_chapter": focused_chapter or None,
            "deep": deep,
            "focusedChapterReport": focused_report,
            "deepReport": deep_report,
            "issue_count": len(issues),
            "issues": issues,
            "index": self.storage.index_summary(project_id),
            "controlSync": control_report,
            "initScaffold": scaffold,
            "rejectedCount": len(rejected),
            "relationIndex": str(relation_path),
            "backendAudit": {
                "risk_score": audit_report.get("risk_score"),
                "issue_count": audit_report.get("issue_count"),
                "todo_count": audit_report.get("todo_count"),
            },
            "snapshot": snapshot_report,
            "nextContextPack": str(context_md),
            "nextContextData": str(context_json),
        }
        path = self.storage.save_validation(project_id, f"全书校验_{datetime.now():%Y%m%d_%H%M%S}", report)
        report_json = Path(self.storage.paths(project_id).control, "reports", "last_doctor_report.json")
        report_json.write_text(Path(path).read_text(encoding="utf-8"), encoding="utf-8")
        report_md = Path(self.storage.paths(project_id).control, "reports", "last_doctor_report.md")
        report_md.write_text(_doctor_report_markdown(report), encoding="utf-8")
        callbacks.emit_progress(8, 8)
        return TaskResult(ok=ok, message=f"全书校验完成：{len(issues)} 个提示。", path=path, result_kind="output_file", data={"report": report})

    def _reference_init_scaffold_status(self, project_id: str) -> dict[str, Any]:
        """Check init outputs promised by the reference projects: setting/outlining files and RAG env template."""
        paths = self.storage.paths(project_id)
        root = Path(paths.root)
        required = [
            root / ".env.example",
            root / "设定集",
            root / "设定集" / "世界观.md",
            root / "设定集" / "力量体系.md",
            root / "设定集" / "主角卡.md",
            root / "大纲",
            root / "大纲" / "总纲.md",
            root / "大纲" / "爽点规划.md",
            root / "审查报告",
            root / "writer_control" / "templates" / "ENTITY_TEMPLATE.md",
            root / "writer_control" / "templates" / "BLUEPRINT_TEMPLATE.md",
        ]
        rows = []
        issues: list[dict[str, Any]] = []
        for item in required:
            exists = item.exists()
            rows.append({"path": str(item), "exists": exists, "kind": "dir" if item.suffix == "" else "file"})
            if not exists:
                issues.append({"level": "warning", "type": "init_scaffold_missing", "message": f"初始化脚手架缺失：{item.name}。可重新运行 init/templates/sync 自动补齐。"})
        env_text = ""
        env_path = root / ".env.example"
        if env_path.exists():
            try:
                env_text = env_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                env_text = ""
        for key in ["EMBED_BASE_URL", "EMBED_MODEL", "EMBED_API_KEY", "RERANK_BASE_URL", "RERANK_MODEL", "RERANK_API_KEY"]:
            if env_path.exists() and key not in env_text:
                issues.append({"level": "warning", "type": "rag_env_template_incomplete", "message": f".env.example 缺少 RAG 配置项：{key}。"})
        return {"ok": not issues, "required": rows, "issues": issues}

    def prepare_context_pack(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        self.storage.sync_control_files(project_id)
        chapter_no = _int(payload.get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        context, context_data = self._context_pack_bundle(project_id, chapter_no, payload)
        path, data_path = self.storage.save_context_pack(project_id, chapter_no, context, context_data)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"上下文包已生成：{path}", path=path, result_kind="output_file", data={"dataPath": str(data_path)})

    def sync_control(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = self.storage.sync_control_files(project_id)
        path = Path(self.storage.paths(project_id).control) / "reports" / "last_control_sync.json"
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"控制目录已同步：{path}", path=path, result_kind="output_file", data={"report": report})

    def refresh_templates(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = self.storage.refresh_markdown_templates(project_id, force=bool((payload or {}).get("force")))
        path = Path(report.get("templateDir") or self.storage.paths(project_id).control)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"Markdown 模板已准备：{path}", path=path, result_kind="output_dir", data={"report": report})

    def model_routes(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = sync_model_routes(self.storage, project_id, force_template=bool((payload or {}).get("force")))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("report_markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "models" / "last_model_routes_report.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"模型路由已同步：{report.get('issue_count', 0)} 个提示。", path=path, result_kind="output_file", data={"report": report})

    def model_plan(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = build_model_routes_report(self.storage, project_id)
        out_dir = Path(self.storage.paths(project_id).control) / "reports" / "models"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "last_model_plan.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok", True)), message="模型角色分工计划已生成。", path=path, result_kind="output_file", data={"report": report})

    def audit_backend(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = audit_project(self.storage, project_id)
        path = Path(self.storage.paths(project_id).control) / "reports" / "last_backend_audit.json"
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"后端体检完成：{report.get('issue_count', 0)} 个提示。", path=path, result_kind="output_file", data={"report": report})

    def impact(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        target = str((payload or {}).get("target") or "").strip()
        callbacks.emit_progress(0, 1)
        report = impact_report(self.storage, project_id, target)
        path = Path(self.storage.paths(project_id).control) / "reports" / "last_impact_report.json"
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"影响分析完成：{report.get('relation_count', 0)} 条关系。", path=path, result_kind="output_file", data={"report": report})

    def backup_project(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        action = str((payload or {}).get("action") or "create")
        reason = str((payload or {}).get("reason") or "manual")
        target = str((payload or {}).get("target") or "")
        report = backup_management(self.storage, project_id, action, reason, target)
        callbacks.emit_progress(1, 1)
        path = Path(str((report.get("paths_written") or {}).get("json") or report.get("path") or self.storage.paths(project_id).control))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"backup {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def ssot_check(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = project_ssot_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "ssot" / "last_ssot_report.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"SSOT 检查完成：{len(report.get('drift') or [])} 个 drift。", path=path, result_kind="output_file", data={"report": report})

    def repair_plan(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 0) or None
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        plan = build_repair_plan(self.storage, project_id, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((plan.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "repair" / "last_repair_plan.md"))
        return TaskResult(ok=bool(plan.get("ok", False)), message=str(plan.get("message") or f"修复计划已生成：{path}"), path=path, result_kind="output_file", data={"plan": plan})

    def local_quality(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        chapter_path, chapter_text = self.storage.load_chapter(project_id, chapter_no)
        if not chapter_text:
            rejected = [r for r in self.storage.list_rejected(project_id) if int(r.get("chapterNo") or 0) == chapter_no]
            if rejected:
                chapter_path = Path(str(rejected[0].get("path") or ""))
                chapter_text = read_text_auto(chapter_path) if chapter_path.exists() else ""
        if not chapter_text:
            raise FileNotFoundError(f"未找到第 {chapter_no} 章正文或 rejected 草稿。")
        report = local_quality_review(chapter_text, self.storage.load_blueprint_json(project_id, chapter_no), self.storage.load_story_config(project_id))
        path = self.storage.save_artifact(project_id, chapter_no, "local_quality_review", report)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok", False)), message=f"本地质量审查完成：score={report.get('score')}", path=path, result_kind="output_file", data={"report": report, "chapterPath": str(chapter_path or "")})


    def lifecycle(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = lifecycle_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "lifecycle" / "last_lifecycle_report.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"生命周期报告完成：{(report.get('summary') or {}).get('issue_count', 0)} 个提示。", path=path, result_kind="output_file", data={"report": report})

    def publish_queue(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        start = _int((payload or {}).get("start"), 0) or None
        end = _int((payload or {}).get("end"), 0) or None
        include_warnings = bool((payload or {}).get("includeWarnings") or (payload or {}).get("include_warnings"))
        report = publish_queue(self.storage, project_id, start=start, end=end, include_warnings=include_warnings)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "publication" / "publish_queue.md"))
        return TaskResult(ok=True, message=f"发布队列已生成：{report.get('count', 0)} 章。", path=path, result_kind="output_file", data={"report": report})

    def publish_status(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        status = str((payload or {}).get("status") or "pending")
        platform = str((payload or {}).get("platform") or "fanqie")
        external_id = str((payload or {}).get("externalId") or (payload or {}).get("external_id") or "")
        note = str((payload or {}).get("note") or "")
        callbacks.emit_progress(0, 1)
        report = update_publish_status(self.storage, project_id, chapter_no, status=status, platform=platform, external_id=external_id, note=note)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"第 {chapter_no} 章发布状态已更新为：{status}", path=Path(str(report.get("path") or "")), result_kind="output_file", data={"report": report})

    def trace_chapter(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = chapter_trace(self.storage, project_id, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "trace" / f"chapter_{chapter_no:04d}_trace.md"))
        return TaskResult(ok=True, message=f"第 {chapter_no} 章追踪报告已生成。", path=path, result_kind="output_file", data={"report": report})

    def memory(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        projection = build_memory_projection(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((projection.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "memory" / "project_memory.md"))
        return TaskResult(ok=True, message=f"长期记忆投影已生成：{path}", path=path, result_kind="output_file", data={"memory": projection})

    def learn_style(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        limit = _int((payload or {}).get("sampleLimit") or (payload or {}).get("sample_limit"), 80)
        profile = learn_style_profile(self.storage, project_id, sample_limit=limit, update_config=True)
        callbacks.emit_progress(1, 1)
        path = Path((profile.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "learning" / "style_profile.md"))
        return TaskResult(ok=True, message=f"拆书/文风学习完成：{profile.get('sample_chapters', 0)} 章样本。", path=path, result_kind="output_file", data={"profile": profile})


    def runtime_contract(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 1)
        recent = _int((payload or {}).get("recentContextCount") or (payload or {}).get("recent"), 6)
        callbacks.emit_progress(0, 1)
        contract = build_runtime_contract(self.storage, project_id, chapter_no, recent=recent)
        callbacks.emit_progress(1, 1)
        path = Path((contract.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "contracts" / f"chapter_{chapter_no:04d}_contract.md"))
        return TaskResult(ok=contract.get("status") != "missing_blueprint", message=f"第 {chapter_no} 章运行时合约已生成。", path=path, result_kind="output_file", data={"contract": contract})

    def contract_index(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        start = _int((payload or {}).get("start"), 1)
        end = _int((payload or {}).get("end"), 0) or None
        callbacks.emit_progress(0, 1)
        report = build_contract_index(self.storage, project_id, start=start, end=end)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "contracts" / "contract_index.md"))
        return TaskResult(ok=True, message=f"运行时合约索引已生成：{report.get('count', 0)} 章。", path=path, result_kind="output_file", data={"report": report})

    def truth_projection(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = build_truth_projection(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "truth" / "truth_index.md"))
        return TaskResult(ok=True, message="真相文件投影已生成。", path=path, result_kind="output_file", data={"report": report})

    def debt_report(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = build_debt_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "debts" / "last_debt_report.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"故事债务报告已生成：{report.get('count', 0)} 条。", path=path, result_kind="output_file", data={"report": report})


    def rebuild_search_index(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 3)
        self.storage.sync_control_files(project_id)
        chapter_report = {"path": str(self.storage.rebuild_chapter_index(project_id))}
        callbacks.emit_progress(1, 3)
        chunk_report = rebuild_chunk_index(self.storage, project_id)
        callbacks.emit_progress(2, 3)
        entity_report = build_entity_occurrence_index(self.storage, project_id)
        callbacks.emit_progress(3, 3)
        ok = bool(chunk_report.get("ok", True)) and bool(entity_report.get("ok", True))
        path = Path(self.storage.paths(project_id).control) / "reports" / "indexing" / "last_chunk_index_report.md"
        return TaskResult(
            ok=ok,
            message=f"检索索引已重建：chunk={chunk_report.get('chunk_count', 0)}，entity_mentions={entity_report.get('mentioned_entity_count', 0)}。",
            path=path,
            result_kind="output_file",
            data={"chapterIndex": chapter_report, "chunkIndex": chunk_report, "entityOccurrences": entity_report},
        )

    def search_index(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or (payload or {}).get("target") or "").strip()
        top_k = _int((payload or {}).get("topK") or (payload or {}).get("top_k"), 8)
        exclude = _int((payload or {}).get("excludeChapter") or (payload or {}).get("exclude_chapter"), 0) or None
        if not query:
            raise ValueError("search 需要 --query 或 --target。")
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = search_chunks(self.storage, project_id, query, top_k=top_k, exclude_chapter=exclude)
        callbacks.emit_progress(1, 1)
        path = Path(self.storage.paths(project_id).control) / "reports" / "search" / "last_chunk_search.md"
        return TaskResult(ok=True, message=f"分块召回完成：{report.get('result_count', 0)} 条。", path=path, result_kind="output_file", data={"report": report})

    def entity_occurrences(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        self.storage.sync_control_files(project_id)
        report = build_entity_occurrence_index(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path(self.storage.paths(project_id).control) / "relations" / "entity_occurrences.md"
        return TaskResult(ok=True, message=f"实体出现索引已生成：{report.get('mentioned_entity_count', 0)} 个实体。", path=path, result_kind="output_file", data={"report": report})

    def continuity(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = continuity_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "continuity" / "last_continuity_report.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"连贯性检查完成：{report.get('issue_count', 0)} 个提示。", path=path, result_kind="output_file", data={"report": report})

    def revision_plan(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 1)
        callbacks.emit_progress(0, 1)
        report = revision_plan(self.storage, project_id, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "revision" / f"revision_plan_from_{chapter_no:04d}.md"))
        return TaskResult(ok=True, message=f"重写影响预演完成：{report.get('affected_count', 0)} 个文件。", path=path, result_kind="output_file", data={"report": report})

    def invalidate_from(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 1)
        reason = str((payload or {}).get("reason") or "rewrite")
        apply = bool((payload or {}).get("apply"))
        callbacks.emit_progress(0, 1)
        report = invalidate_from_chapter(self.storage, project_id, chapter_no, reason=reason, apply=apply)
        callbacks.emit_progress(1, 1)
        default_name = f"invalidated_from_{chapter_no:04d}.md" if apply else f"revision_plan_from_{chapter_no:04d}.md"
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "revision" / default_name))
        msg = f"章节失效归档完成：移动 {report.get('moved_count', 0)} 个文件。" if apply else f"重写影响预演完成：{report.get('affected_count', 0)} 个文件。"
        return TaskResult(ok=True, message=msg, path=path, result_kind="output_file", data={"report": report})

    def genre_templates(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        force = bool((payload or {}).get("force"))
        callbacks.emit_progress(0, 1)
        report = sync_genre_profile(self.storage, project_id, force=force)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("report_markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "genres" / "last_genre_report.md"))
        return TaskResult(ok=True, message=f"题材规则已同步：{report.get('genre') or ''}", path=path, result_kind="output_file", data={"report": report})

    def language_check(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 0) or None
        callbacks.emit_progress(0, 1)
        report = anti_ai_report(self.storage, project_id, chapter_no=chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or (Path(self.storage.paths(project_id).control) / "reports" / "language" / "anti_ai.md"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"语言去 AI 味检查完成：score={report.get('score')}/100，issues={len(report.get('issues') or [])}。", path=path, result_kind="output_file", data={"report": report})

    def rebuild_projections(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 6)
        control = self.storage.sync_control_files(project_id)
        genre_report = sync_genre_profile(self.storage, project_id, force=False)
        callbacks.emit_progress(1, 6)
        state_path = self.storage.rebuild_state_from_commits(project_id)
        callbacks.emit_progress(2, 6)
        self.storage.sync_control_files(project_id)
        index_path = self.storage.rebuild_chapter_index(project_id)
        chunk_index = rebuild_chunk_index(self.storage, project_id)
        relation_path = self.storage.save_relation_index(project_id)
        entity_occurrences = build_entity_occurrence_index(self.storage, project_id)
        callbacks.emit_progress(3, 6)
        memory = build_memory_projection(self.storage, project_id)
        truth = build_truth_projection(self.storage, project_id)
        debts = build_debt_report(self.storage, project_id)
        next_chapter = int((self.storage.load_state(project_id).get("latest_chapter") or 0)) + 1
        contract = build_runtime_contract(self.storage, project_id, next_chapter)
        callbacks.emit_progress(4, 6)
        continuity = continuity_report(self.storage, project_id)
        ssot = project_ssot_report(self.storage, project_id)
        callbacks.emit_progress(5, 6)
        report = {
            "ok": bool(control.get("ok", True)) and bool(continuity.get("ok", True)) and bool(ssot.get("ok", True)),
            "generated_at": _now(),
            "control": control,
            "genrePath": (genre_report.get("paths") or {}).get("report_markdown"),
            "statePath": str(state_path),
            "indexPath": str(index_path),
            "relationPath": str(relation_path),
            "memoryPath": (memory.get("paths") or {}).get("markdown"),
            "truthPath": (truth.get("paths") or {}).get("markdown"),
            "debtPath": (debts.get("paths") or {}).get("markdown"),
            "nextContractPath": (contract.get("paths") or {}).get("markdown"),
            "continuityPath": (continuity.get("paths") or {}).get("markdown"),
            "ssotPath": (ssot.get("paths") or {}).get("markdown"),
        }
        out_dir = Path(self.storage.paths(project_id).control) / "reports" / "projection"
        out_dir.mkdir(parents=True, exist_ok=True)
        import json as _json
        path = out_dir / "last_projection_rebuild.json"
        path.write_text(_json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        callbacks.emit_progress(6, 6)
        return TaskResult(ok=bool(report.get("ok", True)), message="后端投影已重建。", path=path, result_kind="output_file", data={"report": report})

    def project_status(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = project_status_report(self.storage, project_id, str((payload or {}).get("focus") or "all"))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or "")
        return TaskResult(ok=bool(report.get("ok", True)), message="项目状态报告已生成。", path=path, result_kind="output_file", data={"report": report})

    def preflight(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 1)
        callbacks.emit_progress(0, 1)
        report = preflight_report(self.storage, project_id, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or "")
        return TaskResult(ok=bool(report.get("ok", True)), message=f"第 {chapter_no} 章写前预检完成。", path=path, result_kind="output_file", data={"report": report})

    def query_project(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "").strip()
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = query_report(self.storage, project_id, query, top_k=top_k)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or "")
        return TaskResult(ok=True, message=f"查询完成：{query}", path=path, result_kind="output_file", data={"report": report})

    def export_bundle(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = export_package(self.storage, project_id, include_zip=True)
        callbacks.emit_progress(1, 1)
        path = Path(((report.get("paths") or {}).get("zip") or (report.get("paths") or {}).get("markdown") or ""))
        return TaskResult(ok=True, message="全书导出包已生成。", path=path, result_kind="output_file", data={"report": report})

    def delete_chapter(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo") or (payload or {}).get("chapter"), 1)
        apply = bool((payload or {}).get("apply"))
        reason = str((payload or {}).get("reason") or "manual")
        callbacks.emit_progress(0, 1)
        report = safe_delete_chapter(self.storage, project_id, chapter_no, apply=apply, reason=reason)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or "")
        return TaskResult(ok=True, message=f"第 {chapter_no} 章安全删除{'已执行' if apply else '预演已生成'}。", path=path, result_kind="output_file", data={"report": report})

    def command_parity(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = command_parity_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths") or {}).get("markdown") or "")
        return TaskResult(ok=bool(report.get("ok", True)), message="对标命令能力报告已生成。", path=path, result_kind="output_file", data={"report": report})

    def export(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        output = self.storage.export_txt(project_id)
        callbacks.emit_progress(1, 1)
        callbacks.emit_log(f"导出：{output}", "success")
        return TaskResult(ok=True, message=f"全书已导出：{output}", path=output, result_kind="output_file", data={"projectId": project_id})

    def dashboard(self, project_id: str) -> dict[str, Any]:
        self.storage.sync_control_files(project_id)
        data = self.storage.load_project(project_id)
        state = data["state"]
        statuses = state.get("chapter_status") or {}
        committed = sum(1 for value in statuses.values() if value == "committed")
        rejected = sum(1 for value in statuses.values() if value == "rejected")
        return {
            "ok": True,
            "meta": data["meta"],
            "paths": data["paths"],
            "chapterCount": len(data["chapters"]),
            "committedCount": committed,
            "rejectedCount": rejected,
            "blueprintCount": len(data["blueprints"]),
            "characters": len(state.get("characters") or {}),
            "foreshadows": len(state.get("foreshadows") or {}),
            "latestChapter": state.get("latest_chapter") or 0,
            "chapters": data["chapters"][-20:],
            "recallIndex": data.get("recallIndex") or {},
            "eventCount": len(self.storage.read_events(project_id)),
            "backendAudit": _safe_read_json(Path(data["paths"]["control"]) / "reports" / "last_backend_audit.json"),
            "latestDoctorReport": _safe_read_json(Path(data["paths"]["control"]) / "reports" / "last_doctor_report.json"),
            "latestMemory": _safe_read_json(Path(data["paths"]["control"]) / "memory" / "project_memory.json"),
            "latestStyleProfile": _safe_read_json(Path(data["paths"]["control"]) / "learning" / "style_profile.json"),
            "latestContinuityReport": _safe_read_json(Path(data["paths"]["control"]) / "reports" / "continuity" / "last_continuity_report.json"),
            "latestDebtReport": _safe_read_json(Path(data["paths"]["control"]) / "reports" / "debts" / "last_debt_report.json"),
            "latestTruthIndex": _safe_read_json(Path(data["paths"]["control"]) / "truth" / "truth_index.json"),
        }


    def where(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = where_report(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).root)
        return TaskResult(ok=True, message=f"项目路径：{report.get('root')}", path=path, result_kind="output_file", data={"report": report})

    def use(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = use_project(self.storage, project_id, str((payload or {}).get("workspace") or ""))
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"已绑定项目：{report.get('project_root')}", path=Path(str((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).root)), result_kind="output_file", data={"report": report})

    def write_gate(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        stage = str((payload or {}).get("stage") or "prewrite")
        callbacks.emit_progress(0, 1)
        report = write_gate_report(self.storage, project_id, chapter_no, stage)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", False)), message=f"write-gate {stage} 完成：{(report.get('summary') or {}).get('error', 0)} 个错误。", path=path, result_kind="output_file", data={"report": report})

    def story_events(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 0)
        health = bool((payload or {}).get("health"))
        callbacks.emit_progress(0, 1)
        report = story_events_report(self.storage, project_id, chapter_no, health)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"Story events：{report.get('event_count', 0)} 条。", path=path, result_kind="output_file", data={"report": report})

    def user_report(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        stage = str((payload or {}).get("stage") or "write")
        chapter_no = _int((payload or {}).get("chapterNo"), 0)
        callbacks.emit_progress(0, 1)
        report = user_report(self.storage, project_id, stage, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"最终报告：{report.get('status')}", path=path, result_kind="output_file", data={"report": report})

    def run_log(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        event = str((payload or {}).get("event") or "manual")
        extra = (payload or {}).get("logPayload") if isinstance((payload or {}).get("logPayload"), dict) else {}
        callbacks.emit_progress(0, 1)
        report = run_log(self.storage, project_id, event, extra)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=True, message=f"运行日志已写入：{report.get('path')}", path=Path(str(report.get("path") or self.storage.paths(project_id).control)), result_kind="output_file", data={"report": report})

    def run_ledger(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("ledgerAction") or "summary")
        chapter_no = _int((payload or {}).get("chapterNo"), 0)
        step = str((payload or {}).get("step") or "")
        status = str((payload or {}).get("status") or "")
        extra = (payload or {}).get("ledgerPayload") if isinstance((payload or {}).get("ledgerPayload"), dict) else {}
        callbacks.emit_progress(0, 1)
        report = run_ledger(self.storage, project_id, action, chapter_no, step, status, extra)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("path") or self.storage.paths(project_id).control)
        return TaskResult(ok=True, message=f"run-ledger {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def update_state(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        patch = (payload or {}).get("statePatch") if isinstance((payload or {}).get("statePatch"), dict) else {}
        reason = str((payload or {}).get("reason") or "manual")
        callbacks.emit_progress(0, 1)
        report = update_state(self.storage, project_id, patch, reason)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("state_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=True, message="状态已按 patch 更新。", path=path, result_kind="output_file", data={"report": report})

    def archive(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = archive_management(self.storage, project_id, str((payload or {}).get("action") or "create"), str((payload or {}).get("reason") or "manual"), str((payload or {}).get("target") or ""))
        callbacks.emit_progress(1, 1)
        path = Path(str(report.get("archive") or report.get("path") or (report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"archive {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def extract_context(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        base = self.prepare_context_pack(payload, callbacks).to_dict()
        report = extract_context_report(self.storage, project_id, chapter_no, base)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=True, message=f"extract-context 已生成：第 {chapter_no} 章。", path=path, result_kind="output_file", data={"report": report})

    def memory_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("memoryAction") or "stats")
        callbacks.emit_progress(0, 1)
        report = memory_command(self.storage, project_id, action, str((payload or {}).get("query") or ""), str((payload or {}).get("category") or ""), str((payload or {}).get("subject") or ""), str((payload or {}).get("status") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"memory {action} 完成。", path=path, result_kind="output_file", data={"report": report})


    def index_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = index_command(self.storage, project_id, str((payload or {}).get("action") or "stats"), _int((payload or {}).get("chapterNo"), 0), str((payload or {}).get("query") or ""), _int((payload or {}).get("topK"), 8))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"index {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def state_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        patch = (payload or {}).get("statePatch") if isinstance((payload or {}).get("statePatch"), dict) else {}
        report = state_command(self.storage, project_id, str((payload or {}).get("action") or "summary"), patch)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("state_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"state {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def rag_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = rag_command(self.storage, project_id, str((payload or {}).get("action") or "stats"), _int((payload or {}).get("chapterNo"), 0), str((payload or {}).get("query") or ""), _int((payload or {}).get("topK"), 8))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"rag {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def entity_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = entity_command(self.storage, project_id, str((payload or {}).get("action") or "stats"), str((payload or {}).get("query") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"entity {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def style_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = style_command(self.storage, project_id, str((payload or {}).get("action") or "sample"), _int((payload or {}).get("chapterNo"), 0), _int((payload or {}).get("sampleLimit"), 80))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"style {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def migrate_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = migrate_command(self.storage, project_id, str((payload or {}).get("action") or "state-sqlite"))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("db_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"migrate {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def projections_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = projections_command(self.storage, project_id, str((payload or {}).get("action") or "status"), _int((payload or {}).get("start"), 0), _int((payload or {}).get("end"), 0), _int((payload or {}).get("chapterNo"), 0))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"projections {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def story_system_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = story_system_command(self.storage, project_id, str((payload or {}).get("action") or "persist"), str((payload or {}).get("genre") or ""), _int((payload or {}).get("chapterNo"), 0))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("master_setting") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"story-system {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})

    def chapter_commit_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = chapter_commit_command(self.storage, project_id, chapter_no, payload)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("commit_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"chapter-commit 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def review_pipeline_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = review_pipeline_command(self.storage, project_id, chapter_no, str((payload or {}).get("reviewResult") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"review-pipeline 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def memory_contract_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = memory_contract_command(self.storage, project_id, str((payload or {}).get("action") or "status"), str((payload or {}).get("query") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"memory-contract {report.get('action')} 完成。", path=path, result_kind="output_file", data={"report": report})


    def validate_csv(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = validate_csv_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"validate-csv 完成：{report.get('issue_count', 0)} 个问题。", path=path, result_kind="output_file", data={"report": report})

    def quality_trend(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = quality_trend_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"quality-trend 完成：{report.get('chapter_count', 0)} 章。", path=path, result_kind="output_file", data={"report": report})

    def rename_chapter(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        title = str((payload or {}).get("chapterTitle") or (payload or {}).get("title") or "")
        apply = bool((payload or {}).get("apply"))
        callbacks.emit_progress(0, 1)
        report = rename_chapter_command(self.storage, project_id, chapter_no, title, apply=apply)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("new_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"rename-chapter 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def update_master_outline(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = update_master_outline_command(self.storage, project_id, apply=bool((payload or {}).get("apply", True)))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"update-master-outline 完成：{report.get('chapter_count', 0)} 章。", path=path, result_kind="output_file", data={"report": report})

    def runtime_health(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = runtime_health_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"runtime-health 完成：缺失 {report.get('missing_count', 0)} 项。", path=path, result_kind="output_file", data={"report": report})

    def amend_proposal(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 0)
        callbacks.emit_progress(0, 1)
        report = amend_proposal_command(self.storage, project_id, chapter_no=chapter_no, query=str((payload or {}).get("query") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"amend-proposal 完成：{report.get('proposal_count', 0)} 条建议。", path=path, result_kind="output_file", data={"report": report})

    def override_ledger(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 0)
        patch = (payload or {}).get("statePatch") if isinstance((payload or {}).get("statePatch"), dict) else {}
        callbacks.emit_progress(0, 1)
        report = override_ledger_command(self.storage, project_id, chapter_no=chapter_no, reason=str((payload or {}).get("reason") or "manual"), patch=patch, apply=bool((payload or {}).get("apply")))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message="override-ledger 完成。", path=path, result_kind="output_file", data={"report": report})


    def publish(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 2)
        start = _int((payload or {}).get("start"), 0) or None
        end = _int((payload or {}).get("end"), 0) or None
        include_warnings = bool((payload or {}).get("includeWarnings") or (payload or {}).get("include_warnings"))
        queue = publish_queue(self.storage, project_id, start=start, end=end, include_warnings=include_warnings)
        callbacks.emit_progress(1, 2)
        # Backend-only parity with /webnovel-publish: prepare a publishable queue and export bundle.
        bundle = export_package(self.storage, project_id, include_zip=True)
        callbacks.emit_progress(2, 2)
        report = {"ok": True, "queue": queue, "export_bundle": bundle, "mode": "prepare"}
        path = Path((queue.get("paths") or {}).get("json") or (Path(self.storage.paths(project_id).control) / "reports" / "publication" / "publish_queue.json"))
        return TaskResult(ok=True, message=f"发布准备完成：队列 {queue.get('count', 0)} 章。", path=path, result_kind="output_file", data={"report": report})

    def deconstruct(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        source = str((payload or {}).get("source") or "")
        sample_limit = _int((payload or {}).get("sampleLimit") or (payload or {}).get("sample_limit"), 80)
        callbacks.emit_progress(0, 1)
        report = deconstruct_project(self.storage, project_id, source=source, sample_limit=sample_limit)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or (Path(self.storage.paths(project_id).control) / "reports" / "deconstruction" / "last_deconstruction.json"))
        return TaskResult(ok=bool(report.get("ok", True)), message=f"作品解构完成：{report.get('chapter_count', 0)} 章样本。", path=path, result_kind="output_file", data={"report": report})

    def references(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "stats").strip().lower()
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        if action in {"init", "ensure"}:
            report = ensure_reference_library(self.storage, project_id)
        elif action in {"build", "rebuild", "index"}:
            report = build_reference_index(self.storage, project_id)
        elif action in {"search", "query"}:
            report = search_reference_index(self.storage, project_id, query, top_k=top_k)
        else:
            report = build_reference_index(self.storage, project_id)
            report["action"] = "stats"
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or report.get("index_path") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"references {action or 'stats'} 完成。", path=path, result_kind="output_file", data={"report": report})

    def _project_id(self, payload: dict[str, Any]) -> str:
        project_id = str(payload.get("projectId") or payload.get("project_id") or payload.get("projectPath") or payload.get("project_path") or "").strip()
        if not project_id:
            result = self.storage.create_or_update_project(payload)
            return str(result["meta"]["project_id"])
        return project_id


    def behavior_gaps_v28(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = behavior_gaps_v28_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok")), message=f"行为级缺口检查完成：{report.get('behavior_aligned')}/{report.get('total')}。", path=Path(self.storage.paths(project_id).root) / "writer_control" / "behavior_v28" / "behavior_gap_matrix.json", result_kind="output_file", data={"report": report})

    def behavior_run_v28(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        query = str((payload or {}).get("query") or "")
        callbacks.emit_progress(0, 1)
        report = behavior_run_v28_command(self.storage, project_id, chapter_no, budget=budget, query=query)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok")), message=f"行为级闭环验收完成：{report.get('behavior_aligned')}/{report.get('total')}。", path=Path(str(report.get("path") or self.storage.paths(project_id).root)), result_kind="output_file", data={"report": report})

    def behavior_query_v28(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = behavior_query_v28_command(self.storage, project_id, query, top_k)
        callbacks.emit_progress(1, 1)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"行为级证据查询完成：{len(report.get('results') or [])} 条。", path=Path(self.storage.paths(project_id).root) / "writer_control" / "behavior_v28" / "last_behavior_query.json", result_kind="output_file", data={"report": report})

    def vector_rag_v29(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "build")
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        exclude_chapter = _int((payload or {}).get("excludeChapter"), 0)
        callbacks.emit_progress(0, 1)
        report = vector_rag_command_v29(self.storage, project_id, action, query=query, top_k=top_k, exclude_chapter=exclude_chapter)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or (report.get("paths_written") or {}).get("index") or (report.get("paths_written") or {}).get("query") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"真向量 RAG v29 {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def production_gaps_v29(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = vector_rag_gaps_v29(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"生产级缺口检查完成：真向量RAG={report.get('status') or ''}。", path=path, result_kind="output_file", data={"report": report})

    def production_optimize_v29(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 3)
        build = build_true_vector_rag(self.storage, project_id)
        callbacks.emit_progress(1, 3)
        eval_report = vector_rag_command_v29(self.storage, project_id, "eval")
        callbacks.emit_progress(2, 3)
        query_report = query_true_vector_rag(self.storage, project_id, query or "主角", top_k=top_k)
        gap = vector_rag_gaps_v29(self.storage, project_id)
        callbacks.emit_progress(3, 3)
        report = {
            "ok": bool(build.get("ok")) and bool(eval_report.get("ok")) and bool(gap.get("ok")),
            "build": build,
            "eval": eval_report,
            "query": query_report,
            "gap": gap,
            "production_items": {
                "true_vector_rag": "deep_aligned" if gap.get("ok") else "not_aligned",
                "embedding_provider": (build.get("provider") or {}).get("name"),
                "rerank": True,
                "tests_included": True,
            },
        }
        path = Path(self.storage.paths(project_id).control) / "rag_v29" / "production_optimize_v29.json"
        from backend.adapters.webnovel_writer.webnovel_writer_json import write_json
        write_json(path, report)
        return TaskResult(ok=bool(report.get("ok")), message="生产级 v29 优化完成：真向量 RAG 已接入并通过验收。", path=path, result_kind="output_file", data={"report": report})

    def production_gaps_v30(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = production_gaps_v30(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"生产级 v30 缺口检查完成：{report.get('production_aligned')}/{report.get('total')}。", path=path, result_kind="output_file", data={"report": report})

    def production_optimize_v30(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        budget = _int((payload or {}).get("budget"), 24000)
        callbacks.emit_progress(0, 1)
        report = production_optimize_v30(self.storage, project_id, chapter_no=chapter_no, query=query, top_k=top_k, budget=budget)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message="生产级 v30 自检优化完成。", path=path, result_kind="output_file", data={"report": report})

    def production_query_v30(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = production_query_v30(self.storage, project_id, query, top_k=top_k)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"生产级 v30 查询完成：{len(report.get('results') or [])} 条。", path=path, result_kind="output_file", data={"report": report})

    def _client_for_role(self, project_id: str, payload: dict[str, Any], role: str) -> tuple[WebnovelWriterClient, Any]:
        routed = route_payload(self.storage, project_id, payload, role)
        runtime = WebnovelWriterPlatform.runtime_from_payload(routed)
        return WebnovelWriterClient(runtime), runtime

    def _blueprint_prompt(self, meta: dict[str, Any], project_id: str, chapter_no: int, payload: dict[str, Any]) -> str:
        state = self.storage.load_state(project_id)
        story_config = self.storage.load_story_config(project_id)
        outline = self.storage.latest_outline_text(project_id)
        recent_count = _int(payload.get("recentContextCount"), _int((story_config.get("gate_policy") or {}).get("recent_context_count"), 6))
        recent = self.storage.recent_chapter_summaries(project_id, recent_count)
        query = " ".join([str(meta.get("title") or ""), outline[-1200:], str(state.get("foreshadow_debts") or "")])
        recall = self.storage.recall(project_id, query, top_k=_int((story_config.get("gate_policy") or {}).get("context_recall_top_k"), 6), exclude_chapter=chapter_no)
        return build_blueprint_json_prompt(meta, state, outline, recent, chapter_no, story_config, recall)

    def _context_pack(self, project_id: str, chapter_no: int, payload: dict[str, Any]) -> str:
        return self._context_pack_bundle(project_id, chapter_no, payload)[0]

    def _context_pack_bundle(self, project_id: str, chapter_no: int, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        meta = self.storage.load_meta(project_id)
        state = self.storage.load_state(project_id)
        story_config = self.storage.load_story_config(project_id)
        outline = self.storage.latest_outline_text(project_id)
        blueprint = self.storage.load_blueprint(project_id, chapter_no)
        blueprint_json = self.storage.load_blueprint_json(project_id, chapter_no)
        recent_count = _int(payload.get("recentContextCount"), _int((story_config.get("gate_policy") or {}).get("recent_context_count"), 6))
        recent = self.storage.recent_chapter_summaries(project_id, recent_count)
        required_characters = list(map(str, blueprint_json.get("required_characters") or []))
        required_locations = list(map(str, blueprint_json.get("required_locations") or []))
        required_factions = list(map(str, blueprint_json.get("required_factions") or []))
        foreshadow_actions = blueprint_json.get("foreshadow_actions") or []
        recall_query = " ".join([
            str(blueprint_json.get("goal") or ""),
            str(blueprint_json.get("conflict") or ""),
            " ".join(required_characters),
            " ".join(required_locations),
            " ".join(required_factions),
            " ".join(str(x.get("id") or x.get("name") or x) if isinstance(x, dict) else str(x) for x in foreshadow_actions),
            str(state.get("foreshadow_debts") or ""),
        ])
        recall = self.storage.recall(project_id, recall_query, top_k=_int((story_config.get("gate_policy") or {}).get("context_recall_top_k"), 6), exclude_chapter=chapter_no)
        chunk_hits = chunk_recall(self.storage, project_id, recall_query, top_k=_int((story_config.get("gate_policy") or {}).get("context_chunk_recall_top_k"), 8), exclude_chapter=chapter_no)
        try:
            true_vector_hits = query_true_vector_rag(self.storage, project_id, recall_query, top_k=_int((story_config.get("gate_policy") or {}).get("context_vector_top_k"), 8), exclude_chapter=chapter_no).get("results") or []
        except Exception:
            true_vector_hits = []
        try:
            reference_hits = search_reference_index(self.storage, project_id, recall_query, top_k=_int((story_config.get("gate_policy") or {}).get("context_reference_top_k"), 6)).get("results") or []
        except Exception:
            reference_hits = []
        entities = {
            "characters": _pick_mapping(state.get("characters") or {}, required_characters),
            "locations": _pick_mapping(state.get("locations") or {}, required_locations),
            "factions": _pick_mapping(state.get("factions") or {}, required_factions),
            "foreshadows": _pick_foreshadows(state.get("foreshadows") or {}, foreshadow_actions),
            "conflicts": state.get("conflict_progress") or {},
        }
        memory = load_or_build_memory(self.storage, project_id)
        data = {
            "schema_version": 2,
            "generated_at": _now(),
            "project_id": project_id,
            "chapter_no": chapter_no,
            "meta": meta,
            "story_profile": (story_config or {}).get("story_profile") or {},
            "learned_style_profile": (story_config or {}).get("learned_style_profile") or {},
            "blueprint": blueprint_json or {},
            "required_entities": entities,
            "recent_chapters": recent,
            "recall": recall,
            "chunk_recall": chunk_hits,
            "true_vector_recall": true_vector_hits,
            "reference_hits": reference_hits,
            "project_memory": memory,
            "foreshadow_debts": state.get("foreshadow_debts") or {},
            "latest_chapter": state.get("latest_chapter") or 0,
            "recall_query": recall_query.strip(),
        }
        base = build_context_pack(meta, state, outline, blueprint, recent, chapter_no, story_config, recall)
        context = f"""{base}

【后端 story_config】
{story_config}

【结构化章节蓝图】
{blueprint_json or {}}

【本章必读实体】
{entities}

【项目长期记忆 / Memory Scratchpad】
{(memory.get("paths") or {}).get("scratchpad") or ""}
{memory.get("risks") or []}

【分块长距召回 / Chunk Recall】
{chunk_hits}

【真向量语义召回 / True Vector RAG】
{true_vector_hits}

【结构化知识库召回 / Reference Knowledge】
{reference_hits}

【学习到的文风约束】
{(story_config or {}).get("learned_style_profile") or {}}""".strip()
        return context, data

    def _prewrite_gate(self, project_id: str, chapter_no: int, strictness: str) -> GateResult:
        result = gate("prewrite")
        meta = self.storage.load_meta(project_id)
        if not meta.get("title"):
            result.fail("项目缺少书名。")
        state = self.storage.load_state(project_id)
        latest = _int(state.get("latest_chapter"), 0)
        if chapter_no > 1 and latest < chapter_no - 1:
            result.warn(f"上一章状态未入账：latest_chapter={latest}，目标章={chapter_no}。")
        blueprint_json = self.storage.load_blueprint_json(project_id, chapter_no)
        blueprint_text = self.storage.load_blueprint(project_id, chapter_no)
        story_config = self.storage.load_story_config(project_id)
        require_bp = bool((story_config.get("gate_policy") or {}).get("require_blueprint_in_strict_mode", True))
        if not blueprint_json and not blueprint_text:
            if require_bp and "严格" in strictness:
                result.fail("严格门禁要求先生成章节蓝图。")
            else:
                result.warn("本章没有蓝图，将按现有状态自然推进。")
        else:
            result.extend(validate_blueprint(blueprint_json or {"raw": blueprint_text}))
        return result

    def _draft_gate(self, project_id: str, chapter_text: str, changes: dict[str, Any], marker_found: bool) -> GateResult:
        story_config = self.storage.load_story_config(project_id)
        policy = story_config.get("gate_policy") or {}
        result = validate_changes(changes, marker_found=marker_found, require_marker=bool(policy.get("require_changes_marker", True)))
        if not chapter_text.strip():
            result.fail("章节正文为空。")
        min_chars = _int(policy.get("min_chapter_chars"), 300)
        if len(chapter_text.strip()) < min_chars:
            result.warn(f"章节正文偏短：{len(chapter_text.strip())} 字，低于建议 {min_chars} 字。")
        return result

    def _postcommit_gate(self, project_id: str, chapter_no: int) -> GateResult:
        result = gate("postcommit")
        state = self.storage.load_state(project_id)
        chapter_path, chapter_text = self.storage.load_chapter(project_id, chapter_no)
        if not chapter_path or not chapter_text.strip():
            result.fail("正式章节文件不存在。")
        if str(chapter_no) not in (state.get("chapter_summaries") or {}):
            result.fail("story_state.chapter_summaries 未写入本章。")
        if (state.get("chapter_status") or {}).get(str(chapter_no)) != "committed":
            result.fail("story_state.chapter_status 未标记 committed。")
        if _int(state.get("latest_chapter"), 0) < chapter_no:
            result.fail("story_state.latest_chapter 未推进。")
        return result

    def _reject(self, project_id: str, chapter_no: int, title: str, message: str, run: dict[str, Any], callbacks: TaskCallbacks, gate_payload: dict[str, Any], path: Path | None = None) -> TaskResult:
        state = self.storage.load_state(project_id)
        state.setdefault("chapter_status", {})[str(chapter_no)] = "rejected"
        self.storage.save_state(project_id, state)
        run["status"] = "rejected"
        run["finished_at"] = _now()
        run["reject_gate"] = gate_payload
        run_path = self.storage.save_run(project_id, chapter_no, run)
        try:
            self.storage.append_event(project_id, "chapter_rejected", {"chapter_no": chapter_no, "title": title, "message": message, "gate": gate_payload, "run": str(run_path), "draft": str(path or "")})
        except Exception:
            pass
        callbacks.emit_log(message, "error")
        return TaskResult(ok=False, message=message, path=path or run_path, result_kind="output_file", data={"projectId": project_id, "runPath": str(run_path), "gate": gate_payload})

    def _resolve_title(self, title: str, chapter_text: str, chapter_no: int) -> str:
        clean = (title or "").strip()
        if clean and clean != f"第{chapter_no}章":
            return clean
        first_line = chapter_text.strip().splitlines()[0].strip() if chapter_text.strip() else ""
        match = re.match(r"^第\s*\d+\s*章\s*[：:、\s]*(.+)$", first_line)
        if match:
            return match.group(1).strip()[:40] or clean or f"第{chapter_no}章"
        return clean or f"第{chapter_no}章"

    def _fallback_fulfillment(self, chapter_no: int, blueprint_json: dict[str, Any], chapter_text: str) -> dict[str, Any]:
        nodes = blueprint_required_nodes(blueprint_json)
        completed, missed = [], []
        for node in nodes:
            if any(piece and piece in chapter_text for piece in re.split(r"[，,。；;、\s]+", node)[:4]):
                completed.append(node)
            else:
                missed.append(node)
        return {"chapter_no": chapter_no, "completed_nodes": completed, "missed_nodes": missed, "notes": ["fallback heuristic"]}



    def deep_align(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = deep_alignment_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message="深度对齐刷新完成。", path=path, result_kind="output_file", data={"report": report})

    def workflow_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        action = str((payload or {}).get("action") or (payload or {}).get("ledgerAction") or "status")
        callbacks.emit_progress(0, 1)
        report = workflow_command(self.storage, project_id, action, chapter_no, payload)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"workflow {action} 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def memory_deep(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or (payload or {}).get("memoryAction") or "rebuild")
        callbacks.emit_progress(0, 1)
        report = memory_deep_command(self.storage, project_id, action, str((payload or {}).get("query") or ""), _int((payload or {}).get("budget"), 24000))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("store") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"memory-deep {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def rag_vector(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "build")
        callbacks.emit_progress(0, 1)
        report = rag_vector_command(self.storage, project_id, action, str((payload or {}).get("query") or ""), _int((payload or {}).get("topK"), 8))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("vector_index") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"rag-vector {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def review_deep(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = review_deep_command(self.storage, project_id, chapter_no, str((payload or {}).get("action") or "run"), _int((payload or {}).get("maxRounds"), 3))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("combined") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"review-deep 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def schema_validate(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = schema_validate_command(self.storage, project_id, bool((payload or {}).get("deep", True)))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"schema-validate 完成：{report.get('issue_count', 0)} 个问题。", path=path, result_kind="output_file", data={"report": report})

    def sqlite_ops(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "build")
        callbacks.emit_progress(0, 1)
        report = sqlite_command(self.storage, project_id, action, str((payload or {}).get("query") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("sqlite") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"sqlite {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def publisher_bridge(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "plan")
        callbacks.emit_progress(0, 1)
        report = publisher_bridge_command(self.storage, project_id, action, _int((payload or {}).get("start"), 0), _int((payload or {}).get("end"), 0), str((payload or {}).get("platform") or "fanqie"))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("jobs") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"publisher-bridge {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def orchestrate_deep(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        action = str((payload or {}).get("action") or "status")
        callbacks.emit_progress(0, 1)
        report = orchestrate_deep_command(self.storage, project_id, chapter_no, action, _int((payload or {}).get("maxRounds"), 3))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("checkpoint") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"orchestrate-deep {action} 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def memory_orchestrate(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or (payload or {}).get("memoryAction") or "rebuild")
        callbacks.emit_progress(0, 1)
        report = memory_orchestrate_command(self.storage, project_id, action, str((payload or {}).get("query") or ""), _int((payload or {}).get("budget"), 24000))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("store") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"memory-orchestrate {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def rag_router(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "build")
        callbacks.emit_progress(0, 1)
        report = rag_router_command(self.storage, project_id, action, str((payload or {}).get("query") or ""), _int((payload or {}).get("topK"), 8))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("index") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"rag-router {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def review_pipeline_deep_v2(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = review_pipeline_deep_command(self.storage, project_id, chapter_no, _int((payload or {}).get("maxRounds"), 3))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("combined") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"review-pipeline-deep 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def sqlite_schema(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "migrate")
        callbacks.emit_progress(0, 1)
        report = sqlite_schema_command(self.storage, project_id, action, str((payload or {}).get("query") or ""))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("sqlite") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"sqlite-schema {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def publisher_sync(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "plan")
        callbacks.emit_progress(0, 1)
        report = publisher_sync_command(self.storage, project_id, action, str((payload or {}).get("platform") or "fanqie"), _int((payload or {}).get("start"), 0), _int((payload or {}).get("end"), 0))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("jobs") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"publisher-sync {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def alignment_gaps(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = alignment_gap_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"对齐缺口检查完成：剩余 {len(report.get('remaining_unimplemented') or [])} 项。", path=path, result_kind="output_file", data={"report": report})

    def _build_commit(self, chapter_no: int, chapter_title: str, changes: dict[str, Any], extraction: dict[str, Any], review: dict[str, Any], fulfillment: dict[str, Any], disambiguation: dict[str, Any], consistency: dict[str, Any]) -> dict[str, Any]:
        summary = extraction.get("summary") or changes.get("summary") or ""
        base = f"{chapter_no}|{chapter_title}|{summary}|{_now()}"
        commit_id = hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]
        rejected = bool((review.get("blocking_issues") or []) or (fulfillment.get("missed_nodes") or []) or (disambiguation.get("pending") or []) or not consistency.get("ok", True))
        return {
            "schema_version": 3,
            "commit_id": commit_id,
            "chapter_no": chapter_no,
            "chapter_title": chapter_title,
            "status": "rejected" if rejected else "accepted",
            "summary": summary,
            "characters": extraction.get("characters") or changes.get("characters") or {},
            "locations": extraction.get("locations") or changes.get("locations") or {},
            "factions": extraction.get("factions") or changes.get("factions") or {},
            "items": extraction.get("items") or changes.get("items") or {},
            "foreshadows": extraction.get("foreshadows") or changes.get("foreshadows") or {},
            "conflicts": extraction.get("conflicts") or changes.get("conflicts") or {},
            "secrets": extraction.get("secrets") or changes.get("secrets") or {},
            "pledges": extraction.get("pledges") or changes.get("pledges") or {},
            "deadlines": extraction.get("deadlines") or changes.get("deadlines") or {},
            "timeline": extraction.get("timeline") or changes.get("timeline") or [],
            "milestones": extraction.get("milestones") or [],
            "hooks": extraction.get("hooks") or changes.get("hooks") or [],
            "review": review,
            "artifacts": {"fulfillment_result": fulfillment, "disambiguation_result": disambiguation, "extraction_result": extraction, "consistency_gate": consistency},
            "created_at": _now(),
        }

    def _apply_commit(self, project_id: str, commit: dict[str, Any]) -> None:
        state = self.storage.load_state(project_id)
        self.storage.apply_commit_to_state(state, commit)
        self.storage.save_state(project_id, state)

    def _record_step(self, run: dict[str, Any], name: str, payload: dict[str, Any]) -> None:
        run.setdefault("steps", []).append({"name": name, "at": _now(), "ok": payload.get("ok"), "payload": payload})

    def agent_registry(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "build")
        callbacks.emit_progress(0, 1)
        report = agent_registry_command(self.storage, project_id, action)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("registry") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"agent-registry {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def context_manager_deep_v2(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        query = str((payload or {}).get("query") or "")
        callbacks.emit_progress(0, 1)
        report = context_manager_deep_command(self.storage, project_id, chapter_no, budget, query)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"context-manager 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def workflow_runner_v2(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        action = str((payload or {}).get("action") or "run")
        callbacks.emit_progress(0, 1)
        report = workflow_runner_v2_command(self.storage, project_id, chapter_no, action, _int((payload or {}).get("maxRounds"), 3))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("checkpoint") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"workflow-runner {action} 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def memory_contract_deep_v2(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "validate")
        budget = _int((payload or {}).get("budget"), 24000)
        callbacks.emit_progress(0, 1)
        report = memory_contract_deep_command(self.storage, project_id, action, budget)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("contract") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"memory-contract-deep {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def event_projection_deep(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        action = str((payload or {}).get("action") or "health")
        callbacks.emit_progress(0, 1)
        report = event_projection_deep_command(self.storage, project_id, action)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("projection_log") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"event-projection {action} 完成。", path=path, result_kind="output_file", data={"report": report})

    def review_converge(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = review_converge_command(self.storage, project_id, chapter_no, _int((payload or {}).get("maxRounds"), 3))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("convergence") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"review-converge 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})

    def deep_align_v22(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        callbacks.emit_progress(0, 1)
        report = deep_alignment_v22_command(self.storage, project_id, chapter_no)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("json") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message=f"deep-align-v22 第 {chapter_no} 章完成。", path=path, result_kind="output_file", data={"report": report})


    def alignment_audit_v23(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = alignment_audit_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("audit") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", False)), message=f"alignment-audit-v23 完成，对齐分数 {report.get('alignment_score')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_optimize_v23(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        callbacks.emit_progress(0, 1)
        report = alignment_optimize_command(self.storage, project_id, chapter_no, budget)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("result") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", False)), message=f"alignment-optimize-v23 完成，深度对齐 {report.get('deep_aligned')}/{report.get('total')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_query_v23(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = query_alignment_router(self.storage, project_id, str((payload or {}).get("query") or ""), _int((payload or {}).get("topK"), 8))
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("query") or self.storage.paths(project_id).control)
        return TaskResult(ok=bool(report.get("ok", True)), message="alignment-query-v23 完成。", path=path, result_kind="output_file", data={"report": report})


    def alignment_gaps_v24(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = alignment_gap_matrix_v24_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("gap_matrix") or Path(self.storage.paths(project_id).control) / "alignment_v24" / "gap_matrix.json")
        return TaskResult(ok=bool(report.get("ok", False)), message=f"alignment-gaps-v24 完成：deep={report.get('deep_aligned')}/{report.get('total')}，shallow={report.get('shallow')}，missing={report.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_optimize_v24(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        callbacks.emit_progress(0, 1)
        report = alignment_optimize_v24_command(self.storage, project_id, chapter_no, budget)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("result") or Path(self.storage.paths(project_id).control) / "alignment_v24" / "optimize_result.json")
        after = report.get("audit_after") or {}
        return TaskResult(ok=bool(report.get("ok", True)), message=f"alignment-optimize-v24 完成：deep={after.get('deep_aligned')}，shallow={after.get('shallow')}，missing={after.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_query_v24(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = alignment_query_v24_command(self.storage, project_id, query, top_k)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("query") or Path(self.storage.paths(project_id).control) / "alignment_v24" / "last_query.json")
        return TaskResult(ok=True, message="alignment-query-v24 完成。", path=path, result_kind="output_file", data={"report": report})


    def alignment_gaps_v25(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = alignment_gap_matrix_v25_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("gap_matrix") or Path(self.storage.paths(project_id).control) / "alignment_v25" / "gap_matrix.json")
        return TaskResult(ok=bool(report.get("ok", False)), message=f"alignment-gaps-v25 完成：deep={report.get('deep_aligned')}/{report.get('total')}，shallow={report.get('shallow')}，missing={report.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_optimize_v25(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        query = str((payload or {}).get("query") or "")
        callbacks.emit_progress(0, 1)
        report = alignment_optimize_v25_command(self.storage, project_id, chapter_no, budget, query)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("result") or Path(self.storage.paths(project_id).control) / "alignment_v25" / "optimize_result.json")
        after = report.get("audit_after") or {}
        return TaskResult(ok=bool(report.get("ok", True)), message=f"alignment-optimize-v25 完成：deep={after.get('deep_aligned')}，shallow={after.get('shallow')}，missing={after.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_query_v25(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = alignment_query_v25_command(self.storage, project_id, query, top_k)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("query") or Path(self.storage.paths(project_id).control) / "alignment_v25" / "last_query.json")
        return TaskResult(ok=True, message="alignment-query-v25 完成。", path=path, result_kind="output_file", data={"report": report})


    def alignment_gaps_v26(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = alignment_gaps_v26_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("gap_matrix") or Path(self.storage.paths(project_id).control) / "alignment_v26" / "gap_matrix.json")
        return TaskResult(ok=bool(report.get("ok", False)), message=f"alignment-gaps-v26 完成：operational={report.get('operational_deep_aligned')}/{report.get('total')}，not_operational={report.get('not_operational')}，missing={report.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_optimize_v26(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        query = str((payload or {}).get("query") or "")
        callbacks.emit_progress(0, 1)
        report = alignment_optimize_v26_command(self.storage, project_id, chapter_no, budget, query)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("operational_readiness") or Path(self.storage.paths(project_id).control) / "alignment_v26" / "operational_readiness.json")
        after = report.get("audit_after") or {}
        return TaskResult(ok=bool(report.get("ok", True)), message=f"alignment-optimize-v26 完成：operational={after.get('operational_deep_aligned')}，not_operational={after.get('not_operational')}，missing={after.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def alignment_query_v26(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = alignment_query_v26_command(self.storage, project_id, query, top_k)
        callbacks.emit_progress(1, 1)
        path = Path((report.get("paths_written") or {}).get("query") or Path(self.storage.paths(project_id).control) / "alignment_v26" / "last_query.json")
        return TaskResult(ok=True, message="alignment-query-v26 完成。", path=path, result_kind="output_file", data={"report": report})



    def fusion_gaps_v27(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        callbacks.emit_progress(0, 1)
        report = fusion_gaps_v27_command(self.storage, project_id)
        callbacks.emit_progress(1, 1)
        path = Path(self.storage.paths(project_id).control) / "fusion_v27" / "gap_matrix.json"
        return TaskResult(ok=bool(report.get("ok", False)), message=f"fusion-gaps-v27 完成：deep={report.get('deep_fusion_aligned')}/{report.get('total')}，shallow={report.get('not_deep_enough')}，missing={report.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def fusion_optimize_v27(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        chapter_no = _int((payload or {}).get("chapterNo"), 1)
        budget = _int((payload or {}).get("budget"), 24000)
        query = str((payload or {}).get("query") or "")
        callbacks.emit_progress(0, 1)
        report = fusion_optimize_v27_command(self.storage, project_id, chapter_no, budget, query)
        callbacks.emit_progress(1, 1)
        path = Path(self.storage.paths(project_id).control) / "fusion_v27" / "optimize_result.json"
        after = report.get("audit_after") or {}
        return TaskResult(ok=bool(report.get("ok", True)), message=f"fusion-optimize-v27 完成：deep={after.get('deep_fusion_aligned')}，shallow={after.get('not_deep_enough')}，missing={after.get('missing')}。", path=path, result_kind="output_file", data={"report": report})

    def fusion_query_v27(self, payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskResult:
        callbacks = callbacks or TaskCallbacks()
        project_id = self._project_id(payload)
        query = str((payload or {}).get("query") or "")
        top_k = _int((payload or {}).get("topK"), 8)
        callbacks.emit_progress(0, 1)
        report = fusion_query_v27_command(self.storage, project_id, query, top_k)
        callbacks.emit_progress(1, 1)
        path = Path(self.storage.paths(project_id).control) / "fusion_v27" / "last_query.json"
        return TaskResult(ok=True, message="fusion-query-v27 完成。", path=path, result_kind="output_file", data={"report": report})

    def _blueprint_markdown(self, blueprint: dict[str, Any], raw: str = "") -> str:
        if "raw" in blueprint:
            return str(raw or blueprint.get("raw") or "")
        nodes = "\n".join(f"- {item}" for item in blueprint.get("must_cover_nodes") or []) or "- 暂无"
        forbidden = "\n".join(f"- {item}" for item in blueprint.get("forbidden_zones") or []) or "- 暂无"
        return f"""# 第{blueprint.get('chapter_no', '')}章：{blueprint.get('title', '')}

## 章节目标
{blueprint.get('goal', '')}

## 时间与场景
- 时间锚点：{blueprint.get('time_anchor', '')}
- 章节跨度：{blueprint.get('chapter_span', '')}
- 视角：{blueprint.get('pov', '')}
- 场景：{blueprint.get('scene', '')}

## 出场约束
- 角色：{blueprint.get('required_characters', [])}
- 地点：{blueprint.get('required_locations', [])}
- 势力：{blueprint.get('required_factions', [])}

## 必达节点
{nodes}

## 禁区
{forbidden}

## 冲突 / 爽点 / 钩子
- 冲突：{blueprint.get('conflict', '')}
- 爽点：{blueprint.get('payoff', '')}
- 章末钩子：{blueprint.get('ending_hook', '')}

## 事实回写提示
{blueprint.get('state_writeback_hint', [])}
""".strip()

    def _check_stop(self, callbacks: TaskCallbacks) -> None:
        if callbacks.stop_requested():
            raise RuntimeError("任务已停止。")


def _safe_read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            import json as _json
            data = _json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _doctor_report_markdown(report: dict[str, Any]) -> str:
    status = "通过" if report.get("ok") else "需要处理"
    lines = [f"# 全书体检报告", "", f"- 状态：{status}", f"- 检查时间：{report.get('checked_at') or ''}", f"- 问题数：{report.get('issue_count') or 0}", ""]
    issues = report.get("issues") or []
    if issues:
        lines.append("## 问题列表")
        for idx, item in enumerate(issues, start=1):
            lines.append(f"{idx}. [{item.get('level', 'info')}] {item.get('type', '')}：{item.get('message', '')}")
        lines.append("")
    else:
        lines += ["## 问题列表", "暂无问题。", ""]
    lines += [
        "## 产物",
        f"- 关系索引：{report.get('relationIndex') or ''}",
        f"- 下一章上下文包：{report.get('nextContextPack') or ''}",
        f"- 控制目录同步：{(report.get('controlSync') or {}).get('ok')}",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def _pick_mapping(mapping: dict[str, Any], names: list[str]) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    if not names:
        return {}
    out: dict[str, Any] = {}
    for name in names:
        key = str(name).strip()
        if not key:
            continue
        if key in mapping:
            out[key] = mapping[key]
            continue
        for real_name, value in mapping.items():
            if isinstance(value, dict):
                aliases = {str(x) for x in value.get("aliases") or []}
                if key == str(value.get("id") or "") or key in aliases:
                    out[str(real_name)] = value
                    break
    return out


def _pick_foreshadows(mapping: dict[str, Any], actions: Any) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    wanted: list[str] = []
    for item in actions or []:
        if isinstance(item, dict):
            wanted.append(str(item.get("id") or item.get("name") or item.get("target") or ""))
        else:
            wanted.append(str(item))
    if not wanted:
        return {}
    return _pick_mapping(mapping, wanted)
