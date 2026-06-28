from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from itertools import count
from typing import Any

try:
    from playwright.sync_api import Page, sync_playwright
except Exception as exc:
    Page = Any
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR: Exception | None = exc
else:
    _PLAYWRIGHT_IMPORT_ERROR = None

from backend.shared.app.app_paths import BROWSER_DATA_DIR, CHAPTER_SYNC_DEBUG_DIR, PUBLISH_DEBUG_DIR
from backend.shared.app.app_runtime_defaults import BROWSER_CHANNEL, VIEWPORT

_CONTEXT_DEBUG_CATEGORY: dict[int, str] = {}
_CONTEXT_DEBUG_ENABLED: dict[int, bool] = {}
_CONTEXT_FAILURE_DEBUG_ENABLED: dict[int, bool] = {}
_CONTEXT_AUTH_STATE_FILE: dict[int, Path] = {}
_CONTEXT_DEBUG_FINGERPRINTS: dict[int, set[str]] = {}
_DEBUG_COUNTER = count(1)


def launch_system_browser(playwright: Any, launch_kwargs: dict[str, Any]):
    configured_channel = (BROWSER_CHANNEL or "").strip()
    channels: list[str] = []
    for channel in (configured_channel, "msedge", "chrome"):
        if channel and channel not in channels:
            channels.append(channel)

    errors: list[str] = []
    for channel in channels:
        kwargs = dict(launch_kwargs)
        kwargs["channel"] = channel
        try:
            return playwright.chromium.launch(**kwargs)
        except Exception as exc:
            errors.append(f"{channel}: {exc}")

    detail = "\n".join(errors)
    raise RuntimeError(
        "浏览器启动失败。当前版本不会下载或使用 Playwright 内置 Chromium。"
        "请确认电脑已安装 Microsoft Edge 或 Google Chrome。"
        + (f"\n{detail}" if detail else "")
    )


def maximize_page_window(page: Page) -> None:
    try:
        session = page.context.new_cdp_session(page)
        window_info = session.send("Browser.getWindowForTarget")
        window_id = window_info.get("windowId")
        if window_id is not None:
            session.send("Browser.setWindowBounds", {"windowId": window_id, "bounds": {"windowState": "maximized"}})
    except Exception:

        pass


def make_context(headless: bool = False, *, debug_category: str = "chapter_sync", debug_enabled: bool | None = None, failure_debug_enabled: bool | None = None, auth_state_path: str | Path | None = None):
    if sync_playwright is None:
        raise RuntimeError("缺少依赖：playwright。请先执行：pip install -r requirements.txt") from _PLAYWRIGHT_IMPORT_ERROR

    p = sync_playwright().start()
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ],
    }

    context_kwargs: dict[str, Any] = {}
    if headless:
        context_kwargs["viewport"] = VIEWPORT
    else:
        context_kwargs["no_viewport"] = True
    auth_state_file = resolve_auth_state_file(auth_state_path)
    if auth_state_file.exists():
        context_kwargs["storage_state"] = str(auth_state_file)

    try:
        browser = launch_system_browser(p, launch_kwargs)
        context = browser.new_context(**context_kwargs)
    except Exception as e:
        p.stop()
        raise RuntimeError(
            "浏览器启动失败。当前版本默认使用系统 Microsoft Edge 或 Google Chrome，不再下载 Playwright Chromium；如果浏览器被占用，请先关闭自动化打开的窗口后重试。"
        ) from e

    _CONTEXT_DEBUG_CATEGORY[id(context)] = debug_category or "chapter_sync"
    _CONTEXT_AUTH_STATE_FILE[id(context)] = auth_state_file
    if debug_enabled is not None:
        _CONTEXT_DEBUG_ENABLED[id(context)] = bool(debug_enabled)
    if failure_debug_enabled is not None:
        _CONTEXT_FAILURE_DEBUG_ENABLED[id(context)] = bool(failure_debug_enabled)
    page = context.pages[0] if context.pages else context.new_page()
    if not headless:
        maximize_page_window(page)
        try:
            page.wait_for_timeout(300)
        except Exception:
            pass
    return p, context, page


def close_context(p, context, *, save_state: bool = True) -> None:
    try:
        if save_state:
            auth_state_file = _CONTEXT_AUTH_STATE_FILE.get(id(context), active_auth_state_file())
            auth_state_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                context.storage_state(path=str(auth_state_file), indexed_db=True)
            except TypeError:
                context.storage_state(path=str(auth_state_file))
    except Exception:
        pass
    context_id = id(context)
    _CONTEXT_DEBUG_CATEGORY.pop(context_id, None)
    _CONTEXT_DEBUG_ENABLED.pop(context_id, None)
    _CONTEXT_FAILURE_DEBUG_ENABLED.pop(context_id, None)
    _CONTEXT_AUTH_STATE_FILE.pop(context_id, None)
    _CONTEXT_DEBUG_FINGERPRINTS.pop(context_id, None)
    try:
        browser = context.browser
    except Exception:
        browser = None
    try:
        context.close()
    except Exception:
        pass
    try:
        if browser is not None:
            browser.close()
    except Exception:
        pass
    try:
        p.stop()
    except Exception:
        pass


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
            from backend.shared.app.app_config import load_config

            section = load_config().get("auto_publish", {})
            if isinstance(section, dict):
                return bool(section.get("debugScreenshots", True))
        except Exception:
            return True

    return False


def _debug_dir(category: str):
    return PUBLISH_DEBUG_DIR if category == "auto_publish" else CHAPTER_SYNC_DEBUG_DIR


def _safe_debug_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(name or "page"))
    return cleaned.strip("_")[:80] or "page"


def _debug_dedupe_enabled(category: str) -> bool:
    if category == "auto_publish":
        try:
            from backend.shared.app.app_config import load_config

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


import json
import re as _account_re
from pathlib import Path as _AccountPath

from backend.shared.app.app_paths import FANQIE_ACCOUNTS_FILE, FANQIE_ACCOUNT_STATES_DIR, FANQIE_AUTH_STATE_FILE

_DEFAULT_ACCOUNT_ID = "default"
_DEFAULT_ACCOUNT_NAME = "默认账号"


def list_accounts() -> dict[str, Any]:
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id not in {item["id"] for item in accounts}:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    return {"ok": True, "activeId": active_id, "accounts": [_public_account(item, active_id=active_id) for item in accounts]}


def add_account(name: str) -> dict[str, Any]:
    display_name = str(name or "").strip() or f"账号{time.strftime('%m%d%H%M')}"
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    if display_name in {item["name"] for item in accounts}:
        return {"ok": False, "message": "账号名称已存在。", **list_accounts()}
    account_id = _new_account_id(display_name, accounts)
    accounts.append({"id": account_id, "name": display_name, "state_file": str(_state_file_for(account_id))})
    data["accounts"] = accounts
    data["active_id"] = account_id
    _save_accounts(data)
    return {"ok": True, "message": f"已添加并切换到账号：{display_name}", **list_accounts()}


def switch_account(account_id: str) -> dict[str, Any]:
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    target = next((item for item in accounts if item["id"] == account_id), None)
    if target is None:
        return {"ok": False, "message": "账号不存在。", **list_accounts()}
    data["accounts"] = accounts
    data["active_id"] = account_id
    _save_accounts(data)
    return {"ok": True, "message": f"已切换到账号：{target['name']}", **list_accounts()}


def delete_account(account_id: str) -> dict[str, Any]:
    if account_id == _DEFAULT_ACCOUNT_ID:
        return {"ok": False, "message": "默认账号不能删除。", **list_accounts()}
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    target = next((item for item in accounts if item["id"] == account_id), None)
    if target is None:
        return {"ok": False, "message": "账号不存在。", **list_accounts()}
    accounts = [item for item in accounts if item["id"] != account_id]
    try:
        _state_file_for(account_id).unlink(missing_ok=True)
    except Exception:
        pass
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id == account_id:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    data["accounts"] = accounts
    data["active_id"] = active_id
    _save_accounts(data)
    return {"ok": True, "message": f"已删除账号：{target['name']}", **list_accounts()}


def resolve_auth_state_file(path: str | Path | None = None) -> _AccountPath:
    raw = str(path or "").strip()
    if not raw:
        return FANQIE_AUTH_STATE_FILE
    target = _AccountPath(raw).expanduser()
    if target.exists() and target.is_dir():
        return target / "state.json"
    if not target.suffix:
        return target / "state.json"
    return target


def active_auth_state_file() -> _AccountPath:
    return FANQIE_AUTH_STATE_FILE


def _load_accounts() -> dict[str, Any]:
    if FANQIE_ACCOUNTS_FILE.exists():
        try:
            data = json.loads(FANQIE_ACCOUNTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"active_id": _DEFAULT_ACCOUNT_ID, "accounts": [_default_account()]}


def _save_accounts(data: dict[str, Any]) -> None:
    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    FANQIE_ACCOUNT_STATES_DIR.mkdir(parents=True, exist_ok=True)
    accounts = _normalize_accounts(data.get("accounts"))
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id not in {item["id"] for item in accounts}:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    FANQIE_ACCOUNTS_FILE.write_text(json.dumps({"active_id": active_id, "accounts": accounts}, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_accounts(raw: Any) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not account_id or not name or account_id in seen:
            continue
        state_file = str(item.get("state_file") or (_state_file_for(account_id) if account_id != _DEFAULT_ACCOUNT_ID else FANQIE_AUTH_STATE_FILE))
        accounts.append({"id": account_id, "name": name, "state_file": state_file})
        seen.add(account_id)
    if _DEFAULT_ACCOUNT_ID not in seen:
        accounts.insert(0, _default_account())
    return accounts


def _default_account() -> dict[str, str]:
    return {"id": _DEFAULT_ACCOUNT_ID, "name": _DEFAULT_ACCOUNT_NAME, "state_file": str(FANQIE_AUTH_STATE_FILE)}


def _public_account(item: dict[str, str], *, active_id: str) -> dict[str, Any]:
    state_file = _AccountPath(item.get("state_file") or "")
    return {"id": item["id"], "name": item["name"], "active": item["id"] == active_id, "loggedIn": state_file.exists(), "stateFile": str(state_file)}


def _state_file_for(account_id: str) -> _AccountPath:
    if account_id == _DEFAULT_ACCOUNT_ID:
        return FANQIE_AUTH_STATE_FILE
    FANQIE_ACCOUNT_STATES_DIR.mkdir(parents=True, exist_ok=True)
    safe = _account_re.sub(r"[^0-9A-Za-z_\-]+", "_", account_id).strip("_") or str(int(time.time()))
    return FANQIE_ACCOUNT_STATES_DIR / f"{safe}.json"


def _new_account_id(name: str, accounts: list[dict[str, str]]) -> str:
    base = _account_re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_\-]+", "_", name).strip("_") or "account"
    existing = {item["id"] for item in accounts}
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
