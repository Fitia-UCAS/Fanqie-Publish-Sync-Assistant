from __future__ import annotations


import os
import subprocess
import sys
import ctypes
from pathlib import Path
from typing import NamedTuple

try:
    import webview
except Exception as exc:
    raise SystemExit("缺少依赖：pywebview。请先执行：pip install -r requirements.txt") from exc

from backend.shared.app.app_data_reset import reset_runtime_data
from backend.shared.app.app_logging import setup_logging
from backend.shared.app.app_paths import ensure_data_directories
from backend.api.webview_api import WebviewApi

WINDOW_MIN_SIZE = (1024, 700)
WINDOW_TITLE = "番茄发布同步助手"


def hide_child_console_windows() -> None:
    if sys.platform != "win32":
        return

    original_popen = subprocess.Popen
    subprocess._fanqie_original_popen = original_popen

    def hidden_popen(*args, **kwargs):
        startupinfo = kwargs.get("startupinfo") or subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return original_popen(*args, **kwargs)

    subprocess.Popen = hidden_popen



class WorkArea(NamedTuple):
    left: int
    top: int
    width: int
    height: int



def apply_native_window_icon() -> None:
    if sys.platform != "win32":
        return

    icon_path = Path(__file__).resolve().parent / "logo.ico"
    if not icon_path.exists():
        return

    try:
        user32 = ctypes.windll.user32
        image_icon = 1
        load_from_file = 0x00000010
        default_size = 0x00000040
        wm_seticon = 0x0080
        icon_small = 0
        icon_big = 1

        hicon = user32.LoadImageW(None, str(icon_path), image_icon, 0, 0, load_from_file | default_size)
        if not hicon:
            return

        hwnds: list[int] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_windows(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value == WINDOW_TITLE:
                    hwnds.append(int(hwnd))
            return True

        user32.EnumWindows(enum_windows, 0)
        for hwnd in hwnds:
            user32.SendMessageW(hwnd, wm_seticon, icon_small, hicon)
            user32.SendMessageW(hwnd, wm_seticon, icon_big, hicon)
    except Exception:
        pass


def get_primary_work_area() -> WorkArea | None:
    if sys.platform == "win32":
        try:
            import ctypes

            class Rect(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            rect = Rect()
            user32 = ctypes.windll.user32
            if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                return WorkArea(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
            return WorkArea(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        except Exception:
            return None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        area = WorkArea(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())
        root.destroy()
        return area
    except Exception:
        return None


def get_window_options() -> dict[str, int]:
    area = get_primary_work_area()
    if not area or area.width <= 0 or area.height <= 0:
        return {"width": 1220, "height": 840}
    return {"width": area.width, "height": area.height, "x": area.left, "y": area.top}


def maximize_window(window: object) -> None:
    try:
        window.maximize()
    except Exception:
        pass
    apply_native_window_icon()


def main() -> None:
    hide_child_console_windows()
    reset_runtime_data(preserve_auth_state=True)
    ensure_data_directories()
    setup_logging()
    base_dir = Path(__file__).resolve().parent
    html_path = "file://" + str(base_dir / "frontend" / "index.html").replace(os.sep, "/")
    api = WebviewApi()
    window = webview.create_window(
        WINDOW_TITLE,
        html_path,
        js_api=api,
        fullscreen=False,
        resizable=True,
        min_size=WINDOW_MIN_SIZE,
        text_select=True,
        **get_window_options(),
    )
    api.bind_window(window)
    webview.start(maximize_window, window)


if __name__ == "__main__":
    main()


