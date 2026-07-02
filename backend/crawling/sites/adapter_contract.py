from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from backend.crawling.http import HttpClient
from backend.crawling.records import SiteAdapterPolicy, ChapterContent, ChapterLink, NovelCatalog


class NovelSiteAdapter(ABC):

    site_key = "unknown"
    site_name = "未知站点"
    domains: tuple[str, ...] = ()

    def __init__(self, client: HttpClient, options: SiteAdapterPolicy | None = None) -> None:
        self.client = client
        self.options = options or SiteAdapterPolicy()

    @classmethod
    def supports(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in cls.domains)

    @classmethod
    def default_headers(cls, novel_url: str) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": novel_url,
        }

    @abstractmethod
    def fetch_catalog(self, novel_url: str) -> NovelCatalog:
        raise NotImplementedError

    @abstractmethod
    def fetch_chapter(self, catalog: NovelCatalog, chapter: ChapterLink) -> ChapterContent:
        raise NotImplementedError
