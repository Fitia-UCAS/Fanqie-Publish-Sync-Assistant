from __future__ import annotations


import re

FILENAME_CHAR_TRANSLATION = str.maketrans(
    {
        "<": "＜",
        ">": "＞",
        ':': "：",
        '"': "＂",
        "/": "／",
        "\\": "＼",
        "|": "｜",
        "?": "？",
        "*": "＊",
        "\n": " ",
        "\r": " ",
        "\t": " ",
    }
)
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, *, fallback: str = "untitled", max_length: int = 80) -> str:
    cleaned = str(name or "").strip().translate(FILENAME_CHAR_TRANSLATION)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    cleaned = cleaned[:max_length].rstrip("._ ") or fallback
    if cleaned.upper() in RESERVED_WINDOWS_NAMES:
        cleaned = f"{cleaned}_"
    return cleaned


