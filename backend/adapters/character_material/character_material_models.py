from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONTENT_TYPES: list[str] = [
    "对话",
    "心理活动",
    "动作描写",
    "神态描写",
    "动作神态描写",
    "语气描写",
    "外貌描写",
    "人物评价",
]

CONTENT_TYPE_ALIASES: dict[str, str] = {
    "心理描写": "心理活动",
    "心声": "心理活动",
    "内心活动": "心理活动",
    "动作": "动作描写",
    "神态": "神态描写",
    "动作神态": "动作神态描写",
    "语气": "语气描写",
    "外貌": "外貌描写",
    "评价": "人物评价",
    "旁白评价": "人物评价",
}


@dataclass(slots=True)
class CharacterChapterMeta:
    novel_name: str
    chapter_index: int
    chapter_title: str
    file_name: str
    source_file: str
    start_line: int
    end_line: int
    char_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CharacterChapterText:
    meta: CharacterChapterMeta
    text: str


@dataclass(slots=True)
class CharacterTextChunk:
    novel_name: str
    chapter_index: int
    chapter_title: str
    chunk_id: int
    local_chunk_id: int
    text: str


@dataclass(slots=True)
class CharacterMaterial:
    novel_name: str
    chapter_index: int
    chapter_title: str
    chunk_id: int
    local_chunk_id: int
    item_index: int
    character: str
    content_type: str
    content: str
    source_text: str | None = None

    def to_dict(self, *, include_source_text: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_source_text:
            data.pop("source_text", None)
        return data


@dataclass(slots=True)
class CharacterMaterialStats:
    total_items: int
    unique_characters: int
    character_distribution: dict[str, int]
    content_type_distribution: dict[str, int]
    chapter_distribution: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CharacterMaterialExtractResult:
    output_path: Path
    stats: CharacterMaterialStats


def normalize_content_type(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "素材"
    if text in CONTENT_TYPES:
        return text
    return CONTENT_TYPE_ALIASES.get(text, text)


def build_material_stats(materials: list[CharacterMaterial]) -> CharacterMaterialStats:
    characters = Counter(item.character for item in materials)
    content_types = Counter(item.content_type for item in materials)
    chapters = Counter(item.chapter_title for item in materials)
    return CharacterMaterialStats(
        total_items=len(materials),
        unique_characters=len(characters),
        character_distribution=dict(characters.most_common()),
        content_type_distribution=dict(content_types.most_common()),
        chapter_distribution=dict(chapters.most_common()),
    )
