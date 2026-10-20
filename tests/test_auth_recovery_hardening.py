"""Credential changes revoke older sessions and recovery stays on the host."""
from __future__ import annotations

import pyotp
from sqlalchemy import create_engine, inspect, text

from backend.core.database import ensure_user_auth_version
from backend.models.user import User
from backend.reset_totp_cli import reset_totp_for_user
from tests.test_api import _auth, _login

pytest_plugins = ("tests.test_api",)


def test_password_change_revokes_old_token_and_returns_new_one(api_client):
    old_token = _login(api_client)
    response = api_client.put(
        "/api/user/password", headers=_auth(old_token),
        json={"old_password": "admin123", "new_password": "new-strong-password"},
    )
    assert response.status_code == 200
    new_token = response.json()["access_token"]
    assert api_client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401
    assert api_client.get("/api/auth/me", headers=_auth(new_token)).status_code == 200


def test_totp_requires_code_or_host_recovery(api_client, db):
    old_token = _login(api_client)
    secret = pyotp.random_base32()
    user = db.query(User).filter(User.username == "admin").one()
    user.totp_secret = secret
    db.commit()

    assert api_client.post(
        "/api/auth/reset-totp", json={"username": "admin", "password": "admin123"},
    ).status_code in {404, 405}
    assert api_client.post("/api/user/totp/reset", headers=_auth(old_token)).status_code in {404, 405}
    assert api_client.get(
        f"/api/user/totp/qrcode?token={old_token}",
    ).status_code == 401
    assert api_client.get(
        "/api/user/totp/qrcode", headers=_auth(old_token),
    ).status_code == 400

    assert reset_totp_for_user("admin")
    db.refresh(user)
    assert user.totp_secret is None
    assert api_client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401
    assert _login(api_client)


def test_disabling_totp_revokes_old_token(api_client, db):
    old_token = _login(api_client)
    secret = pyotp.random_base32()
    user = db.query(User).filter(User.username == "admin").one()
    user.totp_secret = secret
    db.commit()
    response = api_client.post(
        "/api/user/totp/disable", headers=_auth(old_token),
        json={"totp_code": pyotp.TOTP(secret).now()},
    )
    assert response.status_code == 200
    assert api_client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401
    assert api_client.get(
        "/api/auth/me", headers=_auth(response.json()["access_token"]),
    ).status_code == 200


def test_existing_users_table_gets_auth_version_without_losing_data():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(50), "
            "password_hash VARCHAR(255), totp_secret VARCHAR(64))"
        ))
        connection.execute(text(
            "INSERT INTO users (id, username, password_hash) VALUES (1, 'admin', 'hash')"
        ))
    ensure_user_auth_version(engine)
    ensure_user_auth_version(engine)
    assert "auth_version" in {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT username, password_hash, auth_version FROM users WHERE id = 1"
        )).one() == ("admin", "hash", 0)
    engine.dispose()
