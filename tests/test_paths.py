from __future__ import annotations

from backend.paths import (
    SYNCING_DIR,
    CONFIG_DIR,
    CONFIG_FILE,
    LOG_CATEGORIES,
    NOVEL_PROCESSING_DIR,
    PROCESS_OUTPUT_DIR,
    PUBLISHING_DIR,
    ROOT_DIR,
    CRAWLING_DIR,
    CRAWLING_OUTPUT_DIR,
    get_state_paths,
    latest_log_file,
    task_log_file,
)


def test_config_file_stays_in_data_settings_dir() -> None:
    assert CONFIG_DIR == ROOT_DIR / "data" / "settings"
    assert CONFIG_FILE == CONFIG_DIR / "app.json"


def test_log_categories_use_timestamped_log_files() -> None:
    for category in LOG_CATEGORIES:
        path = task_log_file(category)
        assert path.name.startswith("task_")
        assert path.name.endswith(".log")
        assert path.parent.name == "tasklogs"


def test_latest_log_file_uses_stable_fallback() -> None:
    for category in LOG_CATEGORIES:
        path = latest_log_file(category)
        assert path.name.endswith(".log")
        assert path.parent.name == "tasklogs"


def test_no_root_features_package() -> None:
    assert not (ROOT_DIR / "features").exists()


def test_no_root_app_package() -> None:
    assert not (ROOT_DIR / "app").exists()


def test_human_readable_architecture_roots_are_used() -> None:
    assert (ROOT_DIR / "backend").exists()
    assert (ROOT_DIR / "frontend").exists()
    assert (ROOT_DIR / "backend" / "publishing").exists()
    assert (ROOT_DIR / "backend" / "syncing").exists()
    assert (ROOT_DIR / "backend" / "fanqie_web").exists()
    assert (ROOT_DIR / "backend" / "actions").exists()
    assert not (ROOT_DIR / "backend" / "shared").exists()
    assert not (ROOT_DIR / "backend" / "adapters").exists()


def test_novel_text_rules_are_kept_in_one_place() -> None:
    assert (ROOT_DIR / "backend" / "novel").exists()
    assert not (ROOT_DIR / "backend" / "novel_tools").exists()
    assert not (ROOT_DIR / "backend" / "common").exists()


def test_open_directory_keys_stay_inside_feature_data_dirs() -> None:
    paths = get_state_paths()

    assert paths["novel_processing"] == str(NOVEL_PROCESSING_DIR)
    assert paths["crawling"] == str(CRAWLING_DIR)
    assert paths["publishing"] == str(PUBLISHING_DIR)
    assert paths["syncing"] == str(SYNCING_DIR)
    assert paths["novel_processing_outputs"] == str(PROCESS_OUTPUT_DIR)
    assert paths["crawling_outputs"] == str(CRAWLING_OUTPUT_DIR)
    assert "config" not in paths
    assert "task_logs" not in paths
