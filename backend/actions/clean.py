from __future__ import annotations


from pathlib import Path

from backend.novel.ad_cleaner import clean_ad_text
from backend.novel.sentence_fixer import fix_sentences
from backend.novel.file_rewrite import update_text_file_in_place
from backend.tasks.callbacks import TaskCallbacks
from backend.text_files import iter_text_files
from backend.paths import PROCESS_BACKUP_DIR
from backend.tasks.outcome import TaskOutcome


_BACKUP_DIRS = {
    "ad": PROCESS_BACKUP_DIR / "clean_ads",
    "move": PROCESS_BACKUP_DIR / "fix_sentences",
}


def clean_text(payload: dict, callbacks: TaskCallbacks | None = None) -> TaskOutcome:
    callbacks = callbacks or TaskCallbacks()
    scope = payload.get("scope") or "ad"
    files = _selected_files(payload)
    if not files:
        return TaskOutcome(False, "请选择有效的 TXT 文件或文件夹。")

    changed = 0
    backup_paths: list[str] = []
    backup_enabled = payload.get("backup") is not False
    backup_root = _BACKUP_DIRS.get(scope, _BACKUP_DIRS["ad"])
    last_path: Path | None = None
    def clean_one(text: str) -> str:
        return _clean_one(scope, text, payload)

    for index, file_path in enumerate(files, start=1):
        update = update_text_file_in_place(
            file_path,
            clean_one,
            backup_dir=backup_root / file_path.parent.name,
            backup=backup_enabled,
        )
        if update.changed:
            changed += 1
        if update.backup_path:
            backup_paths.append(str(update.backup_path))
        last_path = file_path
        callbacks.emit_progress(index, len(files))
        callbacks.emit_log(f"完成：{file_path.name}", "success")

    action = "清理广告" if scope == "ad" else "修复句子"
    message = f"{action}完成：{len(files)} 个文件，覆盖修改 {changed} 个。"
    callbacks.emit_log(message, "success")
    target_path = last_path.parent if len(files) > 1 and last_path else last_path or Path.cwd()
    data: dict[str, object] = {"changed": changed, "backupPaths": backup_paths}
    if backup_paths:
        data["backupPath"] = backup_paths[-1]
        data["backupDir"] = str(Path(backup_paths[-1]).parent)
    return TaskOutcome(
        True,
        message,
        path=target_path,
        result_kind="in_place" if len(files) == 1 else "in_place_batch",
        display_name=target_path.name,
        data=data,
    )


def _selected_files(payload: dict) -> list[Path]:
    batch_folder = str(payload.get("batchFolder") or "").strip()
    input_file = str(payload.get("inputFile") or "").strip()
    if batch_folder:
        return iter_text_files(batch_folder)
    if not input_file:
        return []
    path = Path(input_file)
    return [path] if path.exists() and path.is_file() else []


def _clean_one(scope: str, text: str, payload: dict) -> str:
    if scope == "move":
        return fix_sentences(
            text,
            bool(payload.get("normalizePunctuation", True)),
            int(payload.get("maxMoveChars") or 120),
        )
    return clean_ad_text(text)


