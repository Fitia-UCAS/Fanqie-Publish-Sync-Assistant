from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from backend.paths import RUNS_DIR
from backend.json_files import append_jsonl, read_json, write_json
from backend.workspaces import workspace_dir

RUN_SCHEMA_VERSION = 2


def begin_run(*, workflow: str, page: str, input_payload: dict[str, Any] | None = None, workspace_id: str = "") -> Path:
    started_at = datetime.now().isoformat(timespec="seconds")
    run_id = _new_run_id(workflow)
    run_dir = _run_dir(run_id, workspace_id=workspace_id)
    write_json(
        run_dir / "task.json",
        {
            "schemaVersion": RUN_SCHEMA_VERSION,
            "runId": run_id,
            "workspaceId": workspace_id,
            "workflow": workflow,
            "page": page,
            "status": "running",
            "startedAt": started_at,
            "endedAt": "",
            "input": input_payload or {},
            "result": {},
            "artifacts": {"events": "events.jsonl", "result": "result.json"},
        },
    )
    if workspace_id:
        _write_global_index(run_id=run_id, workspace_id=workspace_id, workflow=workflow, page=page, started_at=started_at, run_dir=run_dir)
    return run_dir


def append_run_event(run_dir: Path | None, event: dict[str, Any]) -> None:
    if run_dir is None:
        return
    append_jsonl(run_dir / "events.jsonl", event)


def finish_run(run_dir: Path | None, *, ok: bool, result: dict[str, Any]) -> None:
    if run_dir is None:
        return
    task_file = run_dir / "task.json"
    task = read_json(task_file)
    task.update(
        {
            "status": "success" if ok else "failed",
            "endedAt": datetime.now().isoformat(timespec="seconds"),
            "result": result,
        }
    )
    write_json(task_file, task)
    write_json(run_dir / "result.json", result)


def _run_dir(run_id: str, *, workspace_id: str = "") -> Path:
    if workspace_id:
        return workspace_dir(workspace_id) / "runs" / run_id
    return RUNS_DIR / run_id


def _write_global_index(*, run_id: str, workspace_id: str, workflow: str, page: str, started_at: str, run_dir: Path) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    append_jsonl(
        RUNS_DIR / "index.jsonl",
        {
            "schemaVersion": RUN_SCHEMA_VERSION,
            "runId": run_id,
            "workspaceId": workspace_id,
            "workflow": workflow,
            "page": page,
            "startedAt": started_at,
            "path": str(run_dir),
        },
    )


def _new_run_id(workflow: str) -> str:
    safe_workflow = re.sub(r"[^0-9A-Za-z_\-]+", "_", workflow).strip("_") or "task"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"run_{stamp}_{safe_workflow}"
