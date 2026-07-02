from __future__ import annotations

import re
from typing import Callable

from backend.crawling.clean import normalize_text
from backend.crawling.records import ChapterContent, ChapterLink


TitleCleaner = Callable[[str], str]


def headers_with_referer(default_headers: Callable[[str], dict[str, str]], site_root: Callable[[str], str], url: str, referer: str) -> dict[str, str]:
    headers = default_headers(url)
    headers["Referer"] = referer or f"{site_root(url)}/"
    return headers


def chapter_fetch_result(chapter: ChapterLink, fetch_content: Callable[[], tuple[str, str]]) -> ChapterContent:
    try:
        title, content = fetch_content()
        if content:
            return ChapterContent(chapter.index, title, content, chapter.url, "html")
        return ChapterContent(chapter.index, chapter.title, "", chapter.url, "html", False, "正文为空")
    except Exception as exc:
        return ChapterContent(chapter.index, chapter.title, "", chapter.url, "html", False, str(exc))


def prefer_clean_title(current: str, candidate: str, clean_title: TitleCleaner) -> str:
    current_clean = clean_title(current)
    candidate_clean = clean_title(candidate)
    return candidate_clean or current_clean


def content_compare_key(text: str) -> str:
    value = re.sub(r"\s+", "", text or "")
    value = re.sub(r"[：:，,。.!！?？、（）()\[\]【】《》\"'“”‘’]+", "", value)
    return value


def remove_embedded_title_lines(lines: list[str], title: str) -> list[str]:
    result = list(lines)
    title_key = content_compare_key(title)
    while result and not result[0].strip():
        result.pop(0)
    if result and content_compare_key(result[0]) == title_key:
        result.pop(0)
    return result


def merge_page_texts(page_texts: list[str], title: str) -> str:
    merged_lines: list[str] = []
    title_key = content_compare_key(title)
    for page_text in page_texts:
        for line in normalize_text(page_text).split("\n"):
            stripped = line.strip()
            if not stripped or content_compare_key(stripped) == title_key:
                continue
            merged_lines.append(stripped)
    return normalize_text("\n".join(merged_lines))


def renumber_unique_chapter_links(chapters: list[ChapterLink]) -> list[ChapterLink]:
    seen: set[str] = set()
    result: list[ChapterLink] = []
    for chapter in chapters:
        key = chapter.chapter_id or chapter.url
        if key in seen:
            continue
        seen.add(key)
        chapter.index = len(result) + 1
        result.append(chapter)
    return result
