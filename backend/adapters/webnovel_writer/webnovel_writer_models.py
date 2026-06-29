from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(slots=True)
class WriterProjectMeta:
    project_id: str
    title: str
    genre: str = ""
    premise: str = ""
    target_audience: str = ""
    style_brief: str = ""
    project_path: str = ""
    novel_file: str = ""
    story_config_source: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WriterPaths:
    root: str
    meta: str
    settings: str
    story_config: str
    state: str
    outlines: str
    volumes: str
    blueprints: str
    chapters: str
    drafts: str
    rejected: str
    reviews: str
    commits: str
    runtime: str
    artifacts: str
    runs: str
    validation: str
    indexes: str
    exports: str
    control: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


ENTITY_BUCKETS = ("characters", "locations", "factions", "items", "foreshadows", "conflicts")
CONTROL_ENTITY_BUCKETS = ENTITY_BUCKETS + ("secrets", "pledges", "deadlines")

DEFAULT_STATE: dict[str, Any] = {
    "schema_version": 3,
    "project_clock": {"created_at": "", "updated_at": ""},
    "characters": {},
    "locations": {},
    "factions": {},
    "items": {},
    "foreshadows": {},
    "conflicts": {},
    "secrets": {},
    "pledges": {},
    "deadlines": {},
    "timeline": [],
    "milestones": [],
    "chapter_summaries": {},
    "chapter_status": {},
    "chapter_titles": {},
    "entity_mentions": [],
    "foreshadow_debts": {},
    "conflict_progress": {},
    "latest_chapter": 0,
    "last_commit_id": "",
}


def fresh_state() -> dict[str, Any]:
    import copy

    state = copy.deepcopy(DEFAULT_STATE)
    stamp = now_iso()
    state["project_clock"] = {"created_at": stamp, "updated_at": stamp}
    return state
