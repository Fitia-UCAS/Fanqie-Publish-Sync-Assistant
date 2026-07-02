from __future__ import annotations


import re


def fix_sentences(text: str, normalize_punctuation: bool = True, max_move_chars: int = 120) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if normalize_punctuation:
        value = value.translate(str.maketrans({"，": "，", "。": "。", "！": "！", "？": "？"}))
    value = re.sub(r"([^。！？……!?\n])\n([^\n第])", r"\1\2", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip() + "\n"


