"""TeleBox account session isolation and lifecycle."""
from __future__ import annotations

import asyncio
import json
from collections import deque
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


def test_total_telebox_worker_limit_is_bounded(monkeypatch):
    monkeypatch.delenv("TELEBOX_MAX_WORKERS", raising=False)
    assert telebox.max_workers() == 2
    for value, expected in [("1", 1), ("0", 1), ("99", 8), ("bad", 2)]:
        monkeypatch.setenv("TELEBOX_MAX_WORKERS", value)
        assert telebox.max_workers() == expected


@pytest.mark.asyncio
async def test_worker_admission_counts_running_and_starting_accounts(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEBOX_MAX_WORKERS", "2")
    service = telebox.TeleBoxService(root=tmp_path)
    service.workers["one"] = {"process": SimpleNamespace(returncode=None)}
    await service._reserve_worker_slot("two")
    with pytest.raises(ValueError, match="并发上限"):
        await service._reserve_worker_slot("three")
    await service._release_worker_slot("two")
    await service._reserve_worker_slot("three")
    await service._release_worker_slot("three")
    service.workers["one"]["process"].returncode = 0
    await service._reserve_worker_slot("four")
    await service._release_worker_slot("four")


def test_telebox_worker_credentials_does_not_construct_pyrogram_client(monkeypatch):
    monkeypatch.setattr(telebox, "get_account_api_credentials", lambda account: (12345, "a" * 32))
    monkeypatch.setattr(telebox, "resolve_account_route", lambda account: {
        "scheme": "socks5", "hostname": "127.0.0.1", "port": 1080,
    })
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _build_account_client=lambda *args, **kwargs: pytest.fail("unexpected Client construction")))
    credentials, secrets = telebox.TeleBoxService._worker_credentials("one")
    assert credentials == {"api_id": 12345, "api_hash": "a" * 32, "proxy": {
        "ip": "127.0.0.1", "port": 1080, "socksType": 5,
        "username": None, "password": None,
    }}
    assert secrets == ["a" * 32]


@pytest.mark.asyncio
async def test_purge_deleted_account_removes_only_its_telebox_data(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service._marker("deleted", True)
    service._marker("live", True)
    (service.directory("deleted") / "config.json").write_text('{"session":"private"}')
    (service.directory("live") / "config.json").write_text('{"session":"keep"}')
    service.logs["deleted"] = deque([{"message": "old"}])
    service.secrets["deleted"] = ["sensitive"]
    stop = AsyncMock()
    monkeypatch.setattr(service, "_terminate_worker", stop)

    assert await service.purge_account_data("deleted") is True
    stop.assert_awaited_once_with("deleted")
    assert not service.directory("deleted").exists()
    assert (service.directory("live") / "config.json").is_file()
    assert "deleted" not in service.logs and "deleted" not in service.secrets
    assert "deleted" not in service.locks
    assert await service.purge_account_data("deleted") is False


@pytest.mark.asyncio
async def test_purge_preserves_recreated_same_name_account(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service._marker("recreated", True)
    stop = AsyncMock()
    monkeypatch.setattr(service, "_terminate_worker", stop)
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        account_exists=lambda name: name == "recreated"))

    assert await service.purge_account_data("recreated") is False
    assert service.directory("recreated").is_dir()
    stop.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_purge_accepts_missing_marker_but_rejects_mismatch(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    monkeypatch.setattr(service, "_terminate_worker", AsyncMock())
    missing = service.directory("missing")
    missing.mkdir()
    (missing / "config.json").write_text("partial")
    assert await service.purge_account_data("missing") is True

    service._marker("one", True)
    marker = service.directory("one") / "panel-state.json"
    marker.write_text('{"account":"other","enabled":true}')
    with pytest.raises(ValueError, match="标记与目录不匹配"):
        await service.purge_account_data("one")
    assert service.directory("one").exists()


@pytest.mark.asyncio
async def test_exact_purge_refuses_linked_directory_or_marker(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service._marker("one", True)
    directory = service.directory("one")
    monkeypatch.setattr(service, "_terminate_worker", AsyncMock())
    monkeypatch.setattr(service, "_is_link", lambda path: path == directory)
    with pytest.raises(ValueError, match="不是普通目录"):
        await service.purge_account_data("one")
    assert directory.exists()
    monkeypatch.setattr(service, "_is_link", lambda path: path == directory / "panel-state.json")
    with pytest.raises(ValueError, match="标记不能是链接"):
        await service.purge_account_data("one")
    assert directory.exists()


@pytest.mark.asyncio
async def test_reconcile_removes_only_marked_orphans(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    for name in ("live", "newly-added", "orphan", "broken", "unknown", " spaced "):
        service._marker(name, True)
    (service.directory("broken") / "panel-state.json").write_text("invalid JSON")
    (service.directory("unknown") / "panel-state.json").unlink()
    monkeypatch.setattr(service, "_terminate_worker", AsyncMock())
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        account_exists=lambda name: name == "newly-added"))

    assert await service.reconcile_orphan_data({"live"}) == ["orphan"]
    for name in ("live", "newly-added", "broken", "unknown", " spaced "):
        assert service.directory(name).exists()
    assert not service.directory("orphan").exists()


@pytest.mark.asyncio
async def test_reconcile_rejects_incomplete_inventory(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service._marker("orphan", True)
    with pytest.raises(ValueError, match="完整账户清单"):
        await service.reconcile_orphan_data([])
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        account_exists=lambda name: (_ for _ in ()).throw(OSError("store unavailable"))))
    with pytest.raises(OSError, match="store unavailable"):
        await service.reconcile_orphan_data(set())
    assert service.directory("orphan").exists()


def test_deleted_account_releases_worker_and_secret_references(tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service.workers["removed"] = {"process": object()}
    service.locks["removed"] = object()
    service.logs["removed"] = deque([{"message": "old"}])
    service.secrets["removed"] = ["sensitive"]
    service.forget_account("removed")
    assert "removed" not in service.workers
    assert "removed" not in service.locks
    assert "removed" not in service.logs
    assert "removed" not in service.secrets


@pytest.mark.parametrize("worker_status", ["running", "failed", "stopped"])
def test_enabled_logs_remain_available_independent_of_worker_status(monkeypatch, tmp_path, worker_status):
    service = telebox.TeleBoxService(root=tmp_path)
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name.strip(), account_exists=lambda name: name == "one"))
    service.workers["one"] = {"status": worker_status}
    service._marker("one", True)
    service._log("one", "diagnostic output")

    assert service.log_items(" one ")["items"] == list(service.logs["one"])


@pytest.mark.asyncio
async def test_disabled_logs_are_hidden_without_deleting_retained_history(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name, account_exists=lambda name: name == "one"))
    service._log("one", "retained output")
    retained = list(service.logs["one"])
    assert service.log_items("one") == {"items": []}

    service._marker("one", True)
    assert service.log_items("one") == {"items": retained}
    await service.stop("one")
    assert service.log_items("one") == {"items": []}
    assert list(service.logs["one"]) == retained

    service._marker("one", True)
    assert service.log_items("one") == {"items": retained}
    with pytest.raises(ValueError, match="账号不存在"):
        service.log_items("unknown")


def test_overview_still_includes_disabled_telebox_accounts(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name,
        account_exists=lambda name: name in {"one", "two"},
        list_accounts=lambda: [{"name": "one"}, {"name": "two"}],
    ))
    service._marker("one", True)
    assert [(account["account"], account["enabled"]) for account in service.overview()["accounts"]] == [
        ("one", True), ("two", False),
    ]


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


def test_telebox_marker_write_never_reuses_predictable_temporary_file(tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    service._marker("one", True)
    fixed_temp = service.directory("one") / "panel-state.tmp"
    fixed_temp.write_text("do-not-touch")
    service._marker("one", False)
    assert fixed_temp.read_text() == "do-not-touch"
    assert json.loads((service.directory("one") / "panel-state.json").read_text()) == {
        "account": "one", "enabled": False,
    }


def test_prepare_refuses_linked_account_directory(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    directory = service.directory("one")
    monkeypatch.setattr(service, "_is_link", lambda path: path == directory)
    with pytest.raises(ValueError, match="不能是链接"):
        service._prepare("one")
    assert not directory.exists()


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
async def test_stdout_drains_after_bad_lines_and_bounds_authorization_tasks(monkeypatch, tmp_path):
    service = telebox.TeleBoxService(root=tmp_path)
    stream = SimpleNamespace(readline=AsyncMock(side_effect=[
        ValueError("Separator is not found, and chunk exceed the limit"),
        b"[]\n",
        b'{"event":"login_token","token":"one"}\n',
        b'{"event":"login_token","token":"two"}\n',
        b'{"event":"state","status":"running"}\n',
        b"",
    ]))
    waiting = asyncio.Event()
    accepted = []

    async def accept(account, worker, token):
        accepted.append(token)
        await waiting.wait()

    monkeypatch.setattr(service, "_accept", accept)
    worker = {"process": SimpleNamespace(stdout=stream), "tasks": set(),
              "pending": {}, "status": "starting"}
    await service._stdout("one", worker)
    await asyncio.sleep(0)
    assert worker["status"] == "running"
    assert accepted == ["one"]
    assert len(worker["tasks"]) == 1
    assert any("单行过长" in entry["message"] for entry in service.logs["one"])
    assert any("非对象数据" in entry["message"] for entry in service.logs["one"])
    waiting.set()
    await asyncio.gather(*worker["tasks"])


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
