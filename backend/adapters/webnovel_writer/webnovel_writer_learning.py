from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def learn_style_profile(storage: Any, project_id: str, *, sample_limit: int = 80, update_config: bool = True) -> dict[str, Any]:
    """Analyze existing chapters and derive a reusable local style profile.

    This syncs part of Tianming/Claude-style "project learning" into the
    backend without using UI or online models.  It is deterministic and safe.
    """
    storage.sync_control_files(project_id)
    chapters = storage.list_chapters(project_id)[-max(1, int(sample_limit or 80)):]
    chapter_rows = []
    total_chars = total_paragraphs = total_dialogue = total_sentences = 0
    endings: list[str] = []
    phrase_counter: Counter[str] = Counter()
    dialogue_verbs: Counter[str] = Counter()

    for row in chapters:
        path = Path(row.get("path") or "")
        text = read_text_auto(path) if path.exists() else ""
        metrics = _chapter_metrics(text)
        chapter_rows.append({"chapter_no": row.get("chapterNo"), "title": row.get("title"), **metrics})
        total_chars += metrics["char_count"]
        total_paragraphs += metrics["paragraph_count"]
        total_dialogue += metrics["dialogue_line_count"]
        total_sentences += metrics["sentence_count"]
        if metrics["ending_tail"]:
            endings.append(metrics["ending_tail"])
        phrase_counter.update(_phrases(text))
        dialogue_verbs.update(re.findall(r"(?:说道|问道|笑道|冷声道|低声道|喃喃|叹道|喝道|怒道|沉声道)", text))

    count = max(1, len(chapter_rows))
    profile = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "project_id": project_id,
        "sample_chapters": len(chapter_rows),
        "averages": {
            "chars_per_chapter": round(total_chars / count, 1),
            "paragraphs_per_chapter": round(total_paragraphs / count, 1),
            "dialogue_lines_per_chapter": round(total_dialogue / count, 1),
            "dialogue_ratio": round(total_dialogue / max(1, total_paragraphs), 3),
            "sentence_count_per_chapter": round(total_sentences / count, 1),
        },
        "chapter_metrics": chapter_rows,
        "common_phrases": [{"phrase": k, "count": v} for k, v in phrase_counter.most_common(50) if v >= 2],
        "dialogue_verbs": [{"verb": k, "count": v} for k, v in dialogue_verbs.most_common(20)],
        "ending_samples": endings[-20:],
        "writing_guidance": _guidance(total_chars / count if chapter_rows else 0, total_dialogue / max(1, total_paragraphs), phrase_counter),
    }

    out_dir = ensure_dir(Path(storage.paths(project_id).control) / "learning")
    json_path = write_json(out_dir / "style_profile.json", profile)
    md_path = write_text(out_dir / "style_profile.md", style_markdown(profile))
    profile["paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(out_dir / "style_profile.json", profile)

    if update_config:
        cfg_path = Path(storage.paths(project_id).story_config)
        cfg = read_json(cfg_path, {}) or {}
        if isinstance(cfg, dict):
            cfg["learned_style_profile"] = {
                "updated_at": profile["generated_at"],
                "sample_chapters": profile["sample_chapters"],
                "averages": profile["averages"],
                "guidance": profile["writing_guidance"],
                "profile_path": str(md_path),
            }
            write_json(cfg_path, cfg)
    return profile


def style_markdown(profile: dict[str, Any]) -> str:
    lines = ["# 拆书/文风学习报告", "", f"- 时间：{profile.get('generated_at')}", f"- 样本章节：{profile.get('sample_chapters')}", ""]
    lines += ["## 平均指标", ""]
    for k, v in (profile.get("averages") or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 写作建议", ""]
    for item in profile.get("writing_guidance") or []:
        lines.append(f"- {item}")
    lines += ["", "## 高频短语", ""]
    phrases = profile.get("common_phrases") or []
    if not phrases:
        lines.append("暂无。")
    for item in phrases[:30]:
        lines.append(f"- {item.get('phrase')}: {item.get('count')}")
    lines += ["", "## 章末样本", ""]
    for item in profile.get("ending_samples") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _chapter_metrics(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    paragraphs = [p.strip() for p in re.split(r"\n+", clean) if p.strip()]
    dialogue = [p for p in paragraphs if re.match(r"^[“\"'「『].+[”\"'」』]", p) or "：“" in p or ':"' in p]
    sentences = [s for s in re.split(r"[。！？!?]+", clean) if s.strip()]
    tail = paragraphs[-1][-80:] if paragraphs else ""
    return {
        "char_count": len(re.sub(r"\s+", "", clean)),
        "paragraph_count": len(paragraphs),
        "dialogue_line_count": len(dialogue),
        "sentence_count": len(sentences),
        "avg_sentence_chars": round(len(re.sub(r"\s+", "", clean)) / max(1, len(sentences)), 1),
        "ending_tail": tail,
    }


def _phrases(text: str) -> list[str]:
    clean = re.sub(r"\s+", "", str(text or ""))
    out = []
    for n in (4, 5, 6):
        for i in range(0, max(0, len(clean) - n + 1)):
            token = clean[i : i + n]
            if re.search(r"[，。！？、；：]", token):
                continue
            if len(set(token)) <= 1:
                continue
            out.append(token)
    return out[:20000]


def _guidance(avg_chars: float, dialogue_ratio: float, phrases: Counter[str]) -> list[str]:
    lines = []
    if avg_chars:
        lines.append(f"建议单章字数贴近当前样本均值 {int(avg_chars)} 字，可上下浮动 20%。")
    if dialogue_ratio < 0.12:
        lines.append("样本偏叙述流，后续写作不要强行塞大量对话。")
    elif dialogue_ratio > 0.35:
        lines.append("样本对话占比较高，后续写作需要保持人物交锋和信息交换密度。")
    else:
        lines.append("样本对话/叙述比例适中，写作时注意一段动作推进后接一段内心或对话。")
    common = [k for k, v in phrases.most_common(20) if v >= 5]
    if common:
        lines.append("检测到若干高频短语，写作时避免机械重复：" + "、".join(common[:8]))
    lines.append("章末优先保留悬念、反转、危险信号或未说出口的信息，服务追读。")
    return lines
