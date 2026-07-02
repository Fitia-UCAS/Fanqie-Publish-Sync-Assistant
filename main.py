from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any

from backend.api.webview import WebviewRouter
from backend.data_reset import reset_runtime_data
from backend.log_setup import setup_logging
from backend.paths import ensure_data_directories

WINDOW_TITLE = "番茄发布与同步助手"
WINDOW_MIN_SIZE = (1180, 760)
FRONTEND_VARIANTS = {"release", "personal"}
DEFAULT_FRONTEND_VARIANT = "personal"


def hide_child_console_windows() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.kernel32.SetConsoleTitleW("番茄发布与同步助手")
    except Exception:
        return


def get_window_options() -> dict[str, Any]:
    base_dir = Path(__file__).resolve().parent
    icon_path = base_dir / "logo.ico"
    options: dict[str, Any] = {}
    if icon_path.exists():
        options["icon"] = str(icon_path)
    return options


def maximize_window(window: Any) -> None:
    try:
        window.maximize()
    except Exception:
        return


def load_webview() -> Any:
    try:
        import webview
    except Exception as exc:  # pragma: no cover
        raise SystemExit("缺少依赖：pywebview。请先执行：pip install -r requirements.txt") from exc
    return webview


def create_app_window(html_path: str, api: WebviewRouter) -> Any:
    """Create the pywebview window with compatibility for older pywebview builds.

    Some local pywebview versions do not accept optional keyword arguments such as
    ``icon``. Keep the app launchable first, then quietly drop unsupported options.
    """
    webview_module = load_webview()
    options: dict[str, Any] = {
        "js_api": api,
        "fullscreen": False,
        "resizable": True,
        "min_size": WINDOW_MIN_SIZE,
        "text_select": True,
    }
    options.update(get_window_options())

    while True:
        try:
            return webview_module.create_window(WINDOW_TITLE, html_path, **options)
        except TypeError as exc:
            message = str(exc)
            unsupported = next((key for key in ("icon", "text_select", "min_size") if key in options and key in message), None)
            if unsupported is None:
                raise
            options.pop(unsupported, None)


def select_frontend_variant() -> str:
    requested = os.environ.get("FANQIE_FRONTEND_VARIANT") or os.environ.get("FANQIE_FRONTEND") or DEFAULT_FRONTEND_VARIANT
    normalized = requested.strip().lower()
    return normalized if normalized in FRONTEND_VARIANTS else DEFAULT_FRONTEND_VARIANT


def frontend_index_path(base_dir: Path, variant: str | None = None) -> Path:
    selected = variant or select_frontend_variant()
    path = base_dir / "frontend" / selected / "index.html"
    if path.exists():
        return path
    legacy = base_dir / "frontend" / "index.html"
    if legacy.exists():
        return legacy
    raise FileNotFoundError(f"未找到前端入口：{path}")


def main() -> None:
    hide_child_console_windows()
    reset_runtime_data(preserve_auth_state=True)
    ensure_data_directories()
    setup_logging()
    base_dir = Path(__file__).resolve().parent
    html_path = "file://" + str(frontend_index_path(base_dir)).replace(os.sep, "/")
    api = WebviewRouter()
    window = create_app_window(html_path, api)
    api.bind_window(window)
    load_webview().start(maximize_window, window)


if __name__ == "__main__":
    main()
