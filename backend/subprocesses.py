from __future__ import annotations

import os
import subprocess
from typing import Any


def windows_no_window_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    for key, value in windows_no_window_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.run(command, **kwargs)


def popen(command: list[str], **kwargs: Any) -> subprocess.Popen:
    for key, value in windows_no_window_kwargs().items():
        kwargs.setdefault(key, value)
    return subprocess.Popen(command, **kwargs)
