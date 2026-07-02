from __future__ import annotations


import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend.novel.ad_cleaner import ad_profiles
from backend.novel.reader import chapters_to_preview
from backend.novel.source import parse_chapter_source
from backend.novel.chapters import Chapter as PreviewChapter
from backend.actions.clean import clean_text
from backend.actions.crawl import crawl_chapters, preview_crawl_output
from backend.actions.process import analyze_novel_file, process_novel
from backend.actions.split import preview_novel_split_output, split_novel
from backend.actions.publish import publish_chapters
from backend.actions.sync import sync_chapters
from backend.settings import deep_update, load_config, save_config, set_config_path
from backend.tasks.callbacks import TaskCallbacks
from backend.tasks.events import TaskEvent
from backend.log_setup import get_logger, setup_logging
from backend.paths import FANQIE_AUTH_STATE_FILE, LOG_FILE, ensure_data_directories, get_state_paths, latest_log_file, task_log_file
from backend.json_files import to_json_safe
from backend.data_reset import reset_app_data, reset_login_state
from backend.tasks.outcome import TaskOutcome
from backend.runs import append_run_event, begin_run, finish_run
from backend.workspaces import ensure_workspace_for_payload
from backend.tasks.registry import TaskRegistry
from backend.api.desktop import open_file, open_login_state_dialog, open_native_dialog, open_path, open_source_dialog
from backend.crawling.crawler import NovelCrawler
from backend.story_analysis import CharacterNotesExtractor
from backend.story_analysis import PlotSummaryUpdater
from backend.api.frontend import FrontendBridge


def _get_config_path(config: dict[str, Any], dotted_path: str) -> str:
    value: Any = config
    for part in str(dotted_path or '').split('.'):
        if not isinstance(value, dict) or part not in value:
            return ''
        value = value.get(part)
    return str(value or '')

LOGGER = get_logger(__name__)


class WebviewRouter:
    def __init__(self) -> None:
        ensure_data_directories()
        self._window = None
        self._config = load_config()
        self._tasks = TaskRegistry()
        self._bridge = FrontendBridge()
        self._character_notes = CharacterNotesExtractor()
        self._plot_notes = PlotSummaryUpdater()
        self._latest_task_logs: dict[str, str] = {}

    def bind_window(self, window: Any) -> None:
        self._window = window
        self._bridge.bind_window(window)

    def get_state(self) -> dict[str, Any]:
        return {
            "config": self._config,
            "recentFiles": [],
            "paths": get_state_paths(),
            "platforms": {"openai": "OpenAI", "local": "本地"},
            "crawlNovelSites": NovelCrawler.sites(),
            "characterNotesPlatforms": self._character_notes.platforms(),
            "characterNotesDefaults": {key: self._character_notes.default_platform_values(key) for key in self._character_notes.platforms()},
            "plotNotesPlatforms": self._plot_notes.platforms(),
            "plotNotesDefaults": {key: self._plot_notes.default_platform_values(key) for key in self._plot_notes.platforms()},
            "adProfiles": ad_profiles(),
            "logTail": self._read_log_tail(),
        }

    def save_config(self, config: dict[str, Any] | None) -> bool:
        deep_update(self._config, config or {})
        self._config = save_config(self._config)
        return True

    def choose_file(self, config_path: str = "", save: bool = False, save_filename: str = "output.txt") -> str:
        path = self._open_dialog(save=save, folder=False, save_filename=save_filename)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            self._config = save_config(self._config)
        return path

    def choose_folder(self, config_path: str = "") -> str:
        path = self._open_dialog(save=False, folder=True)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            self._config = save_config(self._config)
        return path

    def choose_source(self, config_path: str = "") -> str:
        current = _get_config_path(self._config, config_path)
        path = open_source_dialog(self._window, current_path=current)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            self._config = save_config(self._config)
        return path

    def choose_login_state(self, config_path: str = "") -> str:
        current = _get_config_path(self._config, config_path)
        path = open_login_state_dialog(self._window, current_path=current)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            self._config = save_config(self._config)
        return path

    def choose_directory(self, config_path: str = "") -> str:
        return self.choose_folder(config_path)

    def open_path(self, path_key: str) -> bool:
        return open_path(path_key)

    def open_log(self, page: str = "") -> bool:
        category = _log_category_for_page(page)
        remembered = self._latest_task_logs.get(category)
        if remembered and Path(remembered).exists():
            return open_file(remembered, create=True)
        return open_file(str(latest_log_file(category)), create=True)

    def open_backup(self, path: str = "") -> bool:
        if path:
            return open_file(path)
        return open_path("novel_processing_backups")

    def check_login_state(self) -> bool:
        return FANQIE_AUTH_STATE_FILE.exists()

    def do_login(self) -> bool:
        self._bridge.emit_log("auto_publish", "请在下一次自动打开的浏览器中完成登录；登录成功后会保存到当前账号的 state JSON。", "info")
        return True

    def reset_login(self) -> dict[str, Any]:
        result = reset_login_state()
        self._bridge.emit_log("auto_publish", str(result.get("message") or "已重置授权。"), "warning" if result.get("ok") else "error")
        return result


    def reset_app_data(self) -> dict[str, Any]:
        result = reset_app_data(preserve_auth_state=True)
        setup_logging()
        self._config = load_config()
        self._bridge.emit_log("auto_publish", str(result.get("message") or "已重置数据。"), "success" if result.get("ok") else "error")
        return result

    def process_novel_analyze(self, file_path: str) -> dict[str, Any]:
        try:
            return analyze_novel_file(file_path).to_dict()
        except Exception as exc:
            return {"ok": False, "message": str(exc), "chapters": []}

    def process_novel_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return process_novel(payload, callbacks)

        return self._start_task("process_novel", payload.get("logTarget") or "process_novel", worker, payload)

    def novel_split_preview(self, input_file: str = "", output_dir: str = "") -> dict[str, Any]:
        try:
            return preview_novel_split_output(input_file, output_dir)
        except Exception as exc:
            return {"ok": False, "message": str(exc), "outputDir": ""}

    def novel_split_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return split_novel(payload, callbacks)

        return self._start_task("novel_splitter", "novel_splitter", worker, payload)

    def clean_text_run(self, payload: dict[str, Any]) -> bool:
        page = "clean_text_breaks" if payload.get("scope") == "move" else "clean_text_ads"
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return clean_text(payload, callbacks)

        return self._start_task("clean_text", page, worker, payload)

    def auto_publish_list_chapters(self, file_path: str) -> dict[str, Any]:
        return self._list_chapters(file_path)

    def auto_publish_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return publish_chapters(payload, callbacks)

        return self._start_task("auto_publish", "auto_publish", worker, payload)

    def chapter_sync_list_chapters(self, file_path: str) -> dict[str, Any]:
        return self._list_chapters(file_path)

    def chapter_sync_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return sync_chapters(payload, callbacks)

        return self._start_task("chapter_sync", "chapter_sync", worker, payload)

    def web_crawler_preview(self, novel_url: str = "", output_file: str = "") -> dict[str, Any]:
        try:
            return preview_crawl_output(novel_url, output_file)
        except Exception as exc:
            return {"ok": False, "message": str(exc), "title": "", "outputFile": ""}

    def web_crawler_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            return crawl_chapters(payload, callbacks)

        return self._start_task("web_crawler", "web_crawler", worker, payload)



    def character_notes_platform_defaults(self, platform: str = "deepseek") -> dict[str, Any]:
        try:
            values = self._character_notes.default_platform_values(platform)
            return {"ok": True, **values}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_notes_split(self, source: str) -> dict[str, Any]:
        try:
            path = self._character_notes.split_novel(source)
            set_config_path(self._config, "character_notes.source", str(path))
            self._config = save_config(self._config)
            return {"ok": True, "message": f"已切分章节目录：{path}", "path": str(path), "table": self._character_notes.list_chapters(path)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_notes_list(self, source: str) -> dict[str, Any]:
        try:
            return {"ok": True, "message": "章节索引已读取。", "table": self._character_notes.list_chapters(source)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_notes_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            result = self._character_notes.extract(payload, callbacks)
            stats = result.stats.to_dict()
            return TaskOutcome(
                ok=True,
                message=f"角色素材抽取完成：{result.output_path}",
                path=result.output_path,
                result_kind="output_file",
                data={"stats": stats},
            )

        return self._start_task("character_notes", "character_notes", worker, payload)

    def character_notes_stop(self) -> bool:
        return self._stop_task("character_notes", "character_notes", "已请求停止抽取，当前章节结束后会停下。")

    def plot_notes_platform_defaults(self, platform: str = "deepseek") -> dict[str, Any]:
        try:
            values = self._plot_notes.default_platform_values(platform)
            return {"ok": True, **values}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def plot_notes_list(self, source: str) -> dict[str, Any]:
        try:
            return {"ok": True, "message": "章节索引已读取。", "table": self._plot_notes.list_chapters(source)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def plot_notes_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskOutcome | dict[str, Any]:
            result = self._plot_notes.update(payload, callbacks)
            return TaskOutcome(
                ok=True,
                message=f"当前剧情更新完成：{result.output_path}",
                path=result.output_path,
                result_kind="output_file",
                data=result.to_dict(),
            )

        return self._start_task("plot_notes", "plot_notes", worker, payload)

    def plot_notes_stop(self) -> bool:
        return self._stop_task("plot_notes", "plot_notes", "已请求停止总结，当前章节结束后会停下。")

    def auto_publish_stop(self) -> bool:
        return self._stop_task("auto_publish", "auto_publish", "已请求停止发布，当前章节结束后会停下。")

    def chapter_sync_stop(self) -> bool:
        return self._stop_task("chapter_sync", "chapter_sync", "已请求停止同步，当前章节结束后会停下。")

    def auto_publish_pause(self) -> bool:
        return self._pause_task("auto_publish", "auto_publish", "已暂停发布。")

    def auto_publish_resume(self) -> bool:
        return self._resume_task("auto_publish", "auto_publish", "已继续发布。")

    def chapter_sync_pause(self) -> bool:
        return self._pause_task("chapter_sync", "chapter_sync", "已暂停同步。")

    def chapter_sync_resume(self) -> bool:
        return self._resume_task("chapter_sync", "chapter_sync", "已继续同步。")

    def web_crawler_stop(self) -> bool:
        return self._stop_task("web_crawler", "web_crawler", "已请求停止爬取，正在取消未开始的章节。")

    def _list_chapters(self, file_path: str) -> dict[str, Any]:
        try:
            chapters = parse_chapter_source(file_path)
            preview = [
                PreviewChapter(number=chapter.number, title=chapter.subtitle, body=chapter.content, raw_heading=chapter.full_title).to_preview()
                for chapter in chapters
            ]
            return {"ok": True, "message": f"已识别 {len(chapters)} 个章节。", "chapters": preview}
        except Exception as exc:
            return {"ok": False, "message": str(exc), "chapters": []}

    def _start_task(self, task_name: str, page: str, worker: Callable[[TaskCallbacks], TaskOutcome | dict[str, Any]], payload: dict[str, Any] | None = None) -> bool:
        if not self._tasks.start_task(task_name):
            self._bridge.emit_log(page, "任务正在运行，请稍候。", "warning")
            return False
        thread = threading.Thread(target=self._run_worker, args=(task_name, page, worker, payload or {}), daemon=True)
        thread.start()
        return True

    def _stop_task(self, task_name: str, page: str, message: str) -> bool:
        if not self._tasks.request_stop(task_name):
            self._bridge.emit_log(page, "当前没有正在运行的任务。", "warning")
            return False
        self._bridge.emit_log(page, message, "warning")
        return True


    def _pause_task(self, task_name: str, page: str, message: str) -> bool:
        if not self._tasks.request_pause(task_name):
            self._bridge.emit_log(page, "当前没有正在运行的任务。", "warning")
            return False
        self._bridge.emit_log(page, message, "warning")
        return True

    def _resume_task(self, task_name: str, page: str, message: str) -> bool:
        if not self._tasks.request_resume(task_name):
            self._bridge.emit_log(page, "当前没有正在运行的任务。", "warning")
            return False
        self._bridge.emit_log(page, message, "success")
        return True

    def _run_worker(self, task_name: str, page: str, worker: Callable[[TaskCallbacks], TaskOutcome | dict[str, Any]], payload: dict[str, Any]) -> None:
        category = _log_category_for_page(page)
        log_path = None if page in {"auto_publish", "chapter_sync", "web_crawler"} else task_log_file(category)
        if log_path:
            self._latest_task_logs[category] = str(log_path)
            self._write_task_log(log_path, f"任务：{task_name}\n开始：{datetime.now():%Y-%m-%d %H:%M:%S}\n")
        workspace_id = ensure_workspace_for_payload(payload, workflow=task_name)
        run_dir = begin_run(workflow=task_name, page=page, input_payload=payload, workspace_id=workspace_id)

        def emit_log(message: str, level: str = "info") -> None:
            if log_path:
                self._write_task_log(log_path, f"[{datetime.now():%H:%M:%S}] [{level}] {message}\n")
            append_run_event(run_dir, TaskEvent.from_log_message(page, message, level).to_dict())
            self._bridge.emit_log(page, message, level)

        def emit_progress(current: float, total: float) -> None:
            event = TaskEvent.progress(page, current, total)
            append_run_event(run_dir, event.to_dict())
            self._bridge.emit_progress(page, current, total)

        def emit_event(event: TaskEvent) -> None:
            append_run_event(run_dir, event.to_dict())
            self._bridge.emit_event(event)

        def should_stop() -> bool:
            return self._tasks.is_stop_requested(task_name)

        def should_pause() -> bool:
            return self._tasks.is_pause_requested(task_name)

        callbacks = TaskCallbacks(
            log=emit_log,
            progress=emit_progress,
            should_stop=should_stop,
            should_pause=should_pause,
            event=emit_event,
        )
        try:
            result = worker(callbacks)
            payload = result.to_dict() if isinstance(result, TaskOutcome) else dict(result)
            safe_payload = to_json_safe(payload)
            if log_path:
                self._write_task_log(log_path, f"结束：{safe_payload.get('message') or ''}\n")
            finish_run(run_dir, ok=bool(safe_payload.get("ok")), result=safe_payload)
            self._bridge.emit_done(page, bool(safe_payload.get("ok")), safe_payload)
        except Exception as exc:
            LOGGER.exception("Task failed: %s", task_name)
            if log_path:
                self._write_task_log(log_path, f"异常：{exc}\n")
            error_payload = {"ok": False, "message": str(exc)}
            append_run_event(run_dir, TaskEvent.from_log_message(page, str(exc), "error").to_dict())
            finish_run(run_dir, ok=False, result=error_payload)
            self._bridge.emit_log(page, str(exc), "error")
            self._bridge.emit_done(page, False, error_payload)
        finally:
            self._tasks.finish_task(task_name)

    @staticmethod
    def _write_task_log(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(text)

    def _open_dialog(self, *, save: bool, folder: bool, save_filename: str = "output.txt") -> str:
        return open_native_dialog(self._window, save=save, folder=folder, save_filename=save_filename)

    def _read_log_tail(self, limit: int = 3500) -> str:
        try:
            return LOG_FILE.read_text(encoding="utf-8", errors="ignore")[-limit:] if LOG_FILE.exists() else ""
        except Exception:
            return ""


def _log_category_for_page(page: str) -> str:
    normalized = str(page or "").strip()
    return {
        "auto_publish": "auto_publish",
        "chapter_sync": "chapter_sync",
        "web_crawler": "web_crawler",
        "character_notes": "character_notes",
        "plot_notes": "plot_notes",
        "process_novel": "process_novel",
        "process_novel_batch": "process_novel",
        "clean_text_ads": "process_novel",
        "clean_text_breaks": "process_novel",
        "novel_splitter": "process_novel",
    }.get(normalized, "system")


__all__ = ["WebviewRouter"]


