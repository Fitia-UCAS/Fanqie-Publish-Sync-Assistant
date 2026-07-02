from __future__ import annotations
import shutil
import subprocess
import time
from pathlib import Path

from backend.paths import SYNCING_HISTORY_DIR
from backend.novel.text_cleaning import normalize_novel_body


def git_available() -> bool:
    return shutil.which("git") is not None


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def ensure_repo(repo: Path) -> bool:
    if not git_available():
        return False
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace")
        run_git(repo, ["config", "user.name", "novel_sync"])
        run_git(repo, ["config", "user.email", "novel_sync@local"])
        run_git(repo, ["config", "core.quotepath", "false"])
        (repo / ".gitignore").write_text("", encoding="utf-8")
    return True


def repo_for_chapter(chapter_no: int) -> Path:
    return SYNCING_HISTORY_DIR


def latest_commit(repo: Path) -> str:
    result = run_git(repo, ["rev-parse", "--short", "HEAD"])
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def track_snapshot(chapter_no: int, local_title: str, local_body: str, remote_title: str, remote_body: str) -> tuple[bool, Path, str]:
    repo = repo_for_chapter(chapter_no)
    if not ensure_repo(repo):
        return False, repo, ""

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    chapter_dir = repo / "chapters" / f"chapter_{chapter_no:03d}"
    chapter_dir.mkdir(parents=True, exist_ok=True)
    (chapter_dir / "local.txt").write_text(f"标题：{local_title}\n\n{normalize_novel_body(local_body)}\n", encoding="utf-8")
    (chapter_dir / "remote.txt").write_text(f"标题：{remote_title}\n\n{normalize_novel_body(remote_body)}\n", encoding="utf-8")
    (chapter_dir / "meta.txt").write_text(
        "\n".join([
            f"chapter_no={chapter_no}",
            f"time={ts}",
            f"local_title={local_title}",
            f"remote_title={remote_title}",
            "",
        ]),
        encoding="utf-8",
    )

    run_git(repo, ["add", "chapters", ".gitignore"])
    result = run_git(repo, ["diff", "--cached", "--quiet"])
    if result.returncode != 1:
        return False, repo, latest_commit(repo)
    msg = f"track chapter {chapter_no:03d} {time.strftime('%Y-%m-%d %H:%M:%S')}"
    commit = run_git(repo, ["commit", "-m", msg])
    if commit.returncode != 0:
        return False, repo, latest_commit(repo)
    return True, repo, latest_commit(repo)
