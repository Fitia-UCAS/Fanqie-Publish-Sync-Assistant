from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.shared.text_file.text_file_storage import read_text_auto, write_text, ensure_dir
from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


GENRE_LIBRARY: dict[str, dict[str, Any]] = {
    "玄幻": {
        "aliases": ["玄幻", "东方玄幻", "高武玄幻"],
        "core_loop": "目标压迫 → 获得线索/机缘 → 小冲突验证 → 状态成长 → 更大敌人露面",
        "chapter_rhythm": ["开场给压力或异象", "中段让主角用认知差破局", "结尾留下境界/身份/势力钩子"],
        "must_have": ["修炼体系规则", "境界差距代价", "势力压迫", "资源争夺", "阶段性爽点"],
        "avoid": ["无代价越级", "境界规则随意改", "全靠旁白解释设定"],
        "hook_examples": ["旧物共鸣", "强者留痕", "族规/宗门规则被主角反用"],
    },
    "仙侠": {
        "aliases": ["仙侠", "修仙", "凡人流"],
        "core_loop": "资源稀缺 → 因果牵连 → 修行选择 → 风险兑现 → 道心/境界推进",
        "chapter_rhythm": ["先立因果或危机", "中段展示修行代价", "结尾让旧因果或新天机反噬"],
        "must_have": ["资源/寿元/道心约束", "师承或宗门秩序", "因果伏笔", "修行瓶颈"],
        "avoid": ["无因果获得机缘", "角色道心前后矛盾", "突破太随便"],
        "hook_examples": ["禁地符箓自燃", "旧债主上门", "功法缺页指向下一地"],
    },
    "都市": {
        "aliases": ["都市", "都市异能", "都市脑洞"],
        "core_loop": "现实困境 → 能力/信息差 → 当场打脸或破局 → 关系推进 → 新利益冲突",
        "chapter_rhythm": ["开场贴近日常压迫", "中段制造误解/对抗", "结尾给身份、金钱、关系钩子"],
        "must_have": ["现实场景细节", "人情关系", "利益交换", "身份差/能力差爽点"],
        "avoid": ["过度玄幻化", "没有现实阻力", "配角只会无脑嘲讽"],
        "hook_examples": ["电话里的隐藏身份", "一张旧合同", "对手突然认出主角"],
    },
    "系统流": {
        "aliases": ["系统", "系统流", "面板流"],
        "core_loop": "任务/惩罚 → 限制条件 → 主角钻规则空子 → 奖励改变局面 → 新任务升级",
        "chapter_rhythm": ["开场给任务或惩罚倒计时", "中段展示规则漏洞", "结尾奖励或隐藏任务反转"],
        "must_have": ["任务条件", "失败代价", "奖励边界", "系统不能万能", "规则反用"],
        "avoid": ["系统直接替主角解决一切", "奖励失衡", "面板刷屏无剧情"],
        "hook_examples": ["隐藏任务触发", "奖励说明缺一行", "任务目标变成熟人"],
    },
    "悬疑": {
        "aliases": ["悬疑", "悬疑脑洞", "推理"],
        "core_loop": "异常现象 → 证据收集 → 错误解释被推翻 → 新嫌疑/新规则 → 更深谜面",
        "chapter_rhythm": ["开场给异常", "中段给可验证线索", "结尾推翻一个旧判断"],
        "must_have": ["证据链", "误导线索", "动机", "时间/空间限制", "读者可复盘信息"],
        "avoid": ["靠突然设定破案", "线索不可复盘", "谜面太散"],
        "hook_examples": ["同一物品出现两次", "证词时间矛盾", "死者留下不该知道的信息"],
    },
    "规则怪谈": {
        "aliases": ["规则怪谈", "怪谈", "规则类"],
        "core_loop": "规则读取 → 试探边界 → 发现例外 → 代价出现 → 新规则覆盖旧认知",
        "chapter_rhythm": ["开场给规则文本", "中段让主角用细节试探", "结尾发现规则背后的主体"],
        "must_have": ["规则文本", "违反代价", "例外条件", "污染/认知风险", "规则真伪辨别"],
        "avoid": ["规则没有执行后果", "全靠惊吓不靠逻辑", "主角无脑莽"],
        "hook_examples": ["规则第 7 条被涂改", "安全区出现违规物", "广播说出主角名字"],
    },
    "言情": {
        "aliases": ["言情", "古言", "现言", "甜宠", "替身"],
        "core_loop": "关系误差 → 情绪拉扯 → 事件逼近 → 选择暴露真心/伤口 → 关系状态变化",
        "chapter_rhythm": ["开场给情绪缺口", "中段用事件推动关系", "结尾留下误会/心动/身份钩子"],
        "must_have": ["情绪动机", "关系递进", "误会或秘密", "细节互动", "阶段性情绪回报"],
        "avoid": ["只撒糖无冲突", "误会靠不说话硬拖", "人物动机空心"],
        "hook_examples": ["旧称呼脱口而出", "礼物与秘密有关", "对方知道不该知道的细节"],
    },
    "末世": {
        "aliases": ["末世", "灾变", "废土"],
        "core_loop": "资源危机 → 队伍决策 → 外部威胁 → 牺牲/取舍 → 生存版图变化",
        "chapter_rhythm": ["开场资源或安全压力", "中段做艰难选择", "结尾暴露更大灾变规则"],
        "must_have": ["资源账", "安全边界", "队伍关系", "道德代价", "灾变规则"],
        "avoid": ["物资无限", "危机无代价", "队友工具化"],
        "hook_examples": ["补给上有陌生标记", "安全屋门内有脚印", "感染规则改变"],
    },
}


def _slug(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", text)
    return text or "genre"


def detect_genre_key(text: str) -> str:
    raw = str(text or "").strip().lower()
    for key, card in GENRE_LIBRARY.items():
        candidates = [key, *(card.get("aliases") or [])]
        if any(str(c).lower() in raw or raw in str(c).lower() for c in candidates if c):
            return key
    return "玄幻"


def genre_profile_template(genre: str = "") -> str:
    key = detect_genre_key(genre)
    card = GENRE_LIBRARY[key]
    lines = [
        f"# 题材规则：{key}",
        "",
        "- genre: " + key,
        "- priority: normal",
        "- custom_note: ",
        "",
        "## 核心循环",
        str(card.get("core_loop") or ""),
        "",
        "## 章节节奏",
        *[f"- {x}" for x in card.get("chapter_rhythm") or []],
        "",
        "## 必须有",
        *[f"- {x}" for x in card.get("must_have") or []],
        "",
        "## 避免",
        *[f"- {x}" for x in card.get("avoid") or []],
        "",
        "## 钩子示例",
        *[f"- {x}" for x in card.get("hook_examples") or []],
        "",
        "## 自定义补充",
        "- ",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _parse_list_section(lines: list[str], start: int) -> list[str]:
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if m:
            value = m.group(1).strip()
            if value:
                out.append(value)
    return out


def parse_genre_profile_markdown(text: str) -> dict[str, Any]:
    lines = str(text or "").splitlines()
    data: dict[str, Any] = {"genre": "", "priority": "normal", "custom_note": ""}
    for line in lines:
        m = re.match(r"^\s*[-*]\s*([A-Za-z_\-\u4e00-\u9fff]+)\s*[:：]\s*(.*?)\s*$", line)
        if not m:
            continue
        key = m.group(1).strip().lower().replace("-", "_")
        val = m.group(2).strip()
        if key in {"genre", "priority", "custom_note"}:
            data[key] = val
    section_map = {
        "核心循环": "core_loop",
        "章节节奏": "chapter_rhythm",
        "必须有": "must_have",
        "避免": "avoid",
        "钩子示例": "hook_examples",
        "自定义补充": "custom_rules",
    }
    for idx, line in enumerate(lines):
        title = line.strip().lstrip("#").strip()
        if title in section_map:
            field = section_map[title]
            if field == "core_loop":
                body: list[str] = []
                for item in lines[idx + 1:]:
                    if item.startswith("## "):
                        break
                    if item.strip() and not item.strip().startswith("-"):
                        body.append(item.strip())
                data[field] = "\n".join(body).strip()
            else:
                data[field] = _parse_list_section(lines, idx + 1)
    genre = data.get("genre") or detect_genre_key(text)
    key = detect_genre_key(str(genre))
    base = dict(GENRE_LIBRARY.get(key) or {})
    base.update({k: v for k, v in data.items() if v not in ("", [], None)})
    base["genre"] = str(base.get("genre") or key)
    base["source"] = "writer_control/genres/genre_profile.md"
    base["synced_at"] = _now()
    return base


def ensure_genre_files(storage: Any, project_id: str, *, force: bool = False) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    control = Path(paths.control)
    genre_dir = ensure_dir(control / "genres")
    template_dir = ensure_dir(control / "templates")
    cfg = storage.load_story_config(project_id)
    genre = str(((cfg.get("story_profile") or {}).get("genre") or "") or "玄幻")
    template_path = template_dir / "GENRE_TEMPLATE.md"
    profile_path = genre_dir / "genre_profile.md"
    if force or not template_path.exists():
        write_text(template_path, genre_profile_template(genre))
    if force or not profile_path.exists():
        write_text(profile_path, genre_profile_template(genre))
    return {"template": str(template_path), "profile": str(profile_path), "genre": detect_genre_key(genre)}


def sync_genre_profile(storage: Any, project_id: str, *, force: bool = False) -> dict[str, Any]:
    files = ensure_genre_files(storage, project_id, force=force)
    profile_path = Path(files["profile"])
    profile = parse_genre_profile_markdown(read_text_auto(profile_path))
    json_path = profile_path.with_suffix(".json")
    write_json(json_path, profile)
    cfg_path = Path(storage.paths(project_id).story_config)
    cfg = storage.load_story_config(project_id)
    cfg["genre_profile"] = profile
    profile_rules = cfg.setdefault("story_rules", {}).setdefault("style_rules", [])
    for item in (profile.get("must_have") or [])[:8]:
        rule = f"题材必须体现：{item}"
        if rule not in profile_rules:
            profile_rules.append(rule)
    for item in (profile.get("avoid") or [])[:8]:
        rule = f"题材禁区：{item}"
        if rule not in profile_rules:
            profile_rules.append(rule)
    write_json(cfg_path, cfg)
    report = {
        "ok": True,
        "generated_at": _now(),
        "genre": profile.get("genre"),
        "profile": profile,
        "paths": {"markdown": str(profile_path), "json": str(json_path), "template": files.get("template")},
    }
    report_dir = ensure_dir(Path(storage.paths(project_id).control) / "reports" / "genres")
    report_json = report_dir / "last_genre_report.json"
    report_md = report_dir / "last_genre_report.md"
    write_json(report_json, report)
    write_text(report_md, render_genre_report(report))
    report["paths"]["report_json"] = str(report_json)
    report["paths"]["report_markdown"] = str(report_md)
    return report


def render_genre_report(report: dict[str, Any]) -> str:
    p = report.get("profile") or {}
    lines = [f"# 题材规则报告：{p.get('genre') or ''}", "", f"生成时间：{report.get('generated_at')}", "", "## 核心循环", str(p.get("core_loop") or ""), ""]
    for title, key in [("章节节奏", "chapter_rhythm"), ("必须有", "must_have"), ("避免", "avoid"), ("钩子示例", "hook_examples"), ("自定义规则", "custom_rules")]:
        lines += [f"## {title}"]
        items = p.get(key) or []
        if items:
            lines += [f"- {x}" for x in items]
        else:
            lines.append("- 暂无")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_genre_profile(storage: Any, project_id: str) -> dict[str, Any]:
    path = Path(storage.paths(project_id).control) / "genres" / "genre_profile.json"
    data = read_json(path, {})
    if isinstance(data, dict) and data:
        return data
    cfg = storage.load_story_config(project_id)
    gp = cfg.get("genre_profile")
    return gp if isinstance(gp, dict) else {}
