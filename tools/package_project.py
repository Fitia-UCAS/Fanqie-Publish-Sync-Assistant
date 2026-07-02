from __future__ import annotations

import shutil
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "fanqie-publish-sync.zip"
EXCLUDED_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    "build",
    "dist",
    "browser_edge_profile",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".orig", ".log", ".bat", ".spec"}
EXCLUDED_NAME_PREFIXES = ("PATCH_NOTES_", "_pyinstaller_")
RUNTIME_DATA_ROOTS = {"auth", "runtime", "runs", "secrets", "settings", "workspaces"}
RUNTIME_RELATIVE_PATHS = {
    "data/auth/fanqie/default/state.json",
    "data/auth/fanqie/accounts.json",
    "data/auth/fanqie/accounts",
    "data/fanqie_web/chapter_sync_state.json",
}
RUNTIME_LEAF_DIRS = {"backups", "compare_reports", "debug", "history", "outputs", "tasklogs", "tracker", "chapters"}


def should_include(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if relative.parts and relative.parts[0] == "config":
        return False
    if relative.as_posix() in RUNTIME_RELATIVE_PATHS:
        return False
    if relative.parts and relative.parts[0] == "data":
        if relative.name == ".gitkeep" and len(relative.parts) == 2:
            return True
        if len(relative.parts) >= 2 and relative.parts[1] in RUNTIME_DATA_ROOTS:
            return False
        if any(part in RUNTIME_LEAF_DIRS for part in relative.parts[2:]):
            return False
        if path.suffix in {".json", ".log", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md"}:
            return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(EXCLUDED_NAME_PREFIXES):
        return False
    return True


def clean_runtime_caches() -> None:
    for pattern in ("**/__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"):
        for path in ROOT.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def package_project(output: Path = OUTPUT) -> Path:
    clean_runtime_caches()
    if output.exists():
        output.unlink()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and should_include(path):
                archive.write(path, Path(ROOT.name) / path.relative_to(ROOT))
    return output


if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT
    print(package_project(output))
