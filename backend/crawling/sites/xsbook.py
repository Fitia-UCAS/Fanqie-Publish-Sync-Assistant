from __future__ import annotations

import re
import threading
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from backend.crawling.clean import clean_title, is_probably_content, normalize_text
from backend.crawling.records import ChapterContent, ChapterLink, NovelCatalog
from backend.crawling.sites.adapter_contract import NovelSiteAdapter
from backend.crawling.sites.page_text import (
    chapter_fetch_result,
    headers_with_referer,
    merge_page_texts,
    prefer_clean_title,
    remove_embedded_title_lines,
    renumber_unique_chapter_links,
)


class XsbookAdapter(NovelSiteAdapter):

    site_key = "xsbook"
    site_name = "顶点小说"
    domains = ("xsbook.org", "www.xsbook.org")
    base_url = "http://www.xsbook.org"
    MAX_CHAPTER_PAGES = 30
    _browser_lock = threading.Lock()

    @classmethod
    def default_headers(cls, novel_url: str) -> dict[str, str]:
        root = cls._site_root(novel_url)
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Pragma": "no-cache",
            "Referer": f"{root}/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    def fetch_catalog(self, novel_url: str) -> NovelCatalog:
        catalog_url = self._catalog_url(novel_url)
        html = self._fetch_text(catalog_url, referer=f"{self._site_root(catalog_url)}/")
        title = self._extract_catalog_title(html)
        chapters = self._extract_catalog_chapters(html, catalog_url)
        if not chapters:
            raise ValueError("目录页未解析到章节，请确认链接是顶点小说的小说目录页。")
        return NovelCatalog(title=title, novel_id=self._novel_id(catalog_url), url=catalog_url, chapters=chapters)

    def fetch_chapter(self, catalog: NovelCatalog, chapter: ChapterLink) -> ChapterContent:
        return chapter_fetch_result(chapter, lambda: self._fetch_chapter_pages(catalog, chapter))

    def _fetch_chapter_pages(self, catalog: NovelCatalog, chapter: ChapterLink) -> tuple[str, str]:
        url = chapter.url
        referer = catalog.url if catalog else self._catalog_url(chapter.url)
        visited: set[str] = set()
        page_texts: list[str] = []
        title = chapter.title

        for _page_no in range(self.MAX_CHAPTER_PAGES):
            if url in visited:
                break
            visited.add(url)
            html = self._fetch_text(url, referer=referer)
            page_title = self._extract_chapter_title(html, title)
            title = prefer_clean_title(title, page_title, self._clean_chapter_title)
            page_text = self._extract_chapter_content(html, title)
            if page_text:
                page_texts.append(page_text)

            next_url = self._next_same_chapter_url(html, url, chapter.chapter_id)
            if not next_url:
                break
            referer = url
            url = next_url

        content = merge_page_texts(page_texts, title)
        return title, content

    def _fetch_text(self, url: str, referer: str) -> str:
        errors: list[Exception] = []
        for candidate in self._candidate_urls(url):
            try:
                return self.client.get_text(candidate, headers=headers_with_referer(self.default_headers, self._site_root, candidate, referer))
            except Exception as exc:
                errors.append(exc)
                if self._is_definitive_not_found(exc):
                    raise

        if self.options.html_fallback:
            try:
                return self._fetch_text_with_browser(self._canonical_url(url), referer)
            except Exception as browser_exc:
                if errors:
                    raise RuntimeError(f"请求被站点拒绝，requests 与浏览器兜底都失败：{browser_exc}; 原始错误：{errors[-1]}") from browser_exc
                raise
        if errors:
            raise errors[-1]
        raise RuntimeError(f"请求失败：{url}")


    @classmethod
    def _is_definitive_not_found(cls, exc: Exception) -> bool:
        return cls._status_code(exc) == 404

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", None) if response is not None else None

    @classmethod
    def _candidate_urls(cls, url: str) -> list[str]:
        return [cls._canonical_url(url)]

    @classmethod
    def _canonical_url(cls, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        if parsed.netloc.lower().endswith("xsbook.org"):
            return parsed._replace(scheme="http", netloc="www.xsbook.org").geturl()
        return parsed._replace(scheme=parsed.scheme or "http").geturl()

    def _fetch_text_with_browser(self, url: str, referer: str) -> str:
        with self._browser_lock:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=self.default_headers(url)["User-Agent"],
                        locale="zh-CN",
                        extra_http_headers={"Referer": referer or f"{self._site_root(url)}/"},
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=max(5000, self.client.options.timeout * 1000))
                    return page.content()
                finally:
                    browser.close()

    def _catalog_url(self, novel_url: str) -> str:
        parsed = urlparse(novel_url)
        path = parsed.path or "/"
        chapter_match = re.match(r"^/(?P<novel>\d+_\d+)/\d+(?:_\d+)?\.html$", path)
        if chapter_match:
            path = f"/{chapter_match.group('novel')}/"
        elif not path.endswith("/"):
            path = f"{path}/"
        return self._canonical_url(urljoin(self._site_root(novel_url), path))

    @staticmethod
    def _site_root(url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.netloc or "www.xsbook.org").lower()
        if host.endswith("xsbook.org"):
            return "http://www.xsbook.org"
        scheme = parsed.scheme or "http"
        return f"{scheme}://{host}"

    @staticmethod
    def _novel_id(novel_url: str) -> str:
        match = re.search(r"/(\d+_\d+)/?", urlparse(novel_url).path)
        if not match:
            raise ValueError(f"无法识别小说 ID：{novel_url}")
        return match.group(1)

    def _extract_catalog_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for selector in ("#info h1", "h1"):
            node = soup.select_one(selector)
            if node:
                title = normalize_text(node.get_text())
                if title:
                    return title
        meta = soup.select_one("meta[property='og:novel:book_name'], meta[property='og:title']")
        if meta and meta.get("content"):
            return normalize_text(str(meta.get("content")))
        if soup.title:
            return clean_title(soup.title.get_text())
        return "未命名小说"

    def _extract_catalog_chapters(self, html: str, catalog_url: str) -> list[ChapterLink]:
        soup = BeautifulSoup(html, "lxml")
        anchors = self._catalog_chapter_anchors(soup)
        chapters: list[ChapterLink] = []
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            chapter_id = self._chapter_base_id(href)
            if not chapter_id:
                continue
            title = self._clean_chapter_title(anchor.get("title") or anchor.get_text())
            if not title:
                continue
            chapters.append(ChapterLink(0, title, chapter_id, self._canonical_url(urljoin(catalog_url, href)), "html"))
        return renumber_unique_chapter_links(chapters)

    def _catalog_chapter_anchors(self, soup: BeautifulSoup) -> list:
        dl = soup.select_one("#list dl") or soup.select_one("#list")
        if not dl:
            return soup.select("a[rel='chapter']")

        anchors = []
        collecting = False
        saw_catalog_marker = False
        for child in dl.children:
            name = getattr(child, "name", "")
            if name == "dt":
                text = normalize_text(child.get_text(" ", strip=True))
                if "全部章节" in text or "章节目录" in text:
                    collecting = True
                    saw_catalog_marker = True
                continue
            if collecting and name == "a" and child.get("rel") == ["chapter"]:
                anchors.append(child)

        if anchors:
            return anchors
        if saw_catalog_marker:
            return []
        return dl.select("a[rel='chapter']")

    def _extract_chapter_title(self, html: str, fallback_title: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for selector in ("h1.bookname", ".bookname", "h1"):
            node = soup.select_one(selector)
            if node:
                title = self._clean_chapter_title(node.get_text())
                if title:
                    return title
        if soup.title:
            title = self._clean_chapter_title(clean_title(soup.title.get_text(), fallback_title))
            if title:
                return title
        return self._clean_chapter_title(fallback_title)

    def _extract_chapter_content(self, html: str, title: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one("#booktxt") or soup.select_one("#chaptercontent") or soup.select_one(".content")
        if not node:
            return ""
        for tag in node.select("script, style, iframe, ins, .ad, .ads, .advert, .advertisement"):
            tag.decompose()
        lines = [normalize_text(item.get_text(" ", strip=True)) for item in node.select("p")]
        if not any(lines):
            lines = normalize_text(node.get_text("\n", strip=True)).split("\n")
        lines = remove_embedded_title_lines(lines, title)
        text = normalize_text("\n".join(line for line in lines if line.strip()))
        return text if self._looks_like_chapter_text(text) else ""

    def _next_same_chapter_url(self, html: str, current_url: str, chapter_id: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for selector in (".bottem2 #next_url", ".bottem1 #next_url", "a#next_url"):
            anchor = soup.select_one(selector)
            if not anchor:
                continue
            href = (anchor.get("href") or "").strip()
            if not href or href.startswith("javascript:"):
                continue
            if self._chapter_base_id(href) == chapter_id and self._chapter_page_no(href) > 1:
                return self._canonical_url(urljoin(current_url, href))
        return ""

    @staticmethod
    def _looks_like_chapter_text(text: str) -> bool:
        value = normalize_text(text)
        if is_probably_content(value):
            return True
        noise = ("上一章", "下一章", "章节目录", "加入书签", "返回顶部", "点击切换")
        return len(value) >= 10 and sum(fragment in value for fragment in noise) <= 1

    @classmethod
    def _clean_chapter_title(cls, title: str) -> str:
        value = normalize_text(title)
        value = re.sub(r"\s*[（(]\s*\d+\s*/\s*\d+\s*[）)]\s*$", "", value)
        value = re.sub(r"\s+章节免费阅读.*$", "", value)
        value = re.sub(r"\s*[_-].*$", "", value) if "第" not in value[:3] else value
        return normalize_text(value)





    @staticmethod
    def _chapter_base_id(href: str) -> str:
        match = re.search(r"/(\d+)(?:_\d+)?\.html(?:[?#].*)?$", href or "")
        return match.group(1) if match else ""

    @staticmethod
    def _chapter_page_no(href: str) -> int:
        match = re.search(r"/\d+_(\d+)\.html(?:[?#].*)?$", href or "")
        return int(match.group(1)) if match else 1

