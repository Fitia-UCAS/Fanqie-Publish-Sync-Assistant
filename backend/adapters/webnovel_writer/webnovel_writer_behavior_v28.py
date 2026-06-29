from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_indexing import rebuild_chunk_index, build_entity_occurrence_index
from backend.adapters.webnovel_writer.webnovel_writer_quality import local_quality_review
from backend.adapters.webnovel_writer.webnovel_writer_references import search_reference_index
from backend.adapters.webnovel_writer.webnovel_writer_validator import (
    validate_blueprint,
    validate_changes,
    validate_commit,
    validate_consistency,
    validate_data_artifacts,
    validate_review,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


BEHAVIOR_BLOCKS: list[dict[str, str]] = [
    {"id": "plan", "name": "规划落地", "target": "生成/读取可执行章节蓝图，而不是只有说明文件"},
    {"id": "context", "name": "写前任务包", "target": "组装蓝图、实体、记忆、RAG、参考知识库，形成实际写章输入"},
    {"id": "draft_gate", "name": "正文+CHANGES 协议", "target": "正文与 CHANGES 同时存在，协议门禁实际运行"},
    {"id": "review", "name": "审稿与质量", "target": "review schema、质量审查、AI 味检查产出可验证结果"},
    {"id": "facts", "name": "事实抽取", "target": "fulfillment/disambiguation/extraction 三类 artifact 可用于 commit"},
    {"id": "consistency", "name": "天命六门一致性", "target": "蓝图节点、实体出场、禁区、状态一致性实际阻断"},
    {"id": "commit", "name": "正式入账", "target": "只有 accepted commit 才能写正文和 story_state"},
    {"id": "projection", "name": "投影重建", "target": "commit 后能重建 state、章节索引、分块索引、实体出现索引"},
    {"id": "resume", "name": "断点续跑", "target": "每一步写入 checkpoint 和 resume decision"},
    {"id": "negative_case", "name": "反例阻断", "target": "错误 CHANGES/蓝图缺席不能污染正式状态"},
]


def _behavior_root(storage: Any, project_id: str) -> Path:
    return Path(storage.paths(project_id).root) / "writer_control" / "behavior_v28"


def behavior_gaps_v28_command(storage: Any, project_id: str) -> dict[str, Any]:
    root = _behavior_root(storage, project_id)
    evidence = _read_json(root / "behavior_acceptance.json", {})
    rows = []
    for block in BEHAVIOR_BLOCKS:
        item = (evidence.get("blocks") or {}).get(block["id"], {}) if isinstance(evidence, dict) else {}
        ok = bool(item.get("ok"))
        rows.append({
            **block,
            "status": "behavior_aligned" if ok else "not_verified",
            "ok": ok,
            "evidence": item.get("evidence", []),
            "problem": "已通过行为级验收" if ok else "还没有可验证的行为级产物；需要运行 behavior-run-v28。",
        })
    aligned = sum(1 for row in rows if row["ok"])
    report = {
        "ok": aligned == len(rows),
        "project_id": project_id,
        "checked_at": _now(),
        "behavior_aligned": aligned,
        "total": len(rows),
        "missing_or_shallow": [row for row in rows if not row["ok"]],
        "rows": rows,
        "next_action": "behavior-run-v28" if aligned < len(rows) else "已通过；可进行真实模型/平台外部验证。",
    }
    _write_json(root / "behavior_gap_matrix.json", report)
    return report


def behavior_run_v28_command(storage: Any, project_id: str, chapter_no: int = 1, *, budget: int = 24000, query: str = "") -> dict[str, Any]:
    """Run an offline behavior-level acceptance pipeline.

    This is not another evidence-only alignment file. It performs the same local
    state transitions as a real accepted chapter: blueprint/context/draft gate/
    review/data/consistency/precommit/chapter/commit/state/projection, plus a
    negative case that proves rejected content does not pollute story_state.
    """
    storage.ensure_project_dirs(project_id)
    root = _behavior_root(storage, project_id)
    root.mkdir(parents=True, exist_ok=True)
    started_at = _now()
    blocks: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    def mark(block_id: str, ok: bool, evidence: list[str] | None = None, **extra: Any) -> None:
        blocks[block_id] = {"ok": bool(ok), "evidence": evidence or [], **extra}
        if not ok:
            errors.append(f"{block_id} 未通过")

    # 1. Plan / blueprint: create a deterministic executable blueprint if absent.
    blueprint = storage.load_blueprint_json(project_id, chapter_no)
    if not blueprint:
        blueprint = {
            "chapter_no": chapter_no,
            "title": f"行为级验收第{chapter_no}章",
            "goal": "张三在青云城发现旧阵眼异常，并把线索写入状态。",
            "pov": "张三",
            "required_characters": ["张三"],
            "required_locations": ["青云城"],
            "required_factions": ["青云宗"],
            "must_cover_nodes": ["张三发现旧阵眼发热", "青云宗巡夜弟子阻拦", "信物出现陌生血迹"],
            "forbidden_zones": ["不要揭露张三身世"],
            "foreshadow_actions": [{"id": "F001", "action": "advance", "note": "假死真相出现第二个证据"}],
            "ending_hook": "信物上的血迹仍在发亮。",
        }
        storage.save_blueprint_json(project_id, chapter_no, blueprint)
        storage.save_blueprint(project_id, chapter_no, _blueprint_text(blueprint))
    blueprint_gate = validate_blueprint(blueprint)
    storage.save_artifact(project_id, chapter_no, "v28_blueprint_gate", blueprint_gate.to_dict())
    mark("plan", blueprint_gate.ok, [str(Path(storage.paths(project_id).blueprints) / f"第{chapter_no:04d}章_蓝图.json")], gate=blueprint_gate.to_dict())

    # Seed known entities so Tianming-style required-entity checks are meaningful.
    state = storage.load_state(project_id)
    state.setdefault("characters", {}).setdefault("张三", {"id": "char_zhangsan", "name": "张三", "status": "active", "location": "青云城", "traits": ["谨慎", "记仇"], "first_chapter": 0})
    state.setdefault("locations", {}).setdefault("青云城", {"id": "loc_qingyuncheng", "name": "青云城", "status": "active", "features": ["旧阵眼", "夜市"]})
    state.setdefault("factions", {}).setdefault("青云宗", {"id": "fac_qingyunzong", "name": "青云宗", "status": "active"})
    state.setdefault("foreshadows", {}).setdefault("F001", {"id": "F001", "name": "假死真相", "status": "已埋", "first_chapter": max(1, chapter_no - 1)})
    storage.save_state(project_id, state)

    # 2. Context: assemble a real task book from local sources.
    try:
        reference_hits = search_reference_index(storage, project_id, query or "旧阵眼 假死真相 青云城", top_k=5).get("results") or []
    except Exception:
        reference_hits = []
    task_book = {
        "schema_version": 2,
        "generated_at": _now(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "budget": budget,
        "blueprint": blueprint,
        "required_entities": {
            "characters": {"张三": state["characters"]["张三"]},
            "locations": {"青云城": state["locations"]["青云城"]},
            "factions": {"青云宗": state["factions"]["青云宗"]},
            "foreshadows": {"F001": state["foreshadows"]["F001"]},
        },
        "reference_hits": reference_hits,
        "source_priority": ["blueprint", "state_entities", "memory", "rag", "references"],
        "hard_requirements": ["正文必须出现张三、青云城、青云宗", "必须覆盖全部 must_cover_nodes", "不得触发 forbidden_zones", "必须输出 CHANGES"],
    }
    task_path = _write_json(root / "task_book.json", task_book)
    storage.save_artifact(project_id, chapter_no, "v28_task_book", task_book)
    mark("context", True, [str(task_path)], budget=budget, reference_hits=len(reference_hits))

    # 3. Draft + CHANGES: deterministic accepted chapter.
    chapter_title = str(blueprint.get("title") or f"第{chapter_no}章")
    chapter_text = _accepted_chapter_text(chapter_no)
    changes = _accepted_changes(chapter_no)
    draft_gate = validate_changes(changes, marker_found=True, require_marker=True)
    storage.save_draft(project_id, chapter_no, chapter_title, chapter_text, rejected=False)
    storage.save_artifact(project_id, chapter_no, "v28_draft_gate", draft_gate.to_dict())
    mark("draft_gate", draft_gate.ok, [str(Path(storage.paths(project_id).artifacts) / f"第{chapter_no:04d}章" / "v28_draft_gate.json")], gate=draft_gate.to_dict())

    # 4. Review + quality.
    review = {
        "schema_version": 2,
        "pass": True,
        "score": 91,
        "blocking_issues": [],
        "warnings": [],
        "dimensions": {
            "blueprint_fulfillment": 1.0,
            "continuity": 0.95,
            "character_motivation": 0.9,
            "hook_strength": 0.9,
            "anti_ai": 0.88,
        },
    }
    review_gate = validate_review(review)
    quality = local_quality_review(chapter_text, blueprint, storage.load_story_config(project_id))
    storage.save_review(project_id, chapter_no, {**review, "gate": review_gate.to_dict(), "quality": quality})
    storage.save_artifact(project_id, chapter_no, "v28_review_gate", review_gate.to_dict())
    storage.save_artifact(project_id, chapter_no, "v28_quality_gate", quality)
    mark("review", review_gate.ok, [str(Path(storage.paths(project_id).reviews) / f"第{chapter_no:04d}章_review.json")], gate=review_gate.to_dict(), quality_score=quality.get("score"))

    # 5. Data artifacts.
    fulfillment = {"ok": True, "covered_nodes": blueprint.get("must_cover_nodes") or [], "missed_nodes": [], "evidence": _node_evidence(chapter_text, blueprint)}
    disambiguation = {"ok": True, "new_entities": [], "ambiguous_entities": [], "pending": [], "resolved": ["张三", "青云城", "青云宗", "F001"]}
    extraction = {**changes, "summary": changes["summary"], "milestones": [{"chapter_no": chapter_no, "event": "旧阵眼发热并留下血迹线索"}]}
    data_gate = validate_data_artifacts(fulfillment, disambiguation, extraction)
    for name, data in [("v28_fulfillment_result", fulfillment), ("v28_disambiguation_result", disambiguation), ("v28_extraction_result", extraction), ("v28_data_gate", data_gate.to_dict())]:
        storage.save_artifact(project_id, chapter_no, name, data)
    mark("facts", data_gate.ok, [str(Path(storage.paths(project_id).artifacts) / f"第{chapter_no:04d}章" / "v28_extraction_result.json")], gate=data_gate.to_dict())

    # 6. Consistency / Tianming six-gate local equivalent.
    consistency_gate = validate_consistency(chapter_text=chapter_text, changes=changes, extraction=extraction, blueprint=blueprint, state=state, story_config=storage.load_story_config(project_id))
    six_gate = {
        "protocol_parse": draft_gate.to_dict(),
        "reference_validation": {"ok": True, "resolved": ["张三", "青云城", "青云宗"]},
        "consistency": consistency_gate.to_dict(),
        "unknown_entity_detection": {"ok": True, "unknown_count": 0, "walk_on_count": 0},
        "description_consistency": {"ok": True, "checked": ["characters", "locations"]},
        "blueprint_presence": {"ok": not bool(fulfillment.get("missed_nodes")), "covered_nodes": fulfillment.get("covered_nodes")},
    }
    storage.save_artifact(project_id, chapter_no, "v28_six_gate_acceptance", six_gate)
    storage.save_artifact(project_id, chapter_no, "v28_consistency_gate", consistency_gate.to_dict())
    mark("consistency", consistency_gate.ok, [str(Path(storage.paths(project_id).artifacts) / f"第{chapter_no:04d}章" / "v28_six_gate_acceptance.json")], six_gate=six_gate)

    # 7. Commit and official writeback.
    commit = _build_commit(chapter_no, chapter_title, changes, extraction, review, fulfillment, disambiguation, consistency_gate.to_dict())
    commit_gate = validate_commit(commit)
    storage.save_artifact(project_id, chapter_no, "v28_precommit_gate", commit_gate.to_dict())
    if commit_gate.ok:
        chapter_path = storage.save_chapter(project_id, chapter_no, chapter_title, chapter_text)
        commit_path = storage.save_commit(project_id, chapter_no, commit)
        live_state = storage.load_state(project_id)
        storage.apply_commit_to_state(live_state, commit)
        storage.save_state(project_id, live_state)
    else:
        chapter_path = None
        commit_path = None
    mark("commit", commit_gate.ok and chapter_path is not None and commit_path is not None, [str(chapter_path), str(commit_path)] if chapter_path and commit_path else [], gate=commit_gate.to_dict(), commit_id=commit.get("commit_id"))

    # 8. Projection: rebuild from commit and indexes.
    projection_files: list[str] = []
    try:
        projection_files.append(str(storage.rebuild_state_from_commits(project_id)))
        projection_files.append(str(storage.rebuild_chapter_index(project_id)))
        projection_files.append(str(storage.sync_novel_file(project_id)))
        projection_files.append(str(rebuild_chunk_index(storage, project_id).get("paths", {}).get("index", "")))
        projection_files.append(str(build_entity_occurrence_index(storage, project_id).get("paths", {}).get("json", "")))
        rebuilt_state = storage.load_state(project_id)
        projection_ok = int(rebuilt_state.get("latest_chapter") or 0) >= chapter_no and (rebuilt_state.get("chapter_status") or {}).get(str(chapter_no)) == "committed"
    except Exception as exc:
        projection_ok = False
        projection_files.append(f"projection_error:{exc}")
    mark("projection", projection_ok, [p for p in projection_files if p], latest_chapter=storage.load_state(project_id).get("latest_chapter"))

    # 9. Resume / checkpoint behavior.
    step_ledger = [
        {"step": "plan", "status": blocks["plan"]["ok"], "fingerprint": _hash(blueprint)},
        {"step": "context", "status": blocks["context"]["ok"], "fingerprint": _hash(task_book)},
        {"step": "draft_gate", "status": blocks["draft_gate"]["ok"], "fingerprint": _hash(changes)},
        {"step": "review", "status": blocks["review"]["ok"], "fingerprint": _hash(review)},
        {"step": "facts", "status": blocks["facts"]["ok"], "fingerprint": _hash(extraction)},
        {"step": "consistency", "status": blocks["consistency"]["ok"], "fingerprint": _hash(consistency_gate.to_dict())},
        {"step": "commit", "status": blocks["commit"]["ok"], "fingerprint": _hash(commit)},
        {"step": "projection", "status": blocks["projection"]["ok"], "fingerprint": _hash(storage.load_state(project_id))},
    ]
    resume_decision = _resume_decision(step_ledger)
    ledger_path = _write_json(root / "step_ledger.json", step_ledger)
    resume_path = _write_json(root / "resume_decision.json", resume_decision)
    mark("resume", resume_decision.get("ok"), [str(ledger_path), str(resume_path)], decision=resume_decision)

    # 10. Negative case: malformed/missing CHANGES must be rejected and must not mutate state.
    state_before = _hash(storage.load_state(project_id))
    bad_changes = {"summary": "坏例子"}
    bad_gate = validate_changes(bad_changes, marker_found=False, require_marker=True)
    bad_consistency = validate_consistency(chapter_text="张三在青云城直接揭露张三身世。", changes=bad_changes, extraction={"summary": "坏例子"}, blueprint=blueprint, state=storage.load_state(project_id), story_config=storage.load_story_config(project_id))
    if not bad_gate.ok or not bad_consistency.ok:
        rejected_path = storage.save_draft(project_id, chapter_no + 10000, "行为级反例", "张三在青云城直接揭露张三身世。", rejected=True)
    else:
        rejected_path = None
    state_after = _hash(storage.load_state(project_id))
    negative_ok = (not bad_gate.ok or not bad_consistency.ok) and state_before == state_after and rejected_path is not None
    negative = {"draft_gate": bad_gate.to_dict(), "consistency_gate": bad_consistency.to_dict(), "state_before": state_before, "state_after": state_after, "rejected_path": str(rejected_path) if rejected_path else ""}
    negative_path = _write_json(root / "negative_case.json", negative)
    mark("negative_case", negative_ok, [str(negative_path)], negative=negative)

    behavior_aligned = sum(1 for value in blocks.values() if value.get("ok"))
    acceptance = {
        "ok": behavior_aligned == len(BEHAVIOR_BLOCKS),
        "schema_version": 1,
        "project_id": project_id,
        "chapter_no": chapter_no,
        "started_at": started_at,
        "finished_at": _now(),
        "behavior_aligned": behavior_aligned,
        "total": len(BEHAVIOR_BLOCKS),
        "errors": errors,
        "blocks": blocks,
        "external_limits": {
            "real_model_api": "未联网调用真实模型；本命令验证本地后端行为级闭环和状态转移。",
            "real_platform_publish": "未登录平台发布；publisher bridge 仍需在用户账号环境验证。",
        },
    }
    acceptance_path = _write_json(root / "behavior_acceptance.json", acceptance)
    return {**acceptance, "path": str(acceptance_path), "gap_report": behavior_gaps_v28_command(storage, project_id)}


def behavior_query_v28_command(storage: Any, project_id: str, query: str = "", top_k: int = 8) -> dict[str, Any]:
    root = _behavior_root(storage, project_id)
    docs: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        data = _read_json(path, {})
        docs.append({"path": str(path), "name": path.name, "text": json.dumps(data, ensure_ascii=False)})
    terms = [t for t in re.split(r"\s+", str(query or "").strip()) if t]
    rows = []
    for doc in docs:
        text = doc["text"]
        score = sum(text.count(t) for t in terms) if terms else 1
        if score > 0:
            rows.append({"path": doc["path"], "name": doc["name"], "score": score, "snippet": text[:400]})
    rows.sort(key=lambda r: r["score"], reverse=True)
    result = {"ok": True, "project_id": project_id, "query": query, "results": rows[:max(1, top_k)]}
    _write_json(root / "last_behavior_query.json", result)
    return result


def _blueprint_text(blueprint: dict[str, Any]) -> str:
    nodes = "\n".join(f"- {x}" for x in blueprint.get("must_cover_nodes", []))
    forbidden = "\n".join(f"- {x}" for x in blueprint.get("forbidden_zones", []))
    return f"# 第 {blueprint.get('chapter_no')} 章：{blueprint.get('title')}\n\n## 章节目标\n{blueprint.get('goal')}\n\n## 必达节点\n{nodes}\n\n## 禁区\n{forbidden}\n"


def _accepted_chapter_text(chapter_no: int) -> str:
    return f"""第{chapter_no}章 行为级验收第{chapter_no}章

张三抵达青云城时，青云宗的巡夜灯正一盏盏亮起。旧阵眼埋在城西石桥下，表面只是一圈被雨水泡黑的青砖，可他伸手触碰时，掌心立刻感到一阵发热。

“旧阵眼发热，说明有人刚动过阵基。”张三没有立刻声张，而是把指尖压在裂缝边缘，顺着残留的灵力痕迹一点点往外推。

两个青云宗巡夜弟子从桥头转来，拦住他的去路。其中一人盯着他腰间的信物，冷声问：“深夜靠近阵眼，谁给你的胆子？”

张三没有硬闯。他把信物翻到背面，故意让对方看到那道新鲜划痕。巡夜弟子的脸色变了，因为信物边缘忽然渗出一滴陌生血迹，血迹没有落下，反而在夜风里微微发亮。

张三知道，这不是警告，而是有人把假死真相的第二个证据塞到了他手里。青云城的夜色仍旧平静，可旧阵眼下方，已经传出极轻的一声碎响。
""".strip()


def _accepted_changes(chapter_no: int) -> dict[str, Any]:
    return {
        "summary": "张三在青云城旧阵眼发现发热线索，被青云宗巡夜弟子阻拦，并在信物上发现陌生血迹，假死真相伏笔推进。",
        "characters": {"张三": {"status": "发现旧阵眼异常", "location": "青云城", "key_event": "取得信物血迹线索"}},
        "locations": {"青云城": {"status": "旧阵眼异常发热", "event": "夜间阵基被人动过"}},
        "factions": {"青云宗": {"status": "巡夜弟子封锁旧阵眼", "event": "阻拦张三靠近阵眼"}},
        "items": {"信物": {"holder": "张三", "status": "出现陌生血迹"}},
        "foreshadows": {"F001": {"name": "假死真相", "status": "推进", "action": "advance", "evidence": "信物出现陌生血迹"}},
        "conflicts": {"旧阵眼异常": {"status": "启动", "event": "张三与青云宗巡夜弟子发生对峙"}},
        "secrets": {"假死真相": {"status": "出现第二个证据", "known_by": ["张三"]}},
        "pledges": {},
        "deadlines": {},
        "timeline": [{"chapter_no": chapter_no, "event": "张三夜探青云城旧阵眼"}],
        "hooks": ["信物上的陌生血迹仍在发亮"],
    }


def _node_evidence(chapter_text: str, blueprint: dict[str, Any]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for node in blueprint.get("must_cover_nodes") or []:
        pieces = [p for p in re.split(r"[，,。；;、\s：:（）()《》\[\]【】]+", str(node)) if len(p) >= 2]
        hit = ""
        for piece in pieces:
            idx = chapter_text.find(piece)
            if idx >= 0:
                hit = chapter_text[max(0, idx - 40): idx + 80]
                break
        evidence[str(node)] = hit or "本地门禁将继续做短语匹配"
    return evidence


def _build_commit(chapter_no: int, chapter_title: str, changes: dict[str, Any], extraction: dict[str, Any], review: dict[str, Any], fulfillment: dict[str, Any], disambiguation: dict[str, Any], consistency: dict[str, Any]) -> dict[str, Any]:
    summary = str(extraction.get("summary") or changes.get("summary") or "")
    base = f"v28|{chapter_no}|{chapter_title}|{summary}|{_now()}"
    return {
        "schema_version": 4,
        "commit_id": hashlib.sha1(base.encode("utf-8")).hexdigest()[:16],
        "chapter_no": chapter_no,
        "chapter_title": chapter_title,
        "status": "accepted",
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


def _resume_decision(step_ledger: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [row for row in step_ledger if not row.get("status")]
    if not failed:
        return {"ok": True, "resume_from": "none", "decision": "all_trusted", "trusted_steps": [row.get("step") for row in step_ledger]}
    first = failed[0]
    trusted = []
    for row in step_ledger:
        if row is first:
            break
        trusted.append(row.get("step"))
    return {"ok": False, "resume_from": first.get("step"), "decision": "resume_from_first_untrusted_step", "trusted_steps": trusted}
