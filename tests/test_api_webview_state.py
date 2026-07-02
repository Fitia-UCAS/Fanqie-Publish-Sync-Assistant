from __future__ import annotations

from backend.api.webview import WebviewRouter


def test_webview_state_exposes_supported_crawler_sites() -> None:
    sites = WebviewRouter().get_state()["crawlNovelSites"]

    assert sites
    assert [site["key"] for site in sites] == ["lanmeiwen", "renrenreshu", "xsbook"]


def test_frontend_bridge_does_not_suppress_detailed_crawler_failure_lines() -> None:
    from backend.api.frontend import FrontendBridge

    assert FrontendBridge._should_suppress_ui_log("web_crawler", "失败：第 205 章｜正文为空") is False
    assert FrontendBridge._should_suppress_ui_log("web_crawler", "限流：第 191 章｜HTTP 429") is False
    assert FrontendBridge._should_suppress_ui_log("web_crawler", "抓取：第 123 章") is False
    assert FrontendBridge._should_suppress_ui_log("web_crawler", "写入：第 123 章") is False
    assert FrontendBridge._should_suppress_ui_log("web_crawler", "完成：第 123 章") is True
