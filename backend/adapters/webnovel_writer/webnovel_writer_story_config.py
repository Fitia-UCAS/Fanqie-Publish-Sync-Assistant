from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_STORY_CONFIG: dict[str, Any] = {
    "product_name": "网文写作",
    "schema_version": 3,
    "design_note": "Python 后端负责故事状态、门禁、事实回写、索引检索和落地；前端只负责发起常用操作。",
    "story_profile": {
        "title": "",
        "genre": "",
        "target_audience": "",
        "premise": "",
        "style_brief": "",
        "world_summary": "",
        "core_hook": "",
        "first_volume_goal": "",
        "source_setting_file": "",
    },
    "workflow": {
        "lineage": "tianming-style state gate + webnovel-writer agent workflow + local desktop assistant",
        "steps": [
            "prewrite_gate",
            "context_retrieval",
            "context_agent",
            "drafter",
            "draft_protocol_gate",
            "reviewer_gate",
            "data_agent",
            "consistency_gate",
            "chapter_commit",
            "state_projection",
            "novel_txt_sync",
        ],
        "hard_rule": "不通过 blocking gate 的章节只能进入 rejected/drafts，不能写入 chapters，不能污染 story_state。",
    },
    "story_rules": {
        "world_rules": [],
        "character_rules": [],
        "faction_rules": [],
        "location_rules": [],
        "plot_rules": [],
        "forbidden_patterns": [
            "不能无声明新增关键角色",
            "不能覆盖已确认角色核心性格",
            "不能让角色瞬移到未解释地点",
            "不能跳过章节蓝图的必达节点",
            "不能为了爽点直接破坏世界规则",
        ],
        "style_rules": [
            "中文网文表达，开局快速进入矛盾",
            "每章至少一次冲突/信息/情绪推进",
            "章末保留追读钩子，但不要机械口号",
        ],
    },
    "gate_policy": {
        "unknown_entity_limit": 5,
        "untracked_extra_limit": 3,
        "require_changes_marker": True,
        "require_blueprint_in_strict_mode": True,
        "allow_manual_risk_accept": False,
        "auto_repair_rounds": 1,
        "min_chapter_chars": 300,
        "long_foreshadow_warning_chapters": 30,
        "context_recall_top_k": 6,
        "recent_context_count": 6,
        "auto_patch_omitted_known_entities": True,
        "omitted_known_entity_is_blocking": True,
        "required_entity_presence_is_blocking": True,
        "require_ending_hook": True,
    },
    "entity_schema": {
        "character": ["id", "name", "aliases", "status", "location", "emotion", "ability", "locked_traits", "relations", "history"],
        "location": ["id", "name", "aliases", "status", "features", "history"],
        "faction": ["id", "name", "aliases", "status", "members", "relations", "history"],
        "item": ["id", "name", "aliases", "owner", "status", "history"],
        "foreshadow": ["id", "name", "status", "urgency", "introduced_chapter", "resolved_chapter", "history"],
        "conflict": ["id", "name", "status", "progress", "history"],
    },
    "review_rubric": {
        "blocking": ["事实矛盾", "角色 OOC", "蓝图必达节点缺失", "严重时间线错误", "CHANGES 与正文不符"],
        "quality": ["开章钩子", "冲突推进", "信息密度", "人物动机", "章末追读", "网文节奏"],
    },
    "model_routes": {
        "default": {"platform": "deepseek", "temperature": 0.72, "max_tokens": 8192},
        "planner": {"platform": "deepseek_reasoner", "temperature": 0.42, "max_tokens": 4096},
        "context": {"platform": "deepseek", "temperature": 0.25, "max_tokens": 6144},
        "drafter": {"platform": "deepseek", "temperature": 0.72, "max_tokens": 8192},
        "reviewer": {"platform": "deepseek_reasoner", "temperature": 0.1, "max_tokens": 4096},
        "fact": {"platform": "deepseek_reasoner", "temperature": 0.1, "max_tokens": 6144},
        "repair": {"platform": "deepseek", "temperature": 0.45, "max_tokens": 8192},
    },
    "source_files": {},
}


def default_story_config() -> dict[str, Any]:
    return deepcopy(DEFAULT_STORY_CONFIG)
