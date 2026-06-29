from __future__ import annotations

import re
from collections import Counter
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso


QUALITY_DIMENSIONS = [
    "length", "paragraphs", "dialogue", "ending_hook", "blueprint", "repetition", "ai_smell", "scene_motion",
]


def local_quality_review(chapter_text: str, blueprint: dict[str, Any] | None = None, story_config: dict[str, Any] | None = None) -> dict[str, Any]:
    text = str(chapter_text or "").strip()
    blueprint = blueprint or {}
    story_config = story_config or {}
    issues: list[dict[str, Any]] = []
    suggestions: list[str] = []
    score = 100
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    dialogue_marks = len(re.findall(r"[“”]\s*|^\s*[\"']", text, re.M))
    dialogue_ratio = round(dialogue_marks / max(1, len(paras)), 3)
    ending = paras[-1] if paras else ""

    if cn_chars < 800:
        score -= 12
        issues.append(_issue("warning", "length", f"正文偏短：约 {cn_chars} 个中文字符。"))
        suggestions.append("补一段实质冲突或信息推进，不要只用心理活动凑字。")
    if len(paras) < 8:
        score -= 8
        issues.append(_issue("warning", "paragraphs", f"段落偏少：{len(paras)} 段。"))
    long_paras = [p for p in paras if len(p) > 650]
    if long_paras:
        score -= min(10, len(long_paras) * 3)
        issues.append(_issue("info", "paragraphs", f"存在 {len(long_paras)} 个超长段落，阅读压力偏高。"))
    if dialogue_ratio < 0.08 and len(paras) >= 10:
        score -= 6
        issues.append(_issue("info", "dialogue", "对话占比偏低，可能缺少人物交锋。"))
    if not _has_hook(ending):
        score -= 10
        issues.append(_issue("warning", "ending_hook", "章末追读钩子不明显。"))
        suggestions.append("章末补一个信息差、危险逼近、选择难题或反转线索。")
    required = _as_list(blueprint.get("must_cover_nodes"))
    if required:
        missing = [node for node in required if not _rough_hit(text, str(node))]
        if missing:
            score -= min(20, len(missing) * 6)
            issues.append(_issue("warning", "blueprint", "蓝图节点疑似未充分落地：" + "；".join(map(str, missing[:5]))))
    repeated = _repeated_phrases(text)
    if repeated:
        score -= min(12, len(repeated) * 3)
        issues.append(_issue("info", "repetition", "重复短语偏多：" + "，".join(repeated[:8])))
    smell = _ai_smell(text)
    if smell:
        score -= min(12, len(smell) * 3)
        issues.append(_issue("info", "ai_smell", "疑似 AI 味表达：" + "，".join(smell[:8])))
        suggestions.append("把总结式、口号式表达改成动作、对白和具体感官细节。")
    motion_hits = len(re.findall(r"忽然|猛地|转身|抬手|后退|冲|避开|推开|握住|望向|走进|离开|停下", text))
    if motion_hits < 4 and cn_chars > 1000:
        score -= 5
        issues.append(_issue("info", "scene_motion", "场景动作推进偏少，可能偏说明文。"))

    score = max(0, min(100, score))
    gate = "pass" if score >= 72 and not any(i["level"] == "error" for i in issues) else "needs_review"
    return {
        "ok": gate == "pass",
        "schema_version": 1,
        "checked_at": now_iso(),
        "score": score,
        "gate": gate,
        "dimensions": QUALITY_DIMENSIONS,
        "metrics": {
            "cn_chars": cn_chars,
            "paragraph_count": len(paras),
            "dialogue_ratio": dialogue_ratio,
            "ending_excerpt": ending[-120:],
        },
        "issues": issues,
        "suggestions": suggestions,
    }


def _issue(level: str, typ: str, message: str) -> dict[str, Any]:
    return {"level": level, "type": typ, "message": message}


def _has_hook(ending: str) -> bool:
    if not ending:
        return False
    return bool(re.search(r"[？?！!]|却|忽然|突然|竟|原来|只见|门外|身后|下一刻|血|信|声音|脚步|黑影|秘密|真相", ending[-180:]))


def _rough_hit(text: str, needle: str) -> bool:
    pieces = [x for x in re.split(r"[，,。；;、\s]+", needle) if len(x) >= 2]
    if not pieces:
        return True
    hits = sum(1 for p in pieces[:5] if p in text)
    return hits >= max(1, min(2, len(pieces)))


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _repeated_phrases(text: str) -> list[str]:
    cn = re.sub(r"\s+", "", text)
    grams = [cn[i:i + 4] for i in range(max(0, len(cn) - 3))]
    bad = []
    for phrase, count in Counter(grams).most_common(30):
        if count >= 5 and not re.fullmatch(r"[，。！？；、]+", phrase):
            bad.append(f"{phrase}×{count}")
    return bad[:10]


def _ai_smell(text: str) -> list[str]:
    patterns = [
        "这一刻", "毫无疑问", "命运的齿轮", "空气仿佛凝固", "眼神变得坚定", "心中暗暗发誓",
        "他知道", "不由得", "显然", "仿佛有什么东西", "一种说不出的", "无法形容的",
    ]
    found = []
    for p in patterns:
        c = text.count(p)
        if c >= 2:
            found.append(f"{p}×{c}")
    return found
