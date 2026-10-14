"""Authenticated account-login backup transport contract."""
from __future__ import annotations

from unittest.mock import patch

from tests.test_api import _auth, _login, api_client, db  # noqa: F401


def test_login_backup_export_requires_auth_and_returns_attachment(api_client, db) -> None:  # noqa: F811
    anonymous = api_client.post("/api/accounts/login-backup/export", json={"password": "correct horse battery"})
    assert anonymous.status_code == 401
    token = _login(api_client)
    with patch("backend.api.routes.accounts.export_login_backup", return_value=(b"TGLOGIN1encrypted", 2)):
        response = api_client.post(
            "/api/accounts/login-backup/export",
            json={"password": "correct horse battery"}, headers=_auth(token),
        )
    assert response.status_code == 200
    assert response.content == b"TGLOGIN1encrypted"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accounts-exported"] == "2"


def test_login_backup_import_reads_file_and_returns_counts(api_client, db) -> None:  # noqa: F811
    token = _login(api_client)
    with patch("backend.api.routes.accounts.import_login_backup", return_value={"restored": 1, "skipped": 2}) as importer:
        response = api_client.post(
            "/api/accounts/login-backup/import",
            data={"password": "correct horse battery"},
            files={"file": ("accounts.tglogin", b"TGLOGIN1encrypted", "application/octet-stream")},
            headers=_auth(token),
        )
    assert response.status_code == 200
    assert response.json() == {"restored": 1, "skipped": 2}
    assert importer.call_args.args[:2] == (b"TGLOGIN1encrypted", "correct horse battery")
