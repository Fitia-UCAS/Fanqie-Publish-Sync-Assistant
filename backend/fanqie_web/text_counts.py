from __future__ import annotations

import re

from backend.novel.text_cleaning import normalize_novel_body

_WHITESPACE_CHAR_RE = re.compile(r"[ \f\n\r\t\v\u00a0\u1680\u180e\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]")


def count_non_whitespace_chars(text: str) -> int:
    value = text or ""
    total_utf16_units = len(value.encode("utf-16-le")) // 2
    whitespace_utf16_units = sum(
        len(match.group(0).encode("utf-16-le")) // 2
        for match in _WHITESPACE_CHAR_RE.finditer(value)
    )
    return total_utf16_units - whitespace_utf16_units


def chapter_len(text: str) -> int:
    return count_non_whitespace_chars(normalize_novel_body(text or ""))


def word_count_tolerance(expected: int) -> int:
    return max(120, int(expected * 0.12))


def is_platform_count_compatible(actual: int, expected: int) -> bool:
    actual = int(actual)
    expected = int(expected)

    if expected <= 0:
        return actual <= 0

    if abs(actual - expected) <= word_count_tolerance(expected):
        return True

    if 900 <= expected <= 1500 and 900 <= actual <= 1500:
        return True

    ratio = actual / max(expected, 1)
    return 0.85 <= ratio <= 1.15


def is_row_count_compatible(row: dict | None, expected: int) -> bool:
    if not row:
        return False

    actual = row.get("word_count")
    if actual is None:
        return False

    try:
        return is_platform_count_compatible(int(actual), int(expected))
    except (ValueError, TypeError):
        return False


__all__ = [
    "chapter_len",
    "count_non_whitespace_chars",
    "word_count_tolerance",
    "is_platform_count_compatible",
    "is_row_count_compatible",
]
