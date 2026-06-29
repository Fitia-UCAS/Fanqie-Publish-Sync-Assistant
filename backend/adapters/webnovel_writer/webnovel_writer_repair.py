from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import read_text_auto, write_text


GATE_HINTS = {
    "prewrite": "先补蓝图、项目基础资料或上一章状态，再重新写章。",
    "draft": "修复 CHANGES 协议，确保正文后有明确 CHANGES 区域且字段完整。",
    "review": "根据 blocking_issues 局部重写，不要直接覆盖已通过的设定。",
    "data": "补齐 fulfillment/disambiguation/extraction 三件套，尤其是正文出现的新事实。",
    "consistency": "让正文、蓝图和 CHANGES 对齐；正文出现的实体必须申报。",
    "precommit": "检查 commit 字段完整性。",
    "postcommit": "检查正式正文、commit 与 story_state 投影。",
}


def build_repair_plan(storage: Any, project_id: str, chapter_no: int | None = None) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    rejected = storage.list_rejected(project_id)
    if chapter_no:
        rejected = [r for r in rejected if int(r.get("chapterNo") or 0) == chapter_no]
    if not rejected:
        report = {"ok": False, "message": "没有找到 rejected 草稿。", "chapter_no": chapter_no or 0, "checked_at": now_iso()}
        return _save_plan(paths, report)

    target = rejected[0]
    chapter_no = int(target.get("chapterNo") or chapter_no or 0)
    draft_path = Path(str(target.get("path") or ""))
    draft_text = read_text_auto(draft_path) if draft_path.exists() else ""
    latest_run = _latest_run(paths, chapter_no)
    artifacts = _collect_gate_artifacts(paths, chapter_no)
    gates = _extract_gate_failures(latest_run, artifacts)
    blueprint = storage.load_blueprint_json(project_id, chapter_no)
    context_md = Path(paths.control) / "context_packs" / f"chapter_{chapter_no:04d}_context.md"
    context_excerpt = read_text_auto(context_md)[:6000] if context_md.exists() else ""
    actions = _repair_actions(gates, blueprint, draft_text)
    prompt = _repair_prompt(chapter_no, draft_text, gates, blueprint, context_excerpt, actions)
    report = {
        "ok": True,
        "schema_version": 1,
        "created_at": now_iso(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "rejected_draft": str(draft_path),
        "latest_run": str(latest_run) if latest_run else "",
        "gate_failures": gates,
        "actions": actions,
        "repair_prompt": prompt,
    }
    return _save_plan(paths, report)


def repair_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# 第 {plan.get('chapter_no') or ''} 章修复计划",
        "",
        f"- 时间：{plan.get('created_at') or plan.get('checked_at') or ''}",
        f"- 状态：{'可修复' if plan.get('ok') else '无 rejected 草稿'}",
        f"- rejected：`{plan.get('rejected_draft', '')}`",
        "",
        "## 门禁问题",
        "",
    ]
    failures = plan.get("gate_failures") or []
    if not failures:
        lines.append("暂无可解析门禁问题。")
    for row in failures:
        lines.append(f"- [{row.get('stage')}] {row.get('message')}")
    lines += ["", "## 建议动作", ""]
    for action in plan.get("actions") or []:
        lines.append(f"- {action}")
    if plan.get("repair_prompt"):
        lines += ["", "## 可复制给模型的修复提示", "", "```text", str(plan.get("repair_prompt") or ""), "```"]
    return "\n".join(lines).rstrip() + "\n"


def _save_plan(paths: Any, plan: dict[str, Any]) -> dict[str, Any]:
    folder = Path(paths.control) / "reports" / "repair"
    folder.mkdir(parents=True, exist_ok=True)
    chapter_no = int(plan.get("chapter_no") or 0)
    stem = f"chapter_{chapter_no:04d}_repair_plan" if chapter_no else "last_repair_plan"
    json_path = write_json(folder / f"{stem}.json", plan)
    md_path = write_text(folder / f"{stem}.md", repair_plan_markdown(plan))
    write_json(folder / "last_repair_plan.json", plan)
    write_text(folder / "last_repair_plan.md", repair_plan_markdown(plan))
    plan["paths"] = {"json": str(json_path), "markdown": str(md_path), "latest": str(folder / "last_repair_plan.md")}
    return plan


def _latest_run(paths: Any, chapter_no: int) -> Path | None:
    runs = sorted(Path(paths.runs).glob(f"第{chapter_no:04d}章_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0] if runs else None


def _collect_gate_artifacts(paths: Any, chapter_no: int) -> list[dict[str, Any]]:
    folder = Path(paths.artifacts) / f"第{chapter_no:04d}章"
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*gate*.json")):
        data = read_json(path, {}) or {}
        rows.append({"path": str(path), "data": data})
    return rows


def _extract_gate_failures(run_path: Path | None, artifacts: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if run_path and run_path.exists():
        run = read_json(run_path, {}) or {}
        for step in run.get("steps") or []:
            if isinstance(step, dict):
                payload = step.get("payload") or step.get("result") or step
                if isinstance(payload, dict) and payload.get("ok") is False:
                    for msg in payload.get("errors") or payload.get("failures") or []:
                        rows.append({"stage": str(step.get("name") or payload.get("stage") or "run"), "message": str(msg)})
        gate = run.get("reject_gate") or {}
        if isinstance(gate, dict):
            for msg in gate.get("errors") or gate.get("failures") or []:
                rows.append({"stage": str(gate.get("stage") or "reject_gate"), "message": str(msg)})
    for item in artifacts:
        data = item.get("data") or {}
        if not isinstance(data, dict) or data.get("ok") is not False:
            continue
        stage = str(data.get("stage") or Path(str(item.get("path") or "")).stem)
        for msg in data.get("errors") or data.get("failures") or []:
            rows.append({"stage": stage, "message": str(msg)})
    dedup: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.get("stage", ""), row.get("message", ""))
        if key not in seen:
            seen.add(key)
            dedup.append(row)
    return dedup


def _repair_actions(gates: list[dict[str, str]], blueprint: dict[str, Any], draft_text: str) -> list[str]:
    actions: list[str] = []
    for row in gates:
        stage = str(row.get("stage") or "")
        message = str(row.get("message") or "")
        hint_key = next((k for k in GATE_HINTS if k in stage.lower()), "")
        if hint_key:
            actions.append(GATE_HINTS[hint_key])
        if "CHANGES" in message.upper() or "协议" in message:
            actions.append("补全 CHANGES：summary、characters、locations、foreshadows、conflicts 等字段至少使用空对象。")
        if "必达" in message or "蓝图" in message or "节点" in message:
            actions.append("逐条核对蓝图 must_cover_nodes，把未完成节点写入正文并在 CHANGES 中申报。")
        if "未申报" in message or "漏报" in message:
            actions.append("正文中出现的已登记实体必须写入 CHANGES 对应桶，不能只在正文里出现。")
        if "禁区" in message or "forbidden" in message.lower():
            actions.append("删除或改写触碰禁区的正文片段。")
    if blueprint.get("must_cover_nodes"):
        actions.append("保留蓝图必达节点：" + "；".join(map(str, blueprint.get("must_cover_nodes")[:6])))
    if len(draft_text.strip()) < 500:
        actions.append("草稿正文偏短，重写时先补足场景推进、冲突、情绪回报和章末钩子。")
    out: list[str] = []
    for action in actions:
        if action and action not in out:
            out.append(action)
    return out or ["根据门禁报告局部重写，修复后重新运行 write/review。"]


def _repair_prompt(chapter_no: int, draft_text: str, gates: list[dict[str, str]], blueprint: dict[str, Any], context_excerpt: str, actions: list[str]) -> str:
    gate_text = "\n".join(f"- [{g.get('stage')}] {g.get('message')}" for g in gates) or "- 未解析到具体门禁，按蓝图和 CHANGES 协议重新修复。"
    bp_nodes = "\n".join(f"- {x}" for x in (blueprint.get("must_cover_nodes") or [])) or "- 无"
    action_text = "\n".join(f"- {x}" for x in actions)
    draft_excerpt = re.sub(r"\n{3,}", "\n\n", draft_text.strip())[:9000]
    return f"""请只修复第 {chapter_no} 章，不要改设定，不要跳过门禁。

【门禁失败】
{gate_text}

【必须执行】
{action_text}

【蓝图必达节点】
{bp_nodes}

【上下文摘录】
{context_excerpt[:4000]}

【待修复草稿】
{draft_excerpt}

输出格式必须是：
正文

---CHANGES---
{{
  "summary": "本章摘要",
  "characters": {{}},
  "locations": {{}},
  "factions": {{}},
  "items": {{}},
  "foreshadows": {{}},
  "conflicts": {{}},
  "secrets": {{}},
  "pledges": {{}},
  "deadlines": {{}},
  "timeline": [],
  "hooks": []
}}
""".strip()
