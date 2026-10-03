"""TeleBox task dispatch validates the installed command on the account."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.api.routes import accounts
from backend.services import telebox


def test_node_heap_limit_for_multi_account_host(monkeypatch):
    monkeypatch.delenv("TELEBOX_NODE_HEAP_MB", raising=False)
    assert telebox.node_heap_limit_mb() == 128
    for value, expected in [("96", 96), ("8", 64), ("999", 512), ("bad", 128)]:
        monkeypatch.setenv("TELEBOX_NODE_HEAP_MB", value)
        assert telebox.node_heap_limit_mb() == expected


def test_login_credentials_choose_account_or_private_server_default(monkeypatch):
    monkeypatch.setenv("SIGNPULSE_TG_API_ID", "12345")
    monkeypatch.setenv("SIGNPULSE_TG_API_HASH", "a" * 32)
    assert accounts._login_api_credentials(None, None) == ("12345", "a" * 32)
    assert accounts._login_api_credentials(67890, "b" * 32) == (67890, "b" * 32)
    with pytest.raises(ValueError, match="同时填写"):
        accounts._login_api_credentials(67890, None)
    monkeypatch.delenv("SIGNPULSE_TG_API_ID")
    monkeypatch.delenv("SIGNPULSE_TG_API_HASH")
    with pytest.raises(ValueError, match="服务器缺少"):
        accounts._login_api_credentials(None, None)


def test_existing_telebox_account_refreshes_managed_loader_without_losing_plugins(tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    directory = service.directory("one")
    (directory / "scripts").mkdir(parents=True)
    (directory / "plugins").mkdir()
    (directory / "scripts" / "esbuild-register.cjs").write_text("outdated loader")
    (directory / "plugins" / "custom.ts").write_text("user plugin")
    (directory / "config.json").write_text('{"session":"private"}')

    service._prepare("one")

    assert (directory / "scripts" / "esbuild-register.cjs").read_bytes() == (
        telebox.SOURCE / "scripts" / "esbuild-register.cjs"
    ).read_bytes()
    assert (directory / "plugins" / "custom.ts").read_text() == "user plugin"
    assert (directory / "config.json").read_text() == '{"session":"private"}'


@pytest.mark.asyncio
async def test_dispatch_requires_loaded_command_and_account(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    fake_account = SimpleNamespace(_normalize_account_name=lambda name: name,
                                   account_exists=lambda name: name == "one")
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: fake_account)
    worker = {"status": "running", "pending": {},
              "commands": [{"plugin": "example", "command": "hello"}]}
    service.workers["one"] = worker
    sent = []

    async def send(target, command):
        sent.append(command)
        target["pending"][command["id"]].set_result({"ok": True})

    monkeypatch.setattr(service, "_send", send)
    with pytest.raises(ValueError, match="账号不存在"):
        await service.run_command("two", "example", "hello")
    with pytest.raises(ValueError, match="没有加载"):
        await service.run_command("one", "example", "missing")
    with pytest.raises(ValueError, match="参数无效"):
        await service.run_command("one", "example", "hello", "first\nsecond")
    result = await asyncio.wait_for(service.run_command("one", "example", "hello", "world"), 1)
    assert result["ok"] is True
    assert sent[0]["action"] == "run"
    assert sent[0]["args"] == "world"
    assert worker["pending"] == {}
