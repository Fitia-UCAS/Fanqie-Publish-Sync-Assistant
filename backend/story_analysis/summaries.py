from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PlotChapterSummary:
    novel_name: str
    chapter_index: int
    chapter_title: str
    summary: str
    chapter_context: dict[str, Any] = field(default_factory=dict)
    event_chain: dict[str, Any] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    emotional_beats: list[str] = field(default_factory=list)
    character_updates: list[str] = field(default_factory=list)
    story_threads: list[dict[str, Any]] = field(default_factory=list)
    chapter_hook: dict[str, Any] = field(default_factory=dict)
    unclear_fields: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlotUpdateReport:
    output_path: Path
    debug_path: Path
    total_chapters: int
    updated_chapters: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "outputPath": str(self.output_path),
            "debugPath": str(self.debug_path),
            "totalChapters": self.total_chapters,
            "updatedChapters": self.updated_chapters,
        }
