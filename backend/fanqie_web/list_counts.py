from __future__ import annotations

import time
from typing import Callable, Protocol

from backend.fanqie_web.chapter_list import build_chapter_row_index
from backend.fanqie_web.text_counts import chapter_len, is_platform_count_compatible, word_count_tolerance
from backend.fanqie_web.ui_actions import wait_briefly_for_page_ready


class LocalChapter(Protocol):
    content: str


def verify_chapter_list_counts(
    page,
    *,
    chapter_manage_url: str,
    local_chapters: dict[int, LocalChapter],
    chapter_numbers: list[int],
    action_name: str = "操作",
    log: Callable[[str], None] = print,
) -> dict[int, str]:
    rows = build_chapter_row_index(page, chapter_manage_url, chapter_numbers, log=log)
    failures: dict[int, str] = {}
    for no in chapter_numbers:
        local = local_chapters[no]
        expected = chapter_len(local.content)
        row = rows.get(no)
        if not row:
            failures[no] = f"列表校验失败：没有在章节管理列表找到第 {no} 章。"
            continue
        actual = row.get("word_count")
        if actual is None:
            failures[no] = f"列表校验失败：第 {no} 章没有读到平台字数。列表行：{row.get('title') or row.get('text') or ''}"
            continue
        actual_int = int(actual)
        delta = abs(actual_int - expected)
        tolerance = word_count_tolerance(expected)
        if not is_platform_count_compatible(actual_int, expected):
            failures[no] = (
                f"列表校验失败：第 {no} 章平台列表字数 {actual}，本地约 {expected}，"
                f"差值 {delta} 超过允许范围。"
                f"这通常表示平台列表仍是旧内容，或该章只进入了编辑页/保存了草稿但没有真正完成{action_name}。"
            )
        elif delta > tolerance:
            log(f"列表校验通过：第 {no} 章平台字数 {actual}，本地约 {expected}，差异来自番茄字数统计口径。")
        else:
            log(f"列表校验通过：第 {no} 章平台字数 {actual}，本地约 {expected}。")
    return failures


def wait_for_chapter_list_counts(
    page,
    *,
    chapter_manage_url: str,
    local_chapters: dict[int, LocalChapter],
    chapter_numbers: list[int],
    action_name: str = "操作",
    log: Callable[[str], None] = print,
    max_wait_seconds: int = 120,
    interval_seconds: int = 20,
) -> dict[int, str]:
    max_wait_seconds = max(0, int(max_wait_seconds))
    interval_seconds = max(2, int(interval_seconds))
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0
    last_failures: dict[int, str] = {}

    while True:
        attempt += 1
        if attempt == 1:
            log(f"最终列表校验：{action_name}确认后先刷新章节管理列表；若平台缓存未刷新，会自动等待重试。")
        else:
            log(f"最终列表校验：第 {attempt} 次重试前刷新章节管理列表...")
        try:
            page.goto(chapter_manage_url, wait_until="domcontentloaded", timeout=60000)
            wait_briefly_for_page_ready(page)
        except Exception:
            pass

        failures = verify_chapter_list_counts(
            page,
            chapter_manage_url=chapter_manage_url,
            local_chapters=local_chapters,
            chapter_numbers=chapter_numbers,
            action_name=action_name,
            log=log,
        )
        if not failures:
            if attempt > 1:
                log(f"最终列表校验：等待刷新后通过，共尝试 {attempt} 次。")
            return {}

        last_failures = failures
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            log(f"最终列表校验：等待平台列表刷新超时，已尝试 {attempt} 次。")
            return last_failures

        wait_seconds = min(interval_seconds, max(1, int(remaining)))
        failed_numbers = ", ".join(str(no) for no in sorted(failures))
        log(f"最终列表校验暂未通过：第 {failed_numbers} 章列表字数可能还没刷新，等待 {wait_seconds} 秒后重试...")
        try:
            page.wait_for_timeout(wait_seconds * 1000)
        except Exception:
            time.sleep(wait_seconds)


def verify_single_chapter_count(
    page,
    *,
    chapter_no: int,
    chapter_manage_url: str,
    local: LocalChapter,
    action_name: str = "操作",
    log: Callable[[str], None] = print,
) -> None:
    failures = wait_for_chapter_list_counts(
        page,
        chapter_manage_url=chapter_manage_url,
        local_chapters={chapter_no: local},
        chapter_numbers=[chapter_no],
        action_name=action_name,
        log=log,
    )
    if failures:
        raise RuntimeError(failures[chapter_no])
