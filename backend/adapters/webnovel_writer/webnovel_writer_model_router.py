from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.adapters.webnovel_writer.webnovel_writer_json import read_json, write_json
from backend.shared.text_file.text_file_storage import ensure_dir, read_text_auto, write_text

ROLE_ORDER = ["planner", "context", "drafter", "reviewer", "fact", "repair", "quality", "default"]
ROLE_LABELS = {
    "planner": "规划 / 蓝图",
    "context": "上下文任务书",
    "drafter": "章节起草",
    "reviewer": "审稿门禁",
    "fact": "事实提取",
    "repair": "修复重写",
    "quality": "质量审查",
    "default": "兜底默认",
}

DEFAULT_MODEL_ROUTES: dict[str, dict[str, Any]] = {
    "default": {
        "platform": "deepseek",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.72,
        "max_tokens": 8192,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "兜底模型；留空字段会继续使用前端/环境变量传入值。",
    },
    "planner": {
        "platform": "deepseek_reasoner",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.42,
        "max_tokens": 4096,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "生成全书规划、分卷规划、章节蓝图。",
    },
    "context": {
        "platform": "deepseek",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.25,
        "max_tokens": 6144,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "把 context pack 压成写作任务书。",
    },
    "drafter": {
        "platform": "deepseek",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.72,
        "max_tokens": 8192,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "正文起草，必须输出正文 + CHANGES。",
    },
    "reviewer": {
        "platform": "deepseek_reasoner",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.1,
        "max_tokens": 4096,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "审查阻断问题、蓝图完成度、OOC、节奏等。",
    },
    "fact": {
        "platform": "deepseek_reasoner",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.1,
        "max_tokens": 6144,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "事实提取、fulfillment、disambiguation、extraction。",
    },
    "repair": {
        "platform": "deepseek",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.45,
        "max_tokens": 8192,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "修复协议、重写 blocking issue、保持 CHANGES 对齐。",
    },
    "quality": {
        "platform": "deepseek",
        "model_name": "",
        "base_url": "",
        "api_key_env": "",
        "temperature": 0.1,
        "max_tokens": 4096,
        "max_retries": 3,
        "retry_delay": 2.0,
        "notes": "预留给未来模型质量审查；当前本地 quality 不调用模型。",
    },
}

_FIELD_ALIASES = {
    "model": "model_name",
    "modelName": "model_name",
    "model_name": "model_name",
    "baseUrl": "base_url",
    "base_url": "base_url",
    "apiKeyEnv": "api_key_env",
    "api_key_env": "api_key_env",
    "maxTokens": "max_tokens",
    "max_tokens": "max_tokens",
    "maxRetries": "max_retries",
    "max_retries": "max_retries",
    "retryDelay": "retry_delay",
    "retry_delay": "retry_delay",
    "platform": "platform",
    "temperature": "temperature",
    "notes": "notes",
}

_PAYLOAD_KEYS = {
    "platform": "platform",
    "model_name": "modelName",
    "base_url": "baseUrl",
    "temperature": "temperature",
    "max_tokens": "maxTokens",
    "max_retries": "maxRetries",
    "retry_delay": "retryDelay",
}

_NUMERIC_FLOAT = {"temperature", "retry_delay"}
_NUMERIC_INT = {"max_tokens", "max_retries"}


def model_routes_dir(storage: Any, project_id: str) -> Path:
    return ensure_dir(Path(storage.paths(project_id).control) / "models")


def model_routes_md_path(storage: Any, project_id: str) -> Path:
    return model_routes_dir(storage, project_id) / "model_routes.md"


def model_routes_json_path(storage: Any, project_id: str) -> Path:
    return model_routes_dir(storage, project_id) / "model_routes.json"


def ensure_model_routes(storage: Any, project_id: str, *, force: bool = False) -> dict[str, Any]:
    directory = model_routes_dir(storage, project_id)
    md_path = directory / "model_routes.md"
    json_path = directory / "model_routes.json"
    created: list[str] = []
    if force or not md_path.exists():
        write_text(md_path, model_routes_markdown_template(DEFAULT_MODEL_ROUTES))
        created.append(str(md_path))
    if force or not json_path.exists():
        write_json(json_path, normalize_model_routes(DEFAULT_MODEL_ROUTES))
        created.append(str(json_path))
    return {"ok": True, "created": created, "paths": {"markdown": str(md_path), "json": str(json_path)}}


def sync_model_routes(storage: Any, project_id: str, *, force_template: bool = False) -> dict[str, Any]:
    ensure_model_routes(storage, project_id, force=force_template)
    md_path = model_routes_md_path(storage, project_id)
    json_path = model_routes_json_path(storage, project_id)
    parsed = parse_model_routes_markdown(read_text_auto(md_path))
    if not parsed:
        parsed = read_json(json_path, {}) or {}
    routes = normalize_model_routes(parsed)
    routes = merge_story_config_model_routes(storage, project_id, routes)
    write_json(json_path, routes)
    report = build_model_routes_report(storage, project_id, routes)
    report_dir = ensure_dir(Path(storage.paths(project_id).control) / "reports" / "models")
    report_json = report_dir / "last_model_routes_report.json"
    report_md = report_dir / "last_model_routes_report.md"
    write_json(report_json, report)
    write_text(report_md, model_routes_report_markdown(report))
    return {**report, "paths": {"markdown": str(md_path), "json": str(json_path), "report_json": str(report_json), "report_markdown": str(report_md)}}


def load_model_routes(storage: Any, project_id: str) -> dict[str, dict[str, Any]]:
    ensure_model_routes(storage, project_id)
    json_path = model_routes_json_path(storage, project_id)
    data = read_json(json_path, {}) or {}
    if not isinstance(data, dict) or not data:
        return normalize_model_routes(DEFAULT_MODEL_ROUTES)
    return normalize_model_routes(data)


def route_payload(storage: Any, project_id: str, base_payload: dict[str, Any] | None, role: str) -> dict[str, Any]:
    payload = dict(base_payload or {})
    routes = load_model_routes(storage, project_id)
    route = resolved_route(routes, role)
    # Respect explicit frontend/API payload. Route only fills or overrides when route field is non-empty.
    for key, payload_key in _PAYLOAD_KEYS.items():
        value = route.get(key)
        if value not in (None, ""):
            payload[payload_key] = value
    api_env = str(route.get("api_key_env") or "").strip()
    if api_env and os.getenv(api_env):
        payload["apiKey"] = os.getenv(api_env)
    return payload


def resolved_route(routes: dict[str, dict[str, Any]], role: str) -> dict[str, Any]:
    default = deepcopy(routes.get("default") or DEFAULT_MODEL_ROUTES["default"])
    role_route = routes.get(role) or {}
    merged = deepcopy(default)
    for key, value in role_route.items():
        if value not in (None, ""):
            merged[key] = value
    merged["role"] = role
    merged["label"] = ROLE_LABELS.get(role, role)
    return merged


def build_model_routes_report(storage: Any, project_id: str, routes: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    routes = normalize_model_routes(routes or load_model_routes(storage, project_id))
    resolved = {role: resolved_route(routes, role) for role in ROLE_ORDER}
    issues: list[dict[str, Any]] = []
    for role, route in resolved.items():
        platform = str(route.get("platform") or "").strip()
        if not platform:
            issues.append({"level": "error", "role": role, "type": "missing_platform", "message": f"{role} 未配置 platform。"})
        api_env = str(route.get("api_key_env") or "").strip()
        if api_env and not os.getenv(api_env):
            issues.append({"level": "warning", "role": role, "type": "missing_api_key_env", "message": f"{role} 指定的环境变量 {api_env} 当前未设置。"})
        temp = route.get("temperature")
        if isinstance(temp, (int, float)) and (temp < 0 or temp > 2):
            issues.append({"level": "warning", "role": role, "type": "temperature_range", "message": f"{role} temperature={temp} 超出常用范围。"})
        max_tokens = route.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens < 1024:
            issues.append({"level": "warning", "role": role, "type": "max_tokens_low", "message": f"{role} max_tokens={max_tokens} 可能不足以完成任务。"})
    return {
        "ok": not any(i.get("level") == "error" for i in issues),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_id": project_id,
        "routes": routes,
        "resolved_routes": resolved,
        "issues": issues,
        "issue_count": len(issues),
    }


def merge_story_config_model_routes(storage: Any, project_id: str, routes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    try:
        cfg = storage.load_story_config(project_id)
    except Exception:
        return routes
    cfg_routes = cfg.get("model_routes") if isinstance(cfg, dict) else None
    if not isinstance(cfg_routes, dict):
        return routes
    merged = normalize_model_routes(routes)
    for role, route in cfg_routes.items():
        if not isinstance(route, dict):
            continue
        role_key = str(role).strip()
        if not role_key:
            continue
        merged.setdefault(role_key, {})
        merged[role_key].update(_normalize_route(route))
    return normalize_model_routes(merged)


def normalize_model_routes(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    src = data if isinstance(data, dict) else {}
    for role, default in DEFAULT_MODEL_ROUTES.items():
        raw = src.get(role) if isinstance(src.get(role), dict) else {}
        normalized = deepcopy(default)
        normalized.update(_normalize_route(raw))
        out[role] = normalized
    for role, raw in src.items():
        if role in out or not isinstance(raw, dict):
            continue
        out[str(role)] = _normalize_route(raw)
    return out


def _normalize_route(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        canonical = _FIELD_ALIASES.get(str(key), str(key))
        if canonical in _NUMERIC_FLOAT:
            value = _float(value, DEFAULT_MODEL_ROUTES["default"].get(canonical, 0.0))
        elif canonical in _NUMERIC_INT:
            value = _int(value, DEFAULT_MODEL_ROUTES["default"].get(canonical, 0))
        elif isinstance(value, str):
            value = value.strip()
        out[canonical] = value
    return out


def parse_model_routes_markdown(text: str) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for line in (text or "").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            current = re.split(r"\s+", title, maxsplit=1)[0].strip().lower()
            routes.setdefault(current, {})
            continue
        if not current:
            continue
        kv = re.match(r"^\s*[-*]\s*([A-Za-z_][\w-]*)\s*[:：]\s*(.*?)\s*$", line)
        if kv:
            key = kv.group(1).strip()
            value = kv.group(2).strip()
            routes[current][_FIELD_ALIASES.get(key, key)] = _parse_scalar(value)
    return routes


def model_routes_markdown_template(routes: dict[str, dict[str, Any]]) -> str:
    lines = [
        "# 模型路由配置",
        "",
        "人类编辑这个 Markdown，后端会同步生成 `model_routes.json`。留空字段会继续使用前端输入或环境变量。",
        "",
        "字段说明：",
        "- platform: deepseek / deepseek_reasoner / siliconflow / openai / moonshot / custom",
        "- api_key_env: 指定某个角色读取哪个环境变量，例如 DEEPSEEK_API_KEY；留空则按平台默认环境变量。",
        "- model_name/base_url: 留空则按平台默认值或前端输入。",
        "",
    ]
    for role in ROLE_ORDER:
        route = routes.get(role) or {}
        lines += [
            f"## {role} {ROLE_LABELS.get(role, '')}".rstrip(),
            f"- platform: {route.get('platform', '')}",
            f"- model_name: {route.get('model_name', '')}",
            f"- base_url: {route.get('base_url', '')}",
            f"- api_key_env: {route.get('api_key_env', '')}",
            f"- temperature: {route.get('temperature', '')}",
            f"- max_tokens: {route.get('max_tokens', '')}",
            f"- max_retries: {route.get('max_retries', '')}",
            f"- retry_delay: {route.get('retry_delay', '')}",
            f"- notes: {route.get('notes', '')}",
            "",
        ]
    return "\n".join(lines).strip() + "\n"


def model_routes_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 模型路由报告",
        "",
        f"- 生成时间：{report.get('generated_at', '')}",
        f"- 项目：{report.get('project_id', '')}",
        f"- 状态：{'通过' if report.get('ok') else '有错误'}",
        f"- 提示数量：{report.get('issue_count', 0)}",
        "",
        "## 各角色实际路由",
        "",
        "| 角色 | 平台 | 模型 | 温度 | Max Tokens | Key 环境变量 | 说明 |",
        "|---|---|---|---:|---:|---|---|",
    ]
    resolved = report.get("resolved_routes") or {}
    for role in ROLE_ORDER:
        route = resolved.get(role) or {}
        lines.append(
            f"| {role} | {route.get('platform', '')} | {route.get('model_name', '') or '(默认)'} | "
            f"{route.get('temperature', '')} | {route.get('max_tokens', '')} | {route.get('api_key_env', '') or '(平台默认)'} | {str(route.get('notes', '')).replace('|', '/')} |"
        )
    lines += ["", "## 问题"]
    issues = report.get("issues") or []
    if not issues:
        lines.append("- 暂无。")
    else:
        for issue in issues:
            lines.append(f"- [{issue.get('level')}] {issue.get('role')}: {issue.get('message')}")
    return "\n".join(lines).strip() + "\n"


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"", "null", "None", "无"}:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value.strip('"\'')


def _int(value: Any, default: Any = 0) -> int:
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return int(default or 0)


def _float(value: Any, default: Any = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default or 0.0)
