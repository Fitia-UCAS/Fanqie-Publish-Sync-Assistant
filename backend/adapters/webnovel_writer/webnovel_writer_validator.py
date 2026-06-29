from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_models import ENTITY_BUCKETS


@dataclass(slots=True)
class GateResult:
    ok: bool = True
    stage: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def fail(self, message: str) -> "GateResult":
        self.ok = False
        self.errors.append(str(message))
        return self

    def warn(self, message: str) -> "GateResult":
        self.warnings.append(str(message))
        return self

    def extend(self, other: "GateResult") -> "GateResult":
        if not other.ok:
            self.ok = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.data.update(other.data)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "stage": self.stage, "errors": self.errors, "warnings": self.warnings, **self.data}


def gate(stage: str) -> GateResult:
    return GateResult(stage=stage)


def require_dict(value: Any, name: str, result: GateResult) -> dict[str, Any]:
    if not isinstance(value, dict):
        result.fail(f"{name} 必须是 JSON object。")
        return {}
    return value


def require_list(value: Any, name: str, result: GateResult) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        result.fail(f"{name} 必须是数组。")
        return []
    return value


def normalize_changes(changes: dict[str, Any]) -> dict[str, Any]:
    """Normalize common model/Tianming style fields into the local schema.

    This keeps compatibility with our existing backend while accepting fact
    bundles that look closer to Tianming's CHANGES protocol.
    """
    if not isinstance(changes, dict):
        return {}
    aliases = {
        "character_state_changes": "characters",
        "CharacterStateChanges": "characters",
        "角色状态变化": "characters",
        "location_state_changes": "locations",
        "LocationStateChanges": "locations",
        "地点状态变化": "locations",
        "faction_state_changes": "factions",
        "FactionStateChanges": "factions",
        "势力状态变化": "factions",
        "item_state_changes": "items",
        "物品流转": "items",
        "foreshadowing_actions": "foreshadows",
        "ForeshadowingActions": "foreshadows",
        "伏笔动作": "foreshadows",
        "conflict_progress": "conflicts",
        "ConflictProgress": "conflicts",
        "冲突进度": "conflicts",
        "new_plot_points": "hooks",
        "NewPlotPoints": "hooks",
        "剧情节点": "hooks",
        "time_advances": "timeline",
        "TimeAdvances": "timeline",
        "时间推进": "timeline",
        "secret_reveals": "secrets",
        "秘密揭示": "secrets",
        "pledge_changes": "pledges",
        "誓约约束变化": "pledges",
        "deadline_changes": "deadlines",
        "截止约束变化": "deadlines",
    }
    out = dict(changes)
    for old, new in aliases.items():
        if old in out and new not in out:
            out[new] = _normalise_change_bucket(out[old]) if new in ENTITY_BUCKETS or new in {"secrets", "pledges", "deadlines"} else out[old]
    for bucket in [*ENTITY_BUCKETS, "secrets", "pledges", "deadlines"]:
        if bucket in out:
            out[bucket] = _normalise_change_bucket(out.get(bucket))
    if "summary" not in out:
        for key in ["本章摘要", "summary_text", "chapter_summary", "Summary"]:
            if key in out:
                out["summary"] = out[key]
                break
    return out


def validate_blueprint(blueprint: dict[str, Any]) -> GateResult:
    result = gate("blueprint")
    require_dict(blueprint, "blueprint", result)
    for key in ["chapter_no", "title", "goal", "must_cover_nodes", "forbidden_zones", "ending_hook"]:
        if key not in blueprint:
            result.warn(f"蓝图缺少字段：{key}")
    for key in ["must_cover_nodes", "forbidden_zones", "required_characters", "required_locations", "required_factions"]:
        if key in blueprint and not isinstance(blueprint.get(key), list):
            result.fail(f"blueprint.{key} 必须是数组。")
    return result


def validate_changes(changes: dict[str, Any], *, marker_found: bool = True, require_marker: bool = True) -> GateResult:
    result = gate("draft")
    changes = normalize_changes(changes)
    require_dict(changes, "CHANGES", result)
    if require_marker and not marker_found:
        result.fail("缺少 ---CHANGES--- 分隔符。")
    required = ["summary", "characters", "locations", "factions", "items", "foreshadows", "conflicts", "timeline", "hooks"]
    for key in required:
        if key not in changes:
            result.fail(f"CHANGES 缺少字段：{key}")
    for key in ["characters", "locations", "factions", "items", "foreshadows", "conflicts"]:
        if key in changes and not isinstance(changes.get(key), dict):
            result.fail(f"CHANGES.{key} 必须是对象。")
    for key in ["timeline", "hooks"]:
        if key in changes and not isinstance(changes.get(key), list):
            result.fail(f"CHANGES.{key} 必须是数组。")
    summary = str(changes.get("summary") or "").strip()
    if len(summary) < 6:
        result.warn("CHANGES.summary 过短，后续状态摘要可能不稳定。")
    result.data["normalized_changes"] = changes
    return result


def validate_review(review: dict[str, Any]) -> GateResult:
    result = gate("review")
    require_dict(review, "review", result)
    if "pass" not in review:
        result.fail("review 缺少 pass 字段。")
    if "blocking_issues" not in review:
        result.fail("review 缺少 blocking_issues 字段。")
    blocking = require_list(review.get("blocking_issues"), "review.blocking_issues", result)
    warnings = require_list(review.get("warnings"), "review.warnings", result)
    result.data["blocking_count"] = len(blocking)
    result.data["warning_count"] = len(warnings)
    if blocking:
        result.fail(f"审稿存在 {len(blocking)} 个 blocking issue。")
    if review.get("pass") is False:
        result.fail("review.pass=false，禁止正式落地。")
    return result


def validate_data_artifacts(fulfillment: dict[str, Any], disambiguation: dict[str, Any], extraction: dict[str, Any]) -> GateResult:
    result = gate("data-agent")
    require_dict(fulfillment, "fulfillment_result", result)
    require_dict(disambiguation, "disambiguation_result", result)
    require_dict(extraction, "extraction_result", result)
    missed = fulfillment.get("missed_nodes") or []
    pending = disambiguation.get("pending") or []
    if not isinstance(missed, list):
        result.fail("fulfillment_result.missed_nodes 必须是数组。")
        missed = []
    if not isinstance(pending, list):
        result.fail("disambiguation_result.pending 必须是数组。")
        pending = []
    if missed:
        result.fail(f"章节蓝图存在 {len(missed)} 个未完成节点。")
    if pending:
        result.fail(f"存在 {len(pending)} 个待消歧实体。")
    if not str(extraction.get("summary") or "").strip():
        result.fail("extraction_result 缺少 summary。")
    return result


def validate_consistency(
    *,
    chapter_text: str,
    changes: dict[str, Any],
    extraction: dict[str, Any],
    blueprint: dict[str, Any] | None,
    state: dict[str, Any],
    story_config: dict[str, Any],
) -> GateResult:
    result = gate("consistency")
    policy = story_config.get("gate_policy") or {}
    changes = normalize_changes(changes)
    chapter_text = str(chapter_text or "")
    summary_text = str(changes.get("summary") or "") + "\n" + str(extraction.get("summary") or "")

    # 1. 必达节点硬校验：正文或变更摘要至少要命中关键词。
    missed_nodes = []
    for node in blueprint_required_nodes(blueprint):
        if not _node_appears(node, chapter_text + "\n" + summary_text):
            missed_nodes.append(node)
    if missed_nodes:
        result.fail(f"蓝图必达节点未体现：{missed_nodes[:5]}")

    # 2. 本章要求出场的实体必须在正文出现；不是只写在 CHANGES 里。
    missing_required = _missing_required_entities(chapter_text, blueprint, state)
    if missing_required:
        if bool(policy.get("required_entity_presence_is_blocking", True)):
            result.fail(f"蓝图指定实体未在正文出现：{missing_required[:8]}")
        else:
            result.warn(f"蓝图指定实体未在正文出现：{missing_required[:8]}")

    # 3. 禁区检查。
    violated = []
    for item in blueprint_forbidden_zones(blueprint) + _list_texts((story_config.get("story_rules") or {}).get("forbidden_patterns")):
        item = str(item).strip()
        if item and item in chapter_text:
            violated.append(item)
    if violated:
        result.fail(f"触发禁区/禁写模式：{violated[:5]}")

    # 4. 正文与 CHANGES 对齐：已知实体出现在正文中，必须在 CHANGES 或提取结果中有对应申报。
    omitted_known = _known_entities_in_text_missing_from_changes(chapter_text, changes, extraction, blueprint, state)
    auto_patch = bool(policy.get("auto_patch_omitted_known_entities", True))
    blocking_omission = bool(policy.get("omitted_known_entity_is_blocking", True))
    auto_patched: list[dict[str, str]] = []
    residual_omitted: list[dict[str, str]] = []
    for row in omitted_known:
        if auto_patch and row.get("bucket") in {"characters", "locations", "factions", "items", "foreshadows", "conflicts"}:
            _patch_omission(changes, row)
            auto_patched.append(row)
        else:
            residual_omitted.append(row)
    if auto_patched:
        result.warn(f"正文出现但 CHANGES 漏报的已知实体已自动补录：{_format_omissions(auto_patched[:8])}")
    if residual_omitted:
        message = f"正文出现已知实体但 CHANGES 未申报：{_format_omissions(residual_omitted[:8])}"
        if blocking_omission:
            result.fail(message)
        else:
            result.warn(message)

    # 5. 额外实体数量提示。模型声明的新实体过多时容易污染状态。
    unknown_limit = int(policy.get("unknown_entity_limit") or 5)
    untracked_extra_limit = int(policy.get("untracked_extra_limit") or 3)
    unknown_declared: list[str] = []
    for bucket in ENTITY_BUCKETS:
        for name in (changes.get(bucket) or {}).keys() if isinstance(changes.get(bucket), dict) else []:
            if not _entity_exists(state, bucket, str(name)):
                unknown_declared.append(f"{bucket}:{name}")
    if len(unknown_declared) > unknown_limit:
        result.fail(f"新增/未知实体过多：{len(unknown_declared)} 个，示例 {unknown_declared[:8]}")
    elif unknown_declared:
        result.warn(f"本章声明新增/未知实体：{unknown_declared[:8]}")

    # 6. 正文中出现较多类似姓名但未声明，提示但不武断拦截。
    possible_names = _possible_cn_names(chapter_text)
    declared_names = set()
    for bucket in ENTITY_BUCKETS:
        if isinstance(changes.get(bucket), dict):
            declared_names.update(map(str, changes[bucket].keys()))
    untracked = [name for name in possible_names if name not in declared_names and not any(_entity_exists(state, bucket, name) for bucket in ENTITY_BUCKETS)]
    if len(untracked) > untracked_extra_limit:
        result.warn(f"疑似未声明实体较多：{untracked[:10]}")

    # 7. 最低章节质量硬条件：不是文学审稿，只检查最容易崩的章末钩子和空洞爽点。
    if bool(policy.get("require_ending_hook", True)):
        tail = chapter_text.strip()[-160:]
        hooks = changes.get("hooks") if isinstance(changes.get("hooks"), list) else []
        if len(chapter_text.strip()) >= 600 and not hooks and not any(p in tail for p in ["？", "?", "！", "!", "却", "忽然", "下一刻", "身后", "门外", "血", "光"]):
            result.warn("章末钩子较弱：CHANGES.hooks 为空，正文尾段也缺少明显追读信号。")

    result.data["unknown_declared"] = unknown_declared
    result.data["possible_untracked_entities"] = untracked[:20]
    result.data["auto_patched_omissions"] = auto_patched
    result.data["residual_omissions"] = residual_omitted
    result.data["normalized_changes"] = changes
    return result


def validate_commit(commit: dict[str, Any]) -> GateResult:
    result = gate("precommit")
    require_dict(commit, "chapter_commit", result)
    for key in ["commit_id", "chapter_no", "chapter_title", "summary", "status", "review", "artifacts"]:
        if key not in commit:
            result.fail(f"chapter_commit 缺少字段：{key}")
    if commit.get("status") != "accepted":
        result.fail(f"chapter_commit.status={commit.get('status')}，非 accepted 禁止正式落地。")
    artifacts = commit.get("artifacts") or {}
    if isinstance(artifacts, dict) and not artifacts.get("consistency_gate"):
        result.fail("chapter_commit.artifacts 缺少 consistency_gate。")
    return result


def blueprint_required_nodes(blueprint: dict[str, Any] | None) -> list[str]:
    if not isinstance(blueprint, dict):
        return []
    nodes = blueprint.get("must_cover_nodes") or blueprint.get("mustCoverNodes") or []
    return [str(item).strip() for item in nodes if str(item).strip()] if isinstance(nodes, list) else []


def blueprint_forbidden_zones(blueprint: dict[str, Any] | None) -> list[str]:
    if not isinstance(blueprint, dict):
        return []
    zones = blueprint.get("forbidden_zones") or blueprint.get("forbiddenZones") or []
    return [str(item).strip() for item in zones if str(item).strip()] if isinstance(zones, list) else []


def blueprint_required_entities(blueprint: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(blueprint, dict):
        return {"characters": [], "locations": [], "factions": []}
    return {
        "characters": _list_texts(blueprint.get("required_characters") or blueprint.get("characters")),
        "locations": _list_texts(blueprint.get("required_locations") or blueprint.get("locations")),
        "factions": _list_texts(blueprint.get("required_factions") or blueprint.get("factions")),
    }


def _normalise_change_bucket(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                name = str(
                    item.get("name")
                    or item.get("id")
                    or item.get("character")
                    or item.get("character_id")
                    or item.get("CharacterId")
                    or item.get("location")
                    or item.get("location_id")
                    or item.get("faction")
                    or item.get("faction_id")
                    or item.get("foreshadow")
                    or item.get("foreshadow_id")
                    or ""
                ).strip()
                if name:
                    out[name] = item
            elif str(item).strip():
                out[str(item).strip()] = {"note": "declared"}
    elif isinstance(value, str) and value.strip():
        for item in re.split(r"[,，、;；\n]+", value):
            item = item.strip()
            if item:
                out[item] = {"note": "declared"}
    return out


def _node_appears(node: str, text: str) -> bool:
    node_text = str(node or "").strip()
    if not node_text:
        return False
    if node_text in text:
        return True
    pieces = [p for p in re.split(r"[，,。；;、\s：:（）()《》\[\]【】]+", node_text) if len(p) >= 2]
    # Chinese blueprint nodes are often compact sentences without separators, e.g.
    # “张三发现旧阵眼发热”.  Split them into meaningful short chunks so the
    # gate checks intent evidence instead of exact wording.
    if len(pieces) <= 1 and len(node_text) >= 6:
        compact = re.sub(r"[，,。；;、\s：:（）()《》\[\]【】]", "", node_text)
        chunks = []
        for size in (4, 3, 2):
            for i in range(0, max(len(compact) - size + 1, 0)):
                chunk = compact[i : i + size]
                if chunk and not any(stop in chunk for stop in ["本章", "需要", "必须", "不要", "不能", "发现"]):
                    chunks.append(chunk)
        pieces = []
        for chunk in chunks:
            if chunk not in pieces:
                pieces.append(chunk)
    if not pieces:
        return False
    hits = sum(1 for p in pieces[:10] if p in text)
    return hits >= max(1, min(2, len(pieces)))


def _entity_exists(state: dict[str, Any], bucket: str, name: str) -> bool:
    return _entity_record(state, bucket, name) is not None


def _entity_record(state: dict[str, Any], bucket: str, name: str) -> dict[str, Any] | None:
    data = state.get(bucket) or {}
    if not isinstance(data, dict):
        return None
    if name in data and isinstance(data.get(name), dict):
        item = dict(data[name])
        item.setdefault("name", name)
        return item
    for key, item in data.items():
        if not isinstance(item, dict):
            continue
        aliases = item.get("aliases") or []
        if name == item.get("name") or name == key or (isinstance(aliases, list) and name in aliases):
            found = dict(item)
            found.setdefault("name", str(item.get("name") or key))
            return found
    return None


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"[,，、;；\n]+", value) if x.strip()]
    return []


def _known_entities_in_text_missing_from_changes(chapter_text: str, changes: dict[str, Any], extraction: dict[str, Any], blueprint: dict[str, Any] | None, state: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    # Check explicitly required blueprint entities first, then all state entities.
    candidates: list[tuple[str, str, dict[str, Any], str]] = []
    required = blueprint_required_entities(blueprint)
    for bucket, names in required.items():
        for name in names:
            record = _entity_record(state, bucket, name) or {"name": name, "aliases": []}
            candidates.append((bucket, name, record, "blueprint"))
    for bucket in ENTITY_BUCKETS:
        for name, item in (state.get(bucket) or {}).items():
            record = item if isinstance(item, dict) else {"name": str(name), "aliases": []}
            candidates.append((bucket, str(record.get("name") or name), record, "state"))

    seen: set[tuple[str, str]] = set()
    for bucket, name, record, source in candidates:
        key = (bucket, name)
        if key in seen:
            continue
        seen.add(key)
        matched = _entity_appears(chapter_text, name, record)
        if not matched:
            continue
        if _declared_in(changes, bucket, name, record) or _declared_in(extraction, bucket, name, record):
            continue
        rows.append({"bucket": bucket, "name": name, "matched": matched, "source": source})
    return rows


def _missing_required_entities(chapter_text: str, blueprint: dict[str, Any] | None, state: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for bucket, names in blueprint_required_entities(blueprint).items():
        label = {"characters": "角色", "locations": "地点", "factions": "势力"}.get(bucket, bucket)
        for name in names:
            record = _entity_record(state, bucket, name) or {"name": name, "aliases": []}
            if not _entity_appears(chapter_text, name, record):
                missing.append(f"{label}:{name}")
    return missing


def _entity_appears(text: str, name: str, record: dict[str, Any]) -> str:
    variants = [name, str(record.get("name") or "")]
    aliases = record.get("aliases") or []
    if isinstance(aliases, list):
        variants.extend(str(x) for x in aliases)
    for variant in variants:
        v = str(variant or "").strip()
        if len(v) >= 2 and v in text:
            return v
    return ""


def _declared_in(bundle: dict[str, Any], bucket: str, name: str, record: dict[str, Any]) -> bool:
    mapping = bundle.get(bucket) if isinstance(bundle, dict) else None
    if not isinstance(mapping, dict):
        return False
    variants = {name, str(record.get("name") or "")}
    aliases = record.get("aliases") or []
    if isinstance(aliases, list):
        variants.update(str(x) for x in aliases)
    keys = set(map(str, mapping.keys()))
    if any(v and v in keys for v in variants):
        return True
    entity_id = str(record.get("id") or "").strip()
    if entity_id and entity_id in keys:
        return True
    return False


def _patch_omission(changes: dict[str, Any], row: dict[str, str]) -> None:
    bucket = row["bucket"]
    name = row["name"]
    changes.setdefault(bucket, {})
    if isinstance(changes[bucket], dict) and name not in changes[bucket]:
        changes[bucket][name] = {
            "note": f"auto_patch: 正文出现 `{row.get('matched') or name}`，但原 CHANGES 未申报；后端补录为出现记录。",
            "auto_patched": True,
        }


def _format_omissions(rows: list[dict[str, str]]) -> list[str]:
    return [f"{r.get('bucket')}:{r.get('name')}" for r in rows]


def _possible_cn_names(text: str) -> list[str]:
    # Conservative heuristic: 《名》 and common two-to-four Chinese name-like tokens near dialogue/actions.
    names: list[str] = []
    for m in re.finditer(r"《([^》]{2,12})》", text):
        names.append(m.group(1))
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})(?:说道|问道|冷笑|皱眉|点头|摇头|看向|走进|拔出|低声)", text):
        names.append(m.group(1))
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen and not any(bad in name for bad in ["这一", "那个", "他们", "众人", "声音"]):
            seen.add(name)
            out.append(name)
    return out[:50]
