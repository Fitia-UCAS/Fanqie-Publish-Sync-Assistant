from __future__ import annotations

import re
from typing import Any

ENTITY_BUCKET_TITLES = {
    "characters": "角色库",
    "locations": "地点库",
    "factions": "势力库",
    "items": "物品库",
    "foreshadows": "伏笔库",
    "conflicts": "冲突线",
    "secrets": "秘密库",
    "pledges": "誓约库",
    "deadlines": "截止约束库",
}

LIST_FIELDS = {
    "aliases", "tags", "traits", "abilities", "skills", "members", "characters",
    "locations", "factions", "items", "related_characters", "involved_characters",
    "participants", "clues", "chapters", "required_characters", "required_locations",
    "required_factions", "must_cover_nodes", "forbidden_zones", "fact_writeback_notes",
    "foreshadow_actions", "scenes", "beats", "risks", "notes_list",
}

FIELD_ALIASES = {
    "编号": "id", "ID": "id", "id": "id",
    "别名": "aliases", "aliases": "aliases",
    "状态": "status", "status": "status",
    "标签": "tags", "tags": "tags",
    "位置": "location", "location": "location",
    "所属势力": "faction", "势力": "faction", "faction": "faction",
    "角色定位": "role", "定位": "role", "role": "role",
    "性格": "traits", "traits": "traits",
    "能力": "abilities", "abilities": "abilities",
    "目标": "goal", "goal": "goal",
    "动机": "motivation", "motivation": "motivation",
    "外貌": "appearance", "appearance": "appearance",
    "进度": "progress", "progress": "progress",
    "备注": "notes", "说明": "notes", "notes": "notes",
    "首次出现": "first_seen_chapter", "first_seen_chapter": "first_seen_chapter",
    "最近出现": "last_seen_chapter", "last_seen_chapter": "last_seen_chapter",
    "成员": "members", "members": "members",
    "拥有者": "owner", "owner": "owner",
    "知情人": "knowers", "knowers": "knowers",
    "关联角色": "related_characters", "related_characters": "related_characters",
    "参与角色": "participants", "participants": "participants",
    "涉及地点": "locations", "locations": "locations",
    "涉及势力": "factions", "factions": "factions",
    "截止章": "due_chapter", "due_chapter": "due_chapter",
    "引入章": "introduced_chapter", "introduced_chapter": "introduced_chapter",
    "回收计划": "payoff_plan", "payoff_plan": "payoff_plan",
    "风险": "risks", "risks": "risks",
}

BLUEPRINT_SECTION_ALIASES = {
    "章节目标": "goal", "目标": "goal",
    "视角": "pov", "POV": "pov", "pov": "pov",
    "主要场景": "main_scene", "场景": "main_scene",
    "出场角色": "required_characters", "角色": "required_characters",
    "地点": "required_locations", "出场地点": "required_locations",
    "势力": "required_factions", "出场势力": "required_factions",
    "必达节点": "must_cover_nodes", "门禁节点": "must_cover_nodes",
    "禁区": "forbidden_zones", "禁止事项": "forbidden_zones",
    "冲突": "conflict", "本章冲突": "conflict",
    "爽点": "payoff_or_emotion", "情绪回报": "payoff_or_emotion", "爽点/情绪回报": "payoff_or_emotion",
    "章末钩子": "ending_hook", "钩子": "ending_hook",
    "事实回写提示": "fact_writeback_notes", "回写提示": "fact_writeback_notes",
    "伏笔动作": "foreshadow_actions", "伏笔": "foreshadow_actions",
    "required_characters": "required_characters", "required_locations": "required_locations", "required_factions": "required_factions",
    "must_cover_nodes": "must_cover_nodes", "forbidden_zones": "forbidden_zones",
    "fact_writeback_notes": "fact_writeback_notes", "foreshadow_actions": "foreshadow_actions",
}

BLUEPRINT_KEY_ALIASES = {
    "章节": "chapter_no", "章号": "chapter_no", "chapter_no": "chapter_no", "chapterNo": "chapter_no",
    "标题": "title", "title": "title",
    "目标": "goal", "goal": "goal",
    "视角": "pov", "POV": "pov", "pov": "pov",
    "主要场景": "main_scene", "main_scene": "main_scene",
    "冲突": "conflict", "conflict": "conflict",
    "爽点": "payoff_or_emotion", "情绪回报": "payoff_or_emotion", "payoff": "payoff_or_emotion",
    "章末钩子": "ending_hook", "ending_hook": "ending_hook",
    "required_characters": "required_characters", "required_locations": "required_locations", "required_factions": "required_factions",
    "must_cover_nodes": "must_cover_nodes", "forbidden_zones": "forbidden_zones",
    "fact_writeback_notes": "fact_writeback_notes", "foreshadow_actions": "foreshadow_actions",
}


def entity_markdown_template(bucket: str) -> str:
    title = ENTITY_BUCKET_TITLES.get(bucket, bucket)
    sample = {
        "characters": "张三",
        "locations": "青云城",
        "factions": "青云宗",
        "items": "天命剑",
        "foreshadows": "假死真相",
        "conflicts": "宗门内斗",
        "secrets": "主角身世",
        "pledges": "三年之约",
        "deadlines": "七日破阵",
    }.get(bucket, "条目名称")
    base = [f"# {title}", "", f"## 示例：{sample}", "- id: ", "- status: ", "- tags: ", "- notes: ", ""]
    extras = {
        "characters": ["- aliases: ", "- role: ", "- faction: ", "- location: ", "- traits: ", "- abilities: ", "### 关系", "- 李四 | 师兄 | 表面信任，实际保留戒心"],
        "locations": ["- type: ", "- feature: ", "- status: ", "- related_characters: "],
        "factions": ["- type: ", "- leader: ", "- members: ", "- relation: "],
        "items": ["- owner: ", "- status: ", "- ability: ", "- origin: "],
        "foreshadows": ["- tier: 1", "- status: open", "- introduced_chapter: ", "- due_chapter: ", "- related_characters: ", "- payoff_plan: "],
        "conflicts": ["- status: open", "- progress: ", "- participants: ", "- stakes: ", "- next_push: "],
        "secrets": ["- status: hidden", "- knowers: ", "- reveal_plan: "],
        "pledges": ["- status: active", "- characters: ", "- condition: ", "- consequence: "],
        "deadlines": ["- status: active", "- due_chapter: ", "- trigger: ", "- consequence: "],
    }.get(bucket, [])
    return "\n".join(base[:4] + extras + base[4:]).strip() + "\n"


def blueprint_markdown_template(chapter_no: int = 1) -> str:
    return f"""# 第 {chapter_no} 章：章节标题

- chapter_no: {chapter_no}
- title: 
- pov: 

## 章节目标

## 主要场景

## 出场角色

## 地点

## 势力

## 必达节点

## 禁区

## 冲突

## 爽点/情绪回报

## 章末钩子

## 事实回写提示
"""


def parse_entity_markdown(text: str, bucket: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    entries: dict[str, Any] = {}
    current_name = ""
    current: dict[str, Any] | None = None
    current_section = ""
    pending_key = ""
    pending_lines: list[str] = []

    def flush_pending() -> None:
        nonlocal pending_key, pending_lines, current
        if current is not None and pending_key:
            value = "\n".join(line.rstrip() for line in pending_lines).strip()
            if value:
                current[pending_key] = value
        pending_key = ""
        pending_lines = []

    def flush_current() -> None:
        nonlocal current, current_name
        flush_pending()
        if current is not None and current_name and not current_name.startswith(("示例", "例子", "模板")):
            current.setdefault("name", current_name)
            entries[current_name] = current

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if pending_key:
                pending_lines.append("")
            continue
        if stripped.startswith("<!--"):
            continue
        h2 = re.match(r"^##\s+(.+?)\s*$", stripped)
        if h2 and not stripped.startswith("###"):
            flush_current()
            current_name = h2.group(1).strip()
            current = {}
            current_section = ""
            continue
        h3 = re.match(r"^###\s+(.+?)\s*$", stripped)
        if h3:
            flush_pending()
            current_section = h3.group(1).strip()
            continue
        if current is None:
            continue
        kv = _parse_kv_line(stripped)
        if kv:
            flush_pending()
            key, value = kv
            key = FIELD_ALIASES.get(key, key)
            if value == "|" or value == "":
                pending_key = key
                pending_lines = []
            else:
                current[key] = _coerce_value(key, value)
            continue
        if current_section in {"关系", "relationships", "Relations"} and stripped.startswith("-"):
            value = stripped.lstrip("- ").strip()
            current.setdefault("relations", []).append(_parse_relation(value))
            continue
        if pending_key:
            pending_lines.append(stripped)
        elif current_section:
            key = FIELD_ALIASES.get(current_section, current_section)
            if stripped.startswith("-"):
                current.setdefault(key, []).append(stripped.lstrip("- ").strip())
            else:
                old = str(current.get(key) or "").strip()
                current[key] = (old + "\n" + stripped).strip() if old else stripped
    flush_current()
    return entries, issues


def parse_blueprint_markdown(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    data: dict[str, Any] = {}
    current_section = ""
    section_lines: list[str] = []

    def flush_section() -> None:
        nonlocal section_lines, current_section
        if not current_section:
            section_lines = []
            return
        key = BLUEPRINT_SECTION_ALIASES.get(current_section, current_section)
        value = _section_value(section_lines)
        if key in LIST_FIELDS:
            if key == "foreshadow_actions":
                values = value if isinstance(value, list) else _split_list(str(value))
                data[key] = [_parse_foreshadow_action(v) for v in values if str(v).strip()]
            else:
                data[key] = value if isinstance(value, list) else _split_list(str(value))
        elif isinstance(value, list):
            data[key] = "\n".join(str(x) for x in value).strip()
        else:
            data[key] = value
        section_lines = []

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if current_section:
                section_lines.append("")
            continue
        h1 = re.match(r"^#\s*第\s*(\d+)\s*章\s*[：:]?\s*(.*?)\s*$", stripped)
        if h1:
            data.setdefault("chapter_no", int(h1.group(1)))
            if h1.group(2):
                data.setdefault("title", h1.group(2).strip())
            continue
        h2 = re.match(r"^##\s+(.+?)\s*$", stripped)
        if h2:
            flush_section()
            current_section = h2.group(1).strip()
            continue
        kv = _parse_kv_line(stripped)
        if kv and not current_section:
            key, value = kv
            key = BLUEPRINT_KEY_ALIASES.get(key, key)
            data[key] = _coerce_value(key, value)
            continue
        if current_section:
            section_lines.append(stripped)
    flush_section()
    if "chapter_no" not in data:
        match = re.search(r"第\s*(\d+)\s*章", text or "")
        if match:
            data["chapter_no"] = int(match.group(1))
        else:
            issues.append({"level": "warning", "type": "blueprint_markdown", "message": "蓝图 Markdown 缺少 chapter_no。"})
    data.setdefault("must_cover_nodes", [])
    data.setdefault("forbidden_zones", [])
    data.setdefault("required_characters", [])
    data.setdefault("required_locations", [])
    data.setdefault("required_factions", [])
    return data, issues


def _parse_kv_line(stripped: str) -> tuple[str, str] | None:
    text = stripped.lstrip("- ").strip()
    match = re.match(r"^([^:：]{1,40})\s*[:：]\s*(.*)$", text)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _coerce_value(key: str, value: str) -> Any:
    value = (value or "").strip()
    if key in LIST_FIELDS:
        return _split_list(value)
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except Exception:
            return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except Exception:
            return value
    return value


def _split_list(value: str) -> list[str]:
    value = str(value or "").strip()
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,，、;；]\s*", value) if part.strip()]


def _section_value(lines: list[str]) -> Any:
    cleaned = [line.strip() for line in lines if line.strip()]
    if not cleaned:
        return ""
    if all(line.startswith("-") for line in cleaned):
        return [line.lstrip("- ").strip() for line in cleaned]
    return "\n".join(cleaned).strip()


def _parse_relation(value: str) -> dict[str, str]:
    parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", value) if p.strip()]
    if not parts:
        return {"target": ""}
    return {
        "target": parts[0],
        "type": parts[1] if len(parts) > 1 else "related_to",
        "note": parts[2] if len(parts) > 2 else "",
    }


def _parse_foreshadow_action(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    text = str(value or "").strip()
    parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", text) if p.strip()]
    if not parts:
        return {"id": "", "action": "", "note": ""}
    return {
        "id": parts[0],
        "action": parts[1] if len(parts) > 1 else "advance",
        "note": parts[2] if len(parts) > 2 else "",
    }
