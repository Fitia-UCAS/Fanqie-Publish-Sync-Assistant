from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from backend.paths import (
    CONFIG_FILE,
    RECENT_INPUTS_FILE,
    SECRET_CONFIG_FILE,
    WORKFLOW_DEFAULTS_FILE,
    ensure_data_directories,
)


WORKFLOW_SECTIONS: tuple[str, ...] = (
    "process_novel",
    "novel_splitter",
    "clean_text",
    "auto_publish",
    "chapter_sync",
    "web_crawler",
    "character_notes",
    "plot_notes",
)

SENSITIVE_KEYS_BY_SECTION: dict[str, set[str]] = {
    "character_notes": {"apiKey"},
    "plot_notes": {"apiKey"},
}


RECENT_INPUT_KEYS_BY_SECTION: dict[str, set[str]] = {
    "process_novel": {"novelFile", "batchFolder", "outputFile"},
    "novel_splitter": {"inputFile", "outputDir"},
    "clean_text": {"adInputFile", "adBatchFolder", "moveInputFile", "moveBatchFolder"},
    "auto_publish": {"novelFile", "chapterManageUrl", "authStatePath"},
    "chapter_sync": {"novelFile", "chapterManageUrl", "authStatePath"},
    "web_crawler": {"novelUrl", "outputFile", "outputAutoUrl"},
    "character_notes": {"source", "outputDir", "outputFile"},
    "plot_notes": {"source", "plotNotesFile", "outputDir", "outputFile"},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "activePage": "auto_publish",
    "process_novel": {
        "novelFile": "",
        "batchFolder": "",
        "outputFile": "",
        "chapter": 1,
        "aroundChapter": 1,
        "start": 1,
        "end": 1,
    },
    "novel_splitter": {
        "inputFile": "",
        "outputDir": "",
        "mode": "chapter",
        "chaptersPerFile": 100,
        "maxChars": 120000,
        "maxLines": 3000,
    },
    "clean_text": {
        "adInputFile": "",
        "adBatchFolder": "",
        "moveInputFile": "",
        "moveBatchFolder": "",
        "adProfile": "default",
        "overwrite": True,
        "backup": True,
        "normalizePunctuation": True,
        "maxMoveChars": 120,
    },
    "auto_publish": {
        "novelFile": "",
        "chapterManageUrl": "",
        "authStatePath": "",
        "start": 1,
        "end": 1,
        "useAi": False,
        "verifyAfterPublish": True,
        "debugScreenshots": True,
        "failureScreenshots": True,
        "dedupeDebugScreenshots": True,
        "gitTracking": True,
        "cleanBeforeRun": True,
        "headless": False,
        "manualSchedule": False,
        "scheduleStartDate": "",
        "scheduleMorningTime": "10:00",
        "scheduleMorningCount": 1,
        "scheduleAfternoonTime": "18:00",
        "scheduleAfternoonCount": 0,
        "operation": "publish",
    },
    "chapter_sync": {
        "novelFile": "",
        "chapterManageUrl": "",
        "authStatePath": "",
        "start": 1,
        "end": 1,
        "useAi": False,
        "verifyAfterPublish": True,
        "debugScreenshots": True,
        "failureScreenshots": True,
        "dedupeDebugScreenshots": True,
        "gitTracking": True,
        "cleanBeforeRun": True,
        "headless": False,
        "manualSchedule": False,
        "scheduleStartDate": "",
        "scheduleMorningTime": "10:00",
        "scheduleMorningCount": 1,
        "scheduleAfternoonTime": "18:00",
        "scheduleAfternoonCount": 0,
        "operation": "push",
    },
    "web_crawler": {
        "novelUrl": "",
        "outputFile": "",
        "outputFileManual": False,
        "outputAutoUrl": "",
        "start": 1,
        "end": 0,
        "maxWorkers": 16,
        "timeout": 25,
        "requestDelayMin": 0.12,
        "requestDelayMax": 0.35,
        "maxRetries": 3,
        "htmlFallback": True,
        "detailedLog": False,
    },
    "character_notes": {
        "source": "",
        "outputDir": "",
        "outputFile": "",
        "characterTarget": "",
        "keyword": "",
        "platform": "deepseek",
        "apiKey": "",
        "baseUrl": "",
        "modelName": "",
        "temperature": 0.2,
        "chapter": "",
        "start": "",
        "end": "",
        "allChapters": True,
        "concurrent": True,
        "maxWorkers": 4,
    },
    "plot_notes": {
        "source": "",
        "plotNotesFile": "",
        "outputDir": "",
        "outputFile": "",
        "platform": "deepseek",
        "apiKey": "",
        "baseUrl": "",
        "modelName": "",
        "temperature": 0.2,
        "chapter": "",
        "aroundChapter": "",
        "start": "",
        "end": "",
        "scope": "range",
        "mode": "extract_merge",
        "targetWords": 260,
        "recentContextCount": 5,
        "replaceExisting": True,
        "maxWorkers": 4,
    },
}


def load_config() -> dict[str, Any]:
    ensure_data_directories()
    config = _merge_default(_load_split_config())
    if not CONFIG_FILE.exists() or not WORKFLOW_DEFAULTS_FILE.exists() or not RECENT_INPUTS_FILE.exists():
        save_config(config)
    return config


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    ensure_data_directories()
    merged = _merge_default(config)
    app_data, workflow_data, recent_data, secret_data = _split_config_for_storage(merged)
    _write_json(CONFIG_FILE, app_data)
    _write_json(WORKFLOW_DEFAULTS_FILE, workflow_data)
    _write_json(RECENT_INPUTS_FILE, recent_data)
    _write_json(SECRET_CONFIG_FILE, secret_data)
    return _merge_default(_join_split_config(app_data, workflow_data, recent_data, secret_data))


def deep_update(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_update(target[key], value)
        else:
            target[key] = value
    return target


def set_config_path(config: dict[str, Any], dotted_path: str, value: Any) -> None:
    if not dotted_path:
        return
    parts = [part for part in dotted_path.split(".") if part]
    current = config
    for part in parts[:-1]:
        next_value = current.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            current[part] = next_value
        current = next_value
    if parts:
        current[parts[-1]] = value


def get_config_section(config: dict[str, Any], section: str) -> dict[str, Any]:
    value = config.get(section)
    if not isinstance(value, dict):
        value = {}
        config[section] = value
    return value


def _load_split_config() -> dict[str, Any]:
    paths = (CONFIG_FILE, WORKFLOW_DEFAULTS_FILE, RECENT_INPUTS_FILE, SECRET_CONFIG_FILE)
    if not any(path.exists() for path in paths):
        return {}
    return _join_split_config(
        _read_json(CONFIG_FILE),
        _read_json(WORKFLOW_DEFAULTS_FILE),
        _read_json(RECENT_INPUTS_FILE),
        _read_json(SECRET_CONFIG_FILE),
    )



def _split_config_for_storage(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    app_data: dict[str, Any] = {
        "activePage": config.get("activePage", DEFAULT_CONFIG["activePage"]),
    }
    workflow_data: dict[str, Any] = {}
    recent_data: dict[str, Any] = {}
    secret_data: dict[str, Any] = {}

    for section in WORKFLOW_SECTIONS:
        value = config.get(section)
        if not isinstance(value, dict):
            continue
        workflow_section: dict[str, Any] = {}
        recent_section: dict[str, Any] = {}
        secret_section: dict[str, Any] = {}
        sensitive_keys = SENSITIVE_KEYS_BY_SECTION.get(section, set())
        recent_keys = RECENT_INPUT_KEYS_BY_SECTION.get(section, set())
        for key, item in value.items():
            if key in sensitive_keys:
                if item:
                    secret_section[key] = item
            elif key in recent_keys:
                recent_section[key] = item
            else:
                workflow_section[key] = item
        workflow_data[section] = workflow_section
        if recent_section:
            recent_data[section] = recent_section
        if secret_section:
            secret_data[section] = secret_section

    for key, value in config.items():
        if key not in {"activePage", "showPersonalPages", *WORKFLOW_SECTIONS}:
            app_data[key] = deepcopy(value)

    return app_data, workflow_data, recent_data, secret_data


def _join_split_config(
    app_data: dict[str, Any],
    workflow_data: dict[str, Any],
    recent_data: dict[str, Any],
    secret_data: dict[str, Any],
) -> dict[str, Any]:
    config: dict[str, Any] = {}
    deep_update(config, _strip_schema(app_data))
    deep_update(config, _strip_schema(workflow_data))
    deep_update(config, _strip_schema(recent_data))
    deep_update(config, _strip_schema(secret_data))
    return config


def _strip_schema(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = deepcopy(data if isinstance(data, dict) else {})
    cleaned.pop("schemaVersion", None)
    return cleaned


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge_default(data: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    deep_update(config, data if isinstance(data, dict) else {})
    return config

