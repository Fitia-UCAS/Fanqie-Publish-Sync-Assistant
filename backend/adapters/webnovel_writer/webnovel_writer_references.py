from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,2}|[A-Za-z0-9_]{2,}")
_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,4}\s+(.+?)\s*$")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def reference_root(storage: Any, project_id: str) -> Path:
    return Path(storage.paths(project_id).control) / "references"


def reference_index_path(storage: Any, project_id: str) -> Path:
    return Path(storage.paths(project_id).indexes) / "reference_index.json"


def ensure_reference_library(storage: Any, project_id: str) -> dict[str, Any]:
    """Create reference knowledge-library folders without adding static Markdown notes.

    Mirrors the reference projects' CSV/knowledge-base layer, but keeps the files
    runtime-created inside a user's project rather than bundled in the application.
    """
    root = reference_root(storage, project_id)
    dirs = {
        "root": ensure_dir(root),
        "csv": ensure_dir(root / "csv"),
        "markdown": ensure_dir(root / "markdown"),
        "text": ensure_dir(root / "text"),
    }
    sample_csv = root / "csv" / "reference_template.csv"
    if not sample_csv.exists():
        sample_csv.write_text("category,title,tags,content\n节奏,示例：章末钩子,钩子;悬念,这里写可检索的写作规则或拆书笔记\n", encoding="utf-8")
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "paths": {k: str(v) for k, v in dirs.items()}, "template": str(sample_csv)}
    _write_runtime_report(storage, project_id, "reference_library", report)
    return report


def build_reference_index(storage: Any, project_id: str) -> dict[str, Any]:
    root = reference_root(storage, project_id)
    ensure_reference_library(storage, project_id)
    docs: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name == "last_reference_index.json" or path.name == "last_reference_search.json":
            continue
        if path.suffix.lower() == ".csv":
            docs.extend(_read_csv_docs(path, root))
        elif path.suffix.lower() in {".md", ".markdown"}:
            docs.extend(_read_markdown_docs(path, root))
        elif path.suffix.lower() in {".txt", ".text"}:
            docs.extend(_read_text_docs(path, root))
        elif path.suffix.lower() == ".json":
            docs.extend(_read_json_docs(path, root))
    for idx, doc in enumerate(docs):
        text = " ".join([str(doc.get("title") or ""), str(doc.get("tags") or ""), str(doc.get("content") or "")])
        tokens = _tokens(text)
        doc["id"] = doc.get("id") or hashlib.sha1((str(doc.get("source")) + text).encode("utf-8", errors="ignore")).hexdigest()[:16]
        doc["ordinal"] = idx
        doc["token_count"] = len(tokens)
        doc["terms"] = dict(Counter(tokens))
    df = Counter()
    for doc in docs:
        df.update(set((doc.get("terms") or {}).keys()))
    index = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "project_id": project_id,
        "document_count": len(docs),
        "avg_doc_len": (sum(int(d.get("token_count") or 0) for d in docs) / len(docs)) if docs else 0,
        "documents": docs,
        "df": dict(df),
        "sources": sorted({str(d.get("source") or "") for d in docs}),
    }
    index_path = write_json(reference_index_path(storage, project_id), index)
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "document_count": len(docs), "index_path": str(index_path), "sources": index["sources"]}
    _write_runtime_report(storage, project_id, "reference_index", report)
    return report


def search_reference_index(storage: Any, project_id: str, query: str, top_k: int = 8) -> dict[str, Any]:
    index_path = reference_index_path(storage, project_id)
    index = read_json(index_path, None)
    if not isinstance(index, dict) or not index.get("documents"):
        build_reference_index(storage, project_id)
        index = read_json(index_path, {}) or {}
    q = str(query or "").strip()
    q_terms = _tokens(q)
    docs = index.get("documents") or []
    df = index.get("df") or {}
    avg_len = float(index.get("avg_doc_len") or 1.0) or 1.0
    total = max(1, len(docs))
    results = []
    for doc in docs:
        terms = doc.get("terms") or {}
        score = 0.0
        for term in q_terms:
            tf = float(terms.get(term) or 0)
            if tf <= 0:
                continue
            doc_len = max(1, int(doc.get("token_count") or 1))
            idf = math.log(1 + (total - int(df.get(term) or 0) + 0.5) / (int(df.get(term) or 0) + 0.5))
            score += idf * ((tf * 2.2) / (tf + 1.2 * (1 - 0.75 + 0.75 * doc_len / avg_len)))
        hay = " ".join([str(doc.get("title") or ""), str(doc.get("tags") or ""), str(doc.get("content") or "")])
        if q and q in hay:
            score += 3.0
        if score > 0:
            results.append({
                "score": round(score, 4),
                "id": doc.get("id"),
                "category": doc.get("category") or "",
                "title": doc.get("title") or "",
                "tags": doc.get("tags") or [],
                "source": doc.get("source") or "",
                "content": _snippet(str(doc.get("content") or ""), q),
            })
    results.sort(key=lambda x: x.get("score") or 0, reverse=True)
    report = {"ok": True, "generated_at": now_iso(), "project_id": project_id, "query": q, "top_k": top_k, "results": results[: max(1, int(top_k or 8))], "index_path": str(index_path)}
    _write_runtime_report(storage, project_id, "reference_search", report)
    return report


def deconstruct_project(storage: Any, project_id: str, source: str = "", sample_limit: int = 80) -> dict[str, Any]:
    """Local deconstruction-agent style report for existing chapters or a reference text."""
    storage.ensure_project_dirs(project_id)
    if source:
        text = read_text_auto(Path(source))
        chapters = [{"chapter_no": 0, "title": Path(source).stem, "text": text}]
        source_label = str(Path(source).expanduser())
    else:
        chapters = []
        for row in storage.list_chapters(project_id)[: max(1, int(sample_limit or 80))]:
            p = Path(row.get("path") or "")
            chapters.append({"chapter_no": row.get("chapterNo"), "title": row.get("title") or p.stem, "text": read_text_auto(p) if p.exists() else ""})
        source_label = "project_chapters"
    rows = []
    ending_samples = []
    opening_samples = []
    hooks = []
    for ch in chapters:
        text = str(ch.get("text") or "").strip()
        if not text:
            continue
        paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
        dialogue_lines = [p for p in paras if "“" in p or '"' in p or re.search(r"：[^\n]{1,80}$", p)]
        opening = paras[0][:160] if paras else text[:160]
        ending = paras[-1][-220:] if paras else text[-220:]
        opening_samples.append({"chapter_no": ch.get("chapter_no"), "text": opening})
        ending_samples.append({"chapter_no": ch.get("chapter_no"), "text": ending})
        hook_type = _hook_type(ending)
        if hook_type:
            hooks.append({"chapter_no": ch.get("chapter_no"), "type": hook_type, "evidence": ending})
        rows.append({
            "chapter_no": ch.get("chapter_no"),
            "title": ch.get("title") or "",
            "chars": len(text),
            "paragraphs": len(paras),
            "dialogue_ratio": round(len(dialogue_lines) / max(1, len(paras)), 3),
            "opening_pattern": _opening_pattern(opening),
            "ending_hook": hook_type or "none",
            "scene_count_estimate": max(1, sum(1 for p in paras if _scene_marker(p))),
        })
    all_text = "\n".join(str(ch.get("text") or "") for ch in chapters)
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "project_id": project_id,
        "source": source_label,
        "chapter_count": len(rows),
        "aggregate": {
            "avg_chars": round(sum(r["chars"] for r in rows) / max(1, len(rows)), 1),
            "avg_paragraphs": round(sum(r["paragraphs"] for r in rows) / max(1, len(rows)), 1),
            "avg_dialogue_ratio": round(sum(r["dialogue_ratio"] for r in rows) / max(1, len(rows)), 3),
        },
        "chapter_patterns": rows,
        "opening_samples": opening_samples[:12],
        "ending_samples": ending_samples[:12],
        "hook_patterns": dict(Counter(h["type"] for h in hooks)),
        "hook_examples": hooks[:20],
        "high_frequency_terms": _top_terms(all_text, 40),
        "deconstruction_notes": _deconstruction_notes(rows, hooks),
    }
    paths = storage.paths(project_id)
    out = Path(paths.control) / "reports" / "deconstruction" / "last_deconstruction.json"
    write_json(out, report)
    report["paths_written"] = {"json": str(out)}
    return report


def _read_csv_docs(path: Path, root: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    rows: list[dict[str, Any]] = []
    try:
        reader = csv.DictReader(text.splitlines())
        if reader.fieldnames:
            for i, row in enumerate(reader):
                content = row.get("content") or row.get("正文") or row.get("内容") or " ".join(str(v or "") for v in row.values())
                title = row.get("title") or row.get("标题") or row.get("name") or f"{path.stem}-{i + 1}"
                rows.append(_doc(path, root, title, content, row.get("category") or row.get("分类") or path.stem, row.get("tags") or row.get("标签") or ""))
            return rows
    except Exception:
        pass
    return [_doc(path, root, path.stem, text, path.stem, "")]


def _read_markdown_docs(path: Path, root: Path) -> list[dict[str, Any]]:
    text = read_text_auto(path)
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [_doc(path, root, path.stem, text, path.parent.name, "")]
    docs = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            docs.append(_doc(path, root, m.group(1).strip(), body, path.parent.name, ""))
    return docs or [_doc(path, root, path.stem, text, path.parent.name, "")]


def _read_text_docs(path: Path, root: Path) -> list[dict[str, Any]]:
    text = read_text_auto(path)
    parts = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(parts) <= 1:
        return [_doc(path, root, path.stem, text, path.parent.name, "")]
    return [_doc(path, root, f"{path.stem}-{i + 1}", p, path.parent.name, "") for i, p in enumerate(parts)]


def _read_json_docs(path: Path, root: Path) -> list[dict[str, Any]]:
    data = read_json(path, None)
    docs = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                docs.append(_doc(path, root, item.get("title") or item.get("name") or f"{path.stem}-{i + 1}", item.get("content") or item.get("text") or json.dumps(item, ensure_ascii=False), item.get("category") or path.stem, item.get("tags") or []))
    elif isinstance(data, dict):
        for key, value in data.items():
            docs.append(_doc(path, root, str(key), json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value, path.stem, ""))
    return docs


def _doc(path: Path, root: Path, title: Any, content: Any, category: Any, tags: Any) -> dict[str, Any]:
    if isinstance(tags, str):
        tags = [x.strip() for x in re.split(r"[;,，；]", tags) if x.strip()]
    elif not isinstance(tags, list):
        tags = [str(tags)] if tags else []
    return {"source": str(path.relative_to(root)), "category": str(category or ""), "title": str(title or ""), "tags": tags, "content": str(content or "").strip()}


def _tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(str(text or ""))]


def _top_terms(text: str, limit: int) -> list[dict[str, Any]]:
    stop = {"一个", "这个", "那个", "他们", "我们", "但是", "然后", "已经", "自己", "没有", "不是", "the", "and", "for", "with"}
    counter = Counter(t for t in _tokens(text) if t not in stop)
    return [{"term": term, "count": count} for term, count in counter.most_common(limit)]


def _snippet(text: str, query: str, width: int = 180) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not query:
        return text[:width]
    idx = text.find(query)
    if idx < 0:
        return text[:width]
    start = max(0, idx - width // 3)
    return text[start : start + width]


def _hook_type(text: str) -> str:
    if re.search(r"[？?]\s*$", text):
        return "question_cliffhanger"
    if re.search(r"(忽然|突然|就在这时|下一刻|却见|只见|门外|身后|黑暗中)", text[-120:]):
        return "sudden_turn"
    if re.search(r"(秘密|真相|身份|血迹|信物|令牌|线索|异样|裂缝)", text[-160:]):
        return "mystery_reveal"
    if re.search(r"(杀|死|战|逃|追|危机|崩塌|爆发)", text[-160:]):
        return "danger_escalation"
    return ""


def _opening_pattern(text: str) -> str:
    if re.search(r"(雨|夜|风|雪|雾|城|山|殿|街|门)", text[:80]):
        return "scene_first"
    if "“" in text[:120] or '"' in text[:120]:
        return "dialogue_first"
    if re.search(r"(疼|痛|醒|睁眼|记得|梦)", text[:100]):
        return "sensation_first"
    return "narration_first"


def _scene_marker(paragraph: str) -> bool:
    return bool(re.search(r"(来到|走进|推开|转身|片刻后|与此同时|另一边|夜色|清晨|黄昏|门外|城中|山上)", paragraph[:80]))


def _deconstruction_notes(rows: list[dict[str, Any]], hooks: list[dict[str, Any]]) -> list[str]:
    notes = []
    if not rows:
        return ["没有可分析文本。"]
    avg_chars = sum(r["chars"] for r in rows) / max(1, len(rows))
    if avg_chars < 1500:
        notes.append("章节样本偏短，更适合短节奏连载；生成时应强化单章目标和章末钩子。")
    elif avg_chars > 3500:
        notes.append("章节样本偏长，生成时需要明确场景分段与中段转折，避免水文。")
    dialogue = sum(r["dialogue_ratio"] for r in rows) / max(1, len(rows))
    if dialogue > 0.45:
        notes.append("对话占比较高，适合用冲突对话推进信息。")
    elif dialogue < 0.15:
        notes.append("叙述占比较高，生成时可适当增加人物互动防止说明文感。")
    if hooks:
        notes.append("样本具备章末钩子，可在蓝图中显式要求 ending_hook。")
    else:
        notes.append("样本章末钩子弱，建议在章节蓝图加入悬念、反转或危险升级。")
    return notes


def _write_runtime_report(storage: Any, project_id: str, stem: str, data: dict[str, Any]) -> None:
    paths = storage.paths(project_id)
    out = Path(paths.control) / "reports" / "references" / f"last_{stem}.json"
    write_json(out, data)
    data.setdefault("paths_written", {})["json"] = str(out)
