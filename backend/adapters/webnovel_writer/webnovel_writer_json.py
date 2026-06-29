from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any


_CHANGES_MARKERS = [
    r"---\s*CHANGES\s*---",
    r"---\s*changes\s*---",
    r"---\s*变更\s*---",
    r"---\s*FACTS\s*---",
    r"---\s*事实\s*---",
]
_CHANGES_MARKER_RE = re.compile(r"(?im)^\s*(?:" + "|".join(_CHANGES_MARKERS) + r")\s*$")
_XML_CHANGES_RE = re.compile(r"(?is)<\s*(?:chapter_changes|changes|facts)\s*>([\s\S]*?)</\s*(?:chapter_changes|changes|facts)\s*>")
_MD_CHANGES_RE = re.compile(r"(?im)^\s{0,3}#{1,4}\s*(?:CHANGES|变更记录|变更声明|变更摘要|状态变更|事实回写|FACTS)\s*$")
_LABEL_CHANGES_RE = re.compile(r"(?im)^\s*(?:CHANGES|变更记录|变更声明|事实回写|FACTS)\s*[:：]\s*$")


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _atomic_write_text(p, text)
    return p


def append_jsonl(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    return p


def read_jsonl(path: str | Path) -> list[Any]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[Any] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            rows.append({"raw": line})
    return rows


def extract_json_object(raw: str) -> dict[str, Any]:
    value = extract_json_value(raw)
    if isinstance(value, dict):
        return value
    if value is None:
        yamlish = parse_loose_mapping(raw)
        if yamlish:
            return yamlish
        return {"raw": str(raw or "").strip()}
    return {"value": value}


def extract_json_value(raw: str) -> Any:
    text = _strip_fences(str(raw or "").strip())
    if not text:
        return None
    for candidate in _json_candidates(text):
        parsed = _loads_lenient(candidate)
        if parsed is not _JSON_FAIL:
            return parsed
    return None


def split_draft_and_changes(raw: str) -> tuple[str, dict[str, Any]]:
    draft, changes, _ = split_draft_and_changes_with_marker(raw)
    return draft, changes


def split_draft_and_changes_with_marker(raw: str) -> tuple[str, dict[str, Any], bool]:
    """Split model output into prose and CHANGES.

    The writer model is not perfectly obedient.  Tianming-style gates should be
    strict about requiring facts, but tolerant about locating the fact block.
    Supported forms:
    - a standalone ---CHANGES--- line, case-insensitive
    - <changes>...</changes> or <chapter_changes>...</chapter_changes>
    - Markdown headers such as ## CHANGES / ## 事实回写
    - a final JSON object/array when the marker was forgotten
    """
    text = str(raw or "").strip()
    if not text:
        return "", {}, False

    xml_matches = list(_XML_CHANGES_RE.finditer(text))
    if xml_matches:
        m = xml_matches[-1]
        draft = (text[: m.start()] + text[m.end() :]).strip()
        return draft, extract_json_object(m.group(1).strip()), True

    marker_matches = list(_CHANGES_MARKER_RE.finditer(text))
    if marker_matches:
        m = marker_matches[-1]
        return text[: m.start()].strip(), extract_json_object(text[m.end() :].strip()), True

    for regex in (_MD_CHANGES_RE, _LABEL_CHANGES_RE):
        matches = list(regex.finditer(text))
        if matches:
            m = matches[-1]
            return text[: m.start()].strip(), extract_json_object(text[m.end() :].strip()), True

    # Fallback: peel off the final JSON object/array if the model forgot the marker.
    tail = _find_trailing_json_region(text)
    if tail:
        start, end = tail
        value = extract_json_object(text[start:end])
        if value and "raw" not in value:
            return text[:start].strip(), value, False
    return text.strip(), {}, False


def parse_loose_mapping(raw: str) -> dict[str, Any]:
    """Parse a small human/LLM-friendly YAML-ish mapping without PyYAML.

    It is intentionally conservative and only supports top-level `key: value`
    pairs and bullet lists.  This gives the gate a useful error surface when a
    model emits Markdown instead of JSON.
    """
    text = _strip_fences(str(raw or "").strip())
    if not text or "{" in text[:20]:
        return {}
    out: dict[str, Any] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        kv = re.match(r"^[-*]?\s*([A-Za-z_][A-Za-z0-9_\-]*|[\u4e00-\u9fff]{2,12})\s*[:：]\s*(.*)$", line)
        if kv:
            key = _normalise_loose_key(kv.group(1))
            value = kv.group(2).strip()
            current_key = key
            if not value:
                out[key] = []
            elif "," in value or "，" in value or "、" in value:
                out[key] = [x.strip() for x in re.split(r"[,，、]", value) if x.strip()]
            else:
                out[key] = _coerce_scalar(value)
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if bullet and current_key:
            out.setdefault(current_key, [])
            if isinstance(out[current_key], list):
                out[current_key].append(_coerce_scalar(bullet.group(1).strip()))
    return out


_JSON_FAIL = object()


def _json_candidates(text: str) -> list[str]:
    stripped = _strip_fences(text)
    candidates = [stripped]
    for match in re.finditer(r"```(?:json|JSON)?\s*([\s\S]*?)```", text, flags=re.I):
        candidates.append(match.group(1).strip())
    for start_ch, end_ch in [("{", "}"), ("[", "]")]:
        start = text.find(start_ch)
        end = text.rfind(end_ch)
        if 0 <= start < end:
            candidates.append(text[start : end + 1])
    # Keep order and remove empty duplicates.
    seen: set[str] = set()
    out: list[str] = []
    for item in candidates:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _loads_lenient(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        pass
    repaired = _repair_common_json_issues(text)
    try:
        return json.loads(repaired)
    except Exception:
        return _JSON_FAIL


def _repair_common_json_issues(text: str) -> str:
    # Safe, conservative repairs for common LLM mistakes.
    s = text.strip().lstrip("\ufeff")
    s = s.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    s = re.sub(r"//.*?$", "", s, flags=re.M)
    s = re.sub(r"/\*[\s\S]*?\*/", "", s)
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # Quote bare object keys: {summary: "..."}, {张三: {...}}
    s = re.sub(r"(?m)([{,]\s*)([A-Za-z_][A-Za-z0-9_\-]*|[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9_\-]{0,30})(\s*:)", r'\1"\2"\3', s)
    # Quote simple unquoted scalar values: {"summary": 本章摘要}
    def _quote_scalar(m: re.Match[str]) -> str:
        prefix, value, suffix = m.group(1), m.group(2).strip(), m.group(3)
        if not value or value[0] in '{["' or re.fullmatch(r"-?\d+(?:\.\d+)?|true|false|null", value, flags=re.I):
            return m.group(0)
        escaped = value.replace('"', '\\"')
        return f'{prefix}"{escaped}"{suffix}'
    s = re.sub(r'(:\s*)([^,{}\[\]"\n][^,{}\[\]\n]*?)(\s*[,}])', _quote_scalar, s)
    # Convert Python booleans/null often emitted by models.
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    # Remove accidental semicolons before close braces.
    s = re.sub(r";\s*([}\]])", r"\1", s)
    return s


def _find_trailing_json_region(text: str) -> tuple[int, int] | None:
    stripped = text.rstrip()
    if not stripped:
        return None
    close = stripped[-1]
    if close not in "}]":
        return None
    open_ch = "{" if close == "}" else "["
    close_ch = close
    depth = 0
    in_string = False
    escape = False
    for idx in range(len(stripped) - 1, -1, -1):
        ch = stripped[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == close_ch:
            depth += 1
        elif ch == open_ch:
            depth -= 1
            if depth == 0:
                return idx, len(stripped)
    return None


def _strip_fences(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json|markdown|md|yaml|yml)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _normalise_loose_key(key: str) -> str:
    mapping = {
        "摘要": "summary",
        "本章摘要": "summary",
        "角色": "characters",
        "地点": "locations",
        "势力": "factions",
        "物品": "items",
        "伏笔": "foreshadows",
        "冲突": "conflicts",
        "时间线": "timeline",
        "钩子": "hooks",
    }
    return mapping.get(key.strip(), key.strip())


def _coerce_scalar(value: str) -> Any:
    v = str(value or "").strip()
    if not v:
        return ""
    if v.lower() in {"true", "false"}:
        return v.lower() == "true"
    if v.lower() in {"null", "none"}:
        return None
    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        parsed = extract_json_value(v)
        if parsed is not None:
            return parsed
    return v


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, newline="") as f:
        tmp = Path(f.name)
        f.write(text)
    tmp.replace(path)
