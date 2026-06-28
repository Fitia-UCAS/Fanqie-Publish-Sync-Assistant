from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.shared.app.app_logging import get_logger
from backend.shared.app.app_paths import get_state_paths

LOGGER = get_logger(__name__)

SUPPORTED_TEXT_SUFFIXES = {".txt", ".md"}
SUPPORTED_SAVE_SUFFIXES = SUPPORTED_TEXT_SUFFIXES | {".json"}


def open_path(path_key: str) -> bool:
    try:
        target = _resolve_path(path_key)
        if target is None:
            return False
        if target.exists() and target.is_file():
            target = target.parent
        elif target.suffix and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target = target.parent
        else:
            target.mkdir(parents=True, exist_ok=True)
        _open_system(target)
        return True
    except Exception:
        LOGGER.exception("Open path failed: %s", path_key)
        return False


def open_file(path_key: str, *, create: bool = False) -> bool:
    try:
        target = _resolve_path(path_key)
        if target is None:
            return False
        if create and target.suffix and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        elif target.suffix and not target.exists():
            return False
        elif not target.suffix:
            target.mkdir(parents=True, exist_ok=True)
        _open_system(target)
        return True
    except Exception:
        LOGGER.exception("Open file failed: %s", path_key)
        return False


def _resolve_path(path_key: str) -> Path | None:
    paths = get_state_paths()
    raw = str(path_key or "").strip()
    if not raw:
        return None
    return Path(paths.get(raw, raw)).expanduser()


def _open_system(target: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(target))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])


def open_native_dialog(window: Any, *, save: bool, folder: bool, save_filename: str = "output.txt", allow_multiple: bool = False) -> str:
    if window is None:
        return ""
    try:
        import webview

        if folder:
            result = window.create_file_dialog(_file_dialog_type(webview, "FOLDER"))
        elif save:
            result = window.create_file_dialog(
                _file_dialog_type(webview, "SAVE"),
                save_filename=save_filename or "output.txt",
                file_types=_dialog_file_types(save_filename),
            )
        else:
            result = window.create_file_dialog(
                _file_dialog_type(webview, "OPEN"),
                allow_multiple=allow_multiple,
                file_types=_dialog_file_types(save_filename),
            )
    except Exception:
        LOGGER.exception("Native file dialog failed")
        return ""

    normalized = _normalize_dialog_result(result, keep_multiple=allow_multiple)
    if save and normalized:
        normalized = _ensure_save_file_path(normalized, save_filename)
        try:
            target = Path(normalized).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.suffix.lower() != ".json":
                target.touch(exist_ok=True)
        except Exception:
            LOGGER.exception("Create selected file failed: %s", normalized)
    return normalized


def _dialog_file_types(save_filename: str = "") -> tuple[str, ...]:
    suffix = Path(save_filename or "").suffix.lower()
    if suffix == ".json":
        return ("All files (*.*)", "JSON files (*.json)")
    if suffix == ".md":
        return ("Markdown files (*.md)", "Text files (*.txt)", "All files (*.*)")
    return ("Text files (*.txt)", "Markdown files (*.md)", "All files (*.*)")


def _ensure_text_file_path(path: str, save_filename: str = "output.txt") -> str:
    target = Path(path).expanduser()
    if target.suffix.lower() in SUPPORTED_TEXT_SUFFIXES:
        return str(target)

    default_suffix = Path(save_filename or "").suffix.lower()
    if default_suffix not in SUPPORTED_TEXT_SUFFIXES:
        default_suffix = ".txt"

    return str(target.with_suffix(default_suffix))


def _ensure_save_file_path(path: str, save_filename: str = "output.txt") -> str:
    target = Path(path).expanduser()
    if target.suffix:
        return str(target)
    default_suffix = Path(save_filename or "").suffix.lower()
    if default_suffix not in SUPPORTED_SAVE_SUFFIXES:
        default_suffix = ".txt"
    return str(target.with_suffix(default_suffix))


def _file_dialog_type(webview: Any, name: str) -> Any:
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog is not None and hasattr(file_dialog, name):
        return getattr(file_dialog, name)
    return getattr(webview, f"{name}_DIALOG")


def _normalize_dialog_result(result: Any, *, keep_multiple: bool = False) -> str:
    if isinstance(result, (list, tuple)):
        if not result:
            return ""
        if keep_multiple:
            return "\n".join(str(item) for item in result if item)
        return str(result[0])
    return str(result or "")



def open_source_dialog(window: Any, *, current_path: str = "") -> str:
    # Keep Fanqie source selection on the same stable native pywebview path as
    # the working novel-processing page. pywebview supports folder dialogs, but
    # file and folder selection are separate dialog modes; for this single
    # compact button we use multi-file selection so each chapter can be a file.
    return open_native_dialog(window, save=False, folder=False, save_filename="novel.md", allow_multiple=True)


def open_login_state_dialog(window: Any, *, current_path: str = "") -> str:
    # Login state is an input path: choosing an existing state file must read it,
    # not open a save dialog or ask whether to replace it. New state files are
    # created by the login flow when no custom state file is selected.
    return open_native_dialog(window, save=False, folder=False, save_filename="state.json")


def _open_subprocess_path_picker(*, mode: str, current_path: str = "") -> str | None:
    """Open the file/folder picker in a child Python process.

    pywebview API calls do not always run on the GUI main thread. Running Tk
    directly inside that callback can trigger Tcl cleanup errors or force the
    picker to fall back to a folder-only dialog. A child process gives Tk its
    own main thread while keeping the main UI clean.
    """

    project_root = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-c",
        "from backend.api.desktop_api import _subprocess_picker_main; raise SystemExit(_subprocess_picker_main())",
        mode,
        str(current_path or ""),
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    popen_factory = getattr(subprocess, "_fanqie_original_popen", subprocess.Popen)
    popen_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        process = popen_factory(
            command,
            cwd=str(project_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **popen_kwargs,
        )
        stdout, stderr = process.communicate()
    except Exception:
        LOGGER.exception("Path picker subprocess failed: %s", mode)
        return None

    if process.returncode not in (0, None):
        LOGGER.warning("Path picker exited with %s: %s", process.returncode, (stderr or "").strip())
        return None
    return (stdout or "").strip().splitlines()[-1] if (stdout or "").strip() else ""

SOURCE_SUFFIXES = {".txt", ".md"}
LOGIN_STATE_SUFFIXES = {".json"}


def _subprocess_picker_main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return 2
    mode = args[0]
    current_path = args[1] if len(args) > 1 else ""
    if mode not in {"source", "login_state"}:
        return 2
    try:
        result = _open_tk_native_picker(mode=mode, current_path=current_path)
    except Exception as exc:
        print(f"选择器打开失败：{exc}", file=sys.stderr)
        return 1
    if result:
        print(result)
    return 0


def _normalize_picker_start(raw: str) -> Path:
    path = Path(raw or "").expanduser()
    if path.is_file():
        path = path.parent
    if not path.exists() or not path.is_dir():
        path = Path.home()
    return path


def _open_tk_native_picker(*, mode: str, current_path: str = "") -> str:
    """Open native-looking Tk file/folder dialogs from the child process.

    The main pywebview callback may not run on Tk's main loop thread, so the
    caller starts this function in a subprocess. We still use Tk's standard
    file dialogs here, instead of the previous custom file tree, so the picker
    looks like the system dialog and can choose both files and directories via a
    small launcher.
    """

    import tkinter as tk
    from tkinter import filedialog, ttk

    start = _normalize_picker_start(current_path)
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update_idletasks()
        root.after(200, lambda: root.attributes("-topmost", False))
    except Exception:
        pass

    try:
        action = _ask_picker_action(root, mode=mode)
        if not action or action == "default":
            return ""
        if mode == "source" and action == "file":
            return str(
                filedialog.askopenfilename(
                    parent=root,
                    title="选择小说文件",
                    initialdir=str(start),
                    filetypes=(
                        ("小说文件", "*.txt *.md"),
                        ("Text files", "*.txt"),
                        ("Markdown files", "*.md"),
                        ("All files", "*.*"),
                    ),
                )
                or ""
            )
        if mode == "source" and action == "folder":
            return str(
                filedialog.askdirectory(
                    parent=root,
                    title="选择章节文件夹",
                    initialdir=str(start),
                    mustexist=True,
                )
                or ""
            )
        if mode == "login_state" and action == "file":
            return str(
                filedialog.askopenfilename(
                    parent=root,
                    title="选择登录状态文件",
                    initialdir=str(start),
                    filetypes=(("所有文件", "*.*"), ("JSON 登录状态", "*.json")),
                )
                or ""
            )
        if mode == "login_state" and action == "folder":
            return str(
                filedialog.askdirectory(
                    parent=root,
                    title="选择登录状态目录",
                    initialdir=str(start),
                    mustexist=False,
                )
                or ""
            )
        return ""
    finally:
        try:
            root.destroy()
        except Exception:
            pass


def _ask_picker_action(root: Any, *, mode: str) -> str:
    import tkinter as tk
    from tkinter import ttk

    selected = {"value": ""}
    title = "选择登录状态" if mode == "login_state" else "选择小说来源"
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=(18, 16, 18, 14))
    frame.pack(fill="both", expand=True)

    if mode == "login_state":
        hint = "选择已有 state.json，或选择一个目录用于保存新的 state.json。"
        actions = [
            ("选择 state.json", "file"),
            ("选择状态目录", "folder"),
            ("使用默认", "default"),
        ]
    else:
        hint = "选择整本小说文件，或选择每章一个文件的章节文件夹。"
        actions = [
            ("选择小说文件", "file"),
            ("选择章节文件夹", "folder"),
        ]

    label = ttk.Label(frame, text=hint, anchor="w", justify="left")
    label.pack(fill="x", pady=(0, 12))

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def finish(value: str) -> None:
        selected["value"] = value
        dialog.destroy()

    for text, value in actions:
        ttk.Button(buttons, text=text, command=lambda value=value: finish(value)).pack(side="left", padx=(0, 8))
    ttk.Button(buttons, text="取消", command=lambda: finish("")).pack(side="right")

    dialog.update_idletasks()
    width = max(dialog.winfo_width(), 420)
    height = max(dialog.winfo_height(), 118)
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    try:
        dialog.lift()
        dialog.attributes("-topmost", True)
        dialog.after(250, lambda: dialog.attributes("-topmost", False))
    except Exception:
        pass

    dialog.protocol("WM_DELETE_WINDOW", lambda: finish(""))
    dialog.wait_window()
    return selected["value"]
