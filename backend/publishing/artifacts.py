from __future__ import annotations

from datetime import datetime
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from backend.publishing.local_source import Chapter
from backend.novel.text_cleaning import normalize_novel_body
from backend.paths import PUBLISHING_DEBUG_DIR, PUBLISHING_TRACKER_DIR
from backend.subprocesses import run as run_subprocess


def clean_previous_publish_artifacts(*, log: Callable[[str], None]) -> None:
    cleaned: list[str] = []
    for directory, label in (
        (PUBLISHING_DEBUG_DIR, "调试截图"),
        (PUBLISHING_TRACKER_DIR, "Git追踪"),
    ):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except FileNotFoundError:
                        pass
            cleaned.append(label)
        except Exception as exc:
            log(f"启动清理{label}失败：{exc}")
    if cleaned:
        log(f"启动时已清理上次番茄发布数据：{'、'.join(cleaned)}。")


def track_publish_chapter(chapter_no: int, local: Chapter, *, enabled: bool, log: Callable[[str], None]) -> Path | None:
    if not enabled:
        return None
    directory = _write_publish_snapshot(chapter_no, local)
    commit_id = _commit_publish_snapshot(PUBLISHING_TRACKER_DIR, chapter_no)
    log(f"Git：已记录发文章节 {commit_id}" if commit_id else "Git：未检测到 Git 或无需新增提交")
    log(f"Git追踪目录：{directory}")
    return directory


def _write_publish_snapshot(chapter_no: int, local: Chapter) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    directory = PUBLISHING_TRACKER_DIR / "chapters" / f"chapter_{chapter_no:03d}" / ts
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "local.txt").write_text(f"标题：{local.subtitle}\n完整标题：{local.full_title}\n\n{normalize_novel_body(local.content)}\n", encoding="utf-8")
    (directory / "meta.txt").write_text(
        "\n".join([
            f"chapter_no={chapter_no}",
            f"time={datetime.now().isoformat(timespec='seconds')}",
            f"title={local.subtitle}",
            f"full_title={local.full_title}",
            "",
        ]),
        encoding="utf-8",
    )
    return directory


def _commit_publish_snapshot(repo: Path, chapter_no: int) -> str:
    if shutil.which("git") is None:
        return ""
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        run_subprocess(["git", "init"], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace")
        _run_git(repo, ["config", "user.name", "fanqie_assistant"])
        _run_git(repo, ["config", "user.email", "fanqie_assistant@local"])
        _run_git(repo, ["config", "core.quotepath", "false"])
    _run_git(repo, ["add", "chapters"])
    changed = _run_git(repo, ["diff", "--cached", "--quiet"])
    if changed.returncode != 1:
        return _latest_commit(repo)
    commit = _run_git(repo, ["commit", "-m", f"publish chapter {chapter_no:03d} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
    if commit.returncode != 0:
        return _latest_commit(repo)
    return _latest_commit(repo)


def _run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess:
    return run_subprocess(["git", *args], cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace")


def _latest_commit(repo: Path) -> str:
    result = _run_git(repo, ["rev-parse", "--short", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else ""
