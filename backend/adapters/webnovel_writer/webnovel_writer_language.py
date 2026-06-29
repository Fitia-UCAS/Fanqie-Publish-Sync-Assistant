from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text
from backend.adapters.webnovel_writer.webnovel_writer_json import write_json


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


AI_FLAVOR_PATTERNS = [
    "不禁", "忍不住", "眼神复杂", "空气仿佛凝固", "心中一震", "微微一愣", "嘴角微微上扬", "淡淡一笑",
    "他知道", "这一刻", "仿佛有什么东西", "命运的齿轮", "前所未有", "无法言喻", "整个人都",
]

FILLER_PATTERNS = ["与此同时", "很快", "下一刻", "片刻之后", "毫无疑问", "事实上", "不得不说", "显然"]


def _chapter_path(storage: Any, project_id: str, chapter_no: int) -> Path | None:
    root = Path(storage.paths(project_id).chapters)
    if not root.exists():
        return None
    candidates = sorted(root.glob(f"第{chapter_no:04d}章*.md")) + sorted(root.glob(f"*{chapter_no:04d}*.md"))
    return candidates[0] if candidates else None


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?\n]+", text) if s.strip()]


def anti_ai_report(storage: Any, project_id: str, chapter_no: int | None = None) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    chapters: list[tuple[int, Path, str]] = []
    if chapter_no:
        p = _chapter_path(storage, project_id, chapter_no)
        if p:
            chapters.append((chapter_no, p, read_text_auto(p)))
    else:
        for p in sorted(Path(paths.chapters).glob("第*章*.md")):
            m = re.search(r"第(\d+)章", p.name)
            no = int(m.group(1)) if m else len(chapters) + 1
            chapters.append((no, p, read_text_auto(p)))
    issues: list[dict[str, Any]] = []
    total_chars = 0
    phrase_counter: Counter[str] = Counter()
    for no, p, text in chapters:
        total_chars += len(text)
        for phrase in AI_FLAVOR_PATTERNS + FILLER_PATTERNS:
            count = text.count(phrase)
            if count:
                phrase_counter[phrase] += count
                severity = "warning" if count <= 2 else "needs_rewrite"
                issues.append({"chapter_no": no, "path": str(p), "type": "stock_phrase", "severity": severity, "phrase": phrase, "count": count, "suggestion": f"减少模板化表达“{phrase}”，改成动作、细节或具体感官。"})
        for sent in _sentences(text):
            if len(sent) > 85:
                issues.append({"chapter_no": no, "path": str(p), "type": "long_sentence", "severity": "warning", "sample": sent[:120], "suggestion": "长句拆分，减少连续抽象修饰。"})
        paras = [x.strip() for x in text.splitlines() if x.strip()]
        if paras:
            short_ratio = sum(1 for x in paras if len(x) < 12) / max(1, len(paras))
            if short_ratio > 0.45:
                issues.append({"chapter_no": no, "path": str(p), "type": "fragmented_paragraphs", "severity": "warning", "ratio": round(short_ratio, 3), "suggestion": "短段过多会显得像模型断句，可合并同一动作链。"})
    score = max(0, 100 - sum(6 if i.get("severity") == "needs_rewrite" else 3 for i in issues))
    report = {
        "ok": not any(i.get("severity") == "needs_rewrite" for i in issues),
        "generated_at": _now(),
        "chapter_no": chapter_no,
        "chapter_count": len(chapters),
        "total_chars": total_chars,
        "score": score,
        "issues": issues[:300],
        "top_phrases": phrase_counter.most_common(30),
    }
    out_dir = ensure_dir(Path(paths.control) / "reports" / "language")
    suffix = f"chapter_{chapter_no:04d}" if chapter_no else "all_chapters"
    json_path = out_dir / f"{suffix}_anti_ai.json"
    md_path = out_dir / f"{suffix}_anti_ai.md"
    write_json(json_path, report)
    write_text(md_path, render_anti_ai_report(report))
    report["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return report


def render_anti_ai_report(report: dict[str, Any]) -> str:
    lines = ["# 语言去 AI 味检查", "", f"生成时间：{report.get('generated_at')}", f"检查章节数：{report.get('chapter_count')}", f"评分：{report.get('score')}/100", "", "## 高频模板词"]
    top = report.get("top_phrases") or []
    if top:
        lines += [f"- {p}: {c}" for p, c in top]
    else:
        lines.append("- 未发现明显模板词。")
    lines += ["", "## 问题清单"]
    issues = report.get("issues") or []
    if not issues:
        lines.append("- 暂无。")
    else:
        for item in issues[:120]:
            chapter = item.get("chapter_no")
            typ = item.get("type")
            phrase = item.get("phrase") or item.get("sample") or ""
            lines.append(f"- 第 {chapter} 章 [{typ}] {phrase}：{item.get('suggestion') or ''}")
    lines += ["", "## 改写原则", "- 把抽象情绪换成动作和物件反应。", "- 把“空气凝固/心中一震”这类套话换成场景专属细节。", "- 章末钩子尽量给新信息，不要只给感叹或口号。"]
    return "\n".join(lines).rstrip() + "\n"
