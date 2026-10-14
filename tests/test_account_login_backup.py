from __future__ import annotations

import asyncio
import base64
import struct
from pathlib import Path

import pytest

from backend.core.config import Settings
from backend.services.account_login_backup import (
    LoginBackupError,
    _new_session_file,
    export_login_backup,
    import_login_backup,
)
from backend.utils import tg_session

API_ID = 611335
API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


class FakeService:
    def __init__(self, session_dir: Path) -> None:
        self.session_dir = session_dir
        self._accounts_cache = object()

    def list_accounts(self, force_refresh: bool = False) -> list[dict[str, str]]:
        suffix = ".session_string" if tg_session.get_session_mode() == "string" else ".session"
        return [{"name": file.name.removesuffix(suffix)} for file in self.session_dir.glob(f"*{suffix}")]


def _session() -> tuple[str, tuple[int, int, bool, bytes, int, bool]]:
    fields = (2, API_ID, False, bytes(range(256)), 123456789, False)
    session = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", *fields)).decode().rstrip("=")
    return session, fields


@pytest.mark.parametrize("mode", ["file", "string"])
def test_encrypted_login_backup_round_trips_across_server_secrets_and_skips_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str,
) -> None:
    monkeypatch.setenv("TG_SESSION_MODE", mode)
    source = tmp_path / "source"
    source.mkdir()
    source_settings = Settings(data_dir=source, session_dir=source, secret_key="source-secret")
    monkeypatch.setattr(tg_session, "get_settings", lambda: source_settings)
    service = FakeService(source)
    session, fields = _session()
    if mode == "file":
        _new_session_file(source / "alice.session", fields)
    else:
        (source / "alice.session_string").write_text(session, encoding="utf-8")
    tg_session.set_account_api_credentials("alice", API_ID, API_HASH)
    blob, count = export_login_backup("correct horse battery", service=service)
    assert count == 1
    assert b"alice" not in blob
    assert API_HASH.encode() not in blob

    destination = tmp_path / "destination"
    destination.mkdir()
    dest_settings = Settings(data_dir=destination, session_dir=destination, secret_key="different-secret")
    monkeypatch.setattr(tg_session, "get_settings", lambda: dest_settings)
    restored_service = FakeService(destination)
    with pytest.raises(LoginBackupError):
        import_login_backup(blob, "incorrect password", service=restored_service)
    assert not list(destination.glob("*.session*"))

    assert import_login_backup(blob, "correct horse battery", service=restored_service) == {"restored": 1, "skipped": 0}
    assert tg_session.get_account_api_credentials("alice") == (API_ID, API_HASH)
    restored = tg_session.load_account_session_string("alice", session_dir=destination, session_mode=mode)
    assert restored == session
    if mode == "file":
        from pyrogram.storage.file_storage import FileStorage

        async def verify_kurigram_storage() -> None:
            storage = FileStorage("alice", destination)
            await storage.open()
            try:
                assert await storage.api_id() == API_ID
                assert await storage.auth_key() == fields[3]
                assert await storage.user_id() == fields[4]
            finally:
                await storage.close()

        asyncio.run(verify_kurigram_storage())
    assert restored_service._accounts_cache is None
    other_fields = (2, API_ID, False, bytes(reversed(range(256))), 987654321, False)
    other_session = base64.urlsafe_b64encode(struct.pack(">BI?256sQ?", *other_fields)).decode().rstrip("=")
    if mode == "file":
        (destination / "alice.session").unlink()
        _new_session_file(destination / "alice.session", other_fields)
        (destination / "alice.session_string").unlink(missing_ok=True)
    else:
        (destination / "alice.session_string").write_text(other_session, encoding="utf-8")
    tg_session.set_account_api_credentials("alice", API_ID, "0" * 32)
    assert import_login_backup(blob, "correct horse battery", service=restored_service) == {"restored": 0, "skipped": 1}
    assert tg_session.load_account_session_string("alice", session_dir=destination, session_mode=mode) == other_session
    assert tg_session.get_account_api_credentials("alice") == (API_ID, "0" * 32)


def test_corrupt_encrypted_backup_does_not_create_accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TG_SESSION_MODE", "file")
    settings = Settings(data_dir=tmp_path, session_dir=tmp_path, secret_key="test-secret")
    monkeypatch.setattr(tg_session, "get_settings", lambda: settings)
    service = FakeService(tmp_path)
    with pytest.raises(LoginBackupError):
        import_login_backup(b"TGLOGIN1" + b"x" * 80, "correct horse battery", service=service)
    assert not list(tmp_path.glob("*.session"))
