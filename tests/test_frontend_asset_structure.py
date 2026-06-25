from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"


def test_frontend_core_scripts_are_split_from_app_shell() -> None:
    core_dir = FRONTEND_DIR / "assets" / "core"
    assert (core_dir / "ui_page_registry.js").exists()
    assert (core_dir / "ui_form_controls.js").exists()
    assert (core_dir / "ui_task_panel.js").exists()
    assert (core_dir / "ui_state_store.js").exists()
    assert (core_dir / "ui_novel_splitter.js").exists()
    assert (core_dir / "ui_character_material.js").exists()
    assert len((FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8").splitlines()) < 460


def test_frontend_page_files_use_page_object_names() -> None:
    page_dir = FRONTEND_DIR / "assets" / "pages"
    expected_pages = {
        "novel_processor_page",
        "fanqie_publisher_page",
        "fanqie_syncer_page",
        "novel_crawler_page",
        "character_material_page",
    }
    assert {path.stem for path in page_dir.glob("*.js")} == expected_pages


def test_frontend_core_scripts_load_before_app_shell() -> None:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    assert html.index("assets/core/ui_page_registry.js") < html.index("assets/app.js")
    assert html.index("assets/core/ui_state_store.js") < html.index("assets/core/ui_task_panel.js")
    assert html.index("assets/core/ui_task_panel.js") < html.index("assets/core/ui_novel_splitter.js")
    assert html.index("assets/core/ui_novel_splitter.js") < html.index("assets/core/ui_character_material.js")
    assert html.index("assets/core/ui_character_material.js") < html.index("assets/app.js")
    for page_file in [
        "novel_processor_page.js",
        "fanqie_publisher_page.js",
        "fanqie_syncer_page.js",
        "novel_crawler_page.js",
        "character_material_page.js",
    ]:
        assert html.index(f"assets/pages/{page_file}") < html.index("assets/app.js")


def test_header_has_separate_reset_data_and_authorization_buttons() -> None:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    app_js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")

    assert 'id="resetDataButton"' in html
    assert 'id="loginButton"' in html
    assert 'reset_app_data' in app_js
    assert 'reset_login' in app_js

def test_novel_processor_uses_console_open_directory_only() -> None:
    page_js = (FRONTEND_DIR / "assets" / "pages" / "novel_processor_page.js").read_text(encoding="utf-8")
    app_js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")
    task_panel_js = (FRONTEND_DIR / "assets" / "core" / "ui_task_panel.js").read_text(encoding="utf-8")

    assert "exOpenOutputDir" not in page_js
    assert "exOpenOutputDir" not in app_js
    assert 'data-open-output="${this.attr(page)}"' in task_panel_js


def test_console_open_directory_uses_feature_data_roots_from_state() -> None:
    task_panel_js = (FRONTEND_DIR / "assets" / "core" / "ui_task_panel.js").read_text(encoding="utf-8")

    assert "statePath(key)" in task_panel_js
    assert "process_novel: 'novel_processor'" in task_panel_js
    assert "process_novel_batch: 'novel_processor'" in task_panel_js
    assert "novel_splitter: 'novel_processor'" in task_panel_js
    assert "clean_text_ads: 'novel_processor'" in task_panel_js
    assert "clean_text_breaks: 'novel_processor'" in task_panel_js
    assert "auto_publish: 'fanqie_publisher'" in task_panel_js
    assert "chapter_sync: 'fanqie_syncer'" in task_panel_js
    assert "character_material: 'character_material'" in task_panel_js
    assert "this.statePath('web_crawler_outputs')" in task_panel_js
    assert "this.statePath('auto_publish_logs')" not in task_panel_js
    assert "this.statePath('chapter_sync_logs')" not in task_panel_js
    assert "|| 'novel_process_outputs'" not in task_panel_js
    assert "|| 'novel_crawl_outputs'" not in task_panel_js


def test_crawler_page_replaces_html_preview_with_detailed_log() -> None:
    page_js = (FRONTEND_DIR / "assets" / "pages" / "novel_crawler_page.js").read_text(encoding="utf-8")
    app_js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")
    config_text = (ROOT_DIR / "config" / "config.json").read_text(encoding="utf-8")

    assert "nsDetailedLog" in page_js
    assert "详细日志" in page_js
    assert "detailedLog" in app_js
    assert "detailedLog" in config_text
    assert "HTML" + " 预览" not in page_js
    assert "ns" + "Allow" + "Html" + "Preview" not in page_js
    assert "allow" + "Html" + "Preview" not in app_js
    assert "allow" + "Html" + "Preview" not in config_text


def test_common_buttons_use_consistent_height_tokens() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--control-height: 40px" in css
    assert "--control-small-height: 32px" in css
    assert "--button-height: var(--control-height)" in css
    assert "--button-small-height: var(--control-small-height)" in css
    assert ".primary-btn, .soft-btn, .ghost-btn, .mini-btn" in css
    assert "height: var(--button-height)" in css
    assert "height: var(--control-height)" in css
    assert ".terminal-clear, .terminal-copy, .terminal-open, .terminal-open-log, .terminal-open-backup" in css
    assert "height: var(--button-small-height)" in css


def test_frontend_task_state_store_is_loaded_before_task_panel() -> None:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    store_js = (FRONTEND_DIR / "assets" / "core" / "ui_state_store.js").read_text(encoding="utf-8")
    task_panel_js = (FRONTEND_DIR / "assets" / "core" / "ui_task_panel.js").read_text(encoding="utf-8")
    app_js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")

    assert html.index("assets/core/ui_state_store.js") < html.index("assets/core/ui_task_panel.js")
    assert "NovelTaskStateStore" in store_js
    assert "applyTaskEvent(event)" in task_panel_js
    assert "terminal-metrics" not in task_panel_js
    assert "taskStore:" in app_js


def test_parameter_controls_share_global_control_height() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--control-height: 40px" in css
    assert ".input, .select, .textarea" in css
    assert ".file-picker" in css
    assert ".start-btn" in css
    assert "height: var(--control-height)" in css
    assert "min-height: var(--control-height)" in css
    assert "height: 48px" not in css
    assert "height: 60px" not in css


def test_controls_and_buttons_share_font_size_token() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--control-font-size: 12px" in css
    assert ".input, .select, .textarea" in css
    assert ".primary-btn, .soft-btn, .ghost-btn, .mini-btn" in css
    assert "font-size: var(--control-font-size)" in css
    assert "font-size: 11.5px" not in css
    assert "font-size: 10.5px" not in css


def test_panels_use_flat_shared_surface_style() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert ".terminal-card" in css
    assert ".card, .fanqie-settings-card" in css
    assert "box-shadow: none" in css
    assert "status-panel .terminal-log" not in css


def test_output_panel_uses_status_message_without_metric_bar() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")
    task_panel_js = (FRONTEND_DIR / "assets" / "core" / "ui_task_panel.js").read_text(encoding="utf-8")

    assert "--output-panel-height" in css
    assert "--settings-panel-height" in css
    assert "terminal-status info" in task_panel_js
    assert "terminal-metrics" not in css
    assert "terminal-metrics" not in task_panel_js
    assert "阶段：等待" not in task_panel_js
    assert "抓取：0" not in task_panel_js
    assert "写入：0" not in task_panel_js


def test_primary_task_buttons_share_icon_action_markup() -> None:
    page_dir = FRONTEND_DIR / "assets" / "pages"
    publisher_js = (page_dir / "fanqie_publisher_page.js").read_text(encoding="utf-8")
    syncer_js = (page_dir / "fanqie_syncer_page.js").read_text(encoding="utf-8")
    crawler_js = (page_dir / "novel_crawler_page.js").read_text(encoding="utf-8")
    processor_js = (page_dir / "novel_processor_page.js").read_text(encoding="utf-8")

    for page_js in [publisher_js, syncer_js, crawler_js, processor_js]:
        assert "big-action primary-action" in page_js

    assert "primary-btn full-btn start-btn" not in publisher_js
    assert "primary-btn full-btn" not in crawler_js
    assert "<span>↑</span><div><b>启动发布</b></div>" in publisher_js
    assert "<span>↓</span><div><b>开始拉取</b></div>" in crawler_js


def test_action_buttons_use_exact_shared_control_height() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--control-icon-size: 24px" in css
    assert ".big-action {" in css
    assert "height: var(--button-height);" in css
    assert "min-height: var(--button-height);" in css
    assert ".compact-actions .big-action, .wide-action" in css
    assert "grid-template-columns: var(--control-icon-size) minmax(0, 1fr);" in css
    assert "box-shadow: none" in css

def test_pages_share_same_workspace_layout_tokens() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--workspace-width: 1200px" in css
    assert "--workspace-left-width: 400px" in css
    assert "--workspace-gap: 26px" in css
    assert "--page-gutter: 64px" in css
    assert "width: min(var(--workspace-width), calc(100% - var(--page-gutter)))" in css
    assert "grid-template-columns: var(--workspace-left-width) minmax(0, 1fr)" in css
    assert "gap: var(--workspace-gap)" in css
    assert "calc(100vw - 64px)" not in css
    assert "width: calc(100vw - 36px)" not in css


def test_page_host_reserves_scrollbar_space_to_prevent_page_switch_shift() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert ".page-host" in css
    assert "overflow-y: scroll" in css
    assert "scrollbar-gutter: stable both-edges" in css
    assert "padding: var(--page-vertical-padding) 0" in css


def test_control_fonts_share_one_weight_and_size_token() -> None:
    css = (FRONTEND_DIR / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "--control-font-weight: 900" in css
    assert "font-weight: var(--control-font-weight)" in css
    assert "--control-font-weight: var(--control-font-weight)" not in css


def test_character_material_console_is_status_only_in_ui() -> None:
    app_js = (FRONTEND_DIR / "assets" / "app.js").read_text(encoding="utf-8")

    assert "'character_material'" in app_js
    assert "loglessPages:" in app_js
    assert "'character_material'" in app_js.split("loglessPages:", 1)[1].split("]", 1)[0]
