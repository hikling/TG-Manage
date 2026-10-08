"""Repeated account probes must release their reference-counted clients."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.services.telegram import accounts as accounts_mod


class _Service(accounts_mod.TelegramAccountsMixin):
    def __init__(self, session_dir):
        self.session_dir = session_dir

    def account_exists(self, _name):
        return True


class _Client:
    def __init__(self, behavior="ok"):
        self.behavior = behavior
        self.active = 0
        self.enters = 0
        self.exits = 0

    async def __aenter__(self):
        self.enters += 1
        self.active += 1
        return self

    async def __aexit__(self, *_args):
        self.exits += 1
        self.active -= 1

    async def get_me(self):
        if self.behavior == "error":
            raise ConnectionError("network unavailable")
        if self.behavior == "timeout":
            await asyncio.sleep(60)
        return SimpleNamespace(id=123)


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["ok", "error", "timeout"])
async def test_status_probe_releases_client_on_all_outcomes(tmp_path, monkeypatch, behavior):
    client = _Client(behavior)
    monkeypatch.setattr("tg_manage.core.get_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    status_write = Mock()
    monkeypatch.setattr(accounts_mod, "set_account_status", status_write)

    iterations = 20 if behavior != "timeout" else 1
    for _ in range(iterations):
        result = await _Service(tmp_path).check_account_status("sample", timeout_seconds=1)
        assert result["ok"] is (behavior == "ok")
        assert client.active == 0
    assert client.enters == client.exits == iterations
