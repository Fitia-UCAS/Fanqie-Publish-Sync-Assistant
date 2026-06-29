from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.adapters.webnovel_writer import WebnovelWriterService
from backend.shared.task.task_callbacks import TaskCallbacks


def dump(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "projectId": str(Path(args.project).expanduser()),
        "projectPath": str(Path(args.project).expanduser()),
        "chapterNo": getattr(args, "chapter", 1),
        "recentContextCount": getattr(args, "recent", 6),
        "force": getattr(args, "force", False),
        "target": getattr(args, "target", ""),
        "reason": getattr(args, "reason", "manual"),
        "start": getattr(args, "start", 0),
        "end": getattr(args, "end", 0),
        "includeWarnings": getattr(args, "include_warnings", False),
        "status": getattr(args, "status", ""),
        "platform": getattr(args, "platform", ""),
        "externalId": getattr(args, "external_id", ""),
        "note": getattr(args, "note", ""),
        "sampleLimit": getattr(args, "sample_limit", 80),
        "apply": getattr(args, "apply", False),
        "query": getattr(args, "query", ""),
        "topK": getattr(args, "top_k", 8),
        "excludeChapter": getattr(args, "exclude_chapter", 0),
        "title": getattr(args, "title", ""),
        "genre": getattr(args, "genre", ""),
        "premise": getattr(args, "premise", ""),
        "novelFilePath": getattr(args, "novel_file", ""),
        "storyConfigPath": getattr(args, "story_config", ""),
        "planType": getattr(args, "plan_type", ""),
        "volumeNo": getattr(args, "volume", 1),
        "chapterTitle": getattr(args, "chapter_title", ""),
        "targetWords": getattr(args, "target_words", 2200),
        "strictness": getattr(args, "strictness", "标准门禁"),
        "autoFix": getattr(args, "auto_fix", False),
        "writeAfterRewrite": getattr(args, "write", False),
        "stage": getattr(args, "stage", "prewrite"),
        "health": getattr(args, "health", False),
        "workspace": getattr(args, "workspace", ""),
        "event": getattr(args, "event", "manual"),
        "logPayload": _json_arg(getattr(args, "payload_json", "")),
        "ledgerAction": getattr(args, "ledger_action", "summary"),
        "ledgerPayload": _json_arg(getattr(args, "payload_json", "")),
        "step": getattr(args, "step", ""),
        "statePatch": _json_arg(getattr(args, "patch_json", "")),
        "memoryAction": getattr(args, "memory_action", "stats"),
        "category": getattr(args, "category", ""),
        "subject": getattr(args, "subject", ""),
        "action": getattr(args, "action", ""),
        "focus": getattr(args, "focus", "all"),
        "source": getattr(args, "source", ""),
        "reviewResult": getattr(args, "review_result", ""),
        "extractionResult": getattr(args, "extraction_result", ""),
        "fulfillmentResult": getattr(args, "fulfillment_result", ""),
        "disambiguationResult": getattr(args, "disambiguation_result", ""),
        "range": getattr(args, "range", ""),
        "deep": getattr(args, "deep", False),
        "budget": getattr(args, "budget", 24000),
        "maxRounds": getattr(args, "max_rounds", 3),
    }


def _json_arg(raw: str) -> dict[str, object]:
    raw = str(raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"value": data}
    except Exception:
        return {"raw": raw}




def _parse_range_text(raw: str, default_start: int = 1, default_end: int | None = None) -> tuple[int, int]:
    """Parse reference-style ranges like '12' or '1-5'."""
    text = str(raw or "").strip()
    if not text:
        return default_start, default_start if default_end is None else default_end
    text = text.replace("—", "-").replace("–", "-").replace("至", "-").replace("到", "-").replace("~", "-")
    if "-" in text:
        left, right = text.split("-", 1)
        start = int(left.strip() or default_start)
        end = int(right.strip() or start)
    else:
        start = end = int(text)
    if start <= 0 or end <= 0:
        raise ValueError("范围必须是正整数。")
    if end < start:
        raise ValueError("范围结束值不能小于开始值。")
    return start, end


def _run_review_range(service: WebnovelWriterService, args: argparse.Namespace, callbacks: TaskCallbacks) -> None:
    start, end = _parse_range_text(getattr(args, "range", ""), getattr(args, "chapter", 1), getattr(args, "chapter", 1))
    outputs = []
    ok = True
    for chapter_no in range(start, end + 1):
        child = dict(payload(args), chapterNo=chapter_no)
        result = service.review_chapter(child, callbacks)
        outputs.append(result.to_dict())
        ok = ok and bool(result.ok)
    dump({"ok": ok, "message": f"审查完成：第 {start}-{end} 章", "range": {"start": start, "end": end}, "outputs": outputs})


def _run_plan_range(service: WebnovelWriterService, args: argparse.Namespace, callbacks: TaskCallbacks) -> None:
    plan_type = getattr(args, "plan_type", "blueprint")
    raw_range = getattr(args, "range", "")
    if not raw_range:
        dump(service.plan(payload(args), callbacks).to_dict())
        return
    start, end = _parse_range_text(raw_range, getattr(args, "volume", 1), getattr(args, "volume", 1))
    outputs = []
    ok = True
    for no in range(start, end + 1):
        if plan_type == "blueprint":
            child = dict(payload(args), chapterNo=no)
        else:
            child = dict(payload(args), volumeNo=no)
        result = service.plan(child, callbacks)
        outputs.append(result.to_dict())
        ok = ok and bool(result.ok)
    label = "章节蓝图" if plan_type == "blueprint" else "分卷大纲"
    dump({"ok": ok, "message": f"{label}规划完成：{start}-{end}", "range": {"start": start, "end": end}, "outputs": outputs})


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.adapters.webnovel_writer.webnovel_writer_cli", description="网文写作后端管理工具")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ['init', 'plan', 'write', 'write-batch', 'review', 'rewrite', 'heal', 'publish', 'deconstruct', 'references', 'templates', 'sync', 'doctor', 'context', 'dashboard', 'audit', 'impact', 'backup', 'ssot', 'repair-plan', 'quality', 'lifecycle', 'publish-queue', 'publish-status', 'trace', 'memory', 'memory-stats', 'memory-query', 'memory-dump', 'memory-conflicts', 'memory-bootstrap', 'memory-update', 'learn', 'continuity', 'revision-plan', 'invalidate', 'rebuild-projections', 'contract', 'contracts', 'truth', 'debts', 'rebuild-search', 'search', 'entity-occurrences', 'model-routes', 'model-plan', 'genre', 'language', 'project-status', 'preflight', 'query', 'export', 'export-package', 'delete-chapter', 'parity', 'where', 'use', 'write-gate', 'story-events', 'user-report', 'run-ledger', 'run-log', 'status', 'update-state', 'archive', 'extract-context', 'index', 'state', 'rag', 'entity', 'style', 'migrate', 'projections', 'story-system', 'chapter-commit', 'review-pipeline', 'memory-contract', 'validate-csv', 'quality-trend', 'rename-chapter', 'update-master-outline', 'runtime-health', 'amend-proposal', 'override-ledger', 'deep-align', 'workflow', 'checkpoint', 'memory-deep', 'rag-vector', 'review-deep', 'schema-validate', 'sqlite', 'publisher-bridge', 'orchestrate-deep', 'workflow-resume', 'memory-orchestrate', 'rag-router', 'review-pipeline-deep', 'sqlite-schema', 'publisher-sync', 'alignment-gaps', 'agent-registry', 'context-manager', 'workflow-runner', 'memory-contract-deep', 'event-projection', 'review-converge', 'deep-align-v22', 'alignment-audit-v23', 'alignment-optimize-v23', 'alignment-query-v23', 'alignment-gaps-v24', 'alignment-optimize-v24', 'alignment-query-v24', 'alignment-gaps-v25', 'alignment-optimize-v25', 'alignment-query-v25', 'alignment-gaps-v26', 'alignment-optimize-v26', 'alignment-query-v26', 'fusion-gaps-v27', 'fusion-optimize-v27', 'fusion-query-v27', 'behavior-gaps-v28', 'behavior-run-v28', 'behavior-query-v28', 'vector-rag-v29', 'production-gaps-v29', 'production-optimize-v29', 'production-gaps-v30', 'production-optimize-v30', 'production-query-v30']:
        p = sub.add_parser(name)
        p.add_argument("--project", required=True, help="小说项目目录")
        if name == "init":
            p.add_argument("--title", default="", help="书名")
            p.add_argument("--genre", default="", help="题材")
            p.add_argument("--premise", default="", help="核心创意/简介")
            p.add_argument("--novel-file", default="", help="可选：已有小说 TXT 路径")
            p.add_argument("--story-config", default="", help="可选：设定 Markdown/JSON 路径")
        if name == "plan":
            p.add_argument("--plan-type", choices=["full", "volume", "blueprint"], default="blueprint", help="规划类型")
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--volume", type=int, default=1)
            p.add_argument("--range", default="", help="兼容 /webnovel-plan 2-3；volume/full 表示卷范围，blueprint 表示章节范围")
        if name in {"write", "review", "rewrite", "heal"}:
            p.add_argument("--chapter", type=int, default=1)
            if name == "review":
                p.add_argument("--range", default="", help="兼容 /webnovel-review 1-5；为空时只审查 --chapter")
        if name in {"write", "write-batch", "rewrite", "heal"}:
            p.add_argument("--chapter-title", default="", help="章节标题")
            p.add_argument("--target-words", type=int, default=2200)
            p.add_argument("--strictness", default="标准门禁")
            p.add_argument("--auto-fix", action="store_true")
        if name == "write-batch":
            p.add_argument("--start", type=int, default=1)
            p.add_argument("--end", type=int, default=1)
        if name in {"rewrite", "heal"}:
            p.add_argument("--apply", action="store_true", help="rewrite: 执行失效归档；heal: 尝试自动修复写入")
            p.add_argument("--write", action="store_true", help="rewrite apply 后继续调用写章流水线")
            p.add_argument("--reason", default="rewrite")
        if name in {"templates", "model-routes", "genre"}:
            p.add_argument("--force", action="store_true", help="覆盖已有 Markdown 模板")
        if name in {"context", "repair-plan", "quality", "trace", "revision-plan", "invalidate", "contract", "language", "preflight", "delete-chapter"}:
            p.add_argument("--chapter", type=int, default=1)
            if name == "context":
                p.add_argument("--recent", type=int, default=6)
        if name == "doctor":
            p.add_argument("--chapter", type=int, default=0, help="兼容 /webnovel-doctor --chapter N；只聚焦单章体检")
            p.add_argument("--deep", action="store_true", help="兼容 /webnovel-doctor --deep；附加 SSOT/continuity/audit 深度体检")
        if name == "impact":
            p.add_argument("--target", default="", help="实体名或 ID；为空时输出全部关系")
        if name in {"search", "query", "alignment-query-v24", "alignment-query-v25", "alignment-query-v26", "alignment-optimize-v25", "alignment-optimize-v26", "fusion-query-v27", "fusion-optimize-v27", "behavior-query-v28", "behavior-run-v28"}:
            p.add_argument("--query", default="", help="要召回的关键词/语义描述")
            p.add_argument("--top-k", type=int, default=8, help="返回分块数量")
            p.add_argument("--exclude-chapter", type=int, default=0, help="排除某章，常用于写章前召回")
        if name == "backup":
            p.add_argument("--action", choices=["create", "list", "verify", "restore-plan"], default="create", help="备份管理动作")
            p.add_argument("--target", default="", help="verify/restore-plan 使用的 zip 路径或文件名")
            p.add_argument("--reason", default="manual", help="快照原因标签")
        if name == "delete-chapter":
            p.add_argument("--apply", action="store_true", help="真正归档删除；不加则只预演")
            p.add_argument("--reason", default="manual", help="删除/归档原因标签")
        if name == "learn":
            p.add_argument("--sample-limit", type=int, default=80, help="拆书/文风学习样本章节数")
        if name == "invalidate":
            p.add_argument("--apply", action="store_true", help="真正归档失效章节；不加则只生成预演")
            p.add_argument("--reason", default="rewrite", help="失效原因标签")
        if name in {"publish-queue", "contracts"}:
            p.add_argument("--start", type=int, default=0 if name == "publish-queue" else 1)
            p.add_argument("--end", type=int, default=0)
            if name == "publish-queue":
                p.add_argument("--include-warnings", action="store_true")
        if name == "publish-status":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--status", default="pending")
            p.add_argument("--platform", default="fanqie")
            p.add_argument("--external-id", default="")
            p.add_argument("--note", default="")
        if name == "publish":
            p.add_argument("--start", type=int, default=0)
            p.add_argument("--end", type=int, default=0)
            p.add_argument("--include-warnings", action="store_true")
        if name == "deconstruct":
            p.add_argument("--source", default="", help="可选：参考小说 TXT/Markdown 路径；为空则解构本项目已有章节")
        if name in {"alignment-optimize-v25", "alignment-optimize-v26", "fusion-optimize-v27", "behavior-run-v28"}:
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--budget", type=int, default=24000)
        if name in {"alignment-optimize-v24", "alignment-gaps-v24"}:
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--budget", type=int, default=24000)
            p.add_argument("--sample-limit", type=int, default=80)
        if name == "references":
            p.add_argument("--action", choices=["init", "build", "rebuild", "stats", "search", "query"], default="stats")
            p.add_argument("--query", default="")
            p.add_argument("--top-k", type=int, default=8)

        if name == "use":
            p.add_argument("--workspace", default="", help="可选：要绑定的工作区目录，默认当前目录")
        if name == "write-gate":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--stage", choices=["prewrite", "precommit", "postcommit"], default="prewrite")
        if name == "story-events":
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--health", action="store_true")
        if name == "user-report":
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--stage", default="write")
        if name == "run-log":
            p.add_argument("--event", default="manual")
            p.add_argument("--payload-json", default="{}")
        if name == "run-ledger":
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--ledger-action", choices=["summary", "record", "record-write-step", "write-resume", "resume"], default="summary")
            p.add_argument("--step", default="")
            p.add_argument("--status", default="")
            p.add_argument("--payload-json", default="{}")
        if name == "status":
            p.add_argument("--focus", choices=["all", "progress", "urgency"], default="all")
        if name == "update-state":
            p.add_argument("--patch-json", default="{}")
            p.add_argument("--reason", default="manual")
        if name == "archive":
            p.add_argument("--action", choices=["create", "list", "verify", "restore-plan"], default="create", help="归档管理动作")
            p.add_argument("--target", default="", help="verify/restore-plan 使用的 zip 路径或文件名")
            p.add_argument("--reason", default="manual")
        if name == "extract-context":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--recent", type=int, default=6)
        if name in {"memory-stats", "memory-query", "memory-dump", "memory-conflicts", "memory-bootstrap", "memory-update"}:
            p.add_argument("--query", default="")
            p.add_argument("--category", default="")
            p.add_argument("--subject", default="")
            p.add_argument("--status", default="")
        if name in {"index", "state", "rag", "entity", "style", "migrate", "projections", "story-system", "memory-contract"}:
            p.add_argument("--action", default="", help="参考项目兼容子动作，例如 stats/rebuild/query/replay/persist")
            p.add_argument("--query", default="")
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--start", type=int, default=0)
            p.add_argument("--end", type=int, default=0)
            p.add_argument("--top-k", type=int, default=8)
            p.add_argument("--sample-limit", type=int, default=80)
            p.add_argument("--patch-json", default="{}")
            p.add_argument("--genre", default="")
        if name == "chapter-commit":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--review-result", default="")
            p.add_argument("--fulfillment-result", default="")
            p.add_argument("--disambiguation-result", default="")
            p.add_argument("--extraction-result", default="")
        if name == "review-pipeline":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--review-result", default="")
        if name == "rename-chapter":
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--chapter-title", default="", help="新章节标题")
            p.add_argument("--apply", action="store_true", help="真正重命名文件；不加则只预演")
        if name == "update-master-outline":
            p.add_argument("--apply", action="store_true", default=True, help="写入大纲/总纲.md")
        if name == "amend-proposal":
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--query", default="")
        if name == "override-ledger":
            p.add_argument("--chapter", type=int, default=0)
            p.add_argument("--reason", default="manual")
            p.add_argument("--patch-json", default="{}")
            p.add_argument("--apply", action="store_true")
        if name in {"workflow", "checkpoint", "memory-deep", "rag-vector", "vector-rag-v29", "production-gaps-v29", "production-optimize-v29", "production-gaps-v30", "production-optimize-v30", "production-query-v30", "review-deep", "schema-validate", "sqlite", "publisher-bridge", "orchestrate-deep", "workflow-resume", "memory-orchestrate", "rag-router", "review-pipeline-deep", "sqlite-schema", "publisher-sync", "alignment-gaps", "agent-registry", "context-manager", "workflow-runner", "memory-contract-deep", "event-projection", "review-converge", "deep-align-v22", "alignment-audit-v23", "alignment-optimize-v23", "alignment-query-v23"}:
            p.add_argument("--action", default="", help="子动作，如 status/build/query/rebuild/plan/queue")
            p.add_argument("--chapter", type=int, default=1)
            p.add_argument("--query", default="")
            p.add_argument("--top-k", type=int, default=8)
            p.add_argument("--start", type=int, default=0)
            p.add_argument("--end", type=int, default=0)
            p.add_argument("--platform", default="fanqie")
            p.add_argument("--budget", type=int, default=24000)
            p.add_argument("--max-rounds", type=int, default=3)
            p.add_argument("--step", default="")
            p.add_argument("--status", default="ok")
            p.add_argument("--payload-json", default="{}")
    args = parser.parse_args()
    service = WebnovelWriterService()
    callbacks = TaskCallbacks()
    if args.cmd == "init":
        data = service.save_project(payload(args))
        # 初始化后立刻生成后端控制模板、同步题材与模型路由；这对应两个参考项目的 /webnovel-init 能力。
        init_payload = dict(payload(args), projectId=data.get("meta", {}).get("project_id") or payload(args).get("projectId"))
        service.refresh_templates(init_payload, callbacks)
        service.model_routes(init_payload, callbacks)
        service.genre_templates(init_payload, callbacks)
        dump({"ok": True, "message": "项目初始化完成", **data})
    elif args.cmd == "plan":
        _run_plan_range(service, args, callbacks)
    elif args.cmd == "write":
        dump(service.write_chapter(payload(args), callbacks).to_dict())
    elif args.cmd == "write-batch":
        dump(service.batch_write(payload(args), callbacks).to_dict())
    elif args.cmd == "review":
        _run_review_range(service, args, callbacks)
    elif args.cmd == "rewrite":
        if not getattr(args, "apply", False):
            dump(service.revision_plan(payload(args), callbacks).to_dict())
        else:
            result = service.invalidate_from(payload(args), callbacks).to_dict()
            if getattr(args, "write", False):
                result = {"rewrite": result, "write": service.write_chapter(payload(args), callbacks).to_dict()}
            dump(result)
    elif args.cmd == "heal":
        if not getattr(args, "apply", False):
            dump(service.repair_plan(payload(args), callbacks).to_dict())
        else:
            heal_payload = dict(payload(args), autoFix=True)
            dump(service.write_chapter(heal_payload, callbacks).to_dict())
    elif args.cmd == "templates":
        dump(service.refresh_templates(payload(args), callbacks).to_dict())
    elif args.cmd == "sync":
        dump(service.sync_control(payload(args), callbacks).to_dict())
    elif args.cmd == "doctor":
        dump(service.validate_project(payload(args), callbacks).to_dict())
    elif args.cmd == "context":
        dump(service.prepare_context_pack(payload(args), callbacks).to_dict())
    elif args.cmd == "audit":
        dump(service.audit_backend(payload(args), callbacks).to_dict())
    elif args.cmd == "impact":
        dump(service.impact(payload(args), callbacks).to_dict())
    elif args.cmd == "backup":
        dump(service.backup_project(payload(args), callbacks).to_dict())
    elif args.cmd == "ssot":
        dump(service.ssot_check(payload(args), callbacks).to_dict())
    elif args.cmd == "repair-plan":
        dump(service.repair_plan(payload(args), callbacks).to_dict())
    elif args.cmd == "quality":
        dump(service.local_quality(payload(args), callbacks).to_dict())
    elif args.cmd == "lifecycle":
        dump(service.lifecycle(payload(args), callbacks).to_dict())
    elif args.cmd == "publish-queue":
        dump(service.publish_queue(payload(args), callbacks).to_dict())
    elif args.cmd == "publish-status":
        dump(service.publish_status(payload(args), callbacks).to_dict())
    elif args.cmd == "publish":
        dump(service.publish(payload(args), callbacks).to_dict())
    elif args.cmd == "deconstruct":
        dump(service.deconstruct(payload(args), callbacks).to_dict())
    elif args.cmd == "references":
        dump(service.references(payload(args), callbacks).to_dict())
    elif args.cmd == "trace":
        dump(service.trace_chapter(payload(args), callbacks).to_dict())
    elif args.cmd == "memory":
        dump(service.memory(payload(args), callbacks).to_dict())
    elif args.cmd == "learn":
        dump(service.learn_style(payload(args), callbacks).to_dict())
    elif args.cmd == "continuity":
        dump(service.continuity(payload(args), callbacks).to_dict())
    elif args.cmd == "revision-plan":
        dump(service.revision_plan(payload(args), callbacks).to_dict())
    elif args.cmd == "invalidate":
        dump(service.invalidate_from(payload(args), callbacks).to_dict())
    elif args.cmd == "contract":
        dump(service.runtime_contract(payload(args), callbacks).to_dict())
    elif args.cmd == "contracts":
        dump(service.contract_index(payload(args), callbacks).to_dict())
    elif args.cmd == "truth":
        dump(service.truth_projection(payload(args), callbacks).to_dict())
    elif args.cmd == "debts":
        dump(service.debt_report(payload(args), callbacks).to_dict())
    elif args.cmd == "rebuild-search":
        dump(service.rebuild_search_index(payload(args), callbacks).to_dict())
    elif args.cmd == "search":
        dump(service.search_index(payload(args), callbacks).to_dict())
    elif args.cmd == "entity-occurrences":
        dump(service.entity_occurrences(payload(args), callbacks).to_dict())
    elif args.cmd == "model-routes":
        dump(service.model_routes(payload(args), callbacks).to_dict())
    elif args.cmd == "model-plan":
        dump(service.model_plan(payload(args), callbacks).to_dict())
    elif args.cmd == "genre":
        dump(service.genre_templates(payload(args), callbacks).to_dict())
    elif args.cmd == "language":
        dump(service.language_check(payload(args), callbacks).to_dict())
    elif args.cmd == "project-status":
        dump(service.project_status(payload(args), callbacks).to_dict())
    elif args.cmd == "preflight":
        dump(service.preflight(payload(args), callbacks).to_dict())
    elif args.cmd == "query":
        dump(service.query_project(payload(args), callbacks).to_dict())
    elif args.cmd == "export":
        dump(service.export(payload(args), callbacks).to_dict())
    elif args.cmd == "export-package":
        dump(service.export_bundle(payload(args), callbacks).to_dict())
    elif args.cmd == "delete-chapter":
        dump(service.delete_chapter(payload(args), callbacks).to_dict())
    elif args.cmd == "parity":
        dump(service.command_parity(payload(args), callbacks).to_dict())
    elif args.cmd == "where":
        dump(service.where(payload(args), callbacks).to_dict())
    elif args.cmd == "use":
        dump(service.use(payload(args), callbacks).to_dict())
    elif args.cmd == "write-gate":
        dump(service.write_gate(payload(args), callbacks).to_dict())
    elif args.cmd == "story-events":
        dump(service.story_events(payload(args), callbacks).to_dict())
    elif args.cmd == "user-report":
        dump(service.user_report(payload(args), callbacks).to_dict())
    elif args.cmd == "run-log":
        dump(service.run_log(payload(args), callbacks).to_dict())
    elif args.cmd == "run-ledger":
        dump(service.run_ledger(payload(args), callbacks).to_dict())
    elif args.cmd == "status":
        dump(service.project_status(payload(args), callbacks).to_dict())
    elif args.cmd == "update-state":
        dump(service.update_state(payload(args), callbacks).to_dict())
    elif args.cmd == "archive":
        dump(service.archive(payload(args), callbacks).to_dict())
    elif args.cmd == "extract-context":
        dump(service.extract_context(payload(args), callbacks).to_dict())
    elif args.cmd in {"memory-stats", "memory-query", "memory-dump", "memory-conflicts", "memory-bootstrap", "memory-update"}:
        data = payload(args)
        data["memoryAction"] = args.cmd.replace("memory-", "")
        dump(service.memory_ops(data, callbacks).to_dict())
    elif args.cmd == "index":
        dump(service.index_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "state":
        dump(service.state_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "rag":
        dump(service.rag_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "entity":
        dump(service.entity_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "style":
        dump(service.style_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "migrate":
        dump(service.migrate_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "projections":
        dump(service.projections_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "story-system":
        dump(service.story_system_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "chapter-commit":
        dump(service.chapter_commit_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "review-pipeline":
        dump(service.review_pipeline_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "memory-contract":
        dump(service.memory_contract_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "validate-csv":
        dump(service.validate_csv(payload(args), callbacks).to_dict())
    elif args.cmd == "quality-trend":
        dump(service.quality_trend(payload(args), callbacks).to_dict())
    elif args.cmd == "rename-chapter":
        dump(service.rename_chapter(payload(args), callbacks).to_dict())
    elif args.cmd == "update-master-outline":
        dump(service.update_master_outline(payload(args), callbacks).to_dict())
    elif args.cmd == "runtime-health":
        dump(service.runtime_health(payload(args), callbacks).to_dict())
    elif args.cmd == "amend-proposal":
        dump(service.amend_proposal(payload(args), callbacks).to_dict())
    elif args.cmd == "override-ledger":
        dump(service.override_ledger(payload(args), callbacks).to_dict())
    elif args.cmd == "deep-align":
        dump(service.deep_align(payload(args), callbacks).to_dict())
    elif args.cmd in {"workflow", "checkpoint"}:
        data = payload(args)
        if args.cmd == "checkpoint" and not data.get("action"):
            data["action"] = "status"
        dump(service.workflow_ops(data, callbacks).to_dict())
    elif args.cmd == "memory-deep":
        dump(service.memory_deep(payload(args), callbacks).to_dict())
    elif args.cmd == "rag-vector":
        dump(service.rag_vector(payload(args), callbacks).to_dict())
    elif args.cmd == "review-deep":
        dump(service.review_deep(payload(args), callbacks).to_dict())
    elif args.cmd == "schema-validate":
        dump(service.schema_validate(payload(args), callbacks).to_dict())
    elif args.cmd == "sqlite":
        dump(service.sqlite_ops(payload(args), callbacks).to_dict())
    elif args.cmd == "publisher-bridge":
        dump(service.publisher_bridge(payload(args), callbacks).to_dict())
    elif args.cmd == "orchestrate-deep":
        dump(service.orchestrate_deep(payload(args), callbacks).to_dict())
    elif args.cmd == "workflow-resume":
        data = dict(payload(args), action="resume")
        dump(service.orchestrate_deep(data, callbacks).to_dict())
    elif args.cmd == "memory-orchestrate":
        dump(service.memory_orchestrate(payload(args), callbacks).to_dict())
    elif args.cmd == "rag-router":
        dump(service.rag_router(payload(args), callbacks).to_dict())
    elif args.cmd == "review-pipeline-deep":
        dump(service.review_pipeline_deep_v2(payload(args), callbacks).to_dict())
    elif args.cmd == "sqlite-schema":
        dump(service.sqlite_schema(payload(args), callbacks).to_dict())
    elif args.cmd == "publisher-sync":
        dump(service.publisher_sync(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-gaps":
        dump(service.alignment_gaps(payload(args), callbacks).to_dict())
    elif args.cmd == "agent-registry":
        dump(service.agent_registry(payload(args), callbacks).to_dict())
    elif args.cmd == "context-manager":
        dump(service.context_manager_deep_v2(payload(args), callbacks).to_dict())
    elif args.cmd == "workflow-runner":
        dump(service.workflow_runner_v2(payload(args), callbacks).to_dict())
    elif args.cmd == "memory-contract-deep":
        dump(service.memory_contract_deep_v2(payload(args), callbacks).to_dict())
    elif args.cmd == "event-projection":
        dump(service.event_projection_deep(payload(args), callbacks).to_dict())
    elif args.cmd == "review-converge":
        dump(service.review_converge(payload(args), callbacks).to_dict())
    elif args.cmd == "deep-align-v22":
        dump(service.deep_align_v22(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-audit-v23":
        dump(service.alignment_audit_v23(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-optimize-v23":
        dump(service.alignment_optimize_v23(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-query-v23":
        dump(service.alignment_query_v23(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-gaps-v24":
        dump(service.alignment_gaps_v24(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-optimize-v24":
        dump(service.alignment_optimize_v24(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-query-v24":
        dump(service.alignment_query_v24(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-gaps-v25":
        dump(service.alignment_gaps_v25(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-optimize-v25":
        dump(service.alignment_optimize_v25(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-query-v25":
        dump(service.alignment_query_v25(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-gaps-v26":
        dump(service.alignment_gaps_v26(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-optimize-v26":
        dump(service.alignment_optimize_v26(payload(args), callbacks).to_dict())
    elif args.cmd == "alignment-query-v26":
        dump(service.alignment_query_v26(payload(args), callbacks).to_dict())
    elif args.cmd == "fusion-gaps-v27":
        dump(service.fusion_gaps_v27(payload(args), callbacks).to_dict())
    elif args.cmd == "fusion-optimize-v27":
        dump(service.fusion_optimize_v27(payload(args), callbacks).to_dict())
    elif args.cmd == "fusion-query-v27":
        dump(service.fusion_query_v27(payload(args), callbacks).to_dict())
    elif args.cmd == "rebuild-projections":
        dump(service.rebuild_projections(payload(args), callbacks).to_dict())
    elif args.cmd == "dashboard":
        service.storage.sync_control_files(str(Path(args.project).expanduser()))
        dump(service.dashboard(str(Path(args.project).expanduser())))

    elif args.cmd == "behavior-gaps-v28":
        dump(service.behavior_gaps_v28(payload(args), callbacks).to_dict())
    elif args.cmd == "behavior-run-v28":
        dump(service.behavior_run_v28(payload(args), callbacks).to_dict())
    elif args.cmd == "behavior-query-v28":
        dump(service.behavior_query_v28(payload(args), callbacks).to_dict())
    elif args.cmd == "vector-rag-v29":
        dump(service.vector_rag_v29(payload(args), callbacks).to_dict())
    elif args.cmd == "production-gaps-v29":
        dump(service.production_gaps_v29(payload(args), callbacks).to_dict())
    elif args.cmd == "production-optimize-v29":
        dump(service.production_optimize_v29(payload(args), callbacks).to_dict())
    elif args.cmd == "production-gaps-v30":
        dump(service.production_gaps_v30(payload(args), callbacks).to_dict())
    elif args.cmd == "production-optimize-v30":
        dump(service.production_optimize_v30(payload(args), callbacks).to_dict())
    elif args.cmd == "production-query-v30":
        dump(service.production_query_v30(payload(args), callbacks).to_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
