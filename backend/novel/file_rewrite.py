from __future__ import annotations


from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from backend.text_files import backup_file, read_text_and_encoding, write_text

TextTransform = Callable[[str], str]


@dataclass(slots=True, frozen=True)
class TextFileUpdate:
    path: Path
    changed: bool
    encoding: str
    backup_path: Path | None = None


def update_text_file_in_place(
    path: str | Path,
    transform: TextTransform,
    *,
    backup_dir: str | Path | None = None,
    backup: bool = True,
) -> TextFileUpdate:

    target = Path(path)
    original, encoding = read_text_and_encoding(target)
    updated = transform(original)
    if updated == original:
        return TextFileUpdate(path=target, changed=False, encoding=encoding)

    backup_path = backup_file(target, backup_dir or target.parent, cleanup_existing=False) if backup else None
    write_text(target, updated, encoding=encoding)
    return TextFileUpdate(path=target, changed=True, encoding=encoding, backup_path=backup_path)


