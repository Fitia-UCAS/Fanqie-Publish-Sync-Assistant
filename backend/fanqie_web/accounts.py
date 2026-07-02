from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from backend.paths import FANQIE_ACCOUNTS_FILE, FANQIE_ACCOUNT_STATES_DIR, FANQIE_AUTH_STATE_FILE

_DEFAULT_ACCOUNT_ID = "default"
_DEFAULT_ACCOUNT_NAME = "默认账号"


SAFE_ACCOUNT_ID_RE = re.compile(r"[^0-9A-Za-z_\-]+")
SAFE_ACCOUNT_NAME_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff_\-]+")


def list_accounts() -> dict[str, Any]:
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id not in {item["id"] for item in accounts}:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    return {"ok": True, "activeId": active_id, "accounts": [_public_account(item, active_id=active_id) for item in accounts]}


def add_account(name: str) -> dict[str, Any]:
    display_name = str(name or "").strip() or f"账号{time.strftime('%m%d%H%M')}"
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    if display_name in {item["name"] for item in accounts}:
        return {"ok": False, "message": "账号名称已存在。", **list_accounts()}
    account_id = _new_account_id(display_name, accounts)
    accounts.append({"id": account_id, "name": display_name, "state_file": str(_state_file_for(account_id))})
    data["accounts"] = accounts
    data["active_id"] = account_id
    _save_accounts(data)
    return {"ok": True, "message": f"已添加并切换到账号：{display_name}", **list_accounts()}


def switch_account(account_id: str) -> dict[str, Any]:
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    target = next((item for item in accounts if item["id"] == account_id), None)
    if target is None:
        return {"ok": False, "message": "账号不存在。", **list_accounts()}
    data["accounts"] = accounts
    data["active_id"] = account_id
    _save_accounts(data)
    return {"ok": True, "message": f"已切换到账号：{target['name']}", **list_accounts()}


def delete_account(account_id: str) -> dict[str, Any]:
    if account_id == _DEFAULT_ACCOUNT_ID:
        return {"ok": False, "message": "默认账号不能删除。", **list_accounts()}
    data = _load_accounts()
    accounts = _normalize_accounts(data.get("accounts"))
    target = next((item for item in accounts if item["id"] == account_id), None)
    if target is None:
        return {"ok": False, "message": "账号不存在。", **list_accounts()}
    accounts = [item for item in accounts if item["id"] != account_id]
    try:
        _state_file_for(account_id).unlink(missing_ok=True)
    except Exception:
        pass
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id == account_id:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    data["accounts"] = accounts
    data["active_id"] = active_id
    _save_accounts(data)
    return {"ok": True, "message": f"已删除账号：{target['name']}", **list_accounts()}


def resolve_auth_state_file(path: str | Path | None = None) -> Path:
    raw = str(path or "").strip()
    if not raw:
        return FANQIE_AUTH_STATE_FILE
    target = Path(raw).expanduser()
    if target.exists() and target.is_dir():
        return target / "state.json"
    if not target.suffix:
        return target / "state.json"
    return target


def active_auth_state_file() -> Path:
    return FANQIE_AUTH_STATE_FILE


def _load_accounts() -> dict[str, Any]:
    if FANQIE_ACCOUNTS_FILE.exists():
        try:
            data = json.loads(FANQIE_ACCOUNTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"active_id": _DEFAULT_ACCOUNT_ID, "accounts": [_default_account()]}


def _save_accounts(data: dict[str, Any]) -> None:
    FANQIE_ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FANQIE_ACCOUNT_STATES_DIR.mkdir(parents=True, exist_ok=True)
    accounts = _normalize_accounts(data.get("accounts"))
    active_id = str(data.get("active_id") or _DEFAULT_ACCOUNT_ID)
    if active_id not in {item["id"] for item in accounts}:
        active_id = accounts[0]["id"] if accounts else _DEFAULT_ACCOUNT_ID
    FANQIE_ACCOUNTS_FILE.write_text(json.dumps({"active_id": active_id, "accounts": accounts}, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_accounts(raw: Any) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not account_id or not name or account_id in seen:
            continue
        state_file = str(item.get("state_file") or (_state_file_for(account_id) if account_id != _DEFAULT_ACCOUNT_ID else FANQIE_AUTH_STATE_FILE))
        accounts.append({"id": account_id, "name": name, "state_file": state_file})
        seen.add(account_id)
    if _DEFAULT_ACCOUNT_ID not in seen:
        accounts.insert(0, _default_account())
    return accounts


def _default_account() -> dict[str, str]:
    return {"id": _DEFAULT_ACCOUNT_ID, "name": _DEFAULT_ACCOUNT_NAME, "state_file": str(FANQIE_AUTH_STATE_FILE)}


def _public_account(item: dict[str, str], *, active_id: str) -> dict[str, Any]:
    state_file = Path(item.get("state_file") or "")
    return {"id": item["id"], "name": item["name"], "active": item["id"] == active_id, "loggedIn": state_file.exists(), "stateFile": str(state_file)}


def _state_file_for(account_id: str) -> Path:
    if account_id == _DEFAULT_ACCOUNT_ID:
        return FANQIE_AUTH_STATE_FILE
    FANQIE_ACCOUNT_STATES_DIR.mkdir(parents=True, exist_ok=True)
    safe = SAFE_ACCOUNT_ID_RE.sub("_", account_id).strip("_") or str(int(time.time()))
    return FANQIE_ACCOUNT_STATES_DIR / f"{safe}.json"


def _new_account_id(name: str, accounts: list[dict[str, str]]) -> str:
    base = SAFE_ACCOUNT_NAME_RE.sub("_", name).strip("_") or "account"
    existing = {item["id"] for item in accounts}
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate
