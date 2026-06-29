from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_indexing import rebuild_chunk_index, search_chunks
from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_story_config import default_story_config
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


COMMAND_PARITY_ROWS: list[dict[str, str]] = [
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-init", "backend_command": "init", "status": "covered", "note": "初始化项目、设定集/大纲脚手架、.env.example RAG 模板、控制目录、模型路由、题材规则"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-plan", "backend_command": "plan", "status": "covered", "note": "全书大纲、分卷大纲、章节蓝图"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-write", "backend_command": "write", "status": "covered", "note": "写前门禁、上下文、起草、审查、事实提取、commit"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-review", "backend_command": "review / quality / language", "status": "covered", "note": "LLM 章节审查、本地质量检查与去 AI 味报告"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-query", "backend_command": "query", "status": "covered", "note": "状态、实体、章节分块召回统一查询"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-learn", "backend_command": "learn", "status": "covered", "note": "本地文风画像与写作习惯学习"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-dashboard", "backend_command": "dashboard / project-status", "status": "covered", "note": "只输出后端数据，不新增界面"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "/webnovel-doctor", "backend_command": "doctor / audit / ssot / continuity", "status": "covered", "note": "工程体检、SSOT、连贯性检查"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-write-batch", "backend_command": "write-batch", "status": "covered", "note": "批量写作流水线，失败章节进入 rejected 并停止"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-delete", "backend_command": "delete-chapter", "status": "covered", "note": "安全归档删除，不直接硬删"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-rewrite", "backend_command": "rewrite", "status": "covered", "note": "重写影响预演、安全失效归档、可选继续写章"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-heal", "backend_command": "heal / repair-plan", "status": "covered", "note": "Rejected 修复计划；apply 时调用自动修复写章链"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-export", "backend_command": "export / export-package", "status": "covered", "note": "全书 TXT/MD/JSON/ZIP 导出"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "/webnovel-publish", "backend_command": "publish / publish-queue / publish-status", "status": "covered", "note": "发布队列与发布状态回写"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "where", "backend_command": "where", "status": "covered", "note": "打印解析出的项目根与关键目录"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "use <路径>", "backend_command": "use", "status": "covered", "note": "绑定当前工作区使用的书项目"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "write-gate", "backend_command": "write-gate", "status": "covered", "note": "prewrite / precommit / postcommit 写章边界校验"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "user-report", "backend_command": "user-report", "status": "covered", "note": "作者友好最终报告，不直接甩原始 JSON"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "run-ledger", "backend_command": "run-ledger", "status": "covered", "note": "记录写章步骤与断点续跑建议"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "run-log", "backend_command": "run-log", "status": "covered", "note": "脱敏运行日志"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "story-events", "backend_command": "story-events", "status": "covered", "note": "查询事件与事件链健康检查"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "memory stats/query/dump/conflicts/bootstrap/update", "backend_command": "memory-stats / memory-query / memory-dump / memory-conflicts / memory-bootstrap / memory-update", "status": "covered", "note": "长期记忆统计、查询、导出、冲突与重建"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "status --focus all/urgency", "backend_command": "status --focus", "status": "covered", "note": "宏观创作健康报告，支持 all/progress/urgency 焦点"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "update-state", "backend_command": "update-state", "status": "covered", "note": "手动状态 patch 并写入事件"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "backup / archive", "backend_command": "backup --action / archive --action", "status": "covered", "note": "备份/归档管理：create/list/verify/restore-plan"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "extract-context", "backend_command": "extract-context", "status": "covered", "note": "提取章节上下文并生成机器报告"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "index", "backend_command": "index", "status": "covered", "note": "索引 stats/rebuild/process-chapter/query，对应章节索引与分块索引"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "state", "backend_command": "state", "status": "covered", "note": "状态 summary/dump/rebuild/patch"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "rag", "backend_command": "rag", "status": "covered", "note": "RAG stats/index-chapter/query，本地分块召回实现"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "entity", "backend_command": "entity", "status": "covered", "note": "实体 stats/link/occurrences"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "style", "backend_command": "style", "status": "covered", "note": "风格采样与文风画像"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "migrate", "backend_command": "migrate", "status": "covered", "note": "state.json 到 SQLite read-model 迁移"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "projections retry/replay", "backend_command": "projections", "status": "covered", "note": "补跑/重放 state、index、chunk、entity projections"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "story-system", "backend_command": "story-system", "status": "covered", "note": "MASTER_SETTING 与运行时合同种子"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "chapter-commit", "backend_command": "chapter-commit", "status": "covered", "note": "从正文和 artifacts 生成章节 commit 并回放状态"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "review-pipeline", "backend_command": "review-pipeline", "status": "covered", "note": "整合本地质量、语言和外部 review 结果"},
    {"source": "lingfengQAQ/webnovel-writer", "source_command": "memory-contract", "backend_command": "memory-contract", "status": "covered", "note": "长期记忆合同状态、冲突与重建"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "deconstruction-agent", "backend_command": "deconstruct", "status": "covered", "note": "作品解构/拆书：开篇、章末钩子、节奏、对话占比与高频结构"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "references/csv + BM25", "backend_command": "references", "status": "covered", "note": "结构化知识库：CSV/Markdown/TXT/JSON 建索引与检索，供 context pack 召回"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "validate_csv.py", "backend_command": "validate-csv", "status": "covered", "note": "结构化知识库 CSV 校验：空文件、表头、重复列、弱主键、空行"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "quality_trend_report.py", "backend_command": "quality-trend", "status": "covered", "note": "跨章节质量趋势：字数、段落、对话占比、问题数与审查覆盖"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "chapter_rename.py", "backend_command": "rename-chapter", "status": "covered", "note": "安全重命名章节并重建索引/全书 TXT"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "update_master_outline.py", "backend_command": "update-master-outline", "status": "covered", "note": "从状态、章节与蓝图重建总纲目录"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "story_runtime_health.py", "backend_command": "runtime-health", "status": "covered", "note": "运行时状态、事件、记忆、真相、模型路由、题材与知识库健康检查"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "amend_proposal_schema.py", "backend_command": "amend-proposal", "status": "covered", "note": "生成安全修订提案，供 heal/rewrite/update-state 使用"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "override_ledger_service.py", "backend_command": "override-ledger", "status": "covered", "note": "记录人工 override ledger，可选应用 state patch"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "workflow_checkpoint.py", "backend_command": "workflow / checkpoint / deep-align", "status": "covered_deep", "note": "步骤级可信产物检查、断点续跑建议、checkpoint.json 与 step_ledger.jsonl"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "memory/store.py + compactor.py + budget.py + orchestrator.py", "backend_command": "memory-deep", "status": "covered_deep", "note": "长期记忆 store/schema/budget/compact/conflicts/query 统一重建"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "rag_adapter.py + vector_projection_writer.py", "backend_command": "rag-vector", "status": "covered_deep", "note": "本地确定性向量投影、向量召回、stats/query/build"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "review_schema.py + review_pipeline.py + fulfillment/disambiguation/extraction artifacts", "backend_command": "review-deep", "status": "covered_deep", "note": "生成 review_result、fulfillment_result、disambiguation_result、extraction_result 四类 commit artifacts"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "schemas.py + state_validator.py + story_event_schema.py", "backend_command": "schema-validate", "status": "covered_deep", "note": "校验 state、events、commits、memory store schema 与事件链"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "migrate_state_to_sqlite.py + index.db read-model", "backend_command": "sqlite", "status": "covered_deep", "note": "生成 webnovel_state.db，含 chapters/entities/events/commits/memories 表和查询"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "publisher formatter/config/adapters bridge", "backend_command": "publisher-bridge", "status": "covered_deep", "note": "生成 publisher_jobs.json、队列状态回写和发布 payload zip"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "agents/skills + skill_runner", "backend_command": "agent-registry", "status": "covered_deep", "note": "后端 agent/skill registry、任务链和模型路由就绪检查，不新增前端"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "context_manager.py + context_weights.py", "backend_command": "context-manager", "status": "covered_deep", "note": "按蓝图、实体、记忆、RAG、知识库和历史章节进行加权上下文预算裁剪"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "workflow_checkpoint.py + run-ledger resume", "backend_command": "workflow-runner", "status": "covered_deep", "note": "生成/签名 prewrite、task_book、fulfillment、disambiguation、extraction 等可信 artifacts 与续跑 checkpoint"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "memory_contract_adapter + memory budget/compactor", "backend_command": "memory-contract-deep", "status": "covered_deep", "note": "校验长期记忆 schema、预算、冲突与可用记忆集合"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "event_log_store.py + projection_log.py", "backend_command": "event-projection", "status": "covered_deep", "note": "事件链 fingerprint、重复事件检测、projection 签名和 replay plan"},
    {"source": "lujih/webnovel-writer-opencode", "source_command": "review convergence / heal loop", "backend_command": "review-converge", "status": "covered_deep", "note": "根据 review/fulfillment/extraction artifacts 生成多轮局部修复动作与收敛计划"},
    {"source": "对齐审计", "source_command": "all remaining shallow capabilities", "backend_command": "alignment-gaps-v24 / alignment-optimize-v24 / alignment-query-v24", "status": "covered_deep", "note": "对 workflow、agent、SSOT、context、RAG、memory、review、entity/debt、publisher、SQLite、security/observability、references/evals 逐项生成深度证据链并复核达标状态"},
    {"source": "对齐审计", "source_command": "operational acceptance and wiring layer", "backend_command": "alignment-gaps-v26 / alignment-optimize-v26 / alignment-query-v26", "status": "covered_deep", "note": "对 v25 的深度证据链追加严格验收、命令接入契约、回归样例和强制策略，避免只生成文件但未进入实际后端链路"},
]


def project_status_report(storage: Any, project_id: str, focus: str = "all") -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    chapters = storage.list_chapters(project_id)
    blueprints = storage.list_blueprints(project_id)
    commits = sorted(Path(paths.commits).glob("第*章_commit.json"))
    rejected = sorted(Path(paths.rejected).glob("第*.txt"))
    reviews = sorted(Path(paths.reviews).glob("第*章_review.json"))
    lifecycle = _safe_json(Path(paths.control) / "reports" / "lifecycle" / "last_lifecycle_report.json")
    latest_chapter = int(state.get("latest_chapter") or 0)
    next_chapter = latest_chapter + 1
    focus = (focus or "all").strip().lower()
    report = {
        "ok": True,
        "generated_at": _now(),
        "project_id": project_id,
        "focus": focus,
        "latest_chapter": latest_chapter,
        "next_chapter": next_chapter,
        "counts": {
            "chapters": len(chapters),
            "blueprints": len(blueprints),
            "commits": len(commits),
            "reviews": len(reviews),
            "rejected": len(rejected),
            "characters": len(state.get("characters") or {}),
            "locations": len(state.get("locations") or {}),
            "factions": len(state.get("factions") or {}),
            "foreshadows": len(state.get("foreshadows") or {}),
            "conflicts": len(state.get("conflicts") or {}),
        },
        "queues": (lifecycle.get("queues") if isinstance(lifecycle, dict) else {}) or {},
        "paths": {
            "control": paths.control,
            "state": paths.state,
            "exports": paths.exports,
            "reports": str(Path(paths.control) / "reports"),
        },
    }
    report["focus_summary"] = _status_focus_summary(report, focus)
    return _write_report(paths, "project_status", report, _project_status_md(report))


def preflight_report(storage: Any, project_id: str, chapter_no: int) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    blueprint_json = storage.load_blueprint_json(project_id, chapter_no)
    blueprint_text = storage.load_blueprint(project_id, chapter_no)
    issues: list[dict[str, Any]] = []

    def issue(level: str, code: str, message: str) -> None:
        issues.append({"level": level, "code": code, "message": message})

    if not blueprint_json and not blueprint_text:
        issue("warning", "missing_blueprint", f"第 {chapter_no} 章没有蓝图。")
    else:
        for key, label in [("goal", "章节目标"), ("must_cover_nodes", "必达节点")]:
            value = blueprint_json.get(key)
            if not value:
                issue("warning", f"blueprint_missing_{key}", f"蓝图缺少{label}。")

    state_buckets = {
        "required_characters": ("characters", "角色"),
        "required_locations": ("locations", "地点"),
        "required_factions": ("factions", "势力"),
    }
    for bp_key, (state_key, label) in state_buckets.items():
        known = set((state.get(state_key) or {}).keys())
        for name in blueprint_json.get(bp_key) or []:
            if str(name) and str(name) not in known:
                issue("error", f"unknown_{state_key}", f"蓝图引用未登记{label}：{name}")

    if chapter_no > 1:
        prev_path, _ = storage.load_chapter(project_id, chapter_no - 1)
        if not prev_path:
            issue("warning", "missing_previous_chapter", f"上一章第 {chapter_no - 1} 章正文不存在。")

    chunk_index = Path(paths.indexes) / "chunk_index.json"
    if not chunk_index.exists():
        issue("warning", "missing_chunk_index", "分块召回索引不存在，建议运行 rebuild-search。")
    routes = Path(paths.control) / "models" / "model_routes.json"
    if not routes.exists():
        issue("warning", "missing_model_routes", "模型路由不存在，建议运行 model-routes。")
    genre = Path(paths.control) / "genres" / "genre_profile.json"
    if not genre.exists():
        issue("warning", "missing_genre_profile", "题材规则不存在，建议运行 genre。")

    report = {
        "ok": not any(x["level"] == "error" for x in issues),
        "generated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "issue_count": len(issues),
        "issues": issues,
        "next_actions": _preflight_actions(issues),
    }
    return _write_report(paths, "preflight", report, _preflight_md(report))


def query_report(storage: Any, project_id: str, query: str, top_k: int = 8) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    q = str(query or "").strip()
    entity_hits: list[dict[str, Any]] = []
    if q:
        for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
            for name, value in (state.get(bucket) or {}).items():
                hay = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
                if q in str(name) or q in hay:
                    entity_hits.append({"bucket": bucket, "name": str(name), "data": value})
    chunk_report = search_chunks(storage, project_id, q, top_k=max(1, int(top_k or 8))) if q else {"results": []}
    chunk_hits = chunk_report.get("results") if isinstance(chunk_report, dict) else chunk_report
    report = {"ok": True, "generated_at": _now(), "project_id": project_id, "query": q, "entity_hits": entity_hits[:50], "chunk_hits": chunk_hits or []}
    return _write_report(paths, "query", report, _query_md(report))


def export_package(storage: Any, project_id: str, include_zip: bool = True) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.ensure_project_dirs(project_id)
    meta = storage.load_meta(project_id)
    title = _safe_name(str(meta.get("title") or Path(paths.root).name or "novel"))
    txt_path = storage.export_txt(project_id)
    chapters = storage.list_chapters(project_id)
    out_dir = ensure_dir(Path(paths.exports) / f"{title}_export_bundle")
    md_path = out_dir / f"{title}_全书.md"
    toc_path = out_dir / "contents.json"
    lines = [f"# {meta.get('title') or title}", ""]
    toc = []
    for row in chapters:
        text = read_text_auto(Path(row["path"])).strip()
        title_line = f"第{row['chapterNo']}章 {row.get('title') or ''}".strip()
        toc.append({"chapterNo": row["chapterNo"], "title": row.get("title") or "", "path": row.get("path")})
        lines += [f"## {title_line}", "", text, ""]
    write_text(md_path, "\n".join(lines).strip() + "\n")
    write_json(toc_path, {"title": meta.get("title") or title, "chapter_count": len(chapters), "chapters": toc})
    zip_path = None
    if include_zip:
        zip_path = Path(paths.exports) / f"{title}_export_bundle.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(txt_path, arcname=txt_path.name)
            zf.write(md_path, arcname=md_path.name)
            zf.write(toc_path, arcname=toc_path.name)
    report = {"ok": True, "generated_at": _now(), "project_id": project_id, "paths": {"txt": str(txt_path), "markdown": str(md_path), "toc": str(toc_path), "zip": str(zip_path or "")}, "chapter_count": len(chapters)}
    return _write_report(paths, "export_package", report, _export_md(report))


def safe_delete_chapter(storage: Any, project_id: str, chapter_no: int, apply: bool = False, reason: str = "manual") -> dict[str, Any]:
    storage.sync_control_files(project_id)
    paths = storage.ensure_project_dirs(project_id)
    root = Path(paths.root)
    candidates: list[Path] = []
    patterns = [
        (Path(paths.chapters), f"第{chapter_no:04d}章_*.txt"),
        (Path(paths.drafts), f"第{chapter_no:04d}章_*.txt"),
        (Path(paths.rejected), f"第{chapter_no:04d}章_*.txt"),
        (Path(paths.reviews), f"第{chapter_no:04d}章_review.json"),
        (Path(paths.commits), f"第{chapter_no:04d}章_commit.json"),
        (Path(paths.blueprints), f"第{chapter_no:04d}章_蓝图.*"),
        (Path(paths.runtime) / f"第{chapter_no:04d}章", "*"),
        (Path(paths.artifacts) / f"第{chapter_no:04d}章", "*"),
        (Path(paths.runs), f"第{chapter_no:04d}章_*.json"),
        (Path(paths.control) / "blueprints", f"chapter_{chapter_no:04d}.*"),
        (Path(paths.control) / "context_packs", f"chapter_{chapter_no:04d}_context.*"),
        (Path(paths.control) / "contracts", f"chapter_{chapter_no:04d}_contract.*"),
    ]
    for folder, pattern in patterns:
        if folder.exists():
            candidates.extend(p for p in folder.glob(pattern) if p.exists())
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = Path(paths.control) / "deleted" / f"chapter_{chapter_no:04d}_{ts}"
    moved: list[dict[str, str]] = []
    if apply:
        ensure_dir(archive_dir)
        for p in candidates:
            if p.is_dir():
                dst = archive_dir / p.relative_to(root)
                ensure_dir(dst.parent)
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(p), str(dst))
            else:
                dst = archive_dir / p.relative_to(root)
                ensure_dir(dst.parent)
                shutil.move(str(p), str(dst))
            moved.append({"from": str(p), "to": str(dst)})
        try:
            storage.rebuild_state_from_commits(project_id)
            storage.rebuild_chapter_index(project_id)
            storage.sync_novel_file(project_id)
            storage.append_event(project_id, "chapter_deleted", {"chapter_no": chapter_no, "reason": reason, "archive": str(archive_dir), "moved": moved})
        except Exception as exc:
            moved.append({"error": str(exc)})
    report = {"ok": True, "generated_at": _now(), "project_id": project_id, "chapter_no": chapter_no, "apply": apply, "reason": reason, "candidate_count": len(candidates), "candidates": [str(p) for p in candidates], "archive": str(archive_dir), "moved": moved}
    return _write_report(paths, "delete_chapter", report, _delete_md(report))


def command_parity_report(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    status = {"covered": 0, "partial": 0, "missing": 0}
    for row in COMMAND_PARITY_ROWS:
        status[row["status"]] = status.get(row["status"], 0) + 1
    report = {"ok": status.get("missing", 0) == 0, "generated_at": _now(), "project_id": project_id, "sources": ["lingfengQAQ/webnovel-writer", "lujih/webnovel-writer-opencode"], "summary": status, "rows": COMMAND_PARITY_ROWS}
    return _write_report(paths, "parity", report, _parity_md(report))


def _write_report(paths: Any, name: str, data: dict[str, Any], markdown: str) -> dict[str, Any]:
    out_dir = ensure_dir(Path(paths.control) / "reports" / name)
    json_path = out_dir / f"last_{name}.json"
    md_path = out_dir / f"last_{name}.md"
    write_json(json_path, data)
    write_text(md_path, markdown)
    data.setdefault("paths", {})
    data["paths"].update({"json": str(json_path), "markdown": str(md_path)})
    write_json(json_path, data)
    return data



def _status_focus_summary(report: dict[str, Any], focus: str) -> dict[str, Any]:
    counts = report.get("counts") or {}
    queues = report.get("queues") or {}
    if focus == "urgency":
        return {
            "focus": "urgency",
            "rejected": counts.get("rejected", 0),
            "ready_to_write": queues.get("ready_to_write") or [],
            "needs_repair": queues.get("needs_repair") or [],
            "ready_to_publish": queues.get("ready_to_publish") or [],
            "next_actions": [
                "优先处理 needs_repair / rejected 章节。",
                "运行 preflight --chapter 下一章，确认写前条件。",
                "运行 publish-queue 检查可发布章节。",
            ],
        }
    if focus == "progress":
        return {
            "focus": "progress",
            "latest_chapter": report.get("latest_chapter"),
            "next_chapter": report.get("next_chapter"),
            "chapters": counts.get("chapters", 0),
            "commits": counts.get("commits", 0),
            "reviews": counts.get("reviews", 0),
            "published": len(queues.get("published") or []) if isinstance(queues, dict) else 0,
        }
    return {
        "focus": "all",
        "latest_chapter": report.get("latest_chapter"),
        "next_chapter": report.get("next_chapter"),
        "counts": counts,
        "queue_names": sorted((queues or {}).keys()) if isinstance(queues, dict) else [],
    }


def _project_status_md(report: dict[str, Any]) -> str:
    lines = ["# 项目状态", "", f"- focus：{report.get('focus')}", f"- 最新已入账章节：{report.get('latest_chapter')}", f"- 下一章：{report.get('next_chapter')}", "", "## 焦点摘要"]
    for k, v in (report.get("focus_summary") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 数量"]
    for k, v in (report.get("counts") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 队列"]
    for k, v in (report.get("queues") or {}).items():
        lines.append(f"- {k}: {len(v) if isinstance(v, list) else v}")
    return "\n".join(lines).strip() + "\n"


def _preflight_md(report: dict[str, Any]) -> str:
    lines = [f"# 第 {report.get('chapter_no')} 章写前预检", "", f"- 状态：{'通过' if report.get('ok') else '需要处理'}", f"- 问题数：{report.get('issue_count')}", "", "## 问题"]
    for item in report.get("issues") or []:
        lines.append(f"- [{item.get('level')}] {item.get('code')}: {item.get('message')}")
    if not report.get("issues"):
        lines.append("暂无问题。")
    lines += ["", "## 建议动作"]
    for item in report.get("next_actions") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"


def _query_md(report: dict[str, Any]) -> str:
    lines = [f"# 查询：{report.get('query')}", "", "## 实体命中"]
    for item in report.get("entity_hits") or []:
        lines.append(f"- {item.get('bucket')} / {item.get('name')}")
    if not report.get("entity_hits"):
        lines.append("暂无实体命中。")
    lines += ["", "## 分块召回"]
    for hit in report.get("chunk_hits") or []:
        lines.append(f"- 第{hit.get('chapter_no')}章 score={hit.get('score')}: {str(hit.get('snippet') or '')[:120]}")
    if not report.get("chunk_hits"):
        lines.append("暂无分块召回。")
    return "\n".join(lines).strip() + "\n"


def _export_md(report: dict[str, Any]) -> str:
    paths = report.get("paths") or {}
    return f"""# 导出报告

- 章节数：{report.get('chapter_count')}
- TXT：{paths.get('txt')}
- Markdown：{paths.get('markdown')}
- TOC：{paths.get('toc')}
- ZIP：{paths.get('zip')}
"""


def _delete_md(report: dict[str, Any]) -> str:
    lines = [f"# 安全删除第 {report.get('chapter_no')} 章", "", f"- apply：{report.get('apply')}", f"- 原因：{report.get('reason')}", f"- 候选文件数：{report.get('candidate_count')}", f"- 归档目录：{report.get('archive')}", "", "## 候选文件"]
    for p in report.get("candidates") or []:
        lines.append(f"- {p}")
    lines += ["", "## 已移动"]
    for item in report.get("moved") or []:
        lines.append(f"- {item}")
    if not report.get("moved"):
        lines.append("未执行移动；加 --apply 才会归档删除。")
    return "\n".join(lines).strip() + "\n"


def _parity_md(report: dict[str, Any]) -> str:
    lines = ["# 对标命令能力报告", "", "来源：lingfengQAQ/webnovel-writer、lujih/webnovel-writer-opencode。", "", "| 来源 | 对方命令 | 本项目后端命令 | 状态 | 说明 |", "|---|---|---|---|---|"]
    for row in report.get("rows") or []:
        lines.append(f"| {row.get('source')} | {row.get('source_command')} | {row.get('backend_command')} | {row.get('status')} | {row.get('note')} |")
    return "\n".join(lines).strip() + "\n"


def _preflight_actions(issues: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    codes = {x.get("code") for x in issues}
    if "missing_blueprint" in codes:
        actions.append("先补 chapter_XXXX.md 蓝图或运行 plan/contract。")
    if "missing_chunk_index" in codes:
        actions.append("运行 rebuild-search 重建分块召回索引。")
    if "missing_model_routes" in codes:
        actions.append("运行 model-routes 生成模型任务路由。")
    if "missing_genre_profile" in codes:
        actions.append("运行 genre 生成题材规则。")
    if any(str(c).startswith("unknown_") for c in codes):
        actions.append("在 writer_control/entities/*.md 登记蓝图引用实体，然后 sync。")
    if not actions:
        actions.append("可以进入写章流程。")
    return actions


def _safe_json(path: Path) -> dict[str, Any]:
    try:
        data = read_json(path, {}) if path.exists() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value).strip("_") or "novel"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
