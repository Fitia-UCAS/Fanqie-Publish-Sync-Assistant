from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import write_json
from backend.adapters.webnovel_writer.webnovel_writer_memory import load_or_build_memory
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def build_runtime_contract(storage: Any, project_id: str, chapter_no: int, *, recent: int = 6) -> dict[str, Any]:
    storage.sync_control_files(project_id)
    meta = storage.load_meta(project_id)
    state = storage.load_state(project_id)
    story_config = storage.load_story_config(project_id)
    blueprint = storage.load_blueprint_json(project_id, chapter_no)
    memory = load_or_build_memory(storage, project_id)
    previous_tail = _previous_tail(storage, project_id, chapter_no)
    recent_summaries = storage.recent_chapter_summaries(project_id, recent)
    required_entities = _required_entities(state, blueprint)
    rule_pack = _rule_pack(story_config, blueprint, state, memory)
    recall_query = _recall_query(meta, blueprint, required_entities, rule_pack)
    recall = storage.recall(project_id, recall_query, top_k=int((story_config.get("gate_policy") or {}).get("context_recall_top_k") or 6), exclude_chapter=chapter_no)

    contract = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "project_id": project_id,
        "chapter_no": chapter_no,
        "title": blueprint.get("title") or f"第{chapter_no}章",
        "status": "ready" if blueprint else "missing_blueprint",
        "meta": {
            "title": meta.get("title") or (story_config.get("story_profile") or {}).get("title") or "",
            "genre": meta.get("genre") or (story_config.get("story_profile") or {}).get("genre") or "",
            "premise": meta.get("premise") or (story_config.get("story_profile") or {}).get("premise") or "",
        },
        "blueprint": blueprint,
        "required_entities": required_entities,
        "hard_rules": rule_pack["hard_rules"],
        "soft_rules": rule_pack["soft_rules"],
        "forbidden_zones": _listify(blueprint.get("forbidden_zones")),
        "must_cover_nodes": _listify(blueprint.get("must_cover_nodes") or blueprint.get("required_beats")),
        "fact_writeback_notes": _listify(blueprint.get("fact_writeback_notes") or blueprint.get("state_writeback_hint")),
        "open_debts": _open_debts(state, memory, chapter_no),
        "recent_summaries": recent_summaries,
        "previous_tail": previous_tail,
        "recall_query": recall_query,
        "long_recall": recall,
        "model_output_contract": _model_output_contract(story_config),
        "blocking_checks": _blocking_checks(story_config),
    }
    out_dir = ensure_dir(Path(storage.paths(project_id).control) / "contracts")
    json_path = write_json(out_dir / f"chapter_{chapter_no:04d}_contract.json", contract)
    md_path = write_text(out_dir / f"chapter_{chapter_no:04d}_contract.md", contract_markdown(contract))
    contract["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, contract)
    return contract


def contract_markdown(contract: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# 第{contract.get('chapter_no')}章运行时合约",
        "",
        f"- 生成时间：{contract.get('generated_at')}",
        f"- 状态：{contract.get('status')}",
        f"- 标题：{contract.get('title') or ''}",
        "",
        "## 本章目标",
        str((contract.get("blueprint") or {}).get("goal") or "待补充"),
        "",
        "## 必须出现 / 必须完成",
    ]
    for item in contract.get("must_cover_nodes") or []:
        lines.append(f"- {item}")
    if not contract.get("must_cover_nodes"):
        lines.append("- 待补充蓝图必达节点。")
    lines += ["", "## 禁区"]
    for item in contract.get("forbidden_zones") or []:
        lines.append(f"- {item}")
    if not contract.get("forbidden_zones"):
        lines.append("暂无。")
    lines += ["", "## 必读实体"]
    req = contract.get("required_entities") or {}
    for bucket, values in req.items():
        if values:
            lines.append(f"### {bucket}")
            for name, item in values.items():
                note = _entity_note(item)
                lines.append(f"- {name}" + (f"：{note}" if note else ""))
    lines += ["", "## 硬规则"]
    for item in contract.get("hard_rules") or []:
        lines.append(f"- {item}")
    lines += ["", "## 开放债务"]
    debts = contract.get("open_debts") or {}
    has_debt = False
    for bucket, values in debts.items():
        if values:
            has_debt = True
            lines.append(f"### {bucket}")
            for item in values[:30]:
                lines.append(f"- {item.get('name')}: {item.get('message') or item.get('status') or ''}")
    if not has_debt:
        lines.append("暂无。")
    lines += ["", "## 上一章结尾"]
    lines.append(contract.get("previous_tail") or "暂无。")
    lines += ["", "## 长距召回"]
    for row in contract.get("long_recall") or []:
        lines.append(f"- 第{row.get('chapter_no')}章 {row.get('title') or ''} score={row.get('score')}: {row.get('snippet') or ''}")
    if not contract.get("long_recall"):
        lines.append("暂无。")
    lines += ["", "## 模型输出协议"]
    for item in contract.get("model_output_contract") or []:
        lines.append(f"- {item}")
    lines += ["", "## 阻断检查"]
    for item in contract.get("blocking_checks") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def build_contract_index(storage: Any, project_id: str, *, start: int = 1, end: int | None = None) -> dict[str, Any]:
    state = storage.load_state(project_id)
    latest = int(state.get("latest_chapter") or 0)
    blueprint_numbers = [int(x.get("chapterNo") or 0) for x in storage.list_blueprints(project_id)]
    max_no = max([latest + 1] + blueprint_numbers + ([end] if end else []))
    start = max(1, int(start or 1))
    end = int(end or max_no)
    rows = []
    for no in range(start, end + 1):
        contract = build_runtime_contract(storage, project_id, no)
        rows.append({"chapter_no": no, "status": contract.get("status"), "path": (contract.get("paths") or {}).get("markdown")})
    out_dir = ensure_dir(Path(storage.paths(project_id).control) / "contracts")
    report = {"ok": True, "generated_at": now_iso(), "start": start, "end": end, "count": len(rows), "contracts": rows}
    json_path = write_json(out_dir / "contract_index.json", report)
    md_path = write_text(out_dir / "contract_index.md", _contract_index_md(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, report)
    return report


def _contract_index_md(report: dict[str, Any]) -> str:
    lines = ["# 运行时合约索引", "", f"- 范围：{report.get('start')} - {report.get('end')}", f"- 数量：{report.get('count')}", ""]
    for row in report.get("contracts") or []:
        lines.append(f"- 第{row.get('chapter_no')}章：{row.get('status')} `{row.get('path')}`")
    return "\n".join(lines).rstrip() + "\n"


def _required_entities(state: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, dict[str, Any]]:
    spec = {
        "characters": _listify(blueprint.get("required_characters") or blueprint.get("characters")),
        "locations": _listify(blueprint.get("required_locations") or blueprint.get("locations")),
        "factions": _listify(blueprint.get("required_factions") or blueprint.get("factions")),
        "items": _listify(blueprint.get("required_items") or blueprint.get("items")),
        "foreshadows": [str(x.get("id") or x.get("name") or x) for x in _listify(blueprint.get("foreshadow_actions"))],
        "conflicts": _listify(blueprint.get("required_conflicts") or blueprint.get("conflicts")),
    }
    out: dict[str, dict[str, Any]] = {}
    for bucket, names in spec.items():
        src = state.get(bucket) or {}
        out[bucket] = {}
        for name in names:
            key = _find_entity_key(src, str(name))
            out[bucket][str(name)] = src.get(key, {"name": str(name), "missing": True}) if key else {"name": str(name), "missing": True}
    return out


def _find_entity_key(mapping: dict[str, Any], name: str) -> str:
    if name in mapping:
        return name
    for key, item in mapping.items():
        if not isinstance(item, dict):
            continue
        aliases = [str(item.get("id") or ""), str(item.get("name") or "")] + [str(x) for x in (item.get("aliases") or [])]
        if name in aliases:
            return str(key)
    return ""


def _rule_pack(story_config: dict[str, Any], blueprint: dict[str, Any], state: dict[str, Any], memory: dict[str, Any]) -> dict[str, list[str]]:
    rules = story_config.get("story_rules") or {}
    hard: list[str] = []
    for key in ["world_rules", "character_rules", "faction_rules", "location_rules", "plot_rules", "forbidden_patterns"]:
        hard.extend(str(x) for x in _listify(rules.get(key)) if str(x).strip())
    hard.extend(str(x) for x in _listify(blueprint.get("forbidden_zones")) if str(x).strip())
    risks = memory.get("risks") or []
    for item in risks[:12]:
        if isinstance(item, dict) and item.get("message"):
            hard.append(str(item.get("message")))
    soft = [str(x) for x in _listify(rules.get("style_rules")) if str(x).strip()]
    learned = (story_config.get("learned_style_profile") or {})
    for item in _listify(learned.get("recommendations") or learned.get("style_rules")):
        soft.append(str(item))
    return {"hard_rules": _dedupe(hard), "soft_rules": _dedupe(soft)}


def _open_debts(state: dict[str, Any], memory: dict[str, Any], chapter_no: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"foreshadows": [], "conflicts": [], "deadlines": [], "secrets": []}
    for bucket, source_key in [("foreshadows", "open_foreshadows"), ("conflicts", "open_conflicts"), ("deadlines", "open_deadlines"), ("secrets", "open_secrets")]:
        mapping = memory.get(source_key) or state.get(bucket) or {}
        for name, item in mapping.items():
            if not isinstance(item, dict):
                item = {"status": item}
            status = str(item.get("status") or item.get("state") or "open")
            first = _to_int(item.get("introduced_chapter") or item.get("first_seen_chapter") or item.get("chapter_no"), chapter_no)
            age = max(0, chapter_no - first) if first else 0
            out[bucket].append({"name": str(name), "status": status, "age": age, "message": _debt_message(bucket, str(name), status, age)})
    return out


def _debt_message(bucket: str, name: str, status: str, age: int) -> str:
    cn = {"foreshadows": "伏笔", "conflicts": "冲突", "deadlines": "截止约束", "secrets": "秘密"}.get(bucket, bucket)
    if age >= 30:
        return f"{cn}《{name}》已开放 {age} 章，本章应考虑推进、提醒或回收。"
    return f"{cn}《{name}》当前状态：{status}。"


def _model_output_contract(story_config: dict[str, Any]) -> list[str]:
    required = [
        "正文后必须输出独立 CHANGES 区域。",
        "CHANGES 必须能解析为 JSON object。",
        "正文出现的已登记角色、地点、势力、物品、伏笔、冲突、秘密、誓约、截止约束必须在 CHANGES 中申报。",
        "CHANGES 不得引用未登记实体 ID；新增关键实体必须说明原因。",
        "禁止让未通过门禁的内容进入正式章节。",
    ]
    if (story_config.get("gate_policy") or {}).get("require_ending_hook", True):
        required.append("章节结尾必须有追读钩子或明确的情绪悬念。")
    return required


def _blocking_checks(story_config: dict[str, Any]) -> list[str]:
    policy = story_config.get("gate_policy") or {}
    checks = [
        "CHANGES 协议缺失或解析失败。",
        "正文为空或明显过短。",
        "蓝图必达节点缺失。",
        "正文违反禁区或世界硬规则。",
        "正文出现已登记实体但 CHANGES 漏报。",
        "CHANGES 与事实快照冲突。",
    ]
    if policy.get("required_entity_presence_is_blocking", True):
        checks.append("蓝图指定角色/地点/势力未在正文出现。")
    return checks


def _previous_tail(storage: Any, project_id: str, chapter_no: int) -> str:
    if chapter_no <= 1:
        return ""
    _, text = storage.load_chapter(project_id, chapter_no - 1)
    if not text:
        return ""
    clean = text.strip()
    return clean[-900:]


def _recall_query(meta: dict[str, Any], blueprint: dict[str, Any], entities: dict[str, Any], rules: dict[str, list[str]]) -> str:
    parts: list[str] = [str(meta.get("title") or ""), str(blueprint.get("goal") or ""), str(blueprint.get("conflict") or ""), str(blueprint.get("ending_hook") or "")]
    for values in entities.values():
        parts.extend(values.keys())
    parts.extend((rules.get("hard_rules") or [])[:8])
    return "\n".join(x for x in parts if x).strip()


def _entity_note(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item or "")
    for key in ["summary", "notes", "note", "status", "location", "progress"]:
        value = item.get(key)
        if value:
            return str(value)
    return "未登记" if item.get("missing") else ""


def _listify(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, dict):
        return [value]
    text = str(value).strip()
    if not text:
        return []
    return [x.strip() for x in re.split(r"[,，、;；\n]+", text) if x.strip()]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
