from __future__ import annotations
import difflib
import shutil
import subprocess
import time
from pathlib import Path
from backend.paths import SYNCING_COMPARE_DIR
from backend.novel.text_cleaning import normalize_text, normalize_novel_body
def chapter_dir(chapter_no: int) -> Path:
    path = SYNCING_COMPARE_DIR / f"chapter_{chapter_no:03d}"
    path.mkdir(parents=True, exist_ok=True)
    return path
def save_compare_files(chapter_no: int, local_title: str, local_body: str, remote_title: str, remote_body: str) -> tuple[Path, Path]:
    d = chapter_dir(chapter_no)
    local_path = d / "local.txt"
    remote_path = d / "remote.txt"
    local_path.write_text(f"标题：{local_title}\n\n{normalize_novel_body(local_body)}\n", encoding="utf-8")
    remote_path.write_text(f"标题：{remote_title}\n\n{normalize_novel_body(remote_body)}\n", encoding="utf-8")
    return remote_path, local_path
def save_history(chapter_no: int, local_title: str, local_body: str, remote_title: str, remote_body: str) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = chapter_dir(chapter_no) / "history" / ts
    d.mkdir(parents=True, exist_ok=True)
    (d / "local.txt").write_text(f"标题：{local_title}\n\n{normalize_novel_body(local_body)}\n", encoding="utf-8")
    (d / "remote.txt").write_text(f"标题：{remote_title}\n\n{normalize_novel_body(remote_body)}\n", encoding="utf-8")
    return d
def make_git_diff(
    chapter_no: int,
    local_title: str,
    local_body: str,
    remote_title: str,
    remote_body: str,
    direction: str = "local_to_remote",
) -> Path:
    remote_path, local_path = save_compare_files(
        chapter_no=chapter_no,
        local_title=local_title,
        local_body=local_body,
        remote_title=remote_title,
        remote_body=remote_body,
    )
    diff_path = chapter_dir(chapter_no) / "diff.patch"


    if direction == "remote_to_local":
        old_path, new_path = local_path, remote_path
    else:
        old_path, new_path = remote_path, local_path
    git_exe = shutil.which("git")
    if git_exe:
        cmd = [
            git_exe,
            "-c",
            "core.quotepath=false",
            "diff",
            "--no-index",
            "--",
            str(old_path),
            str(new_path),
        ]
        result = subprocess.run(
            cmd,
            cwd=str(SYNCING_COMPARE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        diff_text = result.stdout or result.stderr or ""
        diff_path.write_text(diff_text, encoding="utf-8")
        return diff_path
    old_lines = old_path.read_text(encoding="utf-8").splitlines()
    new_lines = new_path.read_text(encoding="utf-8").splitlines()
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(old_path),
        tofile=str(new_path),
        lineterm="",
    )
    diff_path.write_text("\n".join(diff_lines), encoding="utf-8")
    return diff_path
