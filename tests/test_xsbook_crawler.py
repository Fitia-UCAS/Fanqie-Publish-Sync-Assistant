from __future__ import annotations

from typing import Any

from backend.crawling.records import SiteAdapterPolicy, ChapterLink, NovelCatalog
from backend.crawling.sites.xsbook import XsbookAdapter


class FakeClient:

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.urls: list[str] = []
        self.headers: list[dict[str, str] | None] = []

    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        self.urls.append(url)
        self.headers.append(headers)
        return self.pages[url]


def make_adapter(pages: dict[str, str]) -> XsbookAdapter:
    return XsbookAdapter(FakeClient(pages), SiteAdapterPolicy())


def test_xsbook_adapter_lives_in_own_site_package() -> None:
    assert XsbookAdapter.__module__.endswith("sites.xsbook")
    assert XsbookAdapter.site_key == "xsbook"
    assert any("Sec-Fetch-Mode" in key for key in XsbookAdapter.default_headers("http://www.xsbook.org/215_215658/"))


def test_xsbook_catalog_uses_full_catalog_after_latest_section() -> None:
    catalog_url = "http://www.xsbook.org/215_215658/"
    html = """
    <html><body>
      <div id="info"><h1>斗罗：看我日记，她们疯狂开挂</h1></div>
      <div id="list"><dl>
        <dt>斗罗：看我日记，她们疯狂开挂最新章节</dt>
        <a href="/215_215658/105147485.html" title="第756章 继续跑啊" rel="chapter"><dd>第756章 继续跑啊</dd></a>
        <dt>斗罗：看我日记，她们疯狂开挂全部章节目录（共756章）</dt>
        <a href="/215_215658/103282002.html" title="第1章 你已有被密室之道" rel="chapter"><dd>第1章 你已有被密室之道</dd></a>
        <a href="/215_215658/103282003.html" title="第2章 奖励发放终于站起来了" rel="chapter"><dd>第2章 奖励发放终于站起来了</dd></a>
      </dl></div>
    </body></html>
    """

    catalog = make_adapter({catalog_url: html}).fetch_catalog(catalog_url)

    assert catalog.title == "斗罗：看我日记，她们疯狂开挂"
    assert [chapter.index for chapter in catalog.chapters] == [1, 2]
    assert [chapter.title for chapter in catalog.chapters] == ["第1章 你已有被密室之道", "第2章 奖励发放终于站起来了"]
    assert all("第756章" not in chapter.title for chapter in catalog.chapters)


def test_xsbook_chapter_fetch_merges_paginated_pages_without_page_suffix() -> None:
    first_url = "http://www.xsbook.org/215_215658/103282002.html"
    second_url = "http://www.xsbook.org/215_215658/103282002_2.html"
    long_line_1 = "武魂城里发生了很多事情，主角认真记录日记内容，字数足够长，可以通过正文有效性判断。"
    long_line_2 = "第二页继续同一章内容，应该合并在同一个章节正文下面，并且不写入任何页码提示。"
    pages = {
        first_url: f"""
        <html><body><article class="box_con">
          <h1 class="bookname">第1章 你已有被密室之道（1 / 2）</h1>
          <div id="chaptercontent"><div id="booktxt">
            <p>第1章 你已有被密室之道</p><p>{long_line_1}</p>
          </div></div>
          <div class="bottem2"><a id="next_url" class="block" href="/215_215658/103282002_2.html"> 下一页</a></div>
        </article></body></html>
        """,
        second_url: f"""
        <html><body><article class="box_con">
          <h1 class="bookname">第1章 你已有被密室之道（2 / 2）</h1>
          <div id="chaptercontent"><div id="booktxt"><p>{long_line_2}</p></div></div>
          <div class="bottem2"><a id="next_url" class="block" href="/215_215658/103282003.html">下一章</a></div>
        </article></body></html>
        """,
    }
    adapter = make_adapter(pages)
    chapter = ChapterLink(1, "第1章 你已有被密室之道", "103282002", first_url, "html")
    catalog = NovelCatalog("斗罗：看我日记，她们疯狂开挂", "215_215658", "http://www.xsbook.org/215_215658/", [chapter])

    result = adapter.fetch_chapter(catalog, chapter)

    assert result.ok
    assert result.title == "第1章 你已有被密室之道"
    assert long_line_1 in result.content
    assert long_line_2 in result.content
    assert "（1 / 2）" not in result.title + result.content
    assert "（2 / 2）" not in result.title + result.content
    assert result.content.count("第1章 你已有被密室之道") == 0

from pathlib import Path
from typing import cast

from backend.crawling.records import ChapterContent, NovelCrawlerRequest
from backend.crawling.crawler import NovelCrawler
from backend.novel.source import parse_chapter_blocks


class ResumeFakeAdapter:

    site_key = "resume_fake"
    site_name = "断点补抓测试站点"
    domains = ("resume.example",)
    fetched: list[int] = []

    def __init__(self, _client: object, _options: object | None = None) -> None:
        return None

    @classmethod
    def supports(cls, _url: str) -> bool:
        return True

    @classmethod
    def default_headers(cls, _novel_url: str) -> dict[str, str]:
        return {}

    def fetch_catalog(self, novel_url: str) -> NovelCatalog:
        chapters = [
            ChapterLink(1, "第1章 旧一", "1", "http://resume.example/1.html"),
            ChapterLink(2, "第2章 新二", "2", "http://resume.example/2.html"),
            ChapterLink(3, "第3章 旧三", "3", "http://resume.example/3.html"),
            ChapterLink(4, "第4章 新四", "4", "http://resume.example/4.html"),
        ]
        return NovelCatalog("断点补抓", "resume", novel_url, chapters)

    def fetch_chapter(self, _catalog: NovelCatalog, chapter: ChapterLink) -> ChapterContent:
        self.fetched.append(chapter.index)
        return ChapterContent(chapter.index, chapter.title, f"新正文{chapter.index}", chapter.url, chapter.source, True, "")


def test_crawler_only_fetches_missing_chapters_and_merges_existing_txt(tmp_path: Path, monkeypatch: object) -> None:
    output = tmp_path / "断点补抓.txt"
    output.write_text("第1章 旧一\n\n旧正文1\n\n第3章 旧三\n\n旧正文3\n", encoding="utf-8")
    ResumeFakeAdapter.fetched = []
    monkeypatch.setattr("backend.crawling.crawler.adapter_for_url", _resume_fake_adapter_type)

    result = NovelCrawler().crawl_to_txt(
        NovelCrawlerRequest(
            novel_url="http://resume.example/book/",
            output_file=output,
            start=1,
            end=4,
            max_workers=1,
            request_delay_min=0,
            request_delay_max=0,
        )
    )

    text = output.read_text(encoding="utf-8")
    chapters = parse_chapter_blocks(text)
    assert result.ok
    assert result.existing == 2
    assert result.missing == 2
    assert result.downloaded == 2
    assert ResumeFakeAdapter.fetched == [2, 4]
    assert [chapter.number for chapter in chapters] == [1, 2, 3, 4]
    assert "旧正文1" in text
    assert "旧正文3" in text
    assert "新正文2" in text
    assert "新正文4" in text


def test_crawler_skips_network_when_existing_txt_is_complete(tmp_path: Path, monkeypatch: object) -> None:
    output = tmp_path / "完整.txt"
    output.write_text("第1章 一\n\n旧正文1\n\n第2章 二\n\n旧正文2\n\n第3章 三\n\n旧正文3\n\n第4章 四\n\n旧正文4\n", encoding="utf-8")
    ResumeFakeAdapter.fetched = []
    monkeypatch.setattr("backend.crawling.crawler.adapter_for_url", _resume_fake_adapter_type)

    result = NovelCrawler().crawl_to_txt(
        NovelCrawlerRequest(
            novel_url="http://resume.example/book/",
            output_file=output,
            start=1,
            end=4,
            max_workers=1,
            request_delay_min=0,
            request_delay_max=0,
        )
    )

    assert result.ok
    assert result.existing == 4
    assert result.missing == 0
    assert result.downloaded == 0
    assert ResumeFakeAdapter.fetched == []


def _resume_fake_adapter_type(_url: str) -> type[ResumeFakeAdapter]:
    return cast(type[ResumeFakeAdapter], ResumeFakeAdapter)

from backend.crawling.sites.renrenreshu import RenrenreshuAdapter


def make_renren_adapter(pages: dict[str, str]) -> RenrenreshuAdapter:
    return RenrenreshuAdapter(FakeClient(pages), SiteAdapterPolicy())


def test_renrenreshu_catalog_reads_paginated_directory_pages() -> None:
    first_url = "https://www.renrenreshu.com/chapter/195857.html"
    second_url = "https://www.renrenreshu.com/chapter/195857-2.html"
    pages = {
        first_url: """
        <html><head><title>斗罗：看我日记，她们疯狂开挂_人人热书</title></head><body>
          <div class="chapListBody"><ul>
            <li><a href="/book/195857-1.html">第1章 你已有被密室之道</a></li>
            <li><a href="/book/195857-2.html">第2章 奖励发放终于站起来了</a></li>
          </ul></div>
          <div class="page2"><span class="chapter_page"><select>
            <option value="1">1-100章</option>
            <option value="2">101-200章</option>
          </select></span></div>
        </body></html>
        """,
        second_url: """
        <html><head><title>斗罗：看我日记，她们疯狂开挂_人人热书</title></head><body>
          <div class="chapListBody"><ul>
            <li><a href="/book/195857-101.html">第101章 第二页第一章</a></li>
            <li><a href="/book/195857-102.html">第102章 第二页第二章</a></li>
          </ul></div>
        </body></html>
        """,
    }

    catalog = make_renren_adapter(pages).fetch_catalog(first_url)

    assert catalog.title == "斗罗：看我日记，她们疯狂开挂"
    assert [chapter.index for chapter in catalog.chapters] == [1, 2, 101, 102]
    assert catalog.chapters[2].title == "第101章 第二页第一章"
    assert catalog.chapters[2].url == "https://www.renrenreshu.com/book/195857-101.html"


def test_renrenreshu_chapter_fetch_merges_inner_chapter_pages() -> None:
    first_url = "https://www.renrenreshu.com/book/195857-1.html"
    second_url = "https://www.renrenreshu.com/book/195857-1-2.html"
    long_line_1 = "武魂城里发生了很多事情，主角认真记录日记内容，字数足够长，可以通过正文有效性判断。"
    long_line_2 = "第二页继续同一章内容，应该合并在同一个章节正文下面，并且不写入任何页码提示。"
    pages = {
        first_url: f"""
        <html><body>
          <h1 class="title">第1章 你已有被密室之道</h1>
          <div class="content"><p>第1章 你已有被密室之道</p><p>{long_line_1}</p></div>
          <div class="btnW"><a href="/chapter/195857.html" class="btnYell">目录</a><a href="/book/195857-1-2.html" class="btnGray">下一页</a></div>
        </body></html>
        """,
        second_url: f"""
        <html><body>
          <h1 class="title">第1章 你已有被密室之道</h1>
          <div class="content"><p>{long_line_2}</p></div>
          <div class="btnW"><a href="/book/195857-2.html" class="btnGray">下一章</a></div>
        </body></html>
        """,
    }
    adapter = make_renren_adapter(pages)
    chapter = ChapterLink(1, "第1章 你已有被密室之道", "1", first_url, "html")
    catalog = NovelCatalog("斗罗：看我日记，她们疯狂开挂", "195857", "https://www.renrenreshu.com/chapter/195857.html", [chapter])

    result = adapter.fetch_chapter(catalog, chapter)

    assert result.ok
    assert result.title == "第1章 你已有被密室之道"
    assert long_line_1 in result.content
    assert long_line_2 in result.content
    assert result.content.count("第1章 你已有被密室之道") == 0

from backend.crawling.records import CrawlErrorType
from backend.crawling.write_order import OrderedChapterWriteBuffer
from backend.crawling.sites.lanmeiwen import LanmeiwenAdapter
from backend.settings import _merge_default


class FakeChapterWriter:
    def __init__(self) -> None:
        self.started = False
        self.indexes: list[int] = []

    def start(self) -> None:
        self.started = True

    def append_chapter(self, chapter: ChapterContent) -> bool:
        self.indexes.append(chapter.index)
        return True


def test_write_buffer_flushes_cached_chapters_in_order_and_finalize_logs_writes() -> None:
    writer = FakeChapterWriter()
    written: list[int] = []
    chapters = [ChapterLink(1, "一", "1", "u1"), ChapterLink(2, "二", "2", "u2"), ChapterLink(3, "三", "3", "u3")]
    buffer = OrderedChapterWriteBuffer(
        cast(object, writer),
        chapters,
        lambda chapter: bool(chapter and chapter.ok and chapter.content),
        on_write=written.append,
    )

    assert writer.started
    assert buffer.add_fetched_chapter(ChapterContent(2, "二", "正文2")) == []
    assert writer.indexes == []
    assert buffer.add_fetched_chapter(ChapterContent(1, "一", "正文1")) == [1, 2]
    assert writer.indexes == [1, 2]
    assert written == [1, 2]
    assert buffer.finalize({3: ChapterContent(3, "三", "正文3")}) == [3]
    assert writer.indexes == [1, 2, 3]


class BlockedLanmeiwenAdapter(LanmeiwenAdapter):
    html_called = False

    def _fetch_chapter_api(self, _novel_id: str, _chapter: ChapterLink) -> tuple[str, str]:
        import requests

        response = requests.Response()
        response.status_code = 429
        error = requests.HTTPError("HTTP 429")
        error.response = response
        raise error

    def _fetch_chapter_html(self, _chapter: ChapterLink) -> tuple[str, str]:
        self.html_called = True
        return "标题", "HTML 正文"


class EmptyApiLanmeiwenAdapter(LanmeiwenAdapter):
    html_called = False

    def _fetch_chapter_api(self, _novel_id: str, _chapter: ChapterLink) -> tuple[str, str]:
        return "标题", ""

    def _fetch_chapter_html(self, _chapter: ChapterLink) -> tuple[str, str]:
        self.html_called = True
        return "标题", "HTML 正文"


class FakeHttpClient:
    return_value = ""


def test_lanmeiwen_rate_limit_does_not_use_html_fallback() -> None:
    adapter = BlockedLanmeiwenAdapter(cast(object, FakeHttpClient()), SiteAdapterPolicy(html_fallback=True))
    result = adapter.fetch_chapter(NovelCatalog("书", "abc", "http://www.lanmeiwen.com/novel/abc.html", []), ChapterLink(1, "一", "1", "u"))

    assert not result.ok
    assert result.error_type == CrawlErrorType.RATE_LIMITED
    assert not adapter.html_called


def test_lanmeiwen_empty_api_uses_html_fallback() -> None:
    adapter = EmptyApiLanmeiwenAdapter(cast(object, FakeHttpClient()), SiteAdapterPolicy(html_fallback=True))
    result = adapter.fetch_chapter(NovelCatalog("书", "abc", "http://www.lanmeiwen.com/novel/abc.html", []), ChapterLink(1, "一", "1", "u"))

    assert result.ok
    assert result.source == "html"
    assert result.content == "HTML 正文"
    assert adapter.html_called


def test_config_normalization_preserves_unknown_fields() -> None:
    old_key = "".join(("allow", "Html", "Preview"))
    config = _merge_default({"web_crawler": {old_key: True, "detailedLog": True}, "customRoot": {"x": 1}})

    assert config["web_crawler"][old_key] is True
    assert config["web_crawler"]["detailedLog"] is True
    assert config["customRoot"] == {"x": 1}
