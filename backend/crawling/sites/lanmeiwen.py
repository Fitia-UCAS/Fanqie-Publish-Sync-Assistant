from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.crawling.sites.adapter_contract import NovelSiteAdapter
from backend.crawling.sites.page_text import renumber_unique_chapter_links
from backend.crawling.records import ChapterContent, ChapterLink, CrawlErrorType, NovelCatalog
from backend.crawling.clean import clean_title, is_probably_content, normalize_text


class LanmeiwenAdapter(NovelSiteAdapter):
    site_key = "lanmeiwen"
    site_name = "蓝莓文"
    domains = ("lanmeiwen.com", "www.lanmeiwen.com")
    base_url = "https://www.lanmeiwen.com"

    def fetch_catalog(self, novel_url: str) -> NovelCatalog:
        novel_id = self._novel_id(novel_url)
        try:
            chapters = self._fetch_catalog_api(novel_id)
            title = self._fetch_title_or_default(novel_id)
            return NovelCatalog(title=title, novel_id=novel_id, url=novel_url, chapters=chapters)
        except Exception:
            title, chapters = self._fetch_catalog_html(novel_id)
            return NovelCatalog(title=title, novel_id=novel_id, url=novel_url, chapters=chapters)

    def fetch_chapter(self, catalog: NovelCatalog, chapter: ChapterLink) -> ChapterContent:
        try:
            title, content = self._fetch_chapter_api(catalog.novel_id, chapter)
            if content:
                return ChapterContent(chapter.index, title, content, chapter.url, "api")
        except Exception as exc:
            api_error = str(exc)
            if self._is_block_error(exc):
                return ChapterContent(chapter.index, chapter.title, "", chapter.url, "api", False, api_error, CrawlErrorType.RATE_LIMITED)
        else:
            api_error = "API 返回空正文"

        if self.options.html_fallback:
            try:
                title, content = self._fetch_chapter_html(chapter)
                if content:
                    return ChapterContent(chapter.index, title, content, chapter.url, "html")
            except Exception as exc:
                return ChapterContent(chapter.index, chapter.title, "", chapter.url, "html", False, str(exc), CrawlErrorType.HTML_FALLBACK_FAILED)

        return ChapterContent(chapter.index, chapter.title, "", chapter.url, "api", False, api_error, CrawlErrorType.API_EMPTY_CONTENT)

    @staticmethod
    def _is_block_error(exc: Exception) -> bool:
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) in {403, 429, 444}

    def _novel_id(self, novel_url: str) -> str:
        match = re.search(r"/novel/([^/]+)\.html", urlparse(novel_url).path)
        if not match:
            raise ValueError(f"无法识别小说 ID：{novel_url}")
        return match.group(1)

    def _catalog_api_url(self, novel_id: str) -> str:
        return f"{self.base_url}/api/chapters/{novel_id}"

    def _chapter_api_url(self, novel_id: str, chapter_id: str) -> str:
        return f"{self.base_url}/api/chapter/{novel_id}/{chapter_id}"

    def _catalog_url(self, novel_id: str, page: int = 1) -> str:
        suffix = "" if page <= 1 else f"?cp={page}"
        return f"{self.base_url}/novel/{novel_id}.html{suffix}"

    def _chapter_url(self, novel_id: str, chapter_id: str) -> str:
        return f"{self.base_url}/book/{novel_id}/{chapter_id}.html"

    def _fetch_catalog_api(self, novel_id: str) -> list[ChapterLink]:
        payload = self.client.get_json(self._catalog_api_url(novel_id))
        chapters = self._parse_catalog_payload(payload, novel_id)
        if not chapters:
            raise ValueError("目录 API 未返回章节")
        return chapters

    def _fetch_title_or_default(self, novel_id: str) -> str:
        try:
            html = self.client.get_text(self._catalog_url(novel_id))
            return self._extract_catalog_title(html)
        except Exception:
            return "未命名小说"

    def _parse_catalog_payload(self, payload: Any, novel_id: str) -> list[ChapterLink]:
        items = self._catalog_items(payload)
        chapters: list[ChapterLink] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            chapter_id = item.get("id") or item.get("chapter_id") or item.get("cid") or item.get("uuid")
            title = item.get("title") or item.get("name") or item.get("chapter_title")
            if not chapter_id or not title:
                continue
            chapter_id_text = str(chapter_id).strip()
            chapters.append(
                ChapterLink(
                    index=0,
                    title=normalize_text(str(title)),
                    chapter_id=chapter_id_text,
                    url=self._chapter_url(novel_id, chapter_id_text),
                    source="api",
                )
            )
        return renumber_unique_chapter_links(chapters)

    @staticmethod
    def _catalog_items(payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("目录 API 返回结构不是对象")
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if isinstance(payload.get("chapters"), list):
            return payload["chapters"]
        if isinstance(data, dict):
            if isinstance(data.get("chapters"), list):
                return data["chapters"]
            if isinstance(data.get("list"), list):
                return data["list"]
        raise ValueError(f"无法识别目录 API 返回结构：{str(payload)[:300]}")

    def _fetch_catalog_html(self, novel_id: str) -> tuple[str, list[ChapterLink]]:
        first_html = self.client.get_text(self._catalog_url(novel_id))
        title = self._extract_catalog_title(first_html)
        total_pages = self._extract_total_pages(first_html)
        chapters = self._extract_catalog_chapters(first_html, novel_id)
        for page in range(2, total_pages + 1):
            html = self.client.get_text(self._catalog_url(novel_id, page))
            chapters.extend(self._extract_catalog_chapters(html, novel_id))
        chapters = renumber_unique_chapter_links(chapters)
        if not chapters:
            raise ValueError("HTML 目录未解析到章节")
        return title, chapters

    def _extract_catalog_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        h1 = soup.select_one("h1")
        if h1:
            return clean_title(h1.get_text())
        if soup.title:
            return clean_title(soup.title.get_text())
        return "未命名小说"

    def _extract_total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        for pattern in (r"第\s*\d+\s*页\s*/\s*共\s*(\d+)\s*页", r"共\s*(\d+)\s*页"):
            match = re.search(pattern, text)
            if match:
                return int(match.group(1))
        pages = []
        for anchor in soup.select("a[href*='cp=']"):
            match = re.search(r"cp=(\d+)", anchor.get("href", ""))
            if match:
                pages.append(int(match.group(1)))
        return max(pages) if pages else 1

    def _extract_catalog_chapters(self, html: str, novel_id: str) -> list[ChapterLink]:
        soup = BeautifulSoup(html, "lxml")
        anchors = []
        for selector in ("ul.section-list a[href^='/book/']", ".section-list a[href^='/book/']", "a[href^='/book/']"):
            anchors = soup.select(selector)
            if anchors:
                break

        chapters: list[ChapterLink] = []
        for anchor in anchors:
            title = normalize_text(anchor.get_text())
            href = anchor.get("href", "").strip()
            match = re.search(r"/book/[^/]+/([^/]+)\.html", href)
            if not title or not match:
                continue
            chapter_id = match.group(1)
            chapters.append(ChapterLink(0, title, chapter_id, urljoin(self.base_url, href), "html"))
        return chapters

    def _fetch_chapter_api(self, novel_id: str, chapter: ChapterLink) -> tuple[str, str]:
        payload = self.client.get_json(self._chapter_api_url(novel_id, chapter.chapter_id))
        return self._parse_chapter_payload(payload, chapter.title)

    def _parse_chapter_payload(self, payload: Any, fallback_title: str) -> tuple[str, str]:
        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            candidates.append(payload)
            data = payload.get("data")
            if isinstance(data, dict):
                candidates.append(data)
                chapter = data.get("chapter")
                if isinstance(chapter, dict):
                    candidates.append(chapter)

        for item in candidates:
            title = item.get("title") or item.get("name") or item.get("chapter_title") or fallback_title
            content = item.get("content") or item.get("body") or item.get("text") or item.get("chapter_content") or ""
            if not content:
                continue
            content_text = str(content)
            if "<" in content_text and ">" in content_text:
                content_text = BeautifulSoup(content_text, "lxml").get_text("\n", strip=True)
            return normalize_text(str(title)), normalize_text(content_text)
        return fallback_title, ""

    def _fetch_chapter_html(self, chapter: ChapterLink) -> tuple[str, str]:
        html = self.client.get_text(chapter.url)
        return self._extract_chapter_title(html, chapter.title), self._extract_chapter_content(html)

    def _extract_chapter_title(self, html: str, fallback_title: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        self._remove_noise(soup)
        for selector in ("h1.chapter-title", ".chapter-title", "h1", ".read-title", ".article-title", ".content-title"):
            node = soup.select_one(selector)
            if node:
                title = normalize_text(node.get_text())
                if title:
                    return title
        if soup.title:
            return clean_title(soup.title.get_text(), fallback_title)
        return fallback_title

    def _extract_chapter_content(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        nodes = []
        for selector in ("#articleBody", "article.read-content", ".read-content", ".chapter-content", ".article-content", ".content", "#content", "article"):
            node = soup.select_one(selector)
            if node:
                nodes.append(node)
        for node in nodes:
            if self._looks_like_preview(node):
                continue
            temp = BeautifulSoup(str(node), "lxml")
            self._remove_noise(temp)
            text = normalize_text(temp.get_text("\n", strip=True))
            if is_probably_content(text):
                return text
        return ""

    @staticmethod
    def _remove_noise(soup: BeautifulSoup) -> None:
        for tag in soup.select(
            "script, style, iframe, ins, footer, header, nav, "
            ".menu-top, .menu-bottom, .drawer, .drawer-overlay, "
            ".progress-container, #settingsBtn, "
            ".nav-footer, .comment-section, .comment-list, "
            ".ad, .ads, .advert, .advertisement"
        ):
            tag.decompose()

    @staticmethod
    def _looks_like_preview(node: Any) -> bool:
        html = str(node or "")
        markers = ("height:320px", "overflow: hidden", "ri-loader", "fetchChapter", "章节加载失败", "加载内容失败")
        return any(marker in html for marker in markers)

