"""First-run setup and per-account credential boundaries."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.requests import Request

from backend.api.routes import auth
from backend.models.user import User
from backend.services import users
from backend.services.telegram import credentials
from backend.utils import tg_session


def test_admin_setup_requires_server_token_and_keeps_existing_user(tmp_path, monkeypatch):
    monkeypatch.setattr(
        users, "get_settings", lambda: SimpleNamespace(resolve_base_dir=lambda: tmp_path)
    )
    engine = create_engine("sqlite://")
    User.metadata.create_all(engine)
    request = Request({"type": "http", "method": "POST", "path": "/auth/setup", "headers": [],
                       "client": ("127.0.0.1", 12345)})
    with Session(engine) as db:
        users.prepare_admin_setup(db)
        token_file = users.setup_token_path()
        token = token_file.read_text()
        assert token_file.stat().st_mode & 0o077 == 0
        with pytest.raises(HTTPException) as denied:
            auth.initial_setup(auth.InitialSetupRequest(setup_token="x" * 32,
                                                        password="strong-password-123"), request, db)
        assert denied.value.status_code == 403
        result = auth.initial_setup(auth.InitialSetupRequest(setup_token=token,
                                                             password="strong-password-123"), request, db)
        assert result.access_token
        assert not token_file.exists()
        users.prepare_admin_setup(db)
        assert not token_file.exists()
        assert db.query(User).count() == 1
    engine.dispose()


def test_account_credentials_encrypted_isolated_and_not_in_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tg_session, "get_settings", lambda: SimpleNamespace(
            resolve_session_dir=lambda: tmp_path, secret_key="test-secret-for-account-store"
        )
    )
    first_hash = "a" * 32
    second_hash = "b" * 32
    tg_session.set_account_api_credentials("one", 12345, first_hash)
    tg_session.set_account_api_credentials("two", 54321, second_hash)
    raw = (tmp_path / "accounts.json").read_text()
    assert first_hash not in raw and second_hash not in raw
    assert (tmp_path / "accounts.json").stat().st_mode & 0o077 == 0
    assert tg_session.get_account_api_credentials("one") == (12345, first_hash)
    assert tg_session.get_account_api_credentials("two") == (54321, second_hash)
    assert "api_credentials" not in tg_session.get_account_profile("one")
    tg_session.rename_account_entry("one", "renamed")
    assert tg_session.get_account_api_credentials("renamed") == (12345, first_hash)
    tg_session.delete_account_session_string("renamed")
    with pytest.raises(ValueError, match="重新登录"):
        tg_session.get_account_api_credentials("renamed")


def test_legacy_session_without_encrypted_credentials_uses_compatible_default(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tg_session, "get_settings", lambda: SimpleNamespace(
            resolve_session_dir=lambda: tmp_path, secret_key="test-secret-for-account-store"
        )
    )
    monkeypatch.setattr(
        credentials, "get_settings",
        lambda: SimpleNamespace(resolve_workdir=lambda: tmp_path),
    )
    for name in ("SIGNPULSE_TG_API_ID", "SIGNPULSE_TG_API_HASH", "TG_API_ID", "TG_API_HASH"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "old.session").write_bytes(b"legacy session")
    assert tg_session.get_account_api_credentials("old") == (
        credentials.LEGACY_DEFAULT_API_ID,
        credentials.LEGACY_DEFAULT_API_HASH,
    )
    with pytest.raises(ValueError, match="重新登录"):
        tg_session.get_account_api_credentials("never-logged-in")
