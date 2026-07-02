from __future__ import annotations

import ast
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT_DIR / "backend",)
MIN_DUPLICATE_LINES = 4


@dataclass(slots=True)
class Finding:
    kind: str
    path: str
    detail: str
    recommendation: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR)).replace("\\", "/")


def python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCAN_DIRS:
        files.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _normalized_source(source: str) -> str:
    lines = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return "\n".join(lines)


def duplicate_functions() -> list[Finding]:
    groups: dict[str, list[tuple[Path, str, int]]] = defaultdict(list)
    for path in python_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source = ast.get_source_segment(text, node) or ""
            line_count = len(source.splitlines())
            if line_count < MIN_DUPLICATE_LINES:
                continue
            digest = hashlib.md5(_normalized_source(source).encode("utf-8")).hexdigest()
            groups[digest].append((path, node.name, line_count))

    findings: list[Finding] = []
    for group in groups.values():
        if len(group) <= 1:
            continue
        detail = "; ".join(f"{rel(path)}::{name} ({lines} 行)" for path, name, lines in group)
        findings.append(
            Finding(
                "duplicate_function",
                rel(group[0][0]),
                detail,
                "逐个判断是否真是同一职责；如果是，抽到更贴近业务边界的共享函数，不要用自动重命名。",
            )
        )
    return findings


def run_audit() -> dict[str, list[dict[str, str]]]:
    findings = duplicate_functions()
    return {"findings": [asdict(item) for item in findings]}


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
