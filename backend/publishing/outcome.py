from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PublishedChapter:
    ok: bool
    chapter_no: int
    published: bool
    message: str
    trace_dir: Path | None = None
    error_stage: str = ""
