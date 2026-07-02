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
    )


class RenrenreshuAdapter(NovelSiteAdapter):

    site_key = "renrenreshu"
    site_name = "人人热书"
    domains = ("renrenreshu.com", "www.renrenreshu.com")
    base_url = "https://www.renrenreshu.com"
    MAX_CATALOG_PAGES = 80
    MAX_CHAPTER_PAGES = 20
    _browser_lock = threading.Lock()

    @classmethod
    def default_headers(cls, novel_url: str) -> dict[str, str]:
        root = cls._site_root(novel_url)
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
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
        novel_id = self._novel_id(novel_url)
        catalog_url = self._catalog_url(novel_url)
        html = self._fetch_text(catalog_url, f"{self._site_root(catalog_url)}/")
        title = self._extract_catalog_title(html)
        chapters = self._extract_catalog_chapters(html, catalog_url, novel_id)
        page_count = min(self._catalog_page_count(html), self.MAX_CATALOG_PAGES)
        if page_count > 1:
            chapters = self._merge_catalog_pages(chapters, novel_id, catalog_url, page_count)
        chapters = self._renumber(chapters)
        if not chapters:
            raise ValueError("目录页未解析到章节，请确认链接是人人热书的小说目录页。")
        return NovelCatalog(title=title, novel_id=novel_id, url=catalog_url, chapters=chapters)

    def fetch_chapter(self, catalog: NovelCatalog, chapter: ChapterLink) -> ChapterContent:
        return chapter_fetch_result(chapter, lambda: self._fetch_chapter_pages(catalog, chapter))

    def _merge_catalog_pages(
        self,
        chapters: list[ChapterLink],
        novel_id: str,
        catalog_url: str,
        page_count: int,
    ) -> list[ChapterLink]:
        result = list(chapters)
        for page in range(2, page_count + 1):
            page_chapters = self._fetch_catalog_page(novel_id, catalog_url, page)
            result.extend(page_chapters)
        if len(result) > len(chapters):
            return result
        if self.options.html_fallback:
            browser_chapters = self._fetch_catalog_pages_with_browser(catalog_url, novel_id, page_count)
            if len(browser_chapters) > len(chapters):
                return browser_chapters
        return self._extend_catalog_from_known_page_count(chapters, novel_id, page_count)

    def _fetch_catalog_page(self, novel_id: str, catalog_url: str, page: int) -> list[ChapterLink]:
        for page_url in self._catalog_page_candidates(novel_id, catalog_url, page):
            try:
                html = self._fetch_text(page_url, catalog_url)
            except Exception:
                continue
            chapters = self._extract_catalog_chapters(html, page_url, novel_id)
            if self._has_catalog_page(chapters, page):
                return chapters
        return []

    def _fetch_catalog_pages_with_browser(self, catalog_url: str, novel_id: str, page_count: int) -> list[ChapterLink]:
        try:
            with self._browser_lock:
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        context = browser.new_context(
                            user_agent=self.default_headers(catalog_url)["User-Agent"],
                            locale="zh-CN",
                            extra_http_headers={"Referer": f"{self._site_root(catalog_url)}/"},
                        )
                        page = context.new_page()
                        page.goto(catalog_url, wait_until="domcontentloaded", timeout=max(5000, self.client.options.timeout * 1000))
                        result: list[ChapterLink] = []
                        current_html = page.content()
                        result.extend(self._extract_catalog_chapters(current_html, catalog_url, novel_id))
                        for page_no in range(2, page_count + 1):
                            if not self._switch_catalog_page(page, page_no):
                                break
                            current_html = page.content()
                            page_chapters = self._extract_catalog_chapters(current_html, catalog_url, novel_id)
                            if not self._has_catalog_page(page_chapters, page_no):
                                break
                            result.extend(page_chapters)
                        return self._renumber(result)
                    finally:
                        browser.close()
        except Exception:
            return []

    @staticmethod
    def _switch_catalog_page(page: object, page_no: int) -> bool:
        try:
            select = page.locator(".chapter_page select").first
            if select.count() > 0:
                select.select_option(str(page_no))
                page.wait_for_timeout(1000)
                return True
        except Exception:
            pass
        try:
            next_button = page.locator(".page2 .next, .chapter_page .next, a.next").first
            if next_button.count() <= 0:
                return False
            next_button.click()
            page.wait_for_timeout(1000)
            return True
        except Exception:
            return False

    def _fetch_chapter_pages(self, catalog: NovelCatalog, chapter: ChapterLink) -> tuple[str, str]:
        url = chapter.url
        referer = catalog.url
        visited: set[str] = set()
        page_texts: list[str] = []
        title = chapter.title

        for page_no in range(self.MAX_CHAPTER_PAGES):
            if url in visited:
                break
            visited.add(url)
            html = self._fetch_text(url, referer)
            page_title = self._extract_chapter_title(html, title)
            title = prefer_clean_title(title, page_title, self._clean_chapter_title)
            page_text = self._extract_chapter_content(html, title)
            if page_text:
                page_texts.append(page_text)
            next_url = self._next_same_chapter_url(html, url, chapter.chapter_id, page_no + 1)
            if not next_url:
                break
            referer = url
            url = next_url

        content = merge_page_texts(page_texts, title)
        return title, content

    def _fetch_text(self, url: str, referer: str) -> str:
        return self.client.get_text(self._canonical_url(url), headers=headers_with_referer(self.default_headers, self._site_root, url, referer))


    def _catalog_url(self, novel_url: str) -> str:
        novel_id = self._novel_id(novel_url)
        return f"{self._site_root(novel_url)}/chapter/{novel_id}.html"

    @classmethod
    def _canonical_url(cls, url: str) -> str:
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        if parsed.netloc.lower().endswith("renrenreshu.com"):
            return parsed._replace(scheme="https", netloc="www.renrenreshu.com").geturl()
        return parsed._replace(scheme=parsed.scheme or "https").geturl()

    @staticmethod
    def _site_root(url: str) -> str:
        parsed = urlparse(url)
        host = (parsed.netloc or "www.renrenreshu.com").lower()
        if host.endswith("renrenreshu.com"):
            return "https://www.renrenreshu.com"
        scheme = parsed.scheme or "https"
        return f"{scheme}://{host}"

    @staticmethod
    def _novel_id(novel_url: str) -> str:
        path = urlparse(novel_url).path
        patterns = (
            r"/chapter/(\d+)\.html",
            r"/book/(\d+)\.html",
            r"/book/(\d+)-\d+(?:-\d+)?\.html",
        )
        for pattern in patterns:
            match = re.search(pattern, path)
            if match:
                return match.group(1)
        raise ValueError(f"无法识别小说 ID：{novel_url}")

    def _extract_catalog_title(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        meta = soup.select_one("meta[name='keywords'], meta[property='og:title']")
        if meta and meta.get("content"):
            title = str(meta.get("content")).split(",")[0]
            if title:
                return normalize_text(title)
        if soup.title:
            return clean_title(soup.title.get_text())
        return "未命名小说"

    def _extract_catalog_chapters(self, html: str, catalog_url: str, novel_id: str) -> list[ChapterLink]:
        soup = BeautifulSoup(html, "lxml")
        anchors = soup.select(f".chapListBody a[href*='/book/{novel_id}-']")
        if not anchors:
            anchors = soup.select(f"a[href*='/book/{novel_id}-']")
        chapters: list[ChapterLink] = []
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            chapter_number = self._chapter_number_from_href(href, novel_id)
            if chapter_number <= 0:
                continue
            title = self._clean_chapter_title(anchor.get_text(" ", strip=True))
            if not title:
                title = f"第{chapter_number}章"
            chapters.append(
                ChapterLink(
                    chapter_number,
                    title,
                    str(chapter_number),
                    self._canonical_url(urljoin(catalog_url, href)),
                    "html",
                )
            )
        return chapters

    @staticmethod
    def _catalog_page_count(html: str) -> int:
        soup = BeautifulSoup(html, "lxml")
        values: list[int] = []
        for option in soup.select(".chapter_page option, .page2 option"):
            value = str(option.get("value") or "").strip()
            if value.isdigit():
                values.append(int(value))
        for anchor in soup.select(".chapter_page [data-p], .page [data-p]"):
            value = str(anchor.get("data-p") or "").strip()
            if value.isdigit():
                values.append(int(value))
        return max(values) if values else 1

    def _catalog_page_candidates(self, novel_id: str, catalog_url: str, page: int) -> list[str]:
        root = self._site_root(catalog_url)
        return [
            f"{root}/chapter/{novel_id}-{page}.html",
            f"{root}/chapter/{novel_id}_{page}.html",
            f"{root}/chapter/{novel_id}/{page}.html",
            f"{root}/chapter/{novel_id}.html?page={page}",
            f"{root}/chapter/{novel_id}.html?p={page}",
            f"{root}/chapter/{novel_id}.html?cp={page}",
            f"{root}/chapter/{novel_id}.html?chapter_page={page}",
            f"{root}/ajax/chapter.html?aid={novel_id}&page={page}",
            f"{root}/ajax/chapterlist.html?aid={novel_id}&page={page}",
            f"{root}/ajax/chapter_list.html?aid={novel_id}&page={page}",
            f"{root}/chapterlist.html?aid={novel_id}&page={page}",
        ]

    @staticmethod
    def _has_catalog_page(chapters: list[ChapterLink], page: int) -> bool:
        start = (page - 1) * 100 + 1
        end = page * 100
        return any(start <= chapter.index <= end for chapter in chapters)

    def _extend_catalog_from_known_page_count(
        self,
        chapters: list[ChapterLink],
        novel_id: str,
        page_count: int,
    ) -> list[ChapterLink]:
        by_index = {chapter.index: chapter for chapter in chapters}
        final_index = page_count * 100
        for index in range(1, final_index + 1):
            if index in by_index:
                continue
            title = f"第{index}章"
            by_index[index] = ChapterLink(
                index,
                title,
                str(index),
                f"{self.base_url}/book/{novel_id}-{index}.html",
                "html",
            )
        return [by_index[index] for index in sorted(by_index)]

    def _extract_chapter_title(self, html: str, fallback_title: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        for selector in ("h1.title", ".titBox h1", "h1"):
            node = soup.select_one(selector)
            if node:
                title = self._clean_chapter_title(node.get_text(" ", strip=True))
                if title:
                    return title
        if soup.title:
            title = self._clean_chapter_title(clean_title(soup.title.get_text(), fallback_title))
            if title:
                return title
        return self._clean_chapter_title(fallback_title)

    def _extract_chapter_content(self, html: str, title: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one(".content") or soup.select_one("#content") or soup.select_one("article")
        if not node:
            return ""
        for tag in node.select("script, style, iframe, ins, .ad, .ads, .advert, .advertisement"):
            tag.decompose()
        for tag in node.select("i.icon"):
            tag.replace_with("")
        lines = [normalize_text(item.get_text(" ", strip=True)) for item in node.select("p")]
        if not any(lines):
            lines = normalize_text(node.get_text("\n", strip=True)).split("\n")
        lines = remove_embedded_title_lines(lines, title)
        text = normalize_text("\n".join(line for line in lines if line.strip()))
        return text if self._looks_like_chapter_text(text) else ""

    def _next_same_chapter_url(self, html: str, current_url: str, chapter_id: str, current_page: int) -> str:
        soup = BeautifulSoup(html, "lxml")
        for anchor in soup.select(".btnW a, a.btnGray, a[href*='/book/']"):
            href = (anchor.get("href") or "").strip()
            text = normalize_text(anchor.get_text(" ", strip=True))
            if not href or href.startswith("javascript:"):
                continue
            if "下一页" not in text:
                continue
            if self._chapter_number_from_href(href, self._novel_id_from_book_url(current_url)) != int(chapter_id):
                continue
            page_no = self._chapter_page_no(href)
            if page_no > current_page:
                return self._canonical_url(urljoin(current_url, href))
        return ""

    @staticmethod
    def _chapter_number_from_href(href: str, novel_id: str) -> int:
        match = re.search(rf"/book/{re.escape(novel_id)}-(\d+)(?:-\d+)?\.html(?:[?#].*)?$", href or "")
        return int(match.group(1)) if match else 0

    @staticmethod
    def _novel_id_from_book_url(url: str) -> str:
        match = re.search(r"/book/(\d+)-\d+(?:-\d+)?\.html", urlparse(url).path)
        return match.group(1) if match else ""

    @staticmethod
    def _chapter_page_no(href: str) -> int:
        match = re.search(r"/book/\d+-\d+-(\d+)\.html(?:[?#].*)?$", href or "")
        return int(match.group(1)) if match else 1

    @classmethod
    def _clean_chapter_title(cls, title: str) -> str:
        value = normalize_text(title)
        value = re.sub(r"\s*[（(]\s*\d+\s*/\s*\d+\s*[）)]\s*$", "", value)
        value = re.sub(r"\s*[_-].*$", "", value) if "第" not in value[:3] else value
        return normalize_text(value)




    @staticmethod
    def _looks_like_chapter_text(text: str) -> bool:
        value = normalize_text(text)
        if is_probably_content(value):
            return True
        noise = ("上一章", "下一章", "章节目录", "加入书架", "错乱漏章", "新书推荐", "热门推荐")
        return len(value) >= 20 and sum(fragment in value for fragment in noise) <= 1


    @staticmethod
    def _renumber(chapters: list[ChapterLink]) -> list[ChapterLink]:
        by_index: dict[int, ChapterLink] = {}
        for chapter in chapters:
            if chapter.index <= 0 or chapter.index in by_index:
                continue
            by_index[chapter.index] = chapter
        return [by_index[index] for index in sorted(by_index)]
