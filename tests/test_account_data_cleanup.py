"""Explicit full checks prune only orphaned account-local data."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services import account_data_cleanup as cleanup


class _Accounts:
    def __init__(self, session_dir):
        self.session_dir = session_dir
        self.fail_list = False

    def list_accounts(self, *, force_refresh, strict):
        assert force_refresh and strict
        if self.fail_list:
            raise OSError("session storage unavailable")
        return [{"name": path.name[:-8]} for path in self.session_dir.glob("*.session")]

    def account_exists(self, name):
        return (self.session_dir / f"{name}.session").exists()


@pytest.fixture
def cleanup_env(tmp_path, monkeypatch):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir()
    accounts = _Accounts(session_dir)
    telebox = SimpleNamespace(reconcile_orphan_data=AsyncMock(return_value=["old"]))
    keepalive = SimpleNamespace(prune_account_state=Mock(return_value=1))
    deleted_metadata = Mock()
    monkeypatch.setattr(cleanup, "get_telegram_service", lambda: accounts)
    monkeypatch.setattr(cleanup, "get_device_keepalive_service", lambda: keepalive)
    monkeypatch.setattr(cleanup, "get_settings", lambda: SimpleNamespace(resolve_workdir=lambda: tmp_path))
    monkeypatch.setattr(cleanup, "delete_account_session_string", deleted_metadata)
    monkeypatch.setattr("backend.services.telebox.get_telebox_service", lambda: telebox)
    monkeypatch.setattr(cleanup, "is_string_session_mode", lambda: False)
    return SimpleNamespace(
        accounts=accounts, session_dir=session_dir, avatar_dir=avatar_dir,
        telebox=telebox, keepalive=keepalive, deleted_metadata=deleted_metadata,
    )


@pytest.mark.asyncio
async def test_manual_reconcile_removes_only_orphan_data(cleanup_env):
    env = cleanup_env
    (env.session_dir / "live.session").write_bytes(b"session")
    (env.session_dir / "accounts.json").write_text(
        json.dumps({"accounts": {"live": {}, "old": {"status": "checking"}}}),
        encoding="utf-8",
    )
    (env.avatar_dir / "live.jpg").write_bytes(b"live")
    (env.avatar_dir / "old.no_avatar").write_bytes(b"old")
    (env.avatar_dir / "chats").mkdir()
    (env.avatar_dir / "chats" / "old.jpg").write_bytes(b"shared")

    removed = await cleanup.reconcile_orphan_account_data()

    assert removed == {"telebox": 1, "metadata": 1, "keepalive": 1, "avatars": 1, "pending": 0}
    env.telebox.reconcile_orphan_data.assert_awaited_once_with({"live"})
    env.keepalive.prune_account_state.assert_called_once()
    env.deleted_metadata.assert_called_once_with("old")
    assert (env.avatar_dir / "live.jpg").exists()
    assert not (env.avatar_dir / "old.no_avatar").exists()
    assert (env.avatar_dir / "chats" / "old.jpg").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["corrupt_store", "inventory_io"])
async def test_untrusted_inventory_never_deletes(cleanup_env, failure):
    env = cleanup_env
    (env.avatar_dir / "old.jpg").write_bytes(b"keep")
    if failure == "corrupt_store":
        (env.session_dir / "accounts.json").write_text("{broken", encoding="utf-8")
    else:
        env.accounts.fail_list = True

    with pytest.raises((OSError, ValueError, json.JSONDecodeError)):
        await cleanup.reconcile_orphan_account_data()

    env.telebox.reconcile_orphan_data.assert_not_awaited()
    env.keepalive.prune_account_state.assert_not_called()
    env.deleted_metadata.assert_not_called()
    assert (env.avatar_dir / "old.jpg").exists()


def test_other_session_mode_login_state_is_preserved(cleanup_env):
    env = cleanup_env
    (env.session_dir / "old.session_string").write_bytes(b"do not delete login state")
    (env.session_dir / "accounts.json").write_text(
        json.dumps({"accounts": {"old": {"status": "connected"}}}), encoding="utf-8",
    )
    live, metadata = cleanup._trusted_inventory(env.accounts)
    assert live == metadata == {"old"}


@pytest.mark.asyncio
async def test_empty_unbacked_inventory_preserves_other_data(cleanup_env):
    env = cleanup_env
    (env.avatar_dir / "old.jpg").write_bytes(b"keep")

    result = await cleanup.reconcile_orphan_account_data()

    assert result == {"telebox": 0, "metadata": 0, "keepalive": 0, "avatars": 0, "pending": 0}
    env.telebox.reconcile_orphan_data.assert_not_awaited()
    assert (env.avatar_dir / "old.jpg").exists()
