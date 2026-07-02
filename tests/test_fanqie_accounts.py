from __future__ import annotations

from backend.fanqie_web import accounts


def test_new_account_id_keeps_chinese_names_and_deduplicates() -> None:
    existing = [{"id": "作者_一号"}]

    assert accounts._new_account_id("作者 一号", existing) == "作者_一号_2"


def test_account_state_file_sanitizes_path_unsafe_characters(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(accounts, "FANQIE_ACCOUNT_STATES_DIR", tmp_path)

    path = accounts._state_file_for("writer/account:01")

    assert path == tmp_path / "writer_account_01.json"
