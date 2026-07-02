from __future__ import annotations

from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"

CONFIG_DIR = DATA_DIR / "settings"
CONFIG_FILE = CONFIG_DIR / "app.json"
WORKFLOW_DEFAULTS_FILE = CONFIG_DIR / "workflow_defaults.json"
RECENT_INPUTS_FILE = CONFIG_DIR / "recent_inputs.json"

SECRETS_DIR = DATA_DIR / "secrets"
SECRET_CONFIG_FILE = SECRETS_DIR / "llm.local.json"

AUTH_DIR = DATA_DIR / "auth"
FANQIE_AUTH_DIR = AUTH_DIR / "fanqie"
FANQIE_AUTH_DEFAULT_ACCOUNT_DIR = FANQIE_AUTH_DIR / "default"
FANQIE_AUTH_STATE_FILE = FANQIE_AUTH_DEFAULT_ACCOUNT_DIR / "state.json"
FANQIE_ACCOUNTS_FILE = FANQIE_AUTH_DIR / "accounts.json"
FANQIE_ACCOUNT_STATES_DIR = FANQIE_AUTH_DIR / "accounts"
RUNTIME_DIR = DATA_DIR / "runtime"
BROWSER_DATA_DIR = RUNTIME_DIR / "fanqie_web"

SYSTEM_DIR = DATA_DIR / "system"
SYSTEM_BACKUP_DIR = SYSTEM_DIR / "backups"
SYSTEM_COMPARE_DIR = SYSTEM_DIR / "compare_reports"
SYSTEM_DEBUG_DIR = SYSTEM_DIR / "debug"
SYSTEM_HISTORY_DIR = SYSTEM_DIR / "history"
SYSTEM_TASK_LOG_DIR = SYSTEM_DIR / "tasklogs"
LOG_NAME = "task.log"
LATEST_LOG_NAME = "latest_task.log"
LOG_FILE = SYSTEM_TASK_LOG_DIR / LATEST_LOG_NAME

NOVEL_PROCESSING_DIR = DATA_DIR / "novel_processing"
PROCESS_BACKUP_DIR = NOVEL_PROCESSING_DIR / "backups"
PROCESS_COMPARE_DIR = NOVEL_PROCESSING_DIR / "compare_reports"
PROCESS_DEBUG_DIR = NOVEL_PROCESSING_DIR / "debug"
PROCESS_HISTORY_DIR = NOVEL_PROCESSING_DIR / "history"
NOVEL_PROCESSING_LOG_DIR = NOVEL_PROCESSING_DIR / "tasklogs"
PROCESS_OUTPUT_DIR = NOVEL_PROCESSING_DIR / "outputs"

CRAWLING_DIR = DATA_DIR / "crawling"
CRAWLING_BACKUP_DIR = CRAWLING_DIR / "backups"
CRAWLING_COMPARE_DIR = CRAWLING_DIR / "compare_reports"
CRAWLING_DEBUG_DIR = CRAWLING_DIR / "debug"
CRAWLING_HISTORY_DIR = CRAWLING_DIR / "history"
CRAWLING_LOG_DIR = CRAWLING_DIR / "tasklogs"
CRAWLING_OUTPUT_DIR = CRAWLING_DIR / "outputs"

STORY_ANALYSIS_DIR = DATA_DIR / "story_analysis"
STORY_ANALYSIS_BACKUP_DIR = STORY_ANALYSIS_DIR / "backups"
STORY_ANALYSIS_CHAPTER_DIR = STORY_ANALYSIS_DIR / "chapters"
STORY_ANALYSIS_COMPARE_DIR = STORY_ANALYSIS_DIR / "compare_reports"
STORY_ANALYSIS_DEBUG_DIR = STORY_ANALYSIS_DIR / "debug"
STORY_ANALYSIS_HISTORY_DIR = STORY_ANALYSIS_DIR / "history"
STORY_ANALYSIS_LOG_DIR = STORY_ANALYSIS_DIR / "tasklogs"
STORY_ANALYSIS_OUTPUT_DIR = STORY_ANALYSIS_DIR / "outputs"

PUBLISHING_DIR = DATA_DIR / "publishing"
PUBLISHING_BACKUP_DIR = PUBLISHING_DIR / "backups"
PUBLISHING_COMPARE_DIR = PUBLISHING_DIR / "compare_reports"
PUBLISHING_DEBUG_DIR = PUBLISHING_DIR / "debug"
PUBLISHING_TRACKER_DIR = PUBLISHING_DIR / "tracker"
PUBLISHING_LOG_DIR = PUBLISHING_DIR / "tasklogs"

SYNCING_DIR = DATA_DIR / "syncing"
SYNCING_BACKUP_DIR = SYNCING_DIR / "backups"
SYNCING_COMPARE_DIR = SYNCING_DIR / "compare_reports"
SYNCING_DEBUG_DIR = SYNCING_DIR / "debug"
SYNCING_HISTORY_DIR = SYNCING_DIR / "history"
SYNCING_LOG_DIR = SYNCING_DIR / "tasklogs"

FANQIE_WEB_DIR = DATA_DIR / "fanqie_web"
FANQIE_WEB_BACKUP_DIR = FANQIE_WEB_DIR / "backups"
FANQIE_WEB_COMPARE_DIR = FANQIE_WEB_DIR / "compare_reports"
FANQIE_WEB_DEBUG_DIR = FANQIE_WEB_DIR / "debug"
FANQIE_WEB_HISTORY_DIR = FANQIE_WEB_DIR / "history"
FANQIE_WEB_LOG_DIR = FANQIE_WEB_DIR / "tasklogs"

WORKSPACES_DIR = DATA_DIR / "workspaces"
RUNS_DIR = DATA_DIR / "runs"

STANDARD_DATA_DIRECTORIES: tuple[Path, ...] = (
    SYSTEM_BACKUP_DIR,
    SYSTEM_COMPARE_DIR,
    SYSTEM_DEBUG_DIR,
    SYSTEM_HISTORY_DIR,
    SYSTEM_TASK_LOG_DIR,
    PROCESS_BACKUP_DIR,
    PROCESS_COMPARE_DIR,
    PROCESS_DEBUG_DIR,
    PROCESS_HISTORY_DIR,
    NOVEL_PROCESSING_LOG_DIR,
    CRAWLING_BACKUP_DIR,
    CRAWLING_COMPARE_DIR,
    CRAWLING_DEBUG_DIR,
    CRAWLING_HISTORY_DIR,
    CRAWLING_LOG_DIR,
    STORY_ANALYSIS_BACKUP_DIR,
    STORY_ANALYSIS_COMPARE_DIR,
    STORY_ANALYSIS_DEBUG_DIR,
    STORY_ANALYSIS_HISTORY_DIR,
    STORY_ANALYSIS_LOG_DIR,
    PUBLISHING_BACKUP_DIR,
    PUBLISHING_COMPARE_DIR,
    PUBLISHING_DEBUG_DIR,
    PUBLISHING_TRACKER_DIR,
    PUBLISHING_LOG_DIR,
    SYNCING_BACKUP_DIR,
    SYNCING_COMPARE_DIR,
    SYNCING_DEBUG_DIR,
    SYNCING_HISTORY_DIR,
    SYNCING_LOG_DIR,
    FANQIE_WEB_BACKUP_DIR,
    FANQIE_WEB_COMPARE_DIR,
    FANQIE_WEB_DEBUG_DIR,
    FANQIE_WEB_HISTORY_DIR,
    FANQIE_WEB_LOG_DIR,
)

PROJECT_DIRECTORIES: tuple[Path, ...] = (
    DATA_DIR,
    CONFIG_DIR,
    SECRETS_DIR,
    AUTH_DIR,
    FANQIE_AUTH_DIR,
    FANQIE_AUTH_DEFAULT_ACCOUNT_DIR,
    FANQIE_ACCOUNT_STATES_DIR,
    RUNTIME_DIR,
    BROWSER_DATA_DIR,
    SYSTEM_DIR,
    NOVEL_PROCESSING_DIR,
    PROCESS_OUTPUT_DIR,
    CRAWLING_DIR,
    CRAWLING_OUTPUT_DIR,
    STORY_ANALYSIS_DIR,
    STORY_ANALYSIS_CHAPTER_DIR,
    STORY_ANALYSIS_OUTPUT_DIR,
    PUBLISHING_DIR,
    SYNCING_DIR,
    FANQIE_WEB_DIR,
    WORKSPACES_DIR,
    RUNS_DIR,
    *STANDARD_DATA_DIRECTORIES,
)

LOG_CATEGORIES: dict[str, Path] = {
    "system": SYSTEM_TASK_LOG_DIR,
    "auto_publish": PUBLISHING_LOG_DIR,
    "chapter_sync": SYNCING_LOG_DIR,
    "process_novel": NOVEL_PROCESSING_LOG_DIR,
    "web_crawler": CRAWLING_LOG_DIR,
    "character_notes": STORY_ANALYSIS_LOG_DIR,
    "plot_notes": STORY_ANALYSIS_LOG_DIR,
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
        "settings": str(CONFIG_DIR),
        "settings_file": str(CONFIG_FILE),
        "workflow_defaults_file": str(WORKFLOW_DEFAULTS_FILE),
        "recent_inputs_file": str(RECENT_INPUTS_FILE),
        "secrets": str(SECRETS_DIR),
        "secret_config_file": str(SECRET_CONFIG_FILE),
        "auth": str(AUTH_DIR),
        "fanqie_auth_state": str(FANQIE_AUTH_STATE_FILE),
        "fanqie_accounts_file": str(FANQIE_ACCOUNTS_FILE),
        "fanqie_account_states": str(FANQIE_ACCOUNT_STATES_DIR),
        "data": str(DATA_DIR),
        "runtime": str(RUNTIME_DIR),
        "workspaces": str(WORKSPACES_DIR),
        "runs": str(RUNS_DIR),
        "system_logs": str(SYSTEM_TASK_LOG_DIR),
        "novel_processing": str(NOVEL_PROCESSING_DIR),
        "novel_processing_logs": str(NOVEL_PROCESSING_LOG_DIR),
        "novel_processing_outputs": str(PROCESS_OUTPUT_DIR),
        "novel_processing_backups": str(PROCESS_BACKUP_DIR),
        "novel_processing_compare": str(PROCESS_COMPARE_DIR),
        "novel_processing_debug": str(PROCESS_DEBUG_DIR),
        "novel_processing_history": str(PROCESS_HISTORY_DIR),
        "crawling": str(CRAWLING_DIR),
        "crawling_logs": str(CRAWLING_LOG_DIR),
        "crawling_outputs": str(CRAWLING_OUTPUT_DIR),
        "crawling_backups": str(CRAWLING_BACKUP_DIR),
        "crawling_compare": str(CRAWLING_COMPARE_DIR),
        "crawling_debug": str(CRAWLING_DEBUG_DIR),
        "crawling_history": str(CRAWLING_HISTORY_DIR),
        "story_analysis": str(STORY_ANALYSIS_DIR),
        "story_analysis_logs": str(STORY_ANALYSIS_LOG_DIR),
        "story_analysis_outputs": str(STORY_ANALYSIS_OUTPUT_DIR),
        "story_analysis_chapters": str(STORY_ANALYSIS_CHAPTER_DIR),
        "story_analysis_backups": str(STORY_ANALYSIS_BACKUP_DIR),
        "story_analysis_compare": str(STORY_ANALYSIS_COMPARE_DIR),
        "story_analysis_debug": str(STORY_ANALYSIS_DEBUG_DIR),
        "story_analysis_history": str(STORY_ANALYSIS_HISTORY_DIR),
        "publishing": str(PUBLISHING_DIR),
        "publishing_logs": str(PUBLISHING_LOG_DIR),
        "publishing_backups": str(PUBLISHING_BACKUP_DIR),
        "publishing_compare": str(PUBLISHING_COMPARE_DIR),
        "publishing_debug": str(PUBLISHING_DEBUG_DIR),
        "publishing_tracker": str(PUBLISHING_TRACKER_DIR),
        "syncing": str(SYNCING_DIR),
        "syncing_logs": str(SYNCING_LOG_DIR),
        "syncing_backups": str(SYNCING_BACKUP_DIR),
        "syncing_compare": str(SYNCING_COMPARE_DIR),
        "syncing_debug": str(SYNCING_DEBUG_DIR),
        "syncing_history": str(SYNCING_HISTORY_DIR),
        "fanqie_web": str(FANQIE_WEB_DIR),
        "fanqie_web_logs": str(FANQIE_WEB_LOG_DIR),
        "fanqie_web_backups": str(FANQIE_WEB_BACKUP_DIR),
        "fanqie_web_compare": str(FANQIE_WEB_COMPARE_DIR),
        "fanqie_web_debug": str(FANQIE_WEB_DEBUG_DIR),
        "fanqie_web_history": str(FANQIE_WEB_HISTORY_DIR),
    }


def _path_mtime(path: Path) -> float:
    return path.stat().st_mtime
