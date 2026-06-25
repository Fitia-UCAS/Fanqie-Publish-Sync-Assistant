from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


def _python_files(directory: Path) -> list[Path]:
    return [path for path in directory.rglob("*.py") if "__pycache__" not in path.parts]


def _file_names(directory: Path, suffix: str = ".py") -> set[str]:
    return {path.name for path in directory.glob(f"*{suffix}")}


def _dir_names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir() if path.is_dir() and path.name != "__pycache__"}


class NamingRulesTest(unittest.TestCase):
    def test_python_files_use_snake_case(self) -> None:
        for path in _python_files(ROOT_DIR / "backend") + _python_files(ROOT_DIR / "tests"):
            self.assertRegex(path.name, r"^(__init__|[a-z][a-z0-9_]*).py$", str(path))

    def test_root_directory_uses_project_entry_and_maintenance_names(self) -> None:
        expected_dirs = {"backend", "config", "data", "frontend", "tests", "tools"}
        self.assertTrue(expected_dirs.issubset(_dir_names(ROOT_DIR)))
        self.assertTrue((ROOT_DIR / "main.py").exists())
        self.assertFalse((ROOT_DIR / "utils").exists())

    def test_backend_roots_are_layer_names(self) -> None:
        backend_dir = ROOT_DIR / "backend"
        self.assertEqual(
            _dir_names(backend_dir),
            {"adapters", "api", "models", "services", "shared", "task_logs", "workflows"},
        )
        self.assertEqual(_file_names(backend_dir), {"__init__.py"})

    def test_adapter_directory_names_use_business_capability_nouns(self) -> None:
        adapters_dir = ROOT_DIR / "backend" / "adapters"
        self.assertEqual(_dir_names(adapters_dir), {"character_material", "fanqie_publisher", "fanqie_syncer", "fanqie_web", "novel_crawler"})

    def test_fanqie_publisher_files_share_fanqie_publish_prefix(self) -> None:
        publisher_dir = ROOT_DIR / "backend" / "adapters" / "fanqie_publisher"
        expected = {
            "__init__.py",
            "fanqie_publish_creator.py",
            "fanqie_publish_submitter.py",
            "fanqie_publish_tracker.py",
            "fanqie_publish_local_file.py",
            "fanqie_publish_models.py",
            "fanqie_publish_multi_runner.py",
            "fanqie_publish_options.py",
            "fanqie_publish_service.py",
            "fanqie_publish_single_runner.py",
            "fanqie_publish_verifier.py",
        }
        self.assertEqual(_file_names(publisher_dir), expected)
        for path in publisher_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.startswith("fanqie_publish_"), str(path))

    def test_fanqie_syncer_files_share_fanqie_sync_prefix(self) -> None:
        syncer_dir = ROOT_DIR / "backend" / "adapters" / "fanqie_syncer"
        expected = {
            "__init__.py",
            "fanqie_sync_applier.py",
            "fanqie_sync_creator.py",
            "fanqie_sync_local_file.py",
            "fanqie_sync_models.py",
            "fanqie_sync_multi_runner.py",
            "fanqie_sync_options.py",
            "fanqie_sync_remote_catalog.py",
            "fanqie_sync_service.py",
            "fanqie_sync_single_runner.py",
            "fanqie_sync_submitter.py",
            "fanqie_sync_verifier.py",
            "fanqie_sync_preflight.py",
        }
        self.assertEqual(_file_names(syncer_dir), expected)
        for path in syncer_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.startswith("fanqie_sync_"), str(path))


    def test_fanqie_publish_and_sync_adapters_do_not_import_each_other(self) -> None:
        publisher_dir = ROOT_DIR / "backend" / "adapters" / "fanqie_publisher"
        syncer_dir = ROOT_DIR / "backend" / "adapters" / "fanqie_syncer"
        for path in publisher_dir.glob("*.py"):
            self.assertNotIn("backend.adapters.fanqie_syncer", path.read_text(encoding="utf-8"), str(path))
        for path in syncer_dir.glob("*.py"):
            self.assertNotIn("backend.adapters.fanqie_publisher", path.read_text(encoding="utf-8"), str(path))

    def test_fanqie_web_subfolders_use_one_style_each(self) -> None:
        web_dir = ROOT_DIR / "backend" / "adapters" / "fanqie_web"
        self.assertEqual(_file_names(web_dir), {"__init__.py", "models.py", "chapter_editor_creator.py"})
        self.assertEqual(_dir_names(web_dir), {"browser", "dialogs", "history", "page_actions", "pages"})
        self.assertEqual(_file_names(web_dir / "browser"), {"__init__.py", "browser_session.py"})
        self.assertEqual(_file_names(web_dir / "dialogs"), {"__init__.py", "editing_dialogs.py", "publishing_dialogs.py"})
        self.assertEqual(_file_names(web_dir / "history"), {"__init__.py", "chapter_history_diff_report.py", "chapter_history_tracker.py"})
        for path in (web_dir / "history").glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.startswith("chapter_history_"), str(path))
        self.assertEqual(_file_names(web_dir / "page_actions"), {"__init__.py", "chapter_page_interactions.py", "chapter_page_navigation.py"})
        self.assertEqual(_file_names(web_dir / "pages"), {"__init__.py", "chapter_editor_page.py", "chapter_list_page.py"})

    def test_novel_crawler_files_share_crawler_prefix(self) -> None:
        crawler_dir = ROOT_DIR / "backend" / "adapters" / "novel_crawler"
        required = {
            "__init__.py",
            "crawler_chapter_runner.py",
            "crawler_content_cleaner.py",
            "crawler_http_client.py",
            "crawler_models.py",
            "crawler_service.py",
            "crawler_text_writer.py",
            "crawler_write_buffer.py",
        }
        names = _file_names(crawler_dir)
        self.assertTrue(required.issubset(names))
        for path in crawler_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.startswith("crawler_"), str(path))

    def test_novel_crawler_rate_limit_files_use_rate_limit_names(self) -> None:
        rate_limit_dir = ROOT_DIR / "backend" / "adapters" / "novel_crawler" / "rate_limit"
        self.assertEqual(_file_names(rate_limit_dir), {"__init__.py", "rate_limiter.py"})
        self.assertFalse((ROOT_DIR / "backend" / "adapters" / "novel_crawler" / "crawl_guard").exists())

    def test_novel_crawler_site_files_share_site_prefix(self) -> None:
        sites_dir = ROOT_DIR / "backend" / "adapters" / "novel_crawler" / "sites"
        self.assertEqual(_file_names(sites_dir), {"__init__.py", "site_adapter.py", "site_registry.py"})
        self.assertEqual(_dir_names(sites_dir), {"lanmeiwen", "renrenreshu", "xsbook"})
        for path in sites_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.startswith("site_"), str(path))
        for site_dir in (sites_dir / "lanmeiwen", sites_dir / "renrenreshu", sites_dir / "xsbook"):
            self.assertIn("__init__.py", _file_names(site_dir))
            for path in site_dir.glob("*.py"):
                if path.name != "__init__.py":
                    self.assertTrue(path.name.startswith("site_"), str(path))

    def test_api_files_use_api_suffix(self) -> None:
        api_dir = ROOT_DIR / "backend" / "api"
        self.assertEqual(_file_names(api_dir), {"__init__.py", "desktop_api.py", "frontend_api.py", "webview_api.py"})
        for path in api_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.endswith("_api.py"), str(path))

    def test_models_directory_contains_domain_models(self) -> None:
        self.assertEqual(_file_names(ROOT_DIR / "backend" / "models"), {"__init__.py", "chapter.py"})

    def test_service_files_use_object_role_names(self) -> None:
        services_dir = ROOT_DIR / "backend" / "services"
        expected = {"__init__.py", "service_ad_cleaner.py", "service_chapter_formatter.py", "service_chapter_text_parser.py", "service_sentence_fixer.py", "service_text_file_updater.py"}
        self.assertEqual(_file_names(services_dir), expected)
        for path in services_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertRegex(path.name, r"^service_[a-z][a-z0-9_]*_(cleaner|formatter|fixer|parser|updater)\.py$", str(path))

    def test_service_novel_text_files_use_object_role_names(self) -> None:
        novel_text_dir = ROOT_DIR / "backend" / "services" / "novel_text"
        self.assertEqual(_file_names(novel_text_dir), {"__init__.py", "chapter_parser.py", "text_normalizer.py", "text_splitter.py"})
        for path in novel_text_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertRegex(path.name, r"^(chapter|text)_[a-z]+er\.py$", str(path))

    def test_shared_is_split_into_same_style_subfolders(self) -> None:
        shared_dir = ROOT_DIR / "backend" / "shared"
        self.assertEqual(_file_names(shared_dir), {"__init__.py"})
        self.assertEqual(_dir_names(shared_dir), {"app", "filename", "json", "plain_text", "task", "text_file"})
        expected_files = {
            "app": {"__init__.py", "app_config.py", "app_data_reset.py", "app_errors.py", "app_logging.py", "app_paths.py", "app_runtime_defaults.py"},
            "task": {"__init__.py", "task_callbacks.py", "task_event.py", "task_registry.py", "task_result.py"},
            "text_file": {"__init__.py", "text_file_discovery.py", "text_file_storage.py"},
            "json": {"__init__.py", "json_serialization.py"},
            "filename": {"__init__.py", "filename_sanitizer.py"},
            "plain_text": {"__init__.py", "plain_text_formatting.py"},
        }
        for folder, names in expected_files.items():
            self.assertEqual(_file_names(shared_dir / folder), names)
            prefix = folder.removesuffix("_core")
            for path in (shared_dir / folder).glob("*.py"):
                if path.name != "__init__.py":
                    self.assertTrue(path.name.startswith(prefix + "_"), str(path))

    def test_task_log_files_share_task_log_suffix(self) -> None:
        task_logs_dir = ROOT_DIR / "backend" / "task_logs"
        self.assertEqual(_file_names(task_logs_dir), {"__init__.py", "fanqie_task_log.py", "novel_crawler_task_log.py"})
        for path in task_logs_dir.glob("*.py"):
            if path.name != "__init__.py":
                self.assertTrue(path.name.endswith("_task_log.py"), str(path))

    def test_workflow_files_use_action_object_names(self) -> None:
        workflows_dir = ROOT_DIR / "backend" / "workflows"
        allowed_verbs = {"clean", "crawl", "process", "publish", "split", "sync"}
        expected = {"__init__.py", "clean_text.py", "crawl_web_chapters.py", "process_novel.py", "publish_missing_chapters.py", "split_novel.py", "sync_existing_chapters.py"}
        self.assertEqual(_file_names(workflows_dir), expected)
        for path in workflows_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            verb = path.stem.split("_", 1)[0]
            self.assertIn(verb, allowed_verbs, str(path))

    def test_frontend_assets_use_folder_local_styles(self) -> None:
        assets_dir = ROOT_DIR / "frontend" / "assets"
        self.assertEqual(_file_names(assets_dir, ".js"), {"app.js"})
        self.assertEqual({path.name for path in assets_dir.glob("*.css")}, {"styles.css"})
        core_dir = assets_dir / "core"
        self.assertEqual(_file_names(core_dir, ".js"), {"ui_character_material.js", "ui_form_controls.js", "ui_novel_splitter.js", "ui_page_registry.js", "ui_state_store.js", "ui_task_panel.js"})
        for path in core_dir.glob("*.js"):
            self.assertTrue(path.name.startswith("ui_"), str(path))
        page_dir = assets_dir / "pages"
        expected_pages = {"character_material_page.js", "novel_processor_page.js", "fanqie_publisher_page.js", "fanqie_syncer_page.js", "novel_crawler_page.js"}
        self.assertEqual(_file_names(page_dir, ".js"), expected_pages)
        for path in page_dir.glob("*.js"):
            self.assertTrue(path.name.endswith("_page.js"), str(path))

    def test_tests_use_area_subject_names_after_prefix(self) -> None:
        expected = {
            "__init__.py",
            "test_api_webview_state.py",
            "test_backend_architecture.py",
            "test_backend_smoke.py",
            "test_backend_novel_crawler_xsbook_adapter.py",
            "test_backend_character_material_prompt.py",
            "test_frontend_asset_structure.py",
            "test_project_naming_rules.py",
            "test_project_package_hygiene.py",
            "test_service_chapter_text_parser.py",
            "test_service_text_file_updater.py",
            "test_shared_app_paths.py",
            "test_shared_app_data_reset.py",
            "test_shared_json_serialization.py",
            "test_shared_task_result.py",
            "test_shared_task_event.py",
        }
        actual = {path.name for path in (ROOT_DIR / "tests").glob("*.py")}
        self.assertEqual(actual, expected)
        for path in (ROOT_DIR / "tests").glob("test_*.py"):
            self.assertRegex(path.stem, r"^test_(api|backend|frontend|project|service|shared)_[a-z0-9_]+$", str(path))

    def test_data_directories_use_feature_prefixed_standard_names(self) -> None:
        data_dir = ROOT_DIR / "data"
        self.assertEqual(_dir_names(data_dir), {"app_system", "character_material", "fanqie_publisher", "fanqie_syncer", "fanqie_web", "novel_crawler", "novel_processor"})
        self.assertEqual(
            _dir_names(data_dir / "app_system"),
            {"app_system_backups", "app_system_compare_reports", "app_system_debug", "app_system_history", "app_system_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "fanqie_publisher"),
            {"fanqie_publish_backups", "fanqie_publish_compare_reports", "fanqie_publish_debug", "fanqie_publish_tracker", "fanqie_publish_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "fanqie_syncer"),
            {"fanqie_sync_backups", "fanqie_sync_compare_reports", "fanqie_sync_debug", "fanqie_sync_history", "fanqie_sync_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "fanqie_web"),
            {"fanqie_web_backups", "fanqie_web_compare_reports", "fanqie_web_debug", "fanqie_web_history", "fanqie_web_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "novel_crawler"),
            {"novel_crawl_backups", "novel_crawl_compare_reports", "novel_crawl_debug", "novel_crawl_history", "novel_crawl_outputs", "novel_crawl_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "novel_processor"),
            {"novel_process_backups", "novel_process_compare_reports", "novel_process_debug", "novel_process_history", "novel_process_outputs", "novel_process_tasklogs"},
        )
        self.assertEqual(
            _dir_names(data_dir / "character_material"),
            {
                "character_material_backups",
                "character_material_chapters",
                "character_material_compare_reports",
                "character_material_debug",
                "character_material_history",
                "character_material_outputs",
                "character_material_tasklogs",
            },
        )
        module_suffixes = {
            "app_system": ("app_system", {"backups", "compare_reports", "debug", "history", "tasklogs"}),
            "fanqie_publisher": ("fanqie_publish", {"backups", "compare_reports", "debug", "tracker", "tasklogs"}),
            "fanqie_syncer": ("fanqie_sync", {"backups", "compare_reports", "debug", "history", "tasklogs"}),
            "fanqie_web": ("fanqie_web", {"backups", "compare_reports", "debug", "history", "tasklogs"}),
            "novel_crawler": ("novel_crawl", {"backups", "compare_reports", "debug", "history", "tasklogs"}),
            "novel_processor": ("novel_process", {"backups", "compare_reports", "debug", "history", "tasklogs"}),
            "character_material": ("character_material", {"backups", "chapters", "compare_reports", "debug", "history", "outputs", "tasklogs"}),
        }
        for module_dir, (prefix, suffixes) in module_suffixes.items():
            names = _dir_names(data_dir / module_dir)
            for suffix in suffixes:
                self.assertIn(f"{prefix}_{suffix}", names)
        self.assertFalse((data_dir / "logs").exists())
        for directory in data_dir.rglob("*"):
            if directory.is_dir():
                self.assertNotRegex(directory.name, r"[\u4e00-\u9fff]", str(directory))

    def test_root_maintenance_scripts_live_in_tools(self) -> None:
        tools_dir = ROOT_DIR / "tools"
        expected_tools = {
            "build_exe.py",
            "clean_pyc.py",
            "convert_png_to_ico.py",
            "package_project.py",
            "start.py",
        }
        self.assertEqual(_file_names(tools_dir), expected_tools)
        self.assertFalse((ROOT_DIR / "utils").exists())


if __name__ == "__main__":
    unittest.main()
