from __future__ import annotations

import hashlib
import os
import re
import time
from itertools import count
from typing import Any

try:
    from playwright.sync_api import Page
except Exception:
    Page = Any

from backend.paths import PUBLISHING_DEBUG_DIR, SYNCING_DEBUG_DIR

_CONTEXT_DEBUG_CATEGORY: dict[int, str] = {}
_CONTEXT_DEBUG_ENABLED: dict[int, bool] = {}
_CONTEXT_FAILURE_DEBUG_ENABLED: dict[int, bool] = {}
_CONTEXT_DEBUG_FINGERPRINTS: dict[int, set[str]] = {}
_DEBUG_COUNTER = count(1)


def register_debug_context(context: Any, *, category: str, debug_enabled: bool | None, failure_debug_enabled: bool | None) -> None:
    context_id = id(context)
    _CONTEXT_DEBUG_CATEGORY[context_id] = category or "chapter_sync"
    if debug_enabled is not None:
        _CONTEXT_DEBUG_ENABLED[context_id] = bool(debug_enabled)
    if failure_debug_enabled is not None:
        _CONTEXT_FAILURE_DEBUG_ENABLED[context_id] = bool(failure_debug_enabled)


def forget_debug_context(context: Any) -> None:
    context_id = id(context)
    _CONTEXT_DEBUG_CATEGORY.pop(context_id, None)
    _CONTEXT_DEBUG_ENABLED.pop(context_id, None)
    _CONTEXT_FAILURE_DEBUG_ENABLED.pop(context_id, None)
    _CONTEXT_DEBUG_FINGERPRINTS.pop(context_id, None)


def _current_debug_category(page: Page, category: str | None) -> str:
    if category:
        return category
    try:
        return _CONTEXT_DEBUG_CATEGORY.get(id(page.context), "chapter_sync")
    except Exception:
        return "chapter_sync"


def _debug_enabled(category: str, page: Page | None = None) -> bool:
    if page is not None:
        try:
            flag = _CONTEXT_DEBUG_ENABLED.get(id(page.context))
            if flag is not None:
                return bool(flag)
        except Exception:
            pass
    env_key = "AUTO_PUBLISH_DEBUG" if category == "auto_publish" else "CHAPTER_SYNC_DEBUG"
    env_value = os.getenv(env_key)
    if env_value is not None:
        return env_value == "1"
    if category == "auto_publish":
        try:
            from backend.settings import load_config

            section = load_config().get("auto_publish", {})
            if isinstance(section, dict):
                return bool(section.get("debugScreenshots", True))
        except Exception:
            return True

    return False


def _debug_dir(category: str):
    return PUBLISHING_DEBUG_DIR if category == "auto_publish" else SYNCING_DEBUG_DIR


def _safe_debug_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(name or "page"))
    return cleaned.strip("_")[:80] or "page"


def _debug_dedupe_enabled(category: str) -> bool:
    if category == "auto_publish":
        try:
            from backend.settings import load_config

            section = load_config().get("auto_publish", {})
            if isinstance(section, dict):
                return bool(section.get("dedupeDebugScreenshots", True))
        except Exception:
            return True
    return True


def _page_state_fingerprint(page: Page, screenshot_bytes: bytes) -> str:
    try:
        state = page.evaluate(
            """() => {
                const body = document.body ? document.body.innerText : '';
                const size = `${window.innerWidth}x${window.innerHeight}:${document.documentElement.scrollWidth}x${document.documentElement.scrollHeight}`;
                return `${location.href}\n${document.title}\n${size}\n${body}`;
            }"""
        )
        if isinstance(state, str) and state.strip():
            normalized = "\n".join(line.strip() for line in state.splitlines() if line.strip())
            return hashlib.sha256(normalized.encode("utf-8", errors="ignore")).hexdigest()
    except Exception:
        pass
    return hashlib.sha256(screenshot_bytes).hexdigest()


def save_debug(page: Page, name: str, *, category: str | None = None, force: bool = False) -> None:
    current_category = _current_debug_category(page, category)
    if not _debug_enabled(current_category, page):
        return
    _write_debug_image(page, name, category=current_category, force=force)


def save_failure_debug(page: Page, name: str, *, category: str | None = None) -> None:
    current_category = _current_debug_category(page, category)
    if not _failure_debug_enabled(page):
        return
    _write_debug_image(page, name, category=current_category, force=True)


def _failure_debug_enabled(page: Page) -> bool:
    try:
        flag = _CONTEXT_FAILURE_DEBUG_ENABLED.get(id(page.context))
        if flag is not None:
            return bool(flag)
    except Exception:
        pass
    return True


def _write_debug_image(page: Page, name: str, *, category: str, force: bool = False) -> None:
    directory = _debug_dir(category)
    directory.mkdir(parents=True, exist_ok=True)

    try:
        screenshot_bytes = page.screenshot(full_page=True)
    except Exception:
        return

    if not force and _debug_dedupe_enabled(category):
        try:
            context_id = id(page.context)
        except Exception:
            context_id = 0
        fingerprint = _page_state_fingerprint(page, screenshot_bytes)
        seen = _CONTEXT_DEBUG_FINGERPRINTS.setdefault(context_id, set())
        if fingerprint in seen:
            return
        seen.add(fingerprint)

    ts = time.strftime("%Y%m%d_%H%M%S")
    ms = int((time.time() % 1) * 1000)
    seq = next(_DEBUG_COUNTER)
    stem = f"{ts}_{ms:03d}_{seq:04d}_{_safe_debug_name(name)}"
    png_path = directory / f"{stem}.png"
    try:
        png_path.write_bytes(screenshot_bytes)
    except Exception:
        pass
