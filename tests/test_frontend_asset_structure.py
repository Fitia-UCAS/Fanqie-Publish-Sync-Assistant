from __future__ import annotations

from pathlib import Path
import re

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
PERSONAL_FRONTEND_DIR = FRONTEND_DIR / "personal"
RELEASE_FRONTEND_DIR = FRONTEND_DIR / "release"


def read_frontend(variant: str = "release") -> tuple[str, str, str]:
    frontend_dir = FRONTEND_DIR / variant
    html = (frontend_dir / "index.html").read_text(encoding="utf-8")
    css = (frontend_dir / "assets" / "app.css").read_text(encoding="utf-8")
    js = (frontend_dir / "assets" / "app.js").read_text(encoding="utf-8")
    return html, css, js


def test_frontend_is_split_by_product_variant() -> None:
    assert (ROOT_DIR / "main.py").exists()
    for frontend_dir in (PERSONAL_FRONTEND_DIR, RELEASE_FRONTEND_DIR):
        assert (frontend_dir / "index.html").exists()
        assert (frontend_dir / "assets" / "app.css").exists()
        assert (frontend_dir / "assets" / "app.js").exists()
    assert not (FRONTEND_DIR / "index.html").exists()
    assert not (FRONTEND_DIR / "assets").exists()
    assert not (ROOT_DIR / ("frontend" + "_" + "dash" + "board")).exists()
    assert not (ROOT_DIR / ("main" + "_" + "dash" + "board.py")).exists()


def test_frontend_branding_uses_final_product_name() -> None:
    for variant in ("personal", "release"):
        html, _, _ = read_frontend(variant)
        assert "番茄发布与同步助手" in html
        assert ("FANQIE" + " DASH") not in html
        assert ("Publish Sync" + " Assistant") not in html
        assert ("· " + "Dash" + "board") not in html


def test_frontend_does_not_contain_removed_or_temporary_names() -> None:
    for variant in ("personal", "release"):
        html, css, js = read_frontend(variant)
        merged = "\n".join([html, css, js])
        forbidden = [
            "web" + "novel",
            "Web" + "novel",
            "WEB" + "NOVEL",
            "frontend" + "_" + "dash" + "board",
            "main" + "_" + "dash" + "board",
            "data-" + "dash" + "board" + "-style",
            "fanqie" + "Dash" + "board" + "Style",
            "data-" + "personal",
            "show" + "Personal" + "Pages",
            "极" + "简",
            "简" + "约",
            "Mini" + "mal",
            "mini" + "mal",
        ]
        for word in forbidden:
            assert word not in merged


def test_frontend_uses_theme_names_for_theme_switching() -> None:
    for variant in ("personal", "release"):
        html, _, js = read_frontend(variant)
        assert "data-theme-style" in html
        assert "fanqieUiTheme" in js
        assert "像素原版" in html
        assert "夜间像素" in html


def test_personal_frontend_contains_all_business_pages() -> None:
    html, _, _ = read_frontend("personal")
    for view in ["publish", "sync", "process", "crawler", "character_notes", "plot_notes"]:
        assert f'data-view="{view}"' in html
        assert f'data-panel="{view}"' in html
    for title in ["番茄发布", "番茄同步", "小说处理", "网页抓取", "角色素材", "当前剧情"]:
        assert title in html


def test_release_frontend_only_contains_publish_and_sync_pages() -> None:
    html, _, js = read_frontend("release")
    for view in ["publish", "sync"]:
        assert f'data-view="{view}"' in html
        assert f'data-panel="{view}"' in html
    for removed in ["process", "crawler", "character_notes", "plot_notes"]:
        assert f'data-view="{removed}"' not in html
        assert f'data-panel="{removed}"' not in html
        assert removed not in js
    for title in ["小说处理", "网页抓取", "角色素材", "当前剧情"]:
        assert title not in html


def test_main_defaults_to_release_frontend_but_can_select_personal() -> None:
    import main

    assert main.DEFAULT_FRONTEND_VARIANT == "release"
    assert main.frontend_index_path(ROOT_DIR, "release") == RELEASE_FRONTEND_DIR / "index.html"
    assert main.frontend_index_path(ROOT_DIR, "personal") == PERSONAL_FRONTEND_DIR / "index.html"


def _input_tag(html: str, field_id: str) -> str:
    match = re.search(rf"<input[^>]*id=\"{field_id}\"[^>]*>", html)
    assert match is not None
    return match.group(0)


def test_sensitive_inputs_are_password_fields() -> None:
    personal_html, _, _ = read_frontend("personal")
    release_html, _, _ = read_frontend("release")
    for html in (personal_html, release_html):
        for field_id in ["apUrl", "syUrl"]:
            assert 'type="password"' in _input_tag(html, field_id)
    for field_id in ["cmApiKey", "cmBaseUrl", "cpApiKey", "cpBaseUrl"]:
        assert 'type="password"' in _input_tag(personal_html, field_id)


def test_file_and_folder_fields_are_display_only_paths() -> None:
    for variant in ("personal", "release"):
        _, _, js = read_frontend(variant)
        assert "PATH_FIELDS" in js
        assert "baseName" in js
        assert "dataset.fullValue" in js


def test_console_has_separate_toolbar_and_scrollable_log_body() -> None:
    for variant in ("personal", "release"):
        html, css, js = read_frontend(variant)
        assert "console-tools" in html
        assert "console-shell" in html
        assert "copyConsole" in html
        assert "clearConsole" in html
        assert ".console-card" in css
        assert "height: 280px" in css
        assert "overflow-y: auto" in css
        assert "NovelTools" in js


def test_pixel_buttons_share_one_visual_style() -> None:
    for variant in ("personal", "release"):
        _, css, _ = read_frontend(variant)
        assert ".pixel-btn.primary" in css
        assert ".pixel-btn.primary { background: var(--bg-panel); color: var(--text-main); }" in css
        assert "#2daaf2" not in css


def test_crawler_uses_crawl_wording_not_pull_wording() -> None:
    html, _, _ = read_frontend("personal")
    assert "开始抓取" in html
    assert "停止抓取" in html
    assert "预览抓取" not in html
    assert "开始拉取" not in html
