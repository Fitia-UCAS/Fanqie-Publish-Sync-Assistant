from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


def read_frontend() -> tuple[str, str, str]:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    css = (FRONTEND_DIR / "assets" / "app.css").read_text(encoding="utf-8")
    js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")
    return html, css, js


def test_frontend_is_the_main_product_entry() -> None:
    assert (ROOT_DIR / "main.py").exists()
    assert (FRONTEND_DIR / "index.html").exists()
    assert (FRONTEND_DIR / "assets" / "app.css").exists()
    assert (FRONTEND_DIR / "assets" / "app.js").exists()
    assert not (ROOT_DIR / ("frontend" + "_" + "dash" + "board")).exists()
    assert not (ROOT_DIR / ("main" + "_" + "dash" + "board.py")).exists()


def test_frontend_branding_uses_final_product_name() -> None:
    html, _, _ = read_frontend()
    assert "番茄发布与同步助手" in html
    assert ("FANQIE" + " DASH") not in html
    assert ("Publish Sync" + " Assistant") not in html
    assert ("· " + "Dash" + "board") not in html


def test_frontend_does_not_contain_removed_or_temporary_names() -> None:
    html, css, js = read_frontend()
    merged = "\n".join([html, css, js])
    forbidden = [
        "web" + "novel",
        "Web" + "novel",
        "WEB" + "NOVEL",
        "frontend" + "_" + "dash" + "board",
        "main" + "_" + "dash" + "board",
        "data-" + "dash" + "board" + "-style",
        "fanqie" + "Dash" + "board" + "Style",
        "极" + "简",
        "简" + "约",
        "Mini" + "mal",
        "mini" + "mal",
    ]
    for word in forbidden:
        assert word not in merged


def test_frontend_uses_theme_names_for_theme_switching() -> None:
    html, _, js = read_frontend()
    assert "data-theme-style" in html
    assert "fanqieUiTheme" in js
    assert "像素原版" in html
    assert "夜间像素" in html


def test_frontend_contains_all_business_pages() -> None:
    html, _, _ = read_frontend()
    for view in ["publish", "sync", "process", "crawler", "character_material", "current_plot"]:
        assert f'data-view="{view}"' in html
        assert f'data-panel="{view}"' in html
    for title in ["番茄发布", "番茄同步", "小说处理", "网页抓取", "角色素材", "当前剧情"]:
        assert title in html


def test_sensitive_inputs_are_password_fields() -> None:
    html, _, _ = read_frontend()
    for field_id in ["apUrl", "syUrl", "cmApiKey", "cmBaseUrl", "cpApiKey", "cpBaseUrl"]:
        assert f'id="{field_id}" type="password"' in html


def test_file_and_folder_fields_are_display_only_paths() -> None:
    _, _, js = read_frontend()
    assert "PATH_FIELDS" in js
    assert "baseName" in js
    assert "dataset.fullValue" in js


def test_console_has_separate_toolbar_and_scrollable_log_body() -> None:
    html, css, js = read_frontend()
    assert "console-tools" in html
    assert "console-shell" in html
    assert "copyConsole" in html
    assert "clearConsole" in html
    assert ".console-card" in css
    assert "height: 280px" in css
    assert "overflow-y: auto" in css
    assert "NovelTools" in js


def test_pixel_buttons_share_one_visual_style() -> None:
    _, css, _ = read_frontend()
    assert ".pixel-btn.primary" in css
    assert ".pixel-btn.primary { background: var(--bg-panel); color: var(--text-main); }" in css
    assert "#2daaf2" not in css


def test_crawler_uses_crawl_wording_not_pull_wording() -> None:
    html, _, _ = read_frontend()
    assert "开始抓取" in html
    assert "停止抓取" in html
    assert "预览抓取" not in html
    assert "开始拉取" not in html
