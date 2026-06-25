from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.adapters.character_material.character_material_models import normalize_content_type
from backend.adapters.character_material.character_material_prompt import build_character_material_system_prompt, build_character_material_user_prompt
from backend.adapters.character_material.character_material_project import load_character_chapter_index, split_text_file_to_character_project


def test_character_material_prompt_accepts_free_keyword_constraints() -> None:
    prompt = build_character_material_user_prompt(
        "林恒冷笑一声。",
        character_target="林恒",
        keyword="嚣张语气对话 / 吃醋嘴硬 / 打斗动作 / 景色氛围",
    )

    assert "人物 / 对象：林恒" in prompt
    assert "关键词：嚣张语气对话 / 吃醋嘴硬 / 打斗动作 / 景色氛围" in prompt
    assert "小说正文" in prompt


def test_character_material_system_prompt_does_not_limit_content_type_to_fixed_categories() -> None:
    prompt = build_character_material_system_prompt()

    assert "content_type 不要被固定分类限制" in prompt
    assert "关键词理解为本次抽取限定" in prompt
    assert "景色氛围" in prompt


def test_character_material_content_type_keeps_custom_emotion_or_action_type() -> None:
    assert normalize_content_type("吃醋嘴硬") == "吃醋嘴硬"
    assert normalize_content_type("打斗动作") == "打斗动作"
    assert normalize_content_type("") == "素材"

def test_character_material_split_file_name_does_not_repeat_chapter_number(tmp_path: Path) -> None:
    source = tmp_path / "测试小说.txt"
    source.write_text(
        "第238章_劝师姐遵从本心\n\n正文。\n\n第239章 下一章\n\n正文二。\n",
        encoding="utf-8",
    )

    project_dir = split_text_file_to_character_project(source, tmp_path / "character_chapters")
    file_names = sorted(path.name for path in project_dir.glob("*.txt"))

    assert file_names[0] == "第238章_劝师姐遵从本心.txt"
    assert "第238章_第238章" not in file_names[0]
    index = load_character_chapter_index(project_dir)
    assert index[0].chapter_title == "第238章 劝师姐遵从本心"
    assert (project_dir / file_names[0]).read_text(encoding="utf-8").startswith("第238章 劝师姐遵从本心")

