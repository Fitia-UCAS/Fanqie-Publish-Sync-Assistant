from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any

try:
    import webview
except Exception as exc:  # pragma: no cover - depends on local desktop env
    raise SystemExit("缺少依赖：pywebview。请先执行：pip install -r requirements.txt") from exc

from backend.api.webview import WebviewRouter
from backend.data_reset import reset_runtime_data
from backend.log_setup import setup_logging
from backend.paths import ensure_data_directories

WINDOW_TITLE = "番茄发布与同步助手"
WINDOW_MIN_SIZE = (1180, 760)


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


def create_app_window(html_path: str, api: WebviewRouter) -> Any:
    """Create the pywebview window with compatibility for older pywebview builds.

    Some local pywebview versions do not accept optional keyword arguments such as
    ``icon``. Keep the app launchable first, then quietly drop unsupported options.
    """
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
            return webview.create_window(WINDOW_TITLE, html_path, **options)
        except TypeError as exc:
            message = str(exc)
            unsupported = next((key for key in ("icon", "text_select", "min_size") if key in options and key in message), None)
            if unsupported is None:
                raise
            options.pop(unsupported, None)


def main() -> None:
    hide_child_console_windows()
    reset_runtime_data(preserve_auth_state=True)
    ensure_data_directories()
    setup_logging()
    base_dir = Path(__file__).resolve().parent
    html_path = "file://" + str(base_dir / "frontend" / "index.html").replace(os.sep, "/")
    api = WebviewRouter()
    window = create_app_window(html_path, api)
    api.bind_window(window)
    webview.start(maximize_window, window)


if __name__ == "__main__":
    main()
