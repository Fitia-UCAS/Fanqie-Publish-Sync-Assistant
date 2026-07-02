from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"


def _python_files(directory: Path) -> list[Path]:
    return [path for path in directory.rglob("*.py") if "__pycache__" not in path.parts]


def _file_names(directory: Path, suffix: str = ".py") -> set[str]:
    return {path.name for path in directory.glob(f"*{suffix}")}


def _dir_names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir() if path.is_dir() and path.name != "__pycache__"}


def _imports_from_backend() -> list[tuple[Path, str]]:
    imports: list[tuple[Path, str]] = []
    for path in _python_files(BACKEND_DIR) + _python_files(ROOT_DIR / "tests") + _python_files(ROOT_DIR / "tools"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend."):
                imports.append((path, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("backend."):
                        imports.append((path, alias.name))
    return imports


class NamingRulesTest(unittest.TestCase):
    def test_python_files_use_snake_case(self) -> None:
        for path in _python_files(BACKEND_DIR) + _python_files(ROOT_DIR / "tests") + _python_files(ROOT_DIR / "tools"):
            self.assertRegex(path.name, r"^(__init__|[a-z][a-z0-9_]*).py$", str(path))

    def test_backend_avoids_placeholder_names_and_mechanical_suffixes(self) -> None:
        banned_exact = {"models.py", "options.py", "service.py", "utils.py", "helpers.py", "manager.py", "handler.py"}
        banned_suffixes = ("_service.py", "_models.py", "_utils.py", "_helpers.py", "_manager.py", "_handler.py")
        for path in _python_files(BACKEND_DIR):
            if path.name == "__init__.py":
                continue
            self.assertNotIn(path.name, banned_exact, str(path))
            self.assertFalse(path.name.endswith(banned_suffixes), str(path))

    def test_old_architecture_layers_do_not_return(self) -> None:
        for old in ("adapters", "app", "core", "domain", "features", "integrations", "models", "services", "shared", "task_logs"):
            self.assertFalse((BACKEND_DIR / old).exists(), old)

    def test_backend_roots_are_direct_product_areas(self) -> None:
        expected_dirs = {
            "api",
            "actions",
            "crawling",
            "fanqie_web",
            "novel",
            "publishing",
            "story_analysis",
            "syncing",
            "tasks",
        }
        self.assertEqual(_dir_names(BACKEND_DIR), expected_dirs)
        expected_files = {
            "__init__.py",
            "data_reset.py",
            "defaults.py",
            "errors.py",
            "filenames.py",
            "form_inputs.py",
            "json_files.py",
            "log_setup.py",
            "paths.py",
            "runs.py",
            "settings.py",
            "subprocesses.py",
            "text_files.py",
            "workspaces.py",
        }
        self.assertEqual(_file_names(BACKEND_DIR), expected_files)

    def test_no_imports_use_removed_layer_names(self) -> None:
        removed = ("backend.core", "backend.domain", "backend.features", "backend.integrations")
        for path, module in _imports_from_backend():
            self.assertFalse(module.startswith(removed), f"{path} imports {module}")

    def test_business_directories_have_clear_file_names(self) -> None:
        self.assertEqual(
            _file_names(BACKEND_DIR / "publishing"),
            {"__init__.py", "artifacts.py", "batch.py", "chapter.py", "editor.py", "flow.py", "local_source.py", "outcome.py", "plan.py"},
        )
        self.assertEqual(
            _file_names(BACKEND_DIR / "syncing"),
            {"__init__.py", "apply.py", "batch.py", "chapter.py", "content_check.py", "editor.py", "flow.py", "local_source.py", "plan.py", "remote_catalog.py"},
        )
        self.assertEqual(
            _file_names(BACKEND_DIR / "crawling"),
            {"__init__.py", "chapter_fetch.py", "clean.py", "crawler.py", "http.py", "rate_limit.py", "records.py", "txt_writer.py", "write_order.py"},
        )

    def test_fanqie_web_is_flat_and_not_page_prefixed(self) -> None:
        web_dir = BACKEND_DIR / "fanqie_web"
        self.assertEqual(_dir_names(web_dir), set())
        self.assertEqual(
            _file_names(web_dir),
            {
                "__init__.py",
                "accounts.py",
                "browser_debug.py",
                "browser_session.py",
                "chapter_list.py",
                "diff_report.py",
                "list_counts.py",
                "draft_save.py",
                "login.py",
                "edit_dialogs.py",
                "remote_editor.py",
                "form_fields.py",
                "open_chapter.py",
                "open_editor.py",
                "pagination.py",
                "submission.py",
                "submission_dialogs.py",
                "schedule.py",
                "schedule_picker.py",
                "scheduled_date.py",
                "scheduled_time.py",
                "snapshots.py",
                "text_counts.py",
                "text_entry.py",
                "ui_actions.py",
            },
        )
        for name in _file_names(web_dir):
            self.assertFalse(name.startswith("page_"), name)

    def test_novel_text_code_is_in_one_flat_directory(self) -> None:
        self.assertFalse((BACKEND_DIR / "novel_tools").exists())
        self.assertEqual(
            _file_names(BACKEND_DIR / "novel"),
            {
                "__init__.py",
                "ad_cleaner.py",
                "chapters.py",
                "file_rewrite.py",
                "formatting.py",
                "reader.py",
                "sentence_fixer.py",
                "source.py",
                "splitter.py",
                "text_cleaning.py",
            },
        )

    def test_story_analysis_replaces_page_named_backend_dirs(self) -> None:
        self.assertFalse((BACKEND_DIR / "character_notes").exists())
        self.assertFalse((BACKEND_DIR / "plot_notes").exists())
        self.assertEqual(
            _file_names(BACKEND_DIR / "story_analysis"),
            {
                "__init__.py",
                "chapter_files.py",
                "extract_characters.py",
                "llm_json.py",
                "llm.py",
                "material_prompts.py",
                "materials.py",
                "platforms.py",
                "plot_markdown.py",
                "plot_scope.py",
                "summarize_plot.py",
                "summaries.py",
                "summary_prompts.py",
            },
        )

    def test_related_task_helpers_have_one_clear_directory(self) -> None:
        self.assertEqual(_file_names(BACKEND_DIR / "tasks"), {"__init__.py", "callbacks.py", "crawler_log.py", "events.py", "fanqie_log.py", "registry.py", "outcome.py"})

    def test_audit_script_exists_and_does_not_rename(self) -> None:
        audit = ROOT_DIR / "tools" / "audit_names.py"
        self.assertTrue(audit.exists())
        text = audit.read_text(encoding="utf-8")
        self.assertNotIn("os.rename", text)
        self.assertNotIn("shutil.move", text)
        self.assertNotIn("Path.rename", text)


    def test_code_audit_script_reports_duplicate_functions_without_writing(self) -> None:
        audit = ROOT_DIR / "tools" / "audit_code.py"
        self.assertTrue(audit.exists())
        text = audit.read_text(encoding="utf-8")
        self.assertNotIn("os.rename", text)
        self.assertNotIn("shutil.move", text)
        self.assertNotIn("Path.rename", text)

    def test_action_files_use_short_scenario_names(self) -> None:
        actions_dir = BACKEND_DIR / "actions"
        expected = {"__init__.py", "clean.py", "crawl.py", "process.py", "publish.py", "split.py", "sync.py"}
        self.assertEqual(_file_names(actions_dir), expected)

    def test_data_uses_split_storage_names_after_bootstrap(self) -> None:
        data_dir = ROOT_DIR / "data"
        expected = {"system", "auth", "story_analysis", "publishing", "syncing", "fanqie_web", "crawling", "novel_processing", "runs", "runtime", "secrets", "settings", "workspaces"}
        self.assertTrue(expected.issubset(_dir_names(data_dir)))
        for old in {"app_system", "fanqie_publisher", "fanqie_syncer", "novel_crawler", "novel_processor"}:
            self.assertFalse((data_dir / old).exists(), old)
