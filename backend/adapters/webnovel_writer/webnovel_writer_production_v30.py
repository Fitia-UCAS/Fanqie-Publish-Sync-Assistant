from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_behavior_v28 import behavior_run_v28_command
from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.adapters.webnovel_writer.webnovel_writer_vector_rag_v29 import (
    build_true_vector_rag,
    query_true_vector_rag,
    vector_rag_eval_v29,
    vector_rag_gaps_v29,
)
from backend.shared.text_file.text_file_storage import ensure_dir


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


def _write(out_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    path = out_dir / name
    write_json(path, payload)
    return path


def _rag_dir(storage: Any, project_id: str) -> Path:
    return ensure_dir(Path(storage.paths(project_id).control) / "production_v30")


class ExternalRerankProvider:
    """Optional OpenAI/Jina-compatible rerank provider.

    The project must not require a network service to pass local behavior checks, but
    when RERANK_* is configured this adapter performs a real rerank call and records
    the result.  The offline path still uses v29's deterministic rerank scores.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("RERANK_BASE_URL", "").rstrip("/")
        self.model = os.getenv("RERANK_MODEL", "")
        self.api_key = os.getenv("RERANK_API_KEY", "")
        self.timeout = _safe_float(os.getenv("RERANK_TIMEOUT", "30"), 30.0)

    def available(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def rerank(self, query: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.available():
            return {"ok": False, "used": False, "reason": "RERANK_BASE_URL / RERANK_MODEL / RERANK_API_KEY 未配置"}
        url = self.base_url
        if not (url.endswith("/rerank") or url.endswith("/rank")):
            url = f"{url}/rerank"
        documents = [str(doc.get("snippet") or doc.get("text") or "") for doc in docs]
        payload = json.dumps({"model": self.model, "query": query, "documents": documents}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec - user-configured endpoint
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            rows = data.get("results") or data.get("data") or []
            scores: dict[int, float] = {}
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                index = _int(row.get("index"), idx)
                score = _safe_float(row.get("relevance_score", row.get("score", 0.0)), 0.0)
                scores[index] = score
            ranked = []
            for i, doc in enumerate(docs):
                ranked.append({**doc, "external_rerank_score": round(scores.get(i, 0.0), 6)})
            ranked.sort(key=lambda x: (x.get("external_rerank_score") or 0.0, x.get("score") or 0.0), reverse=True)
            return {"ok": True, "used": True, "provider": "external_rerank", "model": self.model, "ranked": ranked, "raw_count": len(rows)}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            return {"ok": False, "used": False, "provider": "external_rerank", "model": self.model, "reason": str(exc)}


def provider_health_v30(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    out_dir = _rag_dir(storage, project_id)
    manifest = read_json(Path(paths.control) / "rag_v29" / "embedding_manifest.json", {}) or {}
    index = read_json(Path(paths.indexes) / "true_vector_rag_index.json", {}) or {}
    provider = index.get("provider") or manifest.get("provider") or {}
    reranker = ExternalRerankProvider()
    rerank_status = {"configured": reranker.available(), "model": reranker.model or "", "base_url_configured": bool(reranker.base_url)}
    report = {
        "ok": True,
        "checked_at": _now(),
        "embedding": {
            "provider": provider,
            "index_exists": (Path(paths.indexes) / "true_vector_rag_index.json").exists(),
            "external_configured": bool(os.getenv("EMBED_BASE_URL") and os.getenv("EMBED_MODEL") and os.getenv("EMBED_API_KEY")),
            "local_fallback": provider.get("name") == "local_tfidf_vector",
            "not_hash_vector": provider.get("name") != "local_hash_vector",
        },
        "rerank": rerank_status,
        "production_policy": {
            "local_acceptance_can_pass_without_network": True,
            "external_provider_validated_only_when_configured": True,
            "hash_vector_allowed": False,
        },
    }
    path = _write(out_dir, "provider_health.json", report)
    report["paths_written"] = {"json": str(path)}
    write_json(path, report)
    return report


def query_vector_rag_v30(storage: Any, project_id: str, query: str, *, top_k: int = 8, exclude_chapter: int = 0) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    out_dir = _rag_dir(storage, project_id)
    base = query_true_vector_rag(storage, project_id, query, top_k=max(top_k * 3, top_k), exclude_chapter=exclude_chapter)
    results = list(base.get("results") or [])
    reranker = ExternalRerankProvider()
    external = reranker.rerank(query, results) if results else {"ok": False, "used": False, "reason": "没有本地候选可重排"}
    if external.get("ok") and external.get("ranked"):
        results = list(external.get("ranked") or [])
        rerank_mode = "external_then_local"
    else:
        rerank_mode = "local_explainable"
    report = {
        "ok": bool(base.get("ok")),
        "checked_at": _now(),
        "query": query,
        "top_k": top_k,
        "provider": base.get("provider"),
        "rerank_mode": rerank_mode,
        "external_rerank": {k: v for k, v in external.items() if k != "ranked"},
        "results": results[:max(0, top_k)],
    }
    path = _write(out_dir, "last_vector_query_v30.json", report)
    report["paths_written"] = {"json": str(path)}
    write_json(path, report)
    return report


def production_gaps_v30(storage: Any, project_id: str) -> dict[str, Any]:
    paths = storage.ensure_project_dirs(project_id)
    out_dir = _rag_dir(storage, project_id)
    rag_gap = vector_rag_gaps_v29(storage, project_id)
    health = provider_health_v30(storage, project_id)
    behavior_path = Path(paths.control) / "behavior_v28" / "behavior_acceptance.json"
    production_path = out_dir / "production_acceptance_v30.json"
    query_path = out_dir / "last_vector_query_v30.json"
    checks = [
        {"name": "true_vector_rag", "ok": bool(rag_gap.get("ok")), "evidence": (rag_gap.get("paths_written") or {}).get("json")},
        {"name": "not_hash_vector", "ok": bool((health.get("embedding") or {}).get("not_hash_vector")), "evidence": (health.get("paths_written") or {}).get("json")},
        {"name": "provider_health", "ok": bool(health.get("ok")), "evidence": (health.get("paths_written") or {}).get("json")},
        {"name": "explainable_query", "ok": query_path.exists(), "evidence": str(query_path)},
        {"name": "behavior_acceptance", "ok": behavior_path.exists(), "evidence": str(behavior_path)},
        {"name": "production_acceptance", "ok": production_path.exists(), "evidence": str(production_path)},
    ]
    missing = [c for c in checks if not c["ok"]]
    report = {
        "ok": not missing,
        "checked_at": _now(),
        "checks": checks,
        "missing": missing,
        "production_aligned": len(checks) - len(missing),
        "total": len(checks),
        "status": "达标" if not missing else "未达标",
    }
    path = _write(out_dir, "production_gap_matrix_v30.json", report)
    report["paths_written"] = {"json": str(path)}
    write_json(path, report)
    return report


def production_optimize_v30(storage: Any, project_id: str, *, chapter_no: int = 1, query: str = "", top_k: int = 8, budget: int = 24000) -> dict[str, Any]:
    out_dir = _rag_dir(storage, project_id)
    started = time.time()
    q = query or "主角"
    # First run the local writing/commit/projection loop so a fresh project has
    # real chapter/state material before vector indexing.
    behavior = behavior_run_v28_command(storage, project_id, chapter_no, budget=budget, query=q)
    build = build_true_vector_rag(storage, project_id)
    eval_report = vector_rag_eval_v29(storage, project_id)
    query_report = query_vector_rag_v30(storage, project_id, q, top_k=top_k, exclude_chapter=0)
    health = provider_health_v30(storage, project_id)
    acceptance_items = [
        {"name": "vector_build", "ok": bool(build.get("ok")), "evidence": (build.get("paths_written") or {}).get("index")},
        {"name": "vector_eval", "ok": bool(eval_report.get("ok")), "evidence": (eval_report.get("paths_written") or {}).get("json")},
        {"name": "query_rerank", "ok": bool(query_report.get("ok")) and bool(query_report.get("results")), "evidence": (query_report.get("paths_written") or {}).get("json")},
        {"name": "provider_health", "ok": bool(health.get("ok")), "evidence": (health.get("paths_written") or {}).get("json")},
        {"name": "behavior_loop", "ok": bool(behavior.get("ok")), "evidence": behavior.get("path")},
        {"name": "rejected_non_pollution", "ok": bool(((behavior.get("blocks") or {}).get("negative_case") or {}).get("ok")), "evidence": behavior.get("path")},
    ]
    failed = [x for x in acceptance_items if not x["ok"]]
    report = {
        "ok": not failed,
        "generated_at": _now(),
        "duration_seconds": round(time.time() - started, 3),
        "acceptance": acceptance_items,
        "failed": failed,
        "provider": build.get("provider"),
        "rerank_mode": query_report.get("rerank_mode"),
        "external_embedding_verified": bool((build.get("provider") or {}).get("external")),
        "external_rerank_verified": bool((query_report.get("external_rerank") or {}).get("used")),
        "local_production_acceptance": not failed,
        "boundary": "外部 embedding/rerank 的真实联网验证会在配置对应环境变量时执行；无配置时使用本地 TF-IDF sparse vector + explainable rerank 验收。",
    }
    path = _write(out_dir, "production_acceptance_v30.json", report)
    report["paths_written"] = {"json": str(path)}
    write_json(path, report)
    # Recompute gaps after writing acceptance.
    gaps = production_gaps_v30(storage, project_id)
    report["gaps_after"] = gaps
    write_json(path, report)
    return report


def production_query_v30(storage: Any, project_id: str, query: str, *, top_k: int = 8) -> dict[str, Any]:
    return query_vector_rag_v30(storage, project_id, query, top_k=top_k)
