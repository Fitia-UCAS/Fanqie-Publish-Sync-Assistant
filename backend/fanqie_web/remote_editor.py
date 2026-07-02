from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Locator, Page


@dataclass(slots=True)
class RemoteChapterEditor:
    page: Page
    chapter_no_loc: Locator
    title_loc: Locator
    body_loc: Locator
    created: bool = True
    opened_new_page: bool = False


__all__ = ["RemoteChapterEditor"]
