from __future__ import annotations


import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from backend.services.service_ad_cleaner import ad_profiles
from backend.services.service_chapter_text_parser import chapters_to_preview
from backend.services.novel_text.chapter_parser import parse_chapter_source
from backend.models.chapter import Chapter as PreviewChapter
from backend.workflows.clean_text import clean_text
from backend.workflows.crawl_web_chapters import crawl_web_chapters, preview_web_crawler_output
from backend.workflows.process_novel import analyze_novel_file, process_novel
from backend.workflows.split_novel import preview_novel_split_output, split_novel
from backend.workflows.publish_missing_chapters import publish_missing_chapters
from backend.workflows.sync_existing_chapters import sync_existing_chapters
from backend.shared.app.app_config import deep_update, load_config, save_config, set_config_path
from backend.shared.task.task_callbacks import TaskCallbacks
from backend.shared.task.task_event import TaskEvent
from backend.shared.app.app_logging import get_logger, setup_logging
from backend.shared.app.app_paths import FANQIE_AUTH_STATE_FILE, LOG_FILE, ensure_data_directories, get_state_paths, latest_log_file, task_log_file
from backend.shared.json.json_serialization import to_json_safe
from backend.shared.app.app_data_reset import reset_app_data, reset_login_state
from backend.shared.task.task_result import TaskResult
from backend.shared.task.task_registry import TaskRegistry
from backend.api.desktop_api import open_file, open_login_state_dialog, open_native_dialog, open_path, open_source_dialog
from backend.adapters.novel_crawler.crawler_service import NovelCrawlerService
from backend.adapters.character_material import CharacterMaterialService
from backend.adapters.current_plot import CurrentPlotService
from backend.adapters.webnovel_writer import WebnovelWriterService
from backend.api.frontend_api import FrontendBridge


def _get_config_path(config: dict[str, Any], dotted_path: str) -> str:
    value: Any = config
    for part in str(dotted_path or '').split('.'):
        if not isinstance(value, dict) or part not in value:
            return ''
        value = value.get(part)
    return str(value or '')

LOGGER = get_logger(__name__)


class WebviewApi:
    def __init__(self) -> None:
        ensure_data_directories()
        self._window = None
        self._config = load_config()
        self._tasks = TaskRegistry()
        self._bridge = FrontendBridge()
        self._character_material = CharacterMaterialService()
        self._current_plot = CurrentPlotService()
        self._webnovel_writer = WebnovelWriterService()
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
            "crawlNovelSites": NovelCrawlerService.sites(),
            "characterMaterialPlatforms": self._character_material.platforms(),
            "characterMaterialDefaults": {key: self._character_material.default_platform_values(key) for key in self._character_material.platforms()},
            "currentPlotPlatforms": self._current_plot.platforms(),
            "currentPlotDefaults": {key: self._current_plot.default_platform_values(key) for key in self._current_plot.platforms()},
            "webnovelWriterPlatforms": self._webnovel_writer.platforms(),
            "webnovelWriterDefaults": {key: self._webnovel_writer.default_platform_values(key) for key in self._webnovel_writer.platforms()},
            "webnovelWriterProjects": self._webnovel_writer.list_projects().get("projects", []),
            "adProfiles": ad_profiles(),
            "logTail": self._read_log_tail(),
        }

    def save_config(self, config: dict[str, Any] | None) -> bool:
        deep_update(self._config, config or {})
        save_config(self._config)
        return True

    def choose_file(self, config_path: str = "", save: bool = False, save_filename: str = "output.txt") -> str:
        path = self._open_dialog(save=save, folder=False, save_filename=save_filename)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            save_config(self._config)
        return path

    def choose_folder(self, config_path: str = "") -> str:
        path = self._open_dialog(save=False, folder=True)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            save_config(self._config)
        return path

    def choose_source(self, config_path: str = "") -> str:
        current = _get_config_path(self._config, config_path)
        path = open_source_dialog(self._window, current_path=current)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            save_config(self._config)
        return path

    def choose_login_state(self, config_path: str = "") -> str:
        current = _get_config_path(self._config, config_path)
        path = open_login_state_dialog(self._window, current_path=current)
        if path and config_path:
            set_config_path(self._config, config_path, path)
            save_config(self._config)
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
        return open_path("process_novel_backups")

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
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return process_novel(payload, callbacks)

        return self._start_task("process_novel", payload.get("logTarget") or "process_novel", worker)

    def novel_split_preview(self, input_file: str = "", output_dir: str = "") -> dict[str, Any]:
        try:
            return preview_novel_split_output(input_file, output_dir)
        except Exception as exc:
            return {"ok": False, "message": str(exc), "outputDir": ""}

    def novel_split_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return split_novel(payload, callbacks)

        return self._start_task("novel_splitter", "novel_splitter", worker)

    def clean_text_run(self, payload: dict[str, Any]) -> bool:
        page = "clean_text_breaks" if payload.get("scope") == "move" else "clean_text_ads"
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return clean_text(payload, callbacks)

        return self._start_task("clean_text", page, worker)

    def auto_publish_list_chapters(self, file_path: str) -> dict[str, Any]:
        return self._list_chapters(file_path)

    def auto_publish_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return publish_missing_chapters(payload, callbacks)

        return self._start_task("auto_publish", "auto_publish", worker)

    def chapter_sync_list_chapters(self, file_path: str) -> dict[str, Any]:
        return self._list_chapters(file_path)

    def chapter_sync_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return sync_existing_chapters(payload, callbacks)

        return self._start_task("chapter_sync", "chapter_sync", worker)

    def web_crawler_preview(self, novel_url: str = "", output_file: str = "") -> dict[str, Any]:
        try:
            return preview_web_crawler_output(novel_url, output_file)
        except Exception as exc:
            return {"ok": False, "message": str(exc), "title": "", "outputFile": ""}

    def web_crawler_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return crawl_web_chapters(payload, callbacks)

        return self._start_task("web_crawler", "web_crawler", worker)



    def webnovel_writer_platform_defaults(self, platform: str = "deepseek") -> dict[str, Any]:
        try:
            values = self._webnovel_writer.default_platform_values(platform)
            return {"ok": True, **values}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def webnovel_writer_list_projects(self) -> dict[str, Any]:
        try:
            return self._webnovel_writer.list_projects()
        except Exception as exc:
            return {"ok": False, "message": str(exc), "projects": []}

    def webnovel_writer_save_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._webnovel_writer.save_project(payload or {})
            meta = result.get("meta", {})
            paths = result.get("paths", {})
            cfg = self._config.setdefault("webnovel_writer", {})
            cfg["projectId"] = meta.get("project_id", "")
            if paths.get("root"):
                cfg["projectPath"] = paths.get("root", "")
            if meta.get("novel_file"):
                cfg["novelFilePath"] = meta.get("novel_file", "")
            if meta.get("story_config_source"):
                cfg["storyConfigPath"] = meta.get("story_config_source", "")
            save_config(self._config)
            return result
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def webnovel_writer_load_project(self, project_id: str = "") -> dict[str, Any]:
        try:
            return self._webnovel_writer.load_project(project_id)
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def webnovel_writer_dashboard(self, project_id: str = "") -> dict[str, Any]:
        try:
            return self._webnovel_writer.dashboard(project_id)
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def webnovel_writer_plan_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return self._webnovel_writer.plan(payload or {}, callbacks)

        return self._start_task("webnovel_writer", "webnovel_writer", worker)

    def webnovel_writer_write_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            if (payload or {}).get("batch"):
                return self._webnovel_writer.batch_write(payload or {}, callbacks)
            return self._webnovel_writer.write_chapter(payload or {}, callbacks)

        return self._start_task("webnovel_writer", "webnovel_writer", worker)

    def webnovel_writer_review_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return self._webnovel_writer.review_chapter(payload or {}, callbacks)

        return self._start_task("webnovel_writer", "webnovel_writer", worker)

    def webnovel_writer_export_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return self._webnovel_writer.export(payload or {}, callbacks)

        return self._start_task("webnovel_writer", "webnovel_writer", worker)

    def webnovel_writer_validate_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            return self._webnovel_writer.validate_project(payload or {}, callbacks)

        return self._start_task("webnovel_writer", "webnovel_writer", worker)

    def webnovel_writer_stop(self) -> bool:
        return self._stop_task("webnovel_writer", "webnovel_writer", "已请求停止 webnovel-writer 任务，当前步骤结束后会停下。")

    def character_material_platform_defaults(self, platform: str = "deepseek") -> dict[str, Any]:
        try:
            values = self._character_material.default_platform_values(platform)
            return {"ok": True, **values}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_material_split(self, source: str) -> dict[str, Any]:
        try:
            path = self._character_material.split_novel(source)
            set_config_path(self._config, "character_material.source", str(path))
            save_config(self._config)
            return {"ok": True, "message": f"已切分章节目录：{path}", "path": str(path), "table": self._character_material.list_chapters(path)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_material_list(self, source: str) -> dict[str, Any]:
        try:
            return {"ok": True, "message": "章节索引已读取。", "table": self._character_material.list_chapters(source)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def character_material_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            result = self._character_material.extract(payload, callbacks)
            stats = result.stats.to_dict()
            return TaskResult(
                ok=True,
                message=f"角色素材抽取完成：{result.output_path}",
                path=result.output_path,
                result_kind="output_file",
                data={"stats": stats},
            )

        return self._start_task("character_material", "character_material", worker)

    def character_material_stop(self) -> bool:
        return self._stop_task("character_material", "character_material", "已请求停止抽取，当前章节结束后会停下。")

    def current_plot_platform_defaults(self, platform: str = "deepseek") -> dict[str, Any]:
        try:
            values = self._current_plot.default_platform_values(platform)
            return {"ok": True, **values}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def current_plot_list(self, source: str) -> dict[str, Any]:
        try:
            return {"ok": True, "message": "章节索引已读取。", "table": self._current_plot.list_chapters(source)}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    def current_plot_run(self, payload: dict[str, Any]) -> bool:
        def worker(callbacks: TaskCallbacks) -> TaskResult | dict[str, Any]:
            result = self._current_plot.update(payload, callbacks)
            return TaskResult(
                ok=True,
                message=f"当前剧情更新完成：{result.output_path}",
                path=result.output_path,
                result_kind="output_file",
                data=result.to_dict(),
            )

        return self._start_task("current_plot", "current_plot", worker)

    def current_plot_stop(self) -> bool:
        return self._stop_task("current_plot", "current_plot", "已请求停止总结，当前章节结束后会停下。")

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

    def _start_task(self, task_name: str, page: str, worker: Callable[[TaskCallbacks], TaskResult | dict[str, Any]]) -> bool:
        if not self._tasks.start_task(task_name):
            self._bridge.emit_log(page, "任务正在运行，请稍候。", "warning")
            return False
        thread = threading.Thread(target=self._run_worker, args=(task_name, page, worker), daemon=True)
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

    def _run_worker(self, task_name: str, page: str, worker: Callable[[TaskCallbacks], TaskResult | dict[str, Any]]) -> None:
        category = _log_category_for_page(page)
        log_path = None if page in {"auto_publish", "chapter_sync", "web_crawler"} else task_log_file(category)
        if log_path:
            self._latest_task_logs[category] = str(log_path)
            self._write_task_log(log_path, f"任务：{task_name}\n开始：{datetime.now():%Y-%m-%d %H:%M:%S}\n")

        def emit_log(message: str, level: str = "info") -> None:
            if log_path:
                self._write_task_log(log_path, f"[{datetime.now():%H:%M:%S}] [{level}] {message}\n")
            self._bridge.emit_log(page, message, level)

        def emit_progress(current: float, total: float) -> None:
            self._bridge.emit_progress(page, current, total)

        def emit_event(event: TaskEvent) -> None:
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
            payload = result.to_dict() if isinstance(result, TaskResult) else dict(result)
            safe_payload = to_json_safe(payload)
            if log_path:
                self._write_task_log(log_path, f"结束：{safe_payload.get('message') or ''}\n")
            self._bridge.emit_done(page, bool(safe_payload.get("ok")), safe_payload)
        except Exception as exc:
            LOGGER.exception("Task failed: %s", task_name)
            if log_path:
                self._write_task_log(log_path, f"异常：{exc}\n")
            self._bridge.emit_log(page, str(exc), "error")
            self._bridge.emit_done(page, False, {"ok": False, "message": str(exc)})
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
        "character_material": "character_material",
        "current_plot": "current_plot",
        "webnovel_writer": "webnovel_writer",
        "process_novel": "process_novel",
        "process_novel_batch": "process_novel",
        "clean_text_ads": "process_novel",
        "clean_text_breaks": "process_novel",
        "novel_splitter": "process_novel",
    }.get(normalized, "system")


NovelToolsApi = WebviewApi
__all__ = ["WebviewApi", "NovelToolsApi"]


