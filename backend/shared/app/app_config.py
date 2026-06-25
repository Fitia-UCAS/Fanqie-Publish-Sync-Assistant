from __future__ import annotations


from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from backend.shared.app.app_paths import CONFIG_FILE, LEGACY_CONFIG_FILE, ensure_data_directories

CONFIG_VERSION = 6

LEGACY_CONFIG_SECTIONS: dict[str, str] = {
    "extract_novel": "process_novel",
    "auto_publish_chapters": "auto_publish",
    "sync_publish_chapters": "chapter_sync",
    "crawl_novel": "web_crawler",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
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
        "start": 1,
        "end": 1,
        "useAi": False,
        "verifyAfterPublish": True,
        "debugScreenshots": True,
        "failureScreenshots": True,
        "dedupeDebugScreenshots": True,
        "gitTracking": True,
        "cleanBeforeRun": True,
        "operation": "publish",
    },
    "chapter_sync": {
        "novelFile": "",
        "chapterManageUrl": "",
        "start": 1,
        "end": 1,
        "useAi": False,
        "verifyAfterPublish": True,
        "debugScreenshots": True,
        "failureScreenshots": True,
        "dedupeDebugScreenshots": True,
        "gitTracking": True,
        "cleanBeforeRun": True,
        "operation": "publish",
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
    "character_material": {
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
}


def load_config() -> dict[str, Any]:
    ensure_data_directories()
    data = _read_json(CONFIG_FILE)
    if not data and LEGACY_CONFIG_FILE.exists():
        data = _read_json(LEGACY_CONFIG_FILE)
    config = _merge_default(data)
    if not CONFIG_FILE.exists():
        save_config(config)
    return config


def save_config(config: dict[str, Any]) -> None:
    ensure_data_directories()
    merged = _merge_default(config)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _merge_default(data: dict[str, Any]) -> dict[str, Any]:
    migrated = _migrate_legacy_sections(data if isinstance(data, dict) else {})
    config = deepcopy(DEFAULT_CONFIG)
    deep_update(config, migrated)
    _remove_unknown_config_keys(config, DEFAULT_CONFIG)
    config["version"] = CONFIG_VERSION
    return config


def _migrate_legacy_sections(data: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(data)
    active_page = migrated.get("activePage")
    if isinstance(active_page, str):
        migrated["activePage"] = LEGACY_CONFIG_SECTIONS.get(active_page, active_page)
    for legacy_key, new_key in LEGACY_CONFIG_SECTIONS.items():
        legacy_value = migrated.pop(legacy_key, None)
        if legacy_value is not None and new_key not in migrated:
            migrated[new_key] = legacy_value
    return migrated


def _remove_unknown_config_keys(config: dict[str, Any], defaults: dict[str, Any]) -> None:
    for key in list(config):
        if key not in defaults:
            config.pop(key, None)
            continue
        value = config.get(key)
        default_value = defaults.get(key)
        if isinstance(value, dict) and isinstance(default_value, dict):
            _remove_unknown_config_keys(value, default_value)


