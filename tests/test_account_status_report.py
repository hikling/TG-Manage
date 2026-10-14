"""Midnight scans stay complete, bounded and safe to deliver."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from backend.services import account_status_report as report
from backend.services.account_check_gate import account_check_gate


@pytest.fixture
def report_env(monkeypatch):
    config = {
        "telegram_bot_notify_enabled": True,
        "telegram_bot_token": "test-token",
        "telegram_bot_chat_id": "123",
        "telegram_bot_message_thread_id": "7",
    }
    service = SimpleNamespace(
        list_accounts=Mock(return_value=[{"name": "alpha"}]),
        check_account_status=AsyncMock(return_value={"ok": True, "status": "connected"}),
    )
    config_service = SimpleNamespace(get_global_settings=lambda: dict(config))
    send = AsyncMock()
    persist = Mock()
    monkeypatch.setattr(report, "get_config_service", lambda: config_service)
    monkeypatch.setattr(report, "get_telegram_service", lambda: service)
    monkeypatch.setattr(report, "send_telegram_bot_message", send)
    monkeypatch.setattr(report, "set_account_status", persist)
    monkeypatch.setattr(report, "INTER_DELAY_SECONDS", 0)
    monkeypatch.setattr(report, "check_account_proxy", AsyncMock(return_value={"proxy_status": "unconfigured"}))
    return config, service, send, persist


@pytest.mark.asyncio
async def test_daily_proxy_health_is_reported_independently_for_every_account(report_env, monkeypatch):
    _, service, send, persist = report_env
    service.list_accounts.return_value = [{"name": name} for name in ["direct", "good", "bad", "changed"]]
    check_proxy = AsyncMock(side_effect=[
        {"proxy_status": "unconfigured"}, {"proxy_status": "healthy"},
        {"proxy_status": "error", "proxy_status_code": "PROXY_AUTH_FAILED"},
        {"proxy_status": "pending"},
    ])
    monkeypatch.setattr(report, "check_account_proxy", check_proxy)
    result = await report.AccountStatusReportService().run()
    assert result["ok"] == 4 and result["fail"] == 0
    assert check_proxy.await_args_list == [
        call(name, timeout_seconds=8.0) for name in ["direct", "good", "bad", "changed"]
    ]
    rows = send.await_args.kwargs["text"].splitlines()
    assert "🟢 direct — 正常" in rows
    assert "🟢 good — 正常 · SOCKS5 🟢 正常" in rows
    assert "🟢 bad — 正常 · SOCKS5 🔴 异常" in rows
    assert "🟢 changed — 正常 · SOCKS5 ⚪ 待检测" in rows
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_daily_proxy_check_runs_even_after_account_failure(report_env, monkeypatch):
    _, service, _, _ = report_env
    service.check_account_status.side_effect = RuntimeError("account failed")
    check_proxy = AsyncMock(return_value={"proxy_status": "healthy"})
    monkeypatch.setattr(report, "check_account_proxy", check_proxy)
    assert (await report.AccountStatusReportService().run())["fail"] == 1
    check_proxy.assert_awaited_once_with("alpha", timeout_seconds=8.0)


@pytest.mark.asyncio
async def test_mixed_fresh_results_icons_and_persisted_failures(report_env, caplog):
    _, service, send, persist = report_env
    service.list_accounts.return_value = [
        {"name": name, "status": "connected"}
        for name in ["alpha", "expired", "slow", "broken", "omega"]
    ]
    service.check_account_status.side_effect = [
        {"ok": True, "status": "connected", "username": "telegram_alpha"},
        {"ok": False, "status": "invalid", "needs_relogin": True},
        {"ok": False, "status": "checking", "code": "TIMEOUT"},
        RuntimeError("https://api.telegram.org/botSECRET/hidden-error"),
        {"ok": True, "status": "connected"},
    ]

    result = await report.AccountStatusReportService().run()

    assert result == {"checked": 5, "ok": 2, "fail": 3, "messages_sent": 1}
    service.list_accounts.assert_called_once_with(force_refresh=True)
    assert service.check_account_status.await_args_list == [
        call(name, timeout_seconds=8.0, no_updates=True)
        for name in ["alpha", "expired", "slow", "broken", "omega"]
    ]
    message = send.await_args.kwargs
    assert message["chat_id"] == "123"
    assert message["message_thread_id"] == 7
    assert "parse_mode" not in message
    assert "总计 5 · 正常 2 · 异常 3" in message["text"]
    assert "🟢 @telegram_alpha — 正常" in message["text"]
    assert "🟢 omega — 正常" in message["text"]
    assert "🔴 expired — 异常（会话失效，请重新登录）" in message["text"]
    assert "🔴 slow — 异常（检测超时）" in message["text"]
    assert "🔴 broken — 异常（检测失败）" in message["text"]
    assert "SECRET" not in caplog.text + message["text"]
    # Healthy and invalid sessions are persisted by the shared probe itself.
    assert [(c.args[0], c.kwargs["status"]) for c in persist.call_args_list] == [
        ("slow", "checking"), ("broken", "error"),
    ]
    assert not account_check_gate._in_flight


@pytest.mark.asyncio
async def test_all_225_accounts_checked_once_and_chunked_without_loss(report_env):
    _, service, send, _ = report_env
    names = [f"account-{i:03d}-" + "🙂" * 30 for i in range(225)]
    service.list_accounts.return_value = [{"name": name} for name in names]
    result = await report.AccountStatusReportService().run()

    assert result["checked"] == result["ok"] == 225
    assert result["fail"] == 0
    assert service.check_account_status.await_count == 225
    assert [c.args[0] for c in service.check_account_status.await_args_list] == names
    messages = [c.kwargs["text"] for c in send.await_args_list]
    assert len(messages) > 1
    assert result["messages_sent"] == len(messages)
    assert all(len(text.encode("utf-16-le")) // 2 <= 3500 for text in messages)
    rows = "\n".join(messages)
    assert "总计 225 · 正常 225 · 异常 0" in rows
    assert rows.count("🟢") == 225
    for name in names:
        assert rows.count(f"🟢 {name} — 正常") == 1
    assert not account_check_gate._in_flight


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"telegram_bot_notify_enabled": False},
        {"telegram_bot_token": " "},
        {"telegram_bot_chat_id": ""},
    ],
)
async def test_missing_or_disabled_bot_still_checks_accounts(report_env, overrides):
    config, service, send, _ = report_env
    config.update(overrides)
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 1
    assert result["messages_sent"] == 0
    service.check_account_status.assert_awaited_once()
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_midnight_report_bypasses_quiet_hours(report_env, monkeypatch):
    config, _, send, _ = report_env
    config.update({
        "telegram_bot_quiet_hours_enabled": True,
        "telegram_bot_quiet_hours_start": "23:00",
        "telegram_bot_quiet_hours_end": "07:00",
    })
    quiet_check = Mock(return_value=True)
    monkeypatch.setattr("backend.services.push_notifications.is_in_quiet_hours", quiet_check)
    await report.AccountStatusReportService().run()
    send.assert_awaited_once()
    quiet_check.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"telegram_bot_notify_enabled": False},
        {"telegram_bot_token": "new-token"},
        {"telegram_bot_chat_id": "456"},
        {"telegram_bot_message_thread_id": 8},
    ],
)
async def test_target_rechecked_before_each_chunk(report_env, changes):
    config, service, send, _ = report_env
    service.list_accounts.return_value = [{"name": f"{i:03d}-" + "x" * 200} for i in range(30)]

    async def reconfigure(**_kwargs):
        config.update(changes)

    send.side_effect = reconfigure
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 30
    assert result["messages_sent"] == 1
    send.assert_awaited_once()
    assert send.await_args.kwargs["chat_id"] == "123"


@pytest.mark.asyncio
async def test_target_changed_during_scan_uses_current_settings(report_env):
    config, service, send, _ = report_env

    async def probe(*_args, **_kwargs):
        config["telegram_bot_chat_id"] = "456"
        return {"ok": True, "status": "connected"}

    service.check_account_status.side_effect = probe
    await report.AccountStatusReportService().run()
    assert send.await_args.kwargs["chat_id"] == "456"


@pytest.mark.asyncio
@pytest.mark.parametrize("busy_kind", ["in_flight", "cooldown"])
async def test_busy_accounts_deferred_after_ready_accounts(report_env, monkeypatch, busy_kind):
    _, service, _, persist = report_env
    service.list_accounts.return_value = [{"name": "busy"}, {"name": "ready"}]
    external = account_check_gate.reserve(["busy"])
    if busy_kind == "cooldown":
        external.finish("busy", success=True)
    now = [0.0]
    monkeypatch.setattr(report, "time", SimpleNamespace(monotonic=lambda: now[0]))
    original_sleep = asyncio.sleep

    async def sleep(seconds):
        if seconds:
            now[0] += seconds
            external.release()
            account_check_gate._deadlines.pop("busy", None)
        await original_sleep(0)

    monkeypatch.setattr(report.asyncio, "sleep", sleep)
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == result["ok"] == 2
    assert [c.args[0] for c in service.check_account_status.await_args_list] == ["ready", "busy"]
    persist.assert_not_called()
    assert not account_check_gate._in_flight


@pytest.mark.asyncio
async def test_cancellation_releases_current_reservation_and_run_lock(report_env):
    _, service, send, persist = report_env
    entered = asyncio.Event()

    async def wait(*_args, **_kwargs):
        entered.set()
        await asyncio.Future()

    service.check_account_status.side_effect = wait
    runner = report.AccountStatusReportService()
    task = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert "alpha" in account_check_gate._in_flight
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not runner._running_lock.locked()
        assert not account_check_gate._in_flight
        assert not account_check_gate._deadlines
        persist.assert_not_called()
        send.assert_not_awaited()
        reservation = account_check_gate.reserve(["alpha"])
        reservation.release()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_while_deferred_keeps_external_reservation(report_env, monkeypatch):
    _, service, send, _ = report_env
    external = account_check_gate.reserve(["alpha"])
    waiting = asyncio.Event()

    async def sleep(_seconds):
        waiting.set()
        await asyncio.Future()

    monkeypatch.setattr(report.asyncio, "sleep", sleep)
    runner = report.AccountStatusReportService()
    task = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "alpha" in account_check_gate._in_flight
        assert not runner._running_lock.locked()
        service.check_account_status.assert_not_awaited()
        send.assert_not_awaited()
    finally:
        external.release()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_concurrent_daily_run_skips_instead_of_double_probing(report_env):
    _, service, send, _ = report_env
    entered, finish = asyncio.Event(), asyncio.Event()

    async def wait(*_args, **_kwargs):
        entered.set()
        await finish.wait()
        return {"ok": True, "status": "connected"}

    service.check_account_status.side_effect = wait
    runner = report.AccountStatusReportService()
    first = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert await runner.run() == {"skipped": True, "checked": 0, "messages_sent": 0}
        service.check_account_status.assert_awaited_once()
        finish.set()
        assert (await first)["checked"] == 1
        send.assert_awaited_once()
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_whole_probe_timeout_is_persisted_and_continues(report_env, monkeypatch):
    _, service, send, persist = report_env
    service.list_accounts.return_value = [{"name": "slow"}, {"name": "ready"}]
    cancelled = asyncio.Event()

    async def probe(name, **_kwargs):
        if name == "slow":
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        return {"ok": True, "status": "connected"}

    monkeypatch.setattr(report, "PROBE_TIMEOUT_SECONDS", 0.01)
    service.check_account_status.side_effect = probe
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 2 and result["fail"] == 1
    assert cancelled.is_set()
    assert persist.call_args.kwargs["code"] == "TIMEOUT"
    assert "🔴 slow — 异常（检测超时）" in send.await_args.kwargs["text"]
    assert "🟢 ready — 正常" in send.await_args.kwargs["text"]
    assert not account_check_gate._in_flight


@pytest.mark.asyncio
async def test_delivery_error_is_sanitized_and_keeps_saved_failure(report_env, caplog):
    _, service, send, persist = report_env
    service.check_account_status.return_value = {"ok": False, "status": "checking", "code": "CONNECTION_ERROR"}
    send.side_effect = RuntimeError("https://api.telegram.org/botSECRET/sendMessage")
    result = await report.AccountStatusReportService().run()
    assert result["fail"] == 1 and result["messages_sent"] == 0
    assert persist.call_args.kwargs["code"] == "CONNECTION_ERROR"
    assert "SECRET" not in caplog.text


@pytest.mark.asyncio
async def test_bad_payload_and_save_error_do_not_stop_scan(report_env, caplog):
    _, service, send, persist = report_env
    service.list_accounts.return_value = [{"name": "bad"}, {"name": "good"}, {"name": "gone"}]
    service.check_account_status.side_effect = [
        None,
        {"ok": True},
        {"ok": False, "status": "not_found", "code": "ACCOUNT_NOT_FOUND", "needs_relogin": True},
    ]
    persist.side_effect = OSError("SECRET file error")
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 3 and result["fail"] == 2
    persist.assert_called_once()
    assert "SECRET" not in caplog.text
    assert "账户已移除" in send.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_empty_inventory_and_duplicate_names(report_env):
    _, service, send, _ = report_env
    service.list_accounts.return_value = []
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 0
    assert "总计 0 · 正常 0 · 异常 0" in send.await_args.kwargs["text"]
    assert "暂无账户" in send.await_args.kwargs["text"]
    service.list_accounts.return_value = [{"name": ""}, {"name": "alpha"}, {"name": " alpha "}]
    result = await report.AccountStatusReportService().run()
    assert result["checked"] == 1
    service.check_account_status.assert_awaited_once()


def test_oversized_unicode_row_is_split_without_losing_characters():
    lines = ["header", "🟢 @" + "🙂" * 5000 + " — 正常", "🔴 last — 异常"]
    chunks = report._message_chunks(lines)
    assert all(len(text.encode("utf-16-le")) // 2 <= 3500 for text in chunks)
    # Row-separator newlines may be consumed at message boundaries.
    assert "".join(chunks).replace("\n", "") == "".join(lines)


def test_shared_report_service_is_reused(monkeypatch):
    monkeypatch.setattr(report, "_service", None)
    assert report.get_account_status_report_service() is report.get_account_status_report_service()
