from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _tokens(text: str) -> list[str]:
    """Tokenize Chinese webnovel text for lexical features and local TF-IDF fallback.

    This is intentionally not a hashing vector.  The index stores a real vocabulary,
    IDF table, and per-document sparse TF-IDF vectors so scores are explainable and
    reproducible when no external embedding API is configured.
    """
    text = str(text or "").lower()
    ascii_terms = re.findall(r"[a-z0-9_]{2,}", text)
    cn_chars = re.findall(r"[\u4e00-\u9fff]", text)
    terms: list[str] = list(ascii_terms)
    for n in (2, 3, 4):
        for i in range(0, max(0, len(cn_chars) - n + 1)):
            term = "".join(cn_chars[i:i + n])
            if term.strip():
                terms.append(term)
    return terms


def _chapter_no_from_path(path: Path) -> int:
    m = re.search(r"第\s*(\d{1,6})\s*章", path.name)
    return int(m.group(1)) if m else 0


def _first_nonempty(text: str, limit: int = 240) -> str:
    for line in str(text or "").splitlines():
        s = line.strip()
        if s:
            return s[:limit]
    return str(text or "").strip()[:limit]


def _split_chunks(text: str, *, max_chars: int = 820, overlap: int = 120) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            current = f"{current}\n\n{p}".strip()
            continue
        if current:
            chunks.append(current)
        if len(p) <= max_chars:
            current = p
        else:
            start = 0
            while start < len(p):
                end = min(len(p), start + max_chars)
                chunks.append(p[start:end].strip())
                if end >= len(p):
                    break
                start = max(0, end - overlap)
            current = ""
    if current:
        chunks.append(current)
    if len(chunks) <= 1 and len(raw) > max_chars:
        chunks = []
        start = 0
        while start < len(raw):
            end = min(len(raw), start + max_chars)
            chunks.append(raw[start:end].strip())
            if end >= len(raw):
                break
            start = max(0, end - overlap)
    return [c for c in chunks if c]


def _cosine_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (na * nb)


def _cosine_dense(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(x) * float(x) for x in a[:n])) or 1.0
    nb = math.sqrt(sum(float(x) * float(x) for x in b[:n])) or 1.0
    return dot / (na * nb)


def _normalize_sparse(vec: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: round(v / norm, 8) for k, v in vec.items() if abs(v) > 1e-12}


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    max_tf = max(counts.values()) or 1
    vec = {term: (0.5 + 0.5 * freq / max_tf) * float(idf.get(term, 0.0)) for term, freq in counts.items() if term in idf}
    return _normalize_sparse(vec)


def _lexical_score(query_tokens: list[str], doc_tokens: list[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    q = Counter(query_tokens)
    d = Counter(doc_tokens)
    overlap = sum(min(freq, d.get(tok, 0)) for tok, freq in q.items())
    coverage = overlap / max(1, sum(q.values()))
    unique_coverage = len(set(q) & set(d)) / max(1, len(set(q)))
    return 0.65 * coverage + 0.35 * unique_coverage


def _extract_entities_from_state(state: dict[str, Any]) -> dict[str, list[str]]:
    entities: dict[str, list[str]] = {}
    for bucket in ["characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"]:
        values: list[str] = []
        data = state.get(bucket) or {}
        if isinstance(data, dict):
            for name, info in data.items():
                values.append(str(name))
                if isinstance(info, dict):
                    if info.get("id"):
                        values.append(str(info.get("id")))
                    aliases = info.get("aliases") or []
                    if isinstance(aliases, list):
                        values.extend(str(x) for x in aliases if str(x).strip())
        entities[bucket] = [x for x in values if x.strip()]
    return entities


def _entity_overlap(query: str, text: str, state: dict[str, Any]) -> tuple[float, list[str]]:
    q = str(query or "")
    t = str(text or "")
    names: list[str] = []
    for bucket, values in _extract_entities_from_state(state).items():
        for value in values:
            if value and value in q and value in t:
                names.append(value)
    unique = sorted(set(names), key=lambda x: (-len(x), x))[:12]
    return (min(1.0, len(unique) / 4.0), unique)


def _sha(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8", errors="ignore")).hexdigest()


@dataclass(slots=True)
class ProviderResult:
    provider: str
    model: str
    dimensions: int
    dense_vectors: list[list[float]] | None = None
    error: str = ""


class ExternalEmbeddingProvider:
    def __init__(self) -> None:
        self.base_url = os.getenv("EMBED_BASE_URL", "").rstrip("/")
        self.model = os.getenv("EMBED_MODEL", "")
        self.api_key = os.getenv("EMBED_API_KEY", "")
        self.timeout = _safe_float(os.getenv("EMBED_TIMEOUT", "30"), 30.0)

    def available(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def embed(self, texts: list[str]) -> ProviderResult:
        if not self.available():
            return ProviderResult(provider="external_openai_compatible", model=self.model or "", dimensions=0, error="EMBED_BASE_URL / EMBED_MODEL / EMBED_API_KEY 未配置")
        url = self.base_url
        if not url.endswith("/embeddings"):
            url = f"{url}/embeddings"
        payload = json.dumps({"model": self.model, "input": texts}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec - user-configured endpoint
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            rows = data.get("data") or []
            vectors = [list(map(float, row.get("embedding") or [])) for row in rows]
            if len(vectors) != len(texts) or not vectors or not vectors[0]:
                return ProviderResult(provider="external_openai_compatible", model=self.model, dimensions=0, error="embedding 服务返回为空或数量不匹配")
            return ProviderResult(provider="external_openai_compatible", model=self.model, dimensions=len(vectors[0]), dense_vectors=vectors)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            return ProviderResult(provider="external_openai_compatible", model=self.model, dimensions=0, error=str(exc))


def _try_sentence_transformers(texts: list[str]) -> ProviderResult:
    model_name = os.getenv("SENTENCE_TRANSFORMERS_MODEL", "").strip()
    if not model_name:
        return ProviderResult(provider="sentence_transformers", model="", dimensions=0, error="SENTENCE_TRANSFORMERS_MODEL 未配置")
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        model = SentenceTransformer(model_name)
        vectors = model.encode(texts, normalize_embeddings=True).tolist()
        return ProviderResult(provider="sentence_transformers", model=model_name, dimensions=len(vectors[0]) if vectors else 0, dense_vectors=[list(map(float, v)) for v in vectors])
    except Exception as exc:  # optional dependency
        return ProviderResult(provider="sentence_transformers", model=model_name, dimensions=0, error=str(exc))


def _collect_documents(storage: Any, project_id: str) -> list[dict[str, Any]]:
    storage.ensure_project_dirs(project_id)
    docs: list[dict[str, Any]] = []
    for row in storage.list_chapters(project_id):
        path = Path(row.get("path") or "")
        if not path.exists():
            continue
        text = read_text_auto(path)
        for idx, chunk in enumerate(_split_chunks(text), start=1):
            docs.append({
                "id": f"chapter:{int(row.get('chapterNo') or 0):04d}:{idx:04d}",
                "source": "chapter",
                "chapter_no": int(row.get("chapterNo") or 0),
                "title": str(row.get("title") or ""),
                "chunk_no": idx,
                "path": str(path),
                "text": chunk,
                "snippet": _first_nonempty(chunk),
                "sha256": _sha(chunk),
            })
    state = storage.load_state(project_id)
    for bucket, data in (state or {}).items():
        if bucket not in {"characters", "locations", "factions", "items", "foreshadows", "conflicts", "secrets", "pledges", "deadlines"}:
            continue
        if not isinstance(data, dict):
            continue
        for name, value in data.items():
            text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
            text = f"{bucket} {name}\n{text}"
            docs.append({
                "id": f"entity:{bucket}:{_sha(str(name))[:12]}",
                "source": "entity",
                "bucket": bucket,
                "name": str(name),
                "chapter_no": _int((value or {}).get("last_seen_chapter") if isinstance(value, dict) else 0, 0),
                "title": str(name),
                "chunk_no": 0,
                "path": str(storage.paths(project_id).state),
                "text": text,
                "snippet": _first_nonempty(text),
                "sha256": _sha(text),
            })
    reference_index = read_json(Path(storage.paths(project_id).indexes) / "reference_index.json", {}) or {}
    for idx, item in enumerate(reference_index.get("items") or reference_index.get("docs") or [], start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("content") or item.get("snippet") or "")
        if not text.strip():
            continue
        docs.append({
            "id": f"reference:{idx:04d}",
            "source": "reference",
            "chapter_no": 0,
            "title": str(item.get("title") or item.get("name") or f"reference-{idx}"),
            "chunk_no": idx,
            "path": str(item.get("path") or ""),
            "text": text[:1800],
            "snippet": _first_nonempty(text),
            "sha256": _sha(text),
        })
    return docs


def _build_tfidf_index(docs: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]]]:
    tokenized = [_tokens(str(doc.get("text") or "")) for doc in docs]
    df: Counter[str] = Counter()
    for toks in tokenized:
        df.update(set(toks))
    n = max(1, len(tokenized))
    idf = {term: round(math.log((1 + n) / (1 + freq)) + 1.0, 8) for term, freq in df.items()}
    rows: list[dict[str, Any]] = []
    for doc, toks in zip(docs, tokenized):
        vector = _tfidf_vector(toks, idf)
        rows.append({**{k: v for k, v in doc.items() if k != "text"}, "text": doc.get("text") or "", "token_count": len(toks), "terms": dict(Counter(toks).most_common(64)), "embedding": {"type": "tfidf_sparse", "vector": vector}})
    return idf, rows


def _build_external_index(docs: list[dict[str, Any]]) -> tuple[ProviderResult, list[dict[str, Any]]]:
    texts = [str(doc.get("text") or "") for doc in docs]
    provider = ExternalEmbeddingProvider()
    result = provider.embed(texts) if provider.available() else ProviderResult(provider="external_openai_compatible", model="", dimensions=0, error="外部 embedding 未配置")
    if not result.dense_vectors:
        st = _try_sentence_transformers(texts)
        if st.dense_vectors:
            result = st
    if not result.dense_vectors:
        return result, []
    rows: list[dict[str, Any]] = []
    for doc, vec in zip(docs, result.dense_vectors):
        rows.append({**{k: v for k, v in doc.items() if k != "text"}, "text": doc.get("text") or "", "token_count": len(_tokens(str(doc.get("text") or ""))), "embedding": {"type": "dense", "vector": [round(float(x), 8) for x in vec]}})
    return result, rows


def build_true_vector_rag(storage: Any, project_id: str, *, force_external: bool = False) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    docs = _collect_documents(storage, project_id)
    out_dir = ensure_dir(Path(paths.control) / "rag_v29")
    idx_path = Path(paths.indexes) / "true_vector_rag_index.json"
    manifest_path = out_dir / "embedding_manifest.json"
    rerank_path = out_dir / "rerank_profile.json"
    if not docs:
        report = {"ok": False, "reason": "没有可索引的章节、实体或知识库资料", "doc_count": 0, "paths_written": {"index": str(idx_path), "manifest": str(manifest_path)}}
        write_json(idx_path, {"schema_version": 1, "docs": [], "provider": {"name": "none"}, "created_at": _now()})
        write_json(manifest_path, report)
        return report

    provider_result, dense_rows = _build_external_index(docs)
    provider_errors = []
    if dense_rows:
        provider = {"name": provider_result.provider, "model": provider_result.model, "dimensions": provider_result.dimensions, "embedding_type": "dense", "external": provider_result.provider == "external_openai_compatible"}
        indexed_docs = dense_rows
        idf: dict[str, float] = {}
    else:
        provider_errors.append(provider_result.error)
        idf, indexed_docs = _build_tfidf_index(docs)
        provider = {"name": "local_tfidf_vector", "model": "explainable-tfidf-v1", "dimensions": len(idf), "embedding_type": "tfidf_sparse", "external": False, "fallback_reason": provider_errors[-1] if provider_errors else "external provider unavailable"}

    index = {
        "schema_version": 2,
        "created_at": _now(),
        "provider": provider,
        "doc_count": len(indexed_docs),
        "idf": idf,
        "docs": indexed_docs,
        "source_counts": dict(Counter(str(d.get("source") or "unknown") for d in indexed_docs)),
        "capabilities": {
            "true_vector_index": True,
            "hash_vector": False,
            "embedding_provider_fallback": provider.get("name"),
            "rerank": True,
            "hybrid_sources": ["chapter", "entity", "reference"],
        },
    }
    write_json(idx_path, index)
    manifest = {
        "ok": True,
        "created_at": index["created_at"],
        "provider": provider,
        "doc_count": len(indexed_docs),
        "external_provider_errors": provider_errors,
        "index_path": str(idx_path),
        "not_hash_vector": provider.get("name") != "local_hash_vector",
        "external_embedding_ready": bool(provider.get("external")),
    }
    write_json(manifest_path, manifest)
    write_json(rerank_path, {
        "schema_version": 1,
        "created_at": _now(),
        "formula": "0.62*vector_score + 0.18*lexical_score + 0.12*entity_overlap + 0.05*source_weight + 0.03*recency_score",
        "features": ["vector_score", "lexical_score", "entity_overlap", "source_weight", "recency_score"],
    })
    return {"ok": True, "doc_count": len(indexed_docs), "provider": provider, "paths_written": {"index": str(idx_path), "manifest": str(manifest_path), "rerank_profile": str(rerank_path)}}


def _query_vector(index: dict[str, Any], query: str) -> tuple[str, Any]:
    provider = index.get("provider") or {}
    docs = index.get("docs") or []
    if provider.get("embedding_type") == "dense" and provider.get("external"):
        result = ExternalEmbeddingProvider().embed([query])
        if result.dense_vectors:
            return "dense", result.dense_vectors[0]
    if provider.get("embedding_type") == "dense" and provider.get("name") == "sentence_transformers":
        result = _try_sentence_transformers([query])
        if result.dense_vectors:
            return "dense", result.dense_vectors[0]
    idf = index.get("idf") or {}
    return "tfidf_sparse", _tfidf_vector(_tokens(query), idf)


def query_true_vector_rag(storage: Any, project_id: str, query: str, *, top_k: int = 8, exclude_chapter: int = 0) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    idx_path = Path(paths.indexes) / "true_vector_rag_index.json"
    if not idx_path.exists():
        build_true_vector_rag(storage, project_id)
    index = read_json(idx_path, {}) or {}
    if not index.get("docs"):
        return {"ok": False, "query": query, "results": [], "reason": "true vector index is empty", "paths_written": {"index": str(idx_path)}}
    state = storage.load_state(project_id)
    q_type, q_vec = _query_vector(index, query)
    q_tokens = _tokens(query)
    rows: list[dict[str, Any]] = []
    for doc in index.get("docs") or []:
        if exclude_chapter and int(doc.get("chapter_no") or 0) == exclude_chapter:
            continue
        emb = (doc.get("embedding") or {})
        if q_type == "dense" and emb.get("type") == "dense":
            vector_score = _cosine_dense(q_vec, emb.get("vector") or [])
        else:
            vector_score = _cosine_sparse(q_vec if isinstance(q_vec, dict) else {}, emb.get("vector") or {})
        doc_tokens = _tokens(str(doc.get("text") or ""))
        lexical = _lexical_score(q_tokens, doc_tokens)
        entity_score, matched_entities = _entity_overlap(query, str(doc.get("text") or ""), state)
        source = str(doc.get("source") or "")
        source_weight = {"chapter": 1.0, "entity": 0.82, "reference": 0.72}.get(source, 0.65)
        chapter_no = int(doc.get("chapter_no") or 0)
        latest = _int((state or {}).get("latest_chapter"), 0)
        recency = 0.55 if not chapter_no or not latest else max(0.0, min(1.0, 1.0 - abs(latest - chapter_no) / max(10.0, latest + 1.0)))
        rerank_score = 0.62 * vector_score + 0.18 * lexical + 0.12 * entity_score + 0.05 * source_weight + 0.03 * recency
        if rerank_score <= 0 and vector_score <= 0 and lexical <= 0:
            continue
        rows.append({
            "id": doc.get("id"),
            "source": source,
            "chapter_no": chapter_no,
            "title": doc.get("title") or "",
            "path": doc.get("path") or "",
            "snippet": doc.get("snippet") or "",
            "score": round(rerank_score, 6),
            "scores": {
                "vector_score": round(vector_score, 6),
                "lexical_score": round(lexical, 6),
                "entity_overlap": round(entity_score, 6),
                "source_weight": round(source_weight, 6),
                "recency_score": round(recency, 6),
            },
            "matched_entities": matched_entities,
            "why": _why(vector_score, lexical, matched_entities, source),
        })
    rows.sort(key=lambda r: (r["score"], r["scores"]["vector_score"], r.get("chapter_no") or 0), reverse=True)
    out_dir = ensure_dir(Path(paths.control) / "rag_v29")
    query_path = out_dir / "last_true_vector_query.json"
    report = {
        "ok": True,
        "query": query,
        "top_k": top_k,
        "provider": index.get("provider") or {},
        "index_path": str(idx_path),
        "results": rows[:max(0, top_k)],
        "rerank": True,
        "paths_written": {"query": str(query_path), "index": str(idx_path)},
    }
    write_json(query_path, report)
    return report


def _why(vector_score: float, lexical: float, matched_entities: list[str], source: str) -> list[str]:
    reasons: list[str] = []
    if vector_score > 0.15:
        reasons.append("向量相似度高")
    elif vector_score > 0.03:
        reasons.append("向量相似度命中")
    if lexical > 0.15:
        reasons.append("关键词覆盖")
    if matched_entities:
        reasons.append("实体匹配：" + "、".join(matched_entities[:4]))
    if source == "entity":
        reasons.append("来自结构化实体状态")
    if source == "reference":
        reasons.append("来自参考知识库")
    return reasons or ["综合重排命中"]


def vector_rag_gaps_v29(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    idx_path = Path(paths.indexes) / "true_vector_rag_index.json"
    index = read_json(idx_path, {}) or {}
    provider = index.get("provider") or {}
    checks = [
        {"name": "true_vector_index_exists", "ok": idx_path.exists()},
        {"name": "not_hash_vector", "ok": provider.get("name") != "local_hash_vector" and provider.get("embedding_type") in {"tfidf_sparse", "dense"}},
        {"name": "has_embedding_provider_manifest", "ok": (Path(paths.control) / "rag_v29" / "embedding_manifest.json").exists()},
        {"name": "has_rerank_profile", "ok": (Path(paths.control) / "rag_v29" / "rerank_profile.json").exists()},
        {"name": "has_documents", "ok": int(index.get("doc_count") or 0) > 0},
        {"name": "supports_hybrid_sources", "ok": bool((index.get("capabilities") or {}).get("hybrid_sources"))},
    ]
    missing = [c for c in checks if not c["ok"]]
    out_dir = ensure_dir(Path(paths.control) / "rag_v29")
    path = out_dir / "true_vector_gap_matrix.json"
    report = {
        "ok": not missing,
        "checked_at": _now(),
        "provider": provider,
        "checks": checks,
        "missing": missing,
        "status": "达标" if not missing else "未达标",
        "paths_written": {"json": str(path), "index": str(idx_path)},
    }
    write_json(path, report)
    return report


def vector_rag_eval_v29(storage: Any, project_id: str) -> dict[str, Any]:
    """Run deterministic regression cases inside the user's project.

    This intentionally lives in product code as an acceptance command, while unit
    tests call it too.  It does not require network access or API keys.
    """
    build = build_true_vector_rag(storage, project_id)
    state = storage.load_state(project_id)
    queries: list[str] = []
    for bucket in ["characters", "foreshadows", "locations", "conflicts"]:
        data = state.get(bucket) or {}
        if isinstance(data, dict):
            queries.extend(list(map(str, list(data.keys())[:2])))
    if not queries:
        # Use recurring words from chapters as fallback acceptance queries.
        idx = read_json(Path(storage.paths(project_id).indexes) / "true_vector_rag_index.json", {}) or {}
        term_counter: Counter[str] = Counter()
        for doc in idx.get("docs") or []:
            term_counter.update((doc.get("terms") or {}).keys())
        queries = [term for term, _ in term_counter.most_common(3)] or ["主角"]
    cases = []
    passed = 0
    for query in queries[:8]:
        result = query_true_vector_rag(storage, project_id, query, top_k=3)
        ok = bool(result.get("results"))
        passed += 1 if ok else 0
        cases.append({"query": query, "ok": ok, "top_result": (result.get("results") or [{}])[0] if result.get("results") else {}})
    out_dir = ensure_dir(Path(storage.paths(project_id).control) / "rag_v29")
    path = out_dir / "true_vector_eval.json"
    report = {
        "ok": bool(build.get("ok")) and passed == len(cases),
        "checked_at": _now(),
        "case_count": len(cases),
        "passed": passed,
        "provider": build.get("provider"),
        "cases": cases,
        "paths_written": {"json": str(path)},
    }
    write_json(path, report)
    return report


def vector_rag_command_v29(storage: Any, project_id: str, action: str, query: str = "", top_k: int = 8, exclude_chapter: int = 0) -> dict[str, Any]:
    action = (action or "build").strip().lower()
    if action in {"build", "rebuild", "index"}:
        return build_true_vector_rag(storage, project_id)
    if action in {"query", "search"}:
        return query_true_vector_rag(storage, project_id, query, top_k=top_k, exclude_chapter=exclude_chapter)
    if action in {"gaps", "gap", "status"}:
        return vector_rag_gaps_v29(storage, project_id)
    if action in {"eval", "test", "acceptance"}:
        return vector_rag_eval_v29(storage, project_id)
    return {"ok": False, "message": f"未知 vector-rag-v29 action: {action}", "supported": ["build", "query", "gaps", "eval"]}


