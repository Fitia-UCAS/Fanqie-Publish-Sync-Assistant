from __future__ import annotations

from pathlib import Path


def do_nothing() -> None:
    return None


def test_reset_app_data_preserves_auth_state_config_and_rebuilds_runtime(monkeypatch, tmp_path: Path) -> None:
    from backend import data_reset as app_data_reset

    data_dir = tmp_path / "data"
    auth_file = data_dir / "auth" / "fanqie" / "default" / "state.json"
    publish_dir = data_dir / "publishing"
    publish_debug = publish_dir / "debug"
    publish_debug.mkdir(parents=True)
    (publish_debug / "old.png").write_text("old", encoding="utf-8")
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text('{"cookies": []}', encoding="utf-8")

    config_file = tmp_path / "config" / "config.json"
    config_file.parent.mkdir(parents=True)
    config_file.write_text('{"auto_publish": {"novelFile": "keep.txt"}}', encoding="utf-8")

    rebuilt_dirs = (publish_debug, publish_dir / "tracker")

    def ensure_runtime_tree() -> None:
        for directory in rebuilt_dirs:
            directory.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(app_data_reset, "DATA_DIR", data_dir)
    monkeypatch.setattr(app_data_reset, "RUNTIME_DATA_DIRS", (publish_dir,))
    monkeypatch.setattr(app_data_reset, "BROWSER_DATA_DIR", data_dir / "runtime" / "fanqie_web")
    monkeypatch.setattr(app_data_reset, "FANQIE_AUTH_STATE_FILE", auth_file)
    monkeypatch.setattr(app_data_reset, "FANQIE_ACCOUNTS_FILE", data_dir / "auth" / "fanqie" / "accounts.json")
    monkeypatch.setattr(app_data_reset, "FANQIE_ACCOUNT_STATES_DIR", data_dir / "auth" / "fanqie" / "accounts")
    monkeypatch.setattr(app_data_reset, "ensure_data_directories", ensure_runtime_tree)

    result = app_data_reset.reset_app_data(preserve_auth_state=True)

    assert result["ok"] is True
    assert auth_file.exists()
    assert auth_file.read_text(encoding="utf-8") == '{"cookies": []}'
    assert publish_debug.exists()
    assert not (publish_debug / "old.png").exists()
    assert (publish_dir / "tracker").exists()
    assert config_file.read_text(encoding="utf-8") == '{"auto_publish": {"novelFile": "keep.txt"}}'


def test_reset_login_state_removes_state_and_old_profile(monkeypatch, tmp_path: Path) -> None:
    from backend import data_reset as app_data_reset

    browser_dir = tmp_path / "runtime" / "fanqie_web"
    auth_file = tmp_path / "auth" / "fanqie" / "default" / "state.json"
    old_profile = browser_dir / "browser_edge_profile"
    old_profile.mkdir(parents=True)
    auth_file.parent.mkdir(parents=True)
    auth_file.write_text("{}", encoding="utf-8")
    (old_profile / "cookie").write_text("old", encoding="utf-8")

    monkeypatch.setattr(app_data_reset, "BROWSER_DATA_DIR", browser_dir)
    monkeypatch.setattr(app_data_reset, "FANQIE_AUTH_STATE_FILE", auth_file)
    monkeypatch.setattr(app_data_reset, "FANQIE_ACCOUNTS_FILE", tmp_path / "auth" / "fanqie" / "accounts.json")
    monkeypatch.setattr(app_data_reset, "FANQIE_ACCOUNT_STATES_DIR", tmp_path / "auth" / "fanqie" / "accounts")
    monkeypatch.setattr(app_data_reset, "ensure_data_directories", do_nothing)

    result = app_data_reset.reset_login_state()

    assert result["ok"] is True
    assert not auth_file.exists()
    assert not old_profile.exists()
