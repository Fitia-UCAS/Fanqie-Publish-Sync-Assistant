from __future__ import annotations


from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.novel.ad_cleaner import clean_ad_text
from backend.novel.file_rewrite import update_text_file_in_place
from backend.tasks.crawler_log import CrawlerLog
from backend.tasks.callbacks import TaskCallbacks
from backend.paths import CRAWLING_BACKUP_DIR, CRAWLING_OUTPUT_DIR
from backend.tasks.outcome import TaskOutcome
from backend.novel.text_cleaning import format_novel_text
from backend.crawling.records import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WORKERS,
    DEFAULT_REQUEST_DELAY_MAX,
    DEFAULT_REQUEST_DELAY_MIN,
    DEFAULT_TIMEOUT,
    NovelCrawlerRequest,
)
from backend.crawling.crawler import NovelCrawler



def crawl_chapters(payload: dict[str, Any], callbacks: TaskCallbacks | None = None) -> TaskOutcome:
    callbacks = callbacks or TaskCallbacks()
    url = str(payload.get("novelUrl") or "").strip()
    if not url:
        return TaskOutcome(False, "请输入小说目录链接。")

    output = _output_path(payload)
    request = NovelCrawlerRequest(
        novel_url=url,
        output_file=output,
        start=int(payload.get("start") or 1),
        end=_optional_int(payload.get("end")),
        max_workers=int(payload.get("maxWorkers") or DEFAULT_MAX_WORKERS),
        request_delay_min=_float_value(payload.get("requestDelayMin"), DEFAULT_REQUEST_DELAY_MIN),
        request_delay_max=_float_value(payload.get("requestDelayMax"), DEFAULT_REQUEST_DELAY_MAX),
        timeout=int(payload.get("timeout") or DEFAULT_TIMEOUT),
        max_retries=int(payload.get("maxRetries") or DEFAULT_MAX_RETRIES),
        html_fallback=bool(payload.get("htmlFallback", True)),
        detailed_log=bool(payload.get("detailedLog", False)),
    )

    detail_log = CrawlerLog(callbacks)
    detail_log.log("开始：网页抓取。")
    crawler = NovelCrawler()
    result = crawler.crawl_to_txt(
        request,
        emit_log=detail_log.log,
        emit_progress=detail_log.progress,
        stop_requested=callbacks.stop_requested,
    )
    path = Path(result.path or output or CRAWLING_OUTPUT_DIR)
    post_messages: list[str] = []
    post_backup_paths: list[str] = []
    post_ok = True

    if path.exists():
        try:
            update = update_text_file_in_place(path, clean_ad_text, backup_dir=CRAWLING_BACKUP_DIR / "clean", backup=True)
            if update.backup_path:
                post_backup_paths.append(str(update.backup_path))
            post_messages.append("文本清理完成" if update.changed else "文本清理无需修改")
        except Exception as exc:
            detail_log.log(f"文本清理失败：{exc}", "error")
            post_messages.append(f"文本清理失败：{exc}")
            post_ok = False

    if path.exists():
        try:
            update = update_text_file_in_place(path, format_novel_text, backup_dir=CRAWLING_BACKUP_DIR / "format", backup=True)
            if update.backup_path:
                post_backup_paths.append(str(update.backup_path))
            post_messages.append("格式化正文完成" if update.changed else "正文格式无需修改")
        except Exception as exc:
            detail_log.log(f"格式化正文失败：{exc}", "error")
            post_messages.append(f"格式化正文失败：{exc}")
            post_ok = False

    message = result.message
    if post_messages:
        message += "；" + "；".join(post_messages)
    ok = bool(result.ok and post_ok)
    detail_log.finish(ok, message)
    if ok:
        callbacks.emit_log(f"抓取完成：成功 {result.success}/{result.selected}，输出 {path.name}", "success")
    else:
        callbacks.emit_log(f"抓取完成：成功 {result.success}/{result.selected}，有 {result.failed} 章失败（详情见 data/crawling/tasklogs）", "warning")
    return TaskOutcome(
        ok,
        message,
        path=path,
        result_kind="output_file",
        display_name=path.name,
        data={
            "meta": asdict(result),
            "postProcess": {"ok": post_ok, "messages": post_messages},
            "backupPaths": post_backup_paths,
            "backupPath": post_backup_paths[-1] if post_backup_paths else "",
            "backupDir": str(Path(post_backup_paths[-1]).parent) if post_backup_paths else "",
        },
    )


def _output_path(payload: dict[str, Any]) -> Path | None:
    raw = str(payload.get("outputFile") or "").strip()
    if raw:
        return Path(raw)
    CRAWLING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return CRAWLING_OUTPUT_DIR


def preview_crawl_output(novel_url: str, output_file: str | Path | None = None) -> dict[str, Any]:
    url = str(novel_url or "").strip()
    if not url:
        return {"ok": False, "message": "请输入小说目录链接。", "title": "", "outputFile": ""}
    request = NovelCrawlerRequest(novel_url=url, output_file=Path(output_file) if str(output_file or "").strip() else CRAWLING_OUTPUT_DIR)
    crawler = NovelCrawler()
    catalog, output = crawler.preview_output(request)
    output.parent.mkdir(parents=True, exist_ok=True)
    return {
        "ok": True,
        "message": f"已解析书名：{catalog.title}",
        "title": catalog.title,
        "novelId": catalog.novel_id,
        "total": len(catalog.chapters),
        "outputFile": str(output),
        "displayName": output.name,
    }


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        number = int(value)
        return number if number > 0 else None
    except Exception:
        return None


def _float_value(value: Any, default: float) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except Exception:
        return default


