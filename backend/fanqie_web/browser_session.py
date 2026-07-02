from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import Page, sync_playwright
except Exception as exc:
    Page = Any
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR: Exception | None = exc
else:
    _PLAYWRIGHT_IMPORT_ERROR = None

from backend.defaults import BROWSER_CHANNEL, VIEWPORT
from backend.fanqie_web.accounts import (
    active_auth_state_file,
    add_account,
    delete_account,
    list_accounts,
    resolve_auth_state_file,
    switch_account,
)
from backend.fanqie_web.browser_debug import (
    forget_debug_context,
    register_debug_context,
    save_debug,
    save_failure_debug,
)
from backend.paths import BROWSER_DATA_DIR

_CONTEXT_AUTH_STATE_FILE: dict[int, Path] = {}


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

    _CONTEXT_AUTH_STATE_FILE[id(context)] = auth_state_file
    register_debug_context(context, category=debug_category or "chapter_sync", debug_enabled=debug_enabled, failure_debug_enabled=failure_debug_enabled)
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
    _CONTEXT_AUTH_STATE_FILE.pop(context_id, None)
    forget_debug_context(context)
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
