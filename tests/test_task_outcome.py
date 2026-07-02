from __future__ import annotations

import json
from pathlib import Path

from backend.tasks.outcome import TaskOutcome


def test_task_result_result_kind_and_display_name_are_stable() -> None:
    payload = TaskOutcome(
        True,
        "done",
        path=Path("data/output.txt"),
        result_kind="output_file",
    ).to_dict()

    assert payload["resultKind"] == "output_file"
    assert payload["displayName"] == "output.txt"
    json.dumps(payload, ensure_ascii=False)
