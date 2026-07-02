from __future__ import annotations

import ast
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
BUSINESS_PACKAGES = (
    "backend.story_analysis",
    "backend.crawling",
    "backend.fanqie_web",
    "backend.novel",
    "backend.publishing",
    "backend.syncing",
    "backend.tasks",
)


def _backend_imports() -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for path in BACKEND_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        module = ".".join(path.with_suffix("").relative_to(ROOT_DIR).parts)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend."):
                edges.append((module, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("backend."):
                        edges.append((module, alias.name))
    return edges


def test_business_packages_do_not_depend_on_api_or_actions() -> None:
    for source, target in _backend_imports():
        if source.startswith(BUSINESS_PACKAGES):
            assert not target.startswith(("backend.api", "backend.actions")), f"{source} must not import {target}"


def test_actions_orchestrate_business_packages_directly() -> None:
    action_imports = [target for source, target in _backend_imports() if source.startswith("backend.actions")]
    assert any(target.startswith("backend.publishing.flow") for target in action_imports)
    assert any(target.startswith("backend.syncing.flow") for target in action_imports)
    assert any(target.startswith("backend.crawling") for target in action_imports)


def test_removed_architecture_layers_are_absent() -> None:
    for source, target in _backend_imports():
        assert not target.startswith(("backend.core", "backend.domain", "backend.features", "backend.integrations", "backend.workflows")), f"{source} imports {target}"
        assert target != "backend.fanqie" and not target.startswith("backend.fanqie."), f"{source} imports {target}"
