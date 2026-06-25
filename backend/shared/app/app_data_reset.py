from __future__ import annotations


import logging
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

from backend.shared.app.app_logging import get_logger
from backend.shared.app.app_paths import (
    APP_SYSTEM_DIR,
    BROWSER_DATA_DIR,
    CHAPTER_SYNC_DIR,
    CHARACTER_MATERIAL_DIR,
    DATA_DIR,
    FANQIE_AUTH_STATE_FILE,
    LEGACY_COMMON_DIR,
    PROCESS_NOVEL_DIR,
    PUBLISH_DIR,
    ROOT_DIR,
    WEB_CRAWLER_DIR,
    ensure_data_directories,
)

LOGGER = get_logger(__name__)


RUNTIME_DATA_DIRS: tuple[Path, ...] = (
    APP_SYSTEM_DIR,
    PROCESS_NOVEL_DIR,
    WEB_CRAWLER_DIR,
    CHARACTER_MATERIAL_DIR,
    PUBLISH_DIR,
    CHAPTER_SYNC_DIR,
    LEGACY_COMMON_DIR,
)

_WINDOWS_DELETE_RETRY_COUNT = 3
_WINDOWS_DELETE_RETRY_DELAY_SECONDS = 0.2
_PROJECT_PERMISSION_REPAIRED = False


def reset_login_state() -> dict[str, Any]:
    removed: list[str] = []
    errors: list[str] = []
    _repair_project_permissions_once()
    targets = [FANQIE_AUTH_STATE_FILE, BROWSER_DATA_DIR / "browser_edge_profile"]
    for target in targets:
        _remove_path(target, removed=removed, errors=errors)
    ensure_data_directories()
    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "message": "已清除本地登录授权；下次发布/同步会重新扫码登录。" if not errors else "部分登录授权文件清理失败。",
    }


def reset_runtime_data(*, preserve_auth_state: bool = True) -> dict[str, Any]:
    logging.shutdown()
    _repair_project_permissions_once()

    auth_bytes: bytes | None = None
    if preserve_auth_state and FANQIE_AUTH_STATE_FILE.exists():
        try:
            auth_bytes = FANQIE_AUTH_STATE_FILE.read_bytes()
        except Exception:
            LOGGER.debug("Unable to snapshot auth state before runtime data reset", exc_info=True)

    removed: list[str] = []
    errors: list[str] = []
    for directory in RUNTIME_DATA_DIRS:
        _remove_path(directory, removed=removed, errors=errors)

    if BROWSER_DATA_DIR.exists():
        for child in list(BROWSER_DATA_DIR.iterdir()):
            if preserve_auth_state and _same_path(child, FANQIE_AUTH_STATE_FILE):
                continue
            _remove_path(child, removed=removed, errors=errors)

    ensure_data_directories()
    if preserve_auth_state and auth_bytes is not None:
        try:
            FANQIE_AUTH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            FANQIE_AUTH_STATE_FILE.write_bytes(auth_bytes)
        except Exception as exc:
            LOGGER.exception("Restore auth state failed")
            errors.append(f"{FANQIE_AUTH_STATE_FILE}: {exc}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    gitkeep = DATA_DIR / ".gitkeep"
    if not gitkeep.exists():
        try:
            gitkeep.touch()
        except Exception:
            LOGGER.debug("Unable to create data/.gitkeep", exc_info=True)

    return {
        "ok": not errors,
        "removed": removed,
        "errors": errors,
        "preservedAuthState": bool(preserve_auth_state and FANQIE_AUTH_STATE_FILE.exists()),
        "message": "已重建 data 运行目录；界面配置和番茄登录态已保留。" if not errors else "部分 data 运行目录清理失败。",
    }


def reset_app_data(*, preserve_auth_state: bool = True) -> dict[str, Any]:
    return reset_runtime_data(preserve_auth_state=preserve_auth_state)


def _remove_path(path: Path, *, removed: list[str], errors: list[str]) -> None:
    if not path.exists():
        return

    _make_tree_writable(path)

    last_exc: Exception | None = None
    for attempt in range(_WINDOWS_DELETE_RETRY_COUNT):
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=False, onerror=_handle_remove_error)
            else:
                _make_writable(path)
                path.unlink()
            removed.append(str(path))
            return
        except Exception as exc:
            last_exc = exc
            _make_tree_writable(path)
            if attempt < _WINDOWS_DELETE_RETRY_COUNT - 1:
                time.sleep(_WINDOWS_DELETE_RETRY_DELAY_SECONDS)

    if last_exc is not None:
        LOGGER.exception("Reset runtime data failed: %s", path, exc_info=last_exc)
        errors.append(f"{path}: {last_exc}")


def _handle_remove_error(func: Callable[[str], None], path: str, exc_info: Any) -> None:
    failed_path = Path(path)
    _make_writable(failed_path)
    _grant_current_user_full_control(failed_path)
    func(path)


def _repair_project_permissions_once() -> None:
    global _PROJECT_PERMISSION_REPAIRED
    if _PROJECT_PERMISSION_REPAIRED:
        return
    _PROJECT_PERMISSION_REPAIRED = True

    _make_tree_writable(ROOT_DIR)
    _grant_current_user_full_control(ROOT_DIR)


def _make_tree_writable(path: Path) -> None:
    if not path.exists():
        return
    _make_writable(path)
    if not path.is_dir():
        return

    _clear_windows_attributes(path)

    try:
        for root, dirs, files in os.walk(path):
            root_path = Path(root)
            _make_writable(root_path)
            for name in dirs:
                _make_writable(root_path / name)
            for name in files:
                _make_writable(root_path / name)
    except Exception:
        LOGGER.debug("Unable to make tree writable: %s", path, exc_info=True)


def _make_writable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
    except Exception:
        LOGGER.debug("Unable to chmod writable: %s", path, exc_info=True)


def _clear_windows_attributes(path: Path) -> None:
    if os.name != "nt":
        return
    try:
        subprocess.run(
            ["attrib", "-R", "-S", "-H", str(path / "*"), "/S", "/D"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        subprocess.run(
            ["attrib", "-R", "-S", "-H", str(path)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except Exception:
        LOGGER.debug("Unable to clear Windows attributes: %s", path, exc_info=True)


def _grant_current_user_full_control(path: Path) -> None:
    if os.name != "nt" or not path.exists():
        return

    username = os.environ.get("USERNAME")
    userdomain = os.environ.get("USERDOMAIN")
    account = f"{userdomain}\\{username}" if userdomain and username else username
    if not account:
        return

    try:
        subprocess.run(
            ["icacls", str(path), "/grant", f"{account}:(OI)(CI)F", "/T", "/C", "/Q"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
    except Exception:
        LOGGER.debug("Unable to grant current user full control: %s", path, exc_info=True)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except Exception:
        return str(left) == str(right)


