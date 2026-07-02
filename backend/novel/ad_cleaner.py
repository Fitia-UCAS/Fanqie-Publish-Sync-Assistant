from __future__ import annotations


import re

AD_PATTERNS = [
    r"(?im)^.*最新网址.*$",
    r"(?im)^.*手机用户请浏览.*$",
    r"(?im)^.*请收藏本站.*$",
    r"(?im)^.*本章未完.*$",
    r"(?im)^.*点击下一页继续阅读.*$",
    r"(?im)^.*www\.[a-z0-9.-]+\.[a-z]{2,}.*$",
]


def clean_ad_text(text: str) -> str:
    cleaned = str(text or "")
    for pattern in AD_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.strip() + "\n"


def ad_profiles() -> list[dict[str, str]]:
    return [
        {"key": "default", "name": "默认"},
        {"key": "mimiread", "name": "通用小说站"},
    ]


