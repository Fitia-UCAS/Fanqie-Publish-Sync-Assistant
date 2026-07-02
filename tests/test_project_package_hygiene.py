from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def test_no_empty_frontend_placeholder_components() -> None:
    components_dir = ROOT_DIR / "frontend" / "assets" / "components"
    assert not components_dir.exists()


def test_text_file_helpers_are_flat_and_named_directly() -> None:
    assert (ROOT_DIR / "backend" / "text_files.py").exists()
    assert not (ROOT_DIR / "backend" / "text_file").exists()
    assert not (ROOT_DIR / "backend" / "file_io.py").exists()
    assert not (ROOT_DIR / "backend" / "novel" / "io.py").exists()


def test_package_project_excludes_runtime_caches() -> None:
    from tools.package_project import should_include

    cache_paths = [
        ROOT_DIR / ".pytest_cache" / "README.md",
        ROOT_DIR / "backend" / "__pycache__" / "config.cpython-313.pyc",
        ROOT_DIR / ".mypy_cache" / "state.json",
        ROOT_DIR / ".ruff_cache" / "content",
        ROOT_DIR / "PATCH_NOTES_AUTO_PUBLISH_FIX.md",
        ROOT_DIR / "config" / "config.json",
        ROOT_DIR / "data" / "settings" / "app.json",
        ROOT_DIR / "data" / "secrets" / "llm.local.json",
        ROOT_DIR / "data" / "auth" / "fanqie" / "default" / "state.json",
        ROOT_DIR / "data" / "runtime" / "fanqie_web" / "browser_edge_profile" / "Default" / "Cookies",
        ROOT_DIR / "data" / "auth" / "fanqie" / "default" / "state.json",
        ROOT_DIR / "data" / "auth" / "fanqie" / "accounts.json",
        ROOT_DIR / "data" / "fanqie_web" / "chapter_sync_state.json",
        ROOT_DIR / "data" / "publishing" / "debug" / "screen.png",
        ROOT_DIR / "创建文件链接.bat",
    ]
    assert [should_include(path) for path in cache_paths] == [False] * len(cache_paths)


def test_start_script_uses_split_auth_state_path() -> None:
    text = (ROOT_DIR / "tools" / "start.py").read_text(encoding="utf-8")
    assert '"data" / "auth" / "fanqie" / "default" / "state.json"' in text
    assert '"data" / "fanqie_web" / "state.json"' not in text
