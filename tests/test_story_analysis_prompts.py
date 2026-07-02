from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.story_analysis.materials import normalize_content_type
from backend.story_analysis.material_prompts import build_character_notes_system_prompt, build_character_notes_user_prompt
from backend.story_analysis.chapter_files import load_character_chapter_index, split_text_file_to_character_project


def test_character_notes_prompt_accepts_free_keyword_constraints() -> None:
    prompt = build_character_notes_user_prompt(
        "林恒冷笑一声。",
        character_target="林恒",
        keyword="嚣张语气对话 / 吃醋嘴硬 / 打斗动作 / 景色氛围",
    )

    assert "人物 / 对象：林恒" in prompt
    assert "关键词：嚣张语气对话 / 吃醋嘴硬 / 打斗动作 / 景色氛围" in prompt
    assert "小说正文" in prompt


def test_character_notes_system_prompt_does_not_limit_content_type_to_fixed_categories() -> None:
    prompt = build_character_notes_system_prompt()

    assert "content_type 不要被固定分类限制" in prompt
    assert "关键词理解为本次抽取限定" in prompt
    assert "景色氛围" in prompt


def test_character_notes_content_type_keeps_custom_emotion_or_action_type() -> None:
    assert normalize_content_type("吃醋嘴硬") == "吃醋嘴硬"
    assert normalize_content_type("打斗动作") == "打斗动作"
    assert normalize_content_type("") == "素材"

def test_character_notes_split_file_name_does_not_repeat_chapter_number(tmp_path: Path) -> None:
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



def test_character_notes_prompt_filters_low_value_short_replies() -> None:
    prompt = build_character_notes_system_prompt()
    user_prompt = build_character_notes_user_prompt("【甲：同意！】\n【乙：同意！】", keyword="商业互吹")

    assert "不要提取低信息量水句" in prompt
    assert "不要按每个说话人拆成多条重复素材" in user_prompt


def test_character_notes_low_value_content_filter() -> None:
    from backend.story_analysis.extract_characters import _is_low_value_content

    assert _is_low_value_content("同意！") is True
    assert _is_low_value_content("？？？") is True
    assert _is_low_value_content("我看未必。") is False
    assert _is_low_value_content("有其师必有其徒。") is False


def test_character_notes_bool_payload_accepts_string_false() -> None:
    from backend.story_analysis.extract_characters import _optional_bool

    assert _optional_bool("false", True) is False
    assert _optional_bool("0", True) is False
    assert _optional_bool("true", False) is True
