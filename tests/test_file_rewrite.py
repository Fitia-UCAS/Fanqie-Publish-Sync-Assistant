from __future__ import annotations

from pathlib import Path
import re

from backend.novel.file_rewrite import update_text_file_in_place


def keep_text(text: str) -> str:
    return text

def replace_text(_text: str) -> str:
    return "新正文"


def test_update_text_file_does_not_backup_when_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    backup_dir = tmp_path / "backups"
    source.write_text("第1章 标题\n\n正文\n", encoding="utf-8")

    result = update_text_file_in_place(source, keep_text, backup_dir=backup_dir)

    assert result.changed is False
    assert result.backup_path is None
    assert not backup_dir.exists()


def test_update_text_file_backs_up_then_overwrites_when_changed(tmp_path: Path) -> None:
    source = tmp_path / "novel.txt"
    backup_dir = tmp_path / "backups"
    source.write_text("旧正文", encoding="utf-8")

    result = update_text_file_in_place(source, replace_text, backup_dir=backup_dir)

    assert result.changed is True
    assert result.backup_path is not None
    assert result.backup_path.parent == backup_dir
    assert re.match(r"novel_backup001_\d{8}_\d{6}\.txt", result.backup_path.name)
    assert source.read_text(encoding="utf-8") == "新正文"
    assert result.backup_path.read_text(encoding="utf-8") == "旧正文"
