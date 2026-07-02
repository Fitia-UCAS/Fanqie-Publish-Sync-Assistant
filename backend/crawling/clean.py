from __future__ import annotations


import re


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ").replace("&nbsp;", " ")

    lines: list[str] = []
    blank_count = 0
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            blank_count += 1
            if blank_count <= 1:
                lines.append("")
            continue
        blank_count = 0
        lines.append(line)
    return "\n".join(lines).strip()


def clean_title(text: str, fallback: str = "未命名小说") -> str:
    value = normalize_text(text)
    bracketed = re.search(r"《([^《》]+)》", value)
    if bracketed:
        return normalize_text(bracketed.group(1)) or fallback
    value = re.sub(r"最新章节.*$", "", value)
    value = re.sub(r"全文.*$", "", value)
    value = re.sub(r"_.*$", "", value)
    value = re.sub(r"[《》]", "", value)
    return normalize_text(value) or fallback


def is_probably_content(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    noise = (
        "目录加载中",
        "阅读进度",
        "加载内容失败",
        "章节加载失败",
        "正在努力加载目录",
        "上一章",
        "下一章",
        "返回书页",
        "回到首页",
    )
    hits = sum(fragment in text for fragment in noise)
    return not (hits >= 2 and len(text) < 1000)


