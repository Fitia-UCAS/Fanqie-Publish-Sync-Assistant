from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_models import CONTROL_ENTITY_BUCKETS, now_iso
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{1,4}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for m in _WORD_RE.finditer(text.lower()):
        token = m.group(0).strip()
        if len(token) >= 2 or "\u4e00" <= token <= "\u9fff":
            out.append(token)
    return out


def split_chunks(text: str, *, target_chars: int = 680, overlap_chars: int = 120) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []
    pieces = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p and p.strip()]
    chunks: list[dict[str, Any]] = []
    current = ""
    start_pos = 0
    consumed = 0
    for piece in pieces:
        if current and len(current) + len(piece) > target_chars:
            chunk_text = current.strip()
            chunks.append({"text": chunk_text, "start_char": start_pos, "end_char": start_pos + len(chunk_text)})
            tail = chunk_text[-overlap_chars:] if overlap_chars > 0 else ""
            start_pos = max(0, start_pos + len(chunk_text) - len(tail))
            current = tail + ("\n" if tail else "") + piece
        else:
            if not current:
                start_pos = consumed
            current += ("\n" if current else "") + piece
        consumed += len(piece)
    if current.strip():
        chunk_text = current.strip()
        chunks.append({"text": chunk_text, "start_char": start_pos, "end_char": start_pos + len(chunk_text)})
    return chunks


def _first_line(text: str, width: int = 180) -> str:
    for line in (text or "").splitlines():
        clean = line.strip()
        if clean:
            return clean[:width]
    return (text or "").strip()[:width]


def _chapter_sort_key(row: dict[str, Any]) -> int:
    try:
        return int(row.get("chapterNo") or row.get("chapter_no") or 0)
    except Exception:
        return 0


def rebuild_chunk_index(storage: Any, project_id: str, *, target_chars: int = 680, overlap_chars: int = 120) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    docs: list[dict[str, Any]] = []
    for row in sorted(storage.list_chapters(project_id), key=_chapter_sort_key):
        chapter_no = int(row.get("chapterNo") or 0)
        path = Path(str(row.get("path") or ""))
        if not path.exists():
            continue
        text = read_text_auto(path)
        for idx, chunk in enumerate(split_chunks(text, target_chars=target_chars, overlap_chars=overlap_chars), start=1):
            chunk_text = str(chunk.get("text") or "")
            terms = Counter(tokenize(chunk_text))
            chunk_id = f"C{chapter_no:04d}-{idx:03d}"
            docs.append({
                "chunk_id": chunk_id,
                "chapter_no": chapter_no,
                "chapter_title": row.get("title") or "",
                "chunk_no": idx,
                "path": str(path),
                "start_char": chunk.get("start_char", 0),
                "end_char": chunk.get("end_char", 0),
                "length": max(1, sum(terms.values())),
                "terms": dict(terms),
                "snippet": _first_line(chunk_text, 260),
                "sha256": hashlib.sha256(chunk_text.encode("utf-8", errors="ignore")).hexdigest(),
            })
    df: Counter[str] = Counter()
    for doc in docs:
        df.update((doc.get("terms") or {}).keys())
    index = {
        "schema_version": 1,
        "updated_at": now_iso(),
        "target_chars": target_chars,
        "overlap_chars": overlap_chars,
        "doc_count": len(docs),
        "df": dict(df),
        "docs": docs,
    }
    index_path = Path(paths.indexes) / "chunk_index.json"
    write_json(index_path, index)
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "chunk_count": len(docs),
        "chapter_count": len({d.get("chapter_no") for d in docs}),
        "path": str(index_path),
    }
    report_dir = ensure_dir(Path(paths.control) / "reports" / "indexing")
    write_json(report_dir / "last_chunk_index_report.json", report)
    write_text(report_dir / "last_chunk_index_report.md", _chunk_index_markdown(report))
    return report


def search_chunks(storage: Any, project_id: str, query: str, *, top_k: int = 8, exclude_chapter: int | None = None) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    index_path = Path(paths.indexes) / "chunk_index.json"
    data = read_json(index_path, {}) or {}
    if not data.get("docs"):
        rebuild_chunk_index(storage, project_id)
        data = read_json(index_path, {}) or {}
    rows = _rank_chunks(data, query, top_k=top_k, exclude_chapter=exclude_chapter)
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "query": query,
        "top_k": top_k,
        "exclude_chapter": exclude_chapter,
        "result_count": len(rows),
        "results": rows,
    }
    report_dir = ensure_dir(Path(paths.control) / "reports" / "search")
    write_json(report_dir / "last_chunk_search.json", report)
    write_text(report_dir / "last_chunk_search.md", _chunk_search_markdown(report))
    return report


def chunk_recall(storage: Any, project_id: str, query: str, *, top_k: int = 8, exclude_chapter: int | None = None) -> list[dict[str, Any]]:
    paths = storage.ensure_project_dirs(project_id)
    index_path = Path(paths.indexes) / "chunk_index.json"
    data = read_json(index_path, {}) or {}
    if not data.get("docs"):
        rebuild_chunk_index(storage, project_id)
        data = read_json(index_path, {}) or {}
    return _rank_chunks(data, query, top_k=top_k, exclude_chapter=exclude_chapter)


def _rank_chunks(index: dict[str, Any], query: str, *, top_k: int = 8, exclude_chapter: int | None = None) -> list[dict[str, Any]]:
    q_terms = Counter(tokenize(query or ""))
    if not q_terms:
        return []
    docs = index.get("docs") or []
    if not docs:
        return []
    n_docs = max(1, int(index.get("doc_count") or len(docs)))
    df = index.get("df") or {}
    avg_len = sum(max(1, int(doc.get("length") or 1)) for doc in docs) / max(1, len(docs))
    rows: list[dict[str, Any]] = []
    for doc in docs:
        chapter_no = int(doc.get("chapter_no") or 0)
        if exclude_chapter and chapter_no == exclude_chapter:
            continue
        terms = doc.get("terms") or {}
        length = max(1, int(doc.get("length") or 1))
        score = 0.0
        matched: list[str] = []
        for term, qf in q_terms.items():
            tf = float(terms.get(term) or 0)
            if tf <= 0:
                continue
            matched.append(term)
            freq = float(df.get(term, 0))
            idf = math.log(1 + (n_docs - freq + 0.5) / (freq + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (1 - 0.75 + 0.75 * length / max(1, avg_len))) * qf
        if score > 0:
            rows.append({
                "chunk_id": doc.get("chunk_id"),
                "chapter_no": chapter_no,
                "chapter_title": doc.get("chapter_title") or "",
                "chunk_no": doc.get("chunk_no"),
                "score": round(score, 4),
                "matched_terms": matched[:12],
                "snippet": doc.get("snippet") or "",
                "path": doc.get("path") or "",
                "start_char": doc.get("start_char"),
                "end_char": doc.get("end_char"),
            })
    rows.sort(key=lambda r: (float(r.get("score") or 0), -int(r.get("chapter_no") or 0)), reverse=True)
    return rows[: max(0, top_k)]


def build_entity_occurrence_index(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    state = storage.load_state(project_id)
    entities: list[dict[str, Any]] = []
    for bucket in CONTROL_ENTITY_BUCKETS:
        mapping = state.get(bucket) or {}
        if not isinstance(mapping, dict):
            continue
        for name, value in mapping.items():
            if not isinstance(value, dict):
                value = {"status": value}
            aliases = _aliases_for(name, value)
            entities.append({"bucket": bucket, "name": str(name), "id": str(value.get("id") or ""), "aliases": aliases})
    chapters = []
    for row in sorted(storage.list_chapters(project_id), key=_chapter_sort_key):
        path = Path(str(row.get("path") or ""))
        text = read_text_auto(path) if path.exists() else ""
        chapters.append({"chapter_no": int(row.get("chapterNo") or 0), "title": row.get("title") or "", "path": str(path), "text": text})
    occurrences: dict[str, dict[str, Any]] = {}
    relations: list[dict[str, Any]] = []
    for ent in entities:
        key = f"{ent['bucket']}::{ent['name']}"
        rows: list[dict[str, Any]] = []
        total = 0
        for chapter in chapters:
            count = _count_aliases(str(chapter["text"]), ent["aliases"])
            if count <= 0:
                continue
            total += count
            rows.append({
                "chapter_no": chapter["chapter_no"],
                "title": chapter["title"],
                "count": count,
                "snippet": _snippet_around_alias(str(chapter["text"]), ent["aliases"]),
                "path": chapter["path"],
            })
        if rows:
            occurrences[key] = {
                "bucket": ent["bucket"],
                "name": ent["name"],
                "id": ent["id"],
                "aliases": ent["aliases"],
                "mention_count": total,
                "first_chapter": rows[0]["chapter_no"],
                "last_chapter": rows[-1]["chapter_no"],
                "chapters": rows,
            }
            for row in rows:
                relations.append({
                    "source_type": ent["bucket"],
                    "source": ent["name"],
                    "target_type": "chapter",
                    "target": row["chapter_no"],
                    "relation": "mentioned_in",
                    "weight": row["count"],
                })
    report = {
        "ok": True,
        "generated_at": now_iso(),
        "entity_count": len(entities),
        "mentioned_entity_count": len(occurrences),
        "relation_count": len(relations),
        "occurrences": occurrences,
        "relations": relations,
    }
    rel_dir = ensure_dir(Path(paths.control) / "relations")
    write_json(rel_dir / "entity_occurrences.json", report)
    write_text(rel_dir / "entity_occurrences.md", _entity_occurrence_markdown(report))
    return report


def _aliases_for(name: str, value: dict[str, Any]) -> list[str]:
    aliases = [str(name)]
    raw = value.get("aliases") or value.get("alias") or []
    if isinstance(raw, str):
        raw = re.split(r"[,，、/|\s]+", raw)
    if isinstance(raw, list):
        aliases.extend(str(x) for x in raw if str(x).strip())
    entity_id = str(value.get("id") or "").strip()
    if entity_id:
        aliases.append(entity_id)
    out: list[str] = []
    for item in aliases:
        clean = str(item).strip()
        if clean and clean not in out:
            out.append(clean)
    return sorted(out, key=len, reverse=True)


def _count_aliases(text: str, aliases: list[str]) -> int:
    count = 0
    for alias in aliases:
        if not alias or len(alias) < 2:
            continue
        count += text.count(alias)
    return count


def _snippet_around_alias(text: str, aliases: list[str], width: int = 120) -> str:
    best_idx = -1
    best_alias = ""
    for alias in aliases:
        if not alias:
            continue
        idx = text.find(alias)
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx
            best_alias = alias
    if best_idx < 0:
        return _first_line(text, width)
    start = max(0, best_idx - width // 2)
    end = min(len(text), best_idx + len(best_alias) + width // 2)
    return text[start:end].replace("\n", " ").strip()


def _chunk_index_markdown(report: dict[str, Any]) -> str:
    return f"""# 分块索引报告

- 生成时间：{report.get('generated_at')}
- 章节数：{report.get('chapter_count')}
- 分块数：{report.get('chunk_count')}
- 索引文件：`{report.get('path')}`
"""


def _chunk_search_markdown(report: dict[str, Any]) -> str:
    lines = ["# 分块召回结果", "", f"- 查询：{report.get('query')}", f"- 结果数：{report.get('result_count')}", ""]
    for idx, row in enumerate(report.get("results") or [], start=1):
        lines.append(f"## {idx}. 第{row.get('chapter_no')}章 {row.get('chapter_title') or ''} / {row.get('chunk_id')} / score={row.get('score')}")
        lines.append("")
        lines.append(str(row.get("snippet") or ""))
        lines.append("")
        if row.get("matched_terms"):
            lines.append(f"- 命中词：{', '.join(row.get('matched_terms') or [])}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _entity_occurrence_markdown(report: dict[str, Any]) -> str:
    lines = ["# 实体出现索引", "", f"- 生成时间：{report.get('generated_at')}", f"- 已登记实体：{report.get('entity_count')}", f"- 正文出现实体：{report.get('mentioned_entity_count')}", ""]
    occurrences = report.get("occurrences") or {}
    for key in sorted(occurrences):
        item = occurrences[key]
        lines.append(f"## {item.get('name')}（{item.get('bucket')}）")
        lines.append(f"- mention_count: {item.get('mention_count')}")
        lines.append(f"- first_chapter: {item.get('first_chapter')}")
        lines.append(f"- last_chapter: {item.get('last_chapter')}")
        lines.append(f"- aliases: {', '.join(item.get('aliases') or [])}")
        for row in (item.get("chapters") or [])[:10]:
            lines.append(f"  - 第{row.get('chapter_no')}章 x{row.get('count')}：{row.get('snippet')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
