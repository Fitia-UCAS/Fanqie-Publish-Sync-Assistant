from __future__ import annotations

import ast
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT_DIR / "backend", ROOT_DIR / "tests", ROOT_DIR / "tools")
GENERIC_FILE_STEMS = {
    "service",
    "services",
    "model",
    "models",
    "option",
    "options",
    "util",
    "utils",
    "helper",
    "helpers",
    "manager",
    "handler",
    "factory",
    "common",
    "misc",
    "base",
}
GENERIC_CLASS_SUFFIXES = (
    "Service",
    "Manager",
    "Handler",
    "Helper",
    "Factory",
)
REVIEW_CLASS_SUFFIXES = (
    "Options",
    "Result",
    "Data",
)
MECHANICAL_DIRS = {"core", "domain", "features", "integrations", "shared", "adapters", "services"}
TOKEN_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)")


@dataclass(slots=True)
class Finding:
    kind: str
    path: str
    detail: str
    recommendation: str


@dataclass(slots=True)
class AcceptedRepeat:
    kind: str
    path: str
    detail: str
    reason: str


ACCEPTED_REPEATS: dict[tuple[str, str, str], str] = {}


def snake_tokens(value: str) -> list[str]:
    value = value.removesuffix(".py")
    parts: list[str] = []
    for chunk in re.split(r"[_\-\s]+", value):
        parts.extend(token.lower() for token in TOKEN_RE.findall(chunk) if token)
    return parts


def python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCAN_DIRS:
        if directory.exists():
            files.extend(path for path in directory.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT_DIR)).replace("\\", "/")


def audit_file_names(files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    by_parent: dict[Path, list[Path]] = defaultdict(list)
    for path in files:
        by_parent[path.parent].append(path)
        if path.name == "__init__.py":
            continue
        stem = path.stem
        tokens = snake_tokens(stem)
        parent_tokens = snake_tokens(path.parent.name)
        if stem in GENERIC_FILE_STEMS:
            findings.append(Finding("generic_file", rel(path), f"文件名 `{stem}` 只表达角色，不表达业务", "改成业务动作或业务对象名；如果目录已表达上下文，文件名可以更短但不能空泛。"))
        if tokens and parent_tokens:
            if tokens[: len(parent_tokens)] == parent_tokens or tokens[-len(parent_tokens) :] == parent_tokens:
                findings.append(Finding("dir_file_repeat", rel(path), f"目录 `{path.parent.name}` 与文件 `{path.name}` 重复了相同词组", "优先去掉文件里的重复词，或确认该重复是稳定领域名。"))
            elif tokens[0] == parent_tokens[-1] or tokens[-1] == parent_tokens[-1]:
                findings.append(Finding("dir_file_token_repeat", rel(path), f"目录尾词 `{parent_tokens[-1]}` 出现在文件名前/后端", "检查是否只是目录上下文重复；能省就省。"))
    for parent, group in by_parent.items():
        stems = [p.stem for p in group if p.name != "__init__.py"]
        first_tokens = Counter(tokens[0] for stem in stems if (tokens := snake_tokens(stem)))
        last_tokens = Counter(tokens[-1] for stem in stems if (tokens := snake_tokens(stem)))
        for token, count in first_tokens.items():
            if count >= 3 and token not in {"test"}:
                findings.append(Finding("prefix_cluster", rel(parent), f"同一目录有 {count} 个文件以前缀 `{token}` 开头", "逐个判断这个前缀是不是目录已经表达；如果是，改短。"))
        for token, count in last_tokens.items():
            if count >= 3 and token not in {"test"}:
                findings.append(Finding("suffix_cluster", rel(parent), f"同一目录有 {count} 个文件以后缀 `{token}` 结尾", "逐个判断这个后缀是不是模板词；如果只是角色后缀，换成业务名。"))
    return findings


def audit_directories() -> list[Finding]:
    findings: list[Finding] = []
    for directory in sorted(ROOT_DIR.joinpath("backend").rglob("*")):
        if not directory.is_dir() or "__pycache__" in directory.parts:
            continue
        name = directory.name
        if name in MECHANICAL_DIRS:
            findings.append(Finding("mechanical_dir", rel(directory), f"目录名 `{name}` 是架构套话，不够直观", "小项目里优先使用业务名目录，或把公共文件直接放到 backend 根层。"))
        code_files = [p for p in directory.glob("*.py") if p.name != "__init__.py"]
        child_dirs = [p for p in directory.iterdir() if p.is_dir() and p.name != "__pycache__"]
        if len(code_files) == 1 and not child_dirs:
            findings.append(Finding("single_file_dir", rel(directory), f"目录内只有一个有效 Python 文件 `{code_files[0].name}`", "考虑展平；只有未来明确会增长时才保留。"))
    return findings


def audit_symbols(files: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            findings.append(Finding("syntax_error", rel(path), str(exc), "先修复语法错误。"))
            continue
        for node in ast.walk(tree):
            name = getattr(node, "name", "")
            if isinstance(node, ast.ClassDef):
                if name.endswith(GENERIC_CLASS_SUFFIXES):
                    findings.append(Finding("generic_class_suffix", rel(path), f"类名 `{name}` 使用模板化尾缀", "改成业务对象、业务动作或领域概念名。"))
                elif name.endswith(REVIEW_CLASS_SUFFIXES):
                    findings.append(Finding("review_class_suffix", rel(path), f"类名 `{name}` 使用需要人工确认的尾缀", "如果它确实表示输入参数/输出结果可保留；否则改成更具体的领域名。"))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                tokens = snake_tokens(name)
                if tokens and tokens[-1] in {"handler", "helper", "manager", "service", "util", "utils"}:
                    findings.append(Finding("generic_function_suffix", rel(path), f"函数 `{name}` 以模板词结尾", "改成动作本身，例如 read/write/apply/collect/verify。"))
    return findings


def run_audit() -> dict[str, list[dict[str, str]]]:
    files = python_files()
    raw_findings = audit_directories() + audit_file_names(files) + audit_symbols(files)
    findings: list[Finding] = []
    accepted: list[AcceptedRepeat] = []
    for item in raw_findings:
        key = (item.kind, item.path, item.detail)
        reason = ACCEPTED_REPEATS.get(key)
        if reason:
            accepted.append(AcceptedRepeat(item.kind, item.path, item.detail, reason))
        else:
            findings.append(item)
    return {
        "findings": [asdict(item) for item in findings],
        "accepted": [asdict(item) for item in accepted],
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
