"""TeleBox account session isolation and lifecycle."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.api.routes import accounts
from backend.services import telebox
from backend.services.telegram import credentials


def test_node_heap_limit_for_multi_account_host(monkeypatch):
    monkeypatch.delenv("TELEBOX_NODE_HEAP_MB", raising=False)
    assert telebox.node_heap_limit_mb() == 128
    for value, expected in [("96", 96), ("8", 64), ("999", 512), ("bad", 128)]:
        monkeypatch.setenv("TELEBOX_NODE_HEAP_MB", value)
        assert telebox.node_heap_limit_mb() == expected


def test_worker_passes_telebox_settings_without_panel_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("TB_PREFIX", "! .")
    monkeypatch.setenv("TB_LISTENER_HANDLE_EDITED", "kitt checkin")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("APP_SECRET_KEY", "must-not-leak")
    env = telebox.worker_environment(tmp_path)
    assert env["TB_PREFIX"] == "! ."
    assert env["TB_LISTENER_HANDLE_EDITED"] == "kitt checkin"
    assert env["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert env["HOME"] == str(tmp_path / "home")
    assert env["NODE_PATH"] == str(tmp_path / "plugins/node_modules")
    assert "APP_SECRET_KEY" not in env


def test_login_credentials_choose_account_server_legacy_and_builtin(monkeypatch, tmp_path):
    monkeypatch.setattr(
        credentials, "get_settings",
        lambda: SimpleNamespace(resolve_workdir=lambda: tmp_path),
    )
    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    monkeypatch.delenv("TG_MANAGE_TG_API_ID", raising=False)
    monkeypatch.delenv("TG_MANAGE_TG_API_HASH", raising=False)
    monkeypatch.setenv("SIGNPULSE_TG_API_ID", "12345")
    monkeypatch.setenv("SIGNPULSE_TG_API_HASH", "a" * 32)
    assert accounts._login_api_credentials(None, None) == (12345, "a" * 32)
    monkeypatch.setenv("TG_MANAGE_TG_API_ID", "24680")
    monkeypatch.setenv("TG_MANAGE_TG_API_HASH", "e" * 32)
    assert accounts._login_api_credentials(None, None) == (24680, "e" * 32)
    monkeypatch.delenv("TG_MANAGE_TG_API_ID")
    monkeypatch.delenv("TG_MANAGE_TG_API_HASH")
    assert accounts._login_api_credentials(67890, "b" * 32) == (67890, "b" * 32)
    with pytest.raises(ValueError, match="同时填写"):
        accounts._login_api_credentials(67890, None)
    monkeypatch.delenv("SIGNPULSE_TG_API_ID")
    monkeypatch.delenv("SIGNPULSE_TG_API_HASH")
    monkeypatch.setenv("TG_API_ID", "54321")
    monkeypatch.setenv("TG_API_HASH", "c" * 32)
    assert accounts._login_api_credentials(None, None) == (54321, "c" * 32)
    monkeypatch.delenv("TG_API_ID")
    monkeypatch.delenv("TG_API_HASH")
    (tmp_path / ".telegram_api.json").write_text(
        json.dumps({"api_id": "76543", "api_hash": "d" * 32})
    )
    assert accounts._login_api_credentials(None, None) == (76543, "d" * 32)
    (tmp_path / ".telegram_api.json").unlink()
    assert accounts._login_api_credentials(None, None) == (
        credentials.LEGACY_DEFAULT_API_ID,
        credentials.LEGACY_DEFAULT_API_HASH,
    )
    monkeypatch.setenv("SIGNPULSE_TG_API_ID", "12345")
    with pytest.raises(ValueError, match="必须同时配置"):
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


def test_existing_account_refreshes_upstream_core_and_keeps_plugin_data(tmp_path):
    source = tmp_path / "upstream"
    (source / "src" / "utils").mkdir(parents=True)
    (source / "src" / "utils" / "runtimeManager.ts").write_text("fixed runtime")
    (source / "src" / "plugin").mkdir()
    (source / "src" / "plugin" / "reload.ts").write_text("fixed reload")
    (source / "scripts").mkdir()
    (source / "panel").mkdir()
    (source / "node_modules").mkdir()
    service = telebox.TeleBoxService(root=tmp_path / "accounts", source=source)
    directory = service._prepare("one")
    (directory / "src" / "utils" / "runtimeManager.ts").write_text("old runtime")
    (directory / "src" / "plugin" / "reload.ts").write_text("old reload")
    (directory / "plugins" / "custom.ts").write_text("my plugin")
    (directory / "assets" / "settings.json").write_text('{"enabled":true}')
    (directory / "config.json").write_text('{"session":"private"}')

    service._prepare("one")

    assert (directory / "src" / "utils" / "runtimeManager.ts").read_text() == "fixed runtime"
    assert (directory / "src" / "plugin" / "reload.ts").read_text() == "fixed reload"
    assert (directory / "plugins" / "custom.ts").read_text() == "my plugin"
    assert (directory / "plugins" / "node_modules").is_dir()
    assert (directory / "assets" / "settings.json").read_text() == '{"enabled":true}'
    assert (directory / "config.json").read_text() == '{"session":"private"}'


@pytest.mark.asyncio
async def test_plugin_action_error_keeps_line_across_stderr_chunks(tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    stream = SimpleNamespace(read=AsyncMock(side_effect=[b"[KITT] match ok\n[KITT] action ",
                                                       b"error: missing dep\n", b""]))
    await service._stderr("one", {"process": SimpleNamespace(stderr=stream)})
    assert [(entry["level"], entry["message"]) for entry in service.logs["one"]] == [
        ("info", "[KITT] match ok"), ("error", "[KITT] action error: missing dep")
    ]


@pytest.mark.asyncio
async def test_logout_revokes_running_worker_and_preserves_panel_account(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    fake_account = SimpleNamespace(_normalize_account_name=lambda name: name,
                                   account_exists=lambda name: name == "one")
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: fake_account)
    directory = service.directory("one")
    directory.mkdir()
    (directory / "config.json").write_text('{"session":"private","api_id":123}')
    service._marker("one", True)
    process = SimpleNamespace(returncode=None, pid=1234)
    worker = {"status": "running", "pending": {}, "process": process}
    service.workers["one"] = worker

    async def send(target, command):
        assert command["action"] == "logout"
        target["pending"][command["id"]].set_result({"ok": True, "revoked": True})

    async def stop(name, *, disable):
        assert name == "one" and disable
        service._marker(name, False)
        process.returncode = 0
        worker["status"] = "stopped"
        return service.status(name)

    monkeypatch.setattr(service, "_send", send)
    monkeypatch.setattr(service, "_stop_locked", stop)
    result = await service.logout("one")
    assert result["remote_revoked"] is True
    assert result["authorized"] is False
    assert result["enabled"] is False
    assert json.loads((directory / "config.json").read_text()) == {"api_id": 123}
    assert fake_account.account_exists("one")
    assert worker["pending"] == {}


@pytest.mark.asyncio
async def test_logout_offline_clears_only_local_telebox_session(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name, account_exists=lambda name: name == "one"))
    directory = service.directory("one")
    directory.mkdir()
    (directory / "config.json").write_text('{"session":"private","api_id":123}')
    result = await service.logout("one")
    assert result["remote_revoked"] is False
    assert result["authorized"] is False
    assert json.loads((directory / "config.json").read_text()) == {"api_id": 123}
