from __future__ import annotations


from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parents[3]
CONFIG_DIR = ROOT_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "config.json"
DATA_DIR = ROOT_DIR / "data"
LEGACY_COMMON_DIR = DATA_DIR / "common"
LEGACY_CONFIG_FILE = LEGACY_COMMON_DIR / "config.json"


APP_SYSTEM_DIR = DATA_DIR / "app_system"
APP_SYSTEM_BACKUP_DIR = APP_SYSTEM_DIR / "app_system_backups"
APP_SYSTEM_COMPARE_DIR = APP_SYSTEM_DIR / "app_system_compare_reports"
APP_SYSTEM_DEBUG_DIR = APP_SYSTEM_DIR / "app_system_debug"
APP_SYSTEM_HISTORY_DIR = APP_SYSTEM_DIR / "app_system_history"
SYSTEM_TASK_LOG_DIR = APP_SYSTEM_DIR / "app_system_tasklogs"
LOG_NAME = "task.log"
LATEST_LOG_NAME = "latest_task.log"
LOG_FILE = SYSTEM_TASK_LOG_DIR / LATEST_LOG_NAME

PROCESS_NOVEL_DIR = DATA_DIR / "novel_processor"
PROCESS_BACKUP_DIR = PROCESS_NOVEL_DIR / "novel_process_backups"
PROCESS_COMPARE_DIR = PROCESS_NOVEL_DIR / "novel_process_compare_reports"
PROCESS_DEBUG_DIR = PROCESS_NOVEL_DIR / "novel_process_debug"
PROCESS_HISTORY_DIR = PROCESS_NOVEL_DIR / "novel_process_history"
PROCESS_NOVEL_LOG_DIR = PROCESS_NOVEL_DIR / "novel_process_tasklogs"
PROCESS_OUTPUT_DIR = PROCESS_NOVEL_DIR / "novel_process_outputs"

WEB_CRAWLER_DIR = DATA_DIR / "novel_crawler"
WEB_CRAWLER_BACKUP_DIR = WEB_CRAWLER_DIR / "novel_crawl_backups"
WEB_CRAWLER_COMPARE_DIR = WEB_CRAWLER_DIR / "novel_crawl_compare_reports"
WEB_CRAWLER_DEBUG_DIR = WEB_CRAWLER_DIR / "novel_crawl_debug"
WEB_CRAWLER_HISTORY_DIR = WEB_CRAWLER_DIR / "novel_crawl_history"
WEB_CRAWLER_LOG_DIR = WEB_CRAWLER_DIR / "novel_crawl_tasklogs"
WEB_CRAWLER_OUTPUT_DIR = WEB_CRAWLER_DIR / "novel_crawl_outputs"

CHARACTER_MATERIAL_DIR = DATA_DIR / "character_material"
CHARACTER_MATERIAL_BACKUP_DIR = CHARACTER_MATERIAL_DIR / "character_material_backups"
CHARACTER_MATERIAL_CHAPTER_DIR = CHARACTER_MATERIAL_DIR / "character_material_chapters"
CHARACTER_MATERIAL_COMPARE_DIR = CHARACTER_MATERIAL_DIR / "character_material_compare_reports"
CHARACTER_MATERIAL_DEBUG_DIR = CHARACTER_MATERIAL_DIR / "character_material_debug"
CHARACTER_MATERIAL_HISTORY_DIR = CHARACTER_MATERIAL_DIR / "character_material_history"
CHARACTER_MATERIAL_LOG_DIR = CHARACTER_MATERIAL_DIR / "character_material_tasklogs"
CHARACTER_MATERIAL_OUTPUT_DIR = CHARACTER_MATERIAL_DIR / "character_material_outputs"

PUBLISH_DIR = DATA_DIR / "fanqie_publisher"
PUBLISH_BACKUP_DIR = PUBLISH_DIR / "fanqie_publish_backups"
PUBLISH_COMPARE_DIR = PUBLISH_DIR / "fanqie_publish_compare_reports"
PUBLISH_DEBUG_DIR = PUBLISH_DIR / "fanqie_publish_debug"
PUBLISH_TRACKER_DIR = PUBLISH_DIR / "fanqie_publish_tracker"
AUTO_PUBLISH_LOG_DIR = PUBLISH_DIR / "fanqie_publish_tasklogs"

CHAPTER_SYNC_DIR = DATA_DIR / "fanqie_syncer"
CHAPTER_SYNC_BACKUP_DIR = CHAPTER_SYNC_DIR / "fanqie_sync_backups"
CHAPTER_SYNC_COMPARE_DIR = CHAPTER_SYNC_DIR / "fanqie_sync_compare_reports"
CHAPTER_SYNC_DEBUG_DIR = CHAPTER_SYNC_DIR / "fanqie_sync_debug"
CHAPTER_SYNC_HISTORY_DIR = CHAPTER_SYNC_DIR / "fanqie_sync_history"
CHAPTER_SYNC_LOG_DIR = CHAPTER_SYNC_DIR / "fanqie_sync_tasklogs"

BROWSER_DATA_DIR = DATA_DIR / "fanqie_web"
FANQIE_WEB_BACKUP_DIR = BROWSER_DATA_DIR / "fanqie_web_backups"
FANQIE_WEB_COMPARE_DIR = BROWSER_DATA_DIR / "fanqie_web_compare_reports"
FANQIE_WEB_DEBUG_DIR = BROWSER_DATA_DIR / "fanqie_web_debug"
FANQIE_WEB_HISTORY_DIR = BROWSER_DATA_DIR / "fanqie_web_history"
FANQIE_WEB_LOG_DIR = BROWSER_DATA_DIR / "fanqie_web_tasklogs"
FANQIE_AUTH_STATE_FILE = BROWSER_DATA_DIR / "state.json"

STANDARD_DATA_DIRECTORIES: tuple[Path, ...] = (
    APP_SYSTEM_BACKUP_DIR,
    APP_SYSTEM_COMPARE_DIR,
    APP_SYSTEM_DEBUG_DIR,
    APP_SYSTEM_HISTORY_DIR,
    SYSTEM_TASK_LOG_DIR,
    PROCESS_BACKUP_DIR,
    PROCESS_COMPARE_DIR,
    PROCESS_DEBUG_DIR,
    PROCESS_HISTORY_DIR,
    PROCESS_NOVEL_LOG_DIR,
    WEB_CRAWLER_BACKUP_DIR,
    WEB_CRAWLER_COMPARE_DIR,
    WEB_CRAWLER_DEBUG_DIR,
    WEB_CRAWLER_HISTORY_DIR,
    WEB_CRAWLER_LOG_DIR,
    PUBLISH_BACKUP_DIR,
    PUBLISH_COMPARE_DIR,
    PUBLISH_DEBUG_DIR,
    PUBLISH_TRACKER_DIR,
    AUTO_PUBLISH_LOG_DIR,
    CHAPTER_SYNC_BACKUP_DIR,
    CHAPTER_SYNC_COMPARE_DIR,
    CHAPTER_SYNC_DEBUG_DIR,
    CHAPTER_SYNC_HISTORY_DIR,
    CHAPTER_SYNC_LOG_DIR,
    FANQIE_WEB_BACKUP_DIR,
    FANQIE_WEB_COMPARE_DIR,
    FANQIE_WEB_DEBUG_DIR,
    FANQIE_WEB_HISTORY_DIR,
    FANQIE_WEB_LOG_DIR,
)

PROJECT_DIRECTORIES: tuple[Path, ...] = (
    CONFIG_DIR,
    DATA_DIR,
    APP_SYSTEM_DIR,
    PROCESS_NOVEL_DIR,
    PROCESS_OUTPUT_DIR,
    WEB_CRAWLER_DIR,
    WEB_CRAWLER_OUTPUT_DIR,
    CHARACTER_MATERIAL_DIR,
    CHARACTER_MATERIAL_BACKUP_DIR,
    CHARACTER_MATERIAL_CHAPTER_DIR,
    CHARACTER_MATERIAL_COMPARE_DIR,
    CHARACTER_MATERIAL_DEBUG_DIR,
    CHARACTER_MATERIAL_HISTORY_DIR,
    CHARACTER_MATERIAL_LOG_DIR,
    CHARACTER_MATERIAL_OUTPUT_DIR,
    PUBLISH_DIR,
    CHAPTER_SYNC_DIR,
    BROWSER_DATA_DIR,
    *STANDARD_DATA_DIRECTORIES,
)

LOG_CATEGORIES: dict[str, Path] = {
    "system": SYSTEM_TASK_LOG_DIR,
    "auto_publish": AUTO_PUBLISH_LOG_DIR,
    "chapter_sync": CHAPTER_SYNC_LOG_DIR,
    "process_novel": PROCESS_NOVEL_LOG_DIR,
    "web_crawler": WEB_CRAWLER_LOG_DIR,
    "character_material": CHARACTER_MATERIAL_LOG_DIR,
    "fanqie_web": FANQIE_WEB_LOG_DIR,
}


def ensure_data_directories() -> None:
    for directory in PROJECT_DIRECTORIES:
        directory.mkdir(parents=True, exist_ok=True)


def task_log_file(category: str) -> Path:
    directory = LOG_CATEGORIES.get(category, SYSTEM_TASK_LOG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return directory / f"task_{stamp}.log"


def latest_log_file(category: str) -> Path:
    directory = LOG_CATEGORIES.get(category, SYSTEM_TASK_LOG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    logs = sorted(directory.glob("task_*.log"), key=_path_mtime, reverse=True)
    return logs[0] if logs else directory / LATEST_LOG_NAME


def get_state_paths() -> dict[str, str]:
    ensure_data_directories()
    return {
        "config": str(CONFIG_DIR),
        "config_file": str(CONFIG_FILE),
        "data": str(DATA_DIR),
        "task_logs": str(DATA_DIR),
        "novel_processor": str(PROCESS_NOVEL_DIR),
        "novel_crawler": str(WEB_CRAWLER_DIR),
        "character_material": str(CHARACTER_MATERIAL_DIR),
        "fanqie_publisher": str(PUBLISH_DIR),
        "fanqie_syncer": str(CHAPTER_SYNC_DIR),
        "system_logs": str(SYSTEM_TASK_LOG_DIR),
        "auto_publish_logs": str(AUTO_PUBLISH_LOG_DIR),
        "publisher_debug": str(PUBLISH_DEBUG_DIR),
        "publisher_tracker": str(PUBLISH_TRACKER_DIR),
        "publisher_backups": str(PUBLISH_BACKUP_DIR),
        "publisher_compare": str(PUBLISH_COMPARE_DIR),
        "chapter_sync_logs": str(CHAPTER_SYNC_LOG_DIR),
        "process_novel_logs": str(PROCESS_NOVEL_LOG_DIR),
        "web_crawler_logs": str(WEB_CRAWLER_LOG_DIR),
        "character_material_logs": str(CHARACTER_MATERIAL_LOG_DIR),
        "fanqie_web_logs": str(FANQIE_WEB_LOG_DIR),
        "process_novel_outputs": str(PROCESS_OUTPUT_DIR),
        "web_crawler_outputs": str(WEB_CRAWLER_OUTPUT_DIR),
        "character_material_outputs": str(CHARACTER_MATERIAL_OUTPUT_DIR),
        "character_material_chapters": str(CHARACTER_MATERIAL_CHAPTER_DIR),
        "novel_process_outputs": str(PROCESS_OUTPUT_DIR),
        "novel_crawl_outputs": str(WEB_CRAWLER_OUTPUT_DIR),
        "fanqie_sync_tasklogs": str(CHAPTER_SYNC_LOG_DIR),
        "process_novel_backups": str(PROCESS_BACKUP_DIR),
        "process_novel_compare": str(PROCESS_COMPARE_DIR),
        "process_novel_debug": str(PROCESS_DEBUG_DIR),
        "process_novel_history": str(PROCESS_HISTORY_DIR),
        "web_crawler_backups": str(WEB_CRAWLER_BACKUP_DIR),
        "web_crawler_compare": str(WEB_CRAWLER_COMPARE_DIR),
        "web_crawler_debug": str(WEB_CRAWLER_DEBUG_DIR),
        "web_crawler_history": str(WEB_CRAWLER_HISTORY_DIR),
        "character_material_backups": str(CHARACTER_MATERIAL_BACKUP_DIR),
        "character_material_compare": str(CHARACTER_MATERIAL_COMPARE_DIR),
        "character_material_debug": str(CHARACTER_MATERIAL_DEBUG_DIR),
        "character_material_history": str(CHARACTER_MATERIAL_HISTORY_DIR),
        "chapter_sync_backups": str(CHAPTER_SYNC_BACKUP_DIR),
        "chapter_sync_compare": str(CHAPTER_SYNC_COMPARE_DIR),
        "chapter_sync_history": str(CHAPTER_SYNC_HISTORY_DIR),
        "chapter_sync_debug": str(CHAPTER_SYNC_DEBUG_DIR),
        "fanqie_web_backups": str(FANQIE_WEB_BACKUP_DIR),
        "fanqie_web_compare": str(FANQIE_WEB_COMPARE_DIR),
        "fanqie_web_debug": str(FANQIE_WEB_DEBUG_DIR),
        "fanqie_web_history": str(FANQIE_WEB_HISTORY_DIR),
        "debug": str(CHAPTER_SYNC_DEBUG_DIR),
        "fanqie_auth_state": str(FANQIE_AUTH_STATE_FILE),
    }




def _path_mtime(path: Path) -> float:
    return path.stat().st_mtime
