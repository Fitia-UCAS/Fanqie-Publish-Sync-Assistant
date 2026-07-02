from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.json_files import to_json_safe
from backend.tasks.outcome import TaskOutcome


@dataclass
class NestedPayload:
    path: Path
    items: tuple[Path, ...]


def test_task_result_converts_nested_paths_before_json() -> None:
    result = TaskOutcome(
        True,
        "ok",
        path=Path("data/output.txt"),
        data={"meta": NestedPayload(Path("data/a.txt"), (Path("data/b.txt"),))},
    )

    payload = result.to_dict()

    assert payload["path"].replace("\\", "/") == "data/output.txt"
    assert payload["meta"]["path"].replace("\\", "/") == "data/a.txt"
    assert payload["meta"]["items"][0].replace("\\", "/") == "data/b.txt"
    json.dumps(payload, ensure_ascii=False)


def test_serializer_handles_mixed_containers() -> None:
    payload = to_json_safe({"paths": {Path("a.txt"), Path("b.txt")}})
    json.dumps(payload, ensure_ascii=False)
