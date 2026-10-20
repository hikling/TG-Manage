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
        account_exists=Mock(return_value=True),
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
    monkeypatch.setattr(report, "account_route_status", Mock(return_value={"route_mode": "direct", "route_status": "healthy"}))
    return config, service, send, persist


@pytest.mark.asyncio
async def test_daily_report_projects_saved_routes_without_node_probes(report_env, monkeypatch):
    _, service, send, persist = report_env
    service.list_accounts.return_value = [{"name": name} for name in ["direct", "good", "bad", "changed"]]
    route_status = Mock(side_effect=[
        {"route_mode": "direct", "route_status": "healthy", "exit_ip": "198.51.100.1"},
        {"route_mode": "primary", "route_status": "healthy", "exit_ip": "198.51.100.2"},
        {"route_mode": "fallback", "route_status": "error"},
        {"route_mode": "setup_required", "route_status": "pending"},
    ])
    monkeypatch.setattr(report, "account_route_status", route_status)
    result = await report.AccountStatusReportService().run()
    assert result["ok"] == 4 and result["fail"] == 0
    assert route_status.call_args_list == [call(name) for name in ["direct", "good", "bad", "changed"]]
    rows = send.await_args.kwargs["text"].splitlines()
    assert "🟢 direct — 账户正常 · 直出 · 198.51.100.1" in rows
    assert "🟢 good — 账户正常 · 主订阅 · 198.51.100.2" in rows
    assert "🔴 bad — 账户正常 · 兜底订阅 · IP 未知" in rows
    assert "🔴 changed — 账户正常 · 待配置订阅 · IP 未知" in rows
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_combined_midnight_report_shows_route_and_new_official_messages(report_env):
    _, _, send, _ = report_env
    rows = [
        {"account_name": "quiet", "ok": True, "route_mode": "primary", "route_status": "healthy", "exit_ip": "198.51.100.1"},
        {"account_name": "notice", "ok": True, "route_mode": "primary", "route_status": "healthy", "exit_ip": "198.51.100.2"},
        {"account_name": "proxy-bad", "ok": True, "route_mode": "fallback", "route_status": "error"},
        {"account_name": "read-bad", "ok": True, "route_mode": "direct", "route_status": "healthy"},
    ]
    sent = await report._send_report(rows, {
        "quiet": "empty", "notice": "messages", "proxy-bad": "empty", "read-bad": "failed",
    })
    assert sent == 1
    text = send.await_args.kwargs["text"]
    assert "总计 4 · 正常 1 · 异常 3" in text
    assert "🟢 quiet — 账户正常 · 主订阅 · 无官方新消息" in text
    assert "🔴 notice — 账户正常 · 主订阅 · 有官方新消息" in text
    assert "🔴 proxy-bad — 账户正常 · 兜底订阅 · 无官方新消息" in text
    assert "🔴 read-bad — 账户正常 · 直出 · 官方消息检测异常" in text
    assert "198.51.100.1" not in text and "198.51.100.2" not in text
    assert text.count("🟢") == 1 and text.count("🔴") == 3


@pytest.mark.asyncio
async def test_daily_route_projection_runs_even_after_account_failure(report_env, monkeypatch):
    _, service, _, _ = report_env
    service.check_account_status.side_effect = RuntimeError("account failed")
    route_status = Mock(return_value={"route_mode": "primary", "route_status": "healthy"})
    monkeypatch.setattr(report, "account_route_status", route_status)
    assert (await report.AccountStatusReportService().run())["fail"] == 1
    route_status.assert_called_once_with("alpha")


@pytest.mark.asyncio
async def test_midnight_retry_recovers_without_switching_node(report_env, monkeypatch):
    _, service, _, _ = report_env
    service.check_account_status.side_effect = [
        {"ok": False, "status": "checking", "code": "TIMEOUT"},
        {"ok": True, "status": "connected"},
    ]
    route_service = SimpleNamespace(switch_account_to_alternate_node=AsyncMock())
    monkeypatch.setattr(report, "get_route_service", lambda: route_service)

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert result["ok"] == 1
    assert service.check_account_status.await_count == 2
    route_service.switch_account_to_alternate_node.assert_not_awaited()
    assert "复检恢复" in report.report_chunks(result["rows"])[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("final_ok", [True, False])
async def test_midnight_switches_once_then_reports_final_status(
    report_env, monkeypatch, final_ok,
):
    _, service, _, _ = report_env
    service.check_account_status.side_effect = [
        {"ok": False, "status": "checking", "code": "CONNECTION_ERROR"},
        {"ok": False, "status": "checking", "code": "CONNECTION_ERROR"},
        {"ok": final_ok, "status": "connected" if final_ok else "checking",
         "code": "OK" if final_ok else "CONNECTION_ERROR"},
    ]
    switch = AsyncMock(return_value=True)
    monkeypatch.setattr(
        report, "get_route_service",
        lambda: SimpleNamespace(switch_account_to_alternate_node=switch),
    )
    monkeypatch.setattr(
        report, "account_route_status",
        Mock(return_value={"route_mode": "fallback", "route_status": "healthy"}),
    )

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert service.check_account_status.await_count == 3
    switch.assert_awaited_once_with("alpha")
    assert result["ok"] == int(final_ok)
    text = report.report_chunks(result["rows"], {"alpha": "empty"})[0]
    if final_ok:
        assert "🟢 alpha — 账户正常 · 兜底订阅 · 无官方新消息 · 换线后恢复" in text
    else:
        assert "🔴 alpha — 账户异常（连接失败） · 兜底订阅 · 无官方新消息 · 换线复检后仍异常" in text


@pytest.mark.asyncio
async def test_midnight_without_alternate_reports_failure_after_two_checks(
    report_env, monkeypatch,
):
    _, service, _, _ = report_env
    service.check_account_status.return_value = {
        "ok": False, "status": "checking", "code": "TIMEOUT",
    }
    switch = AsyncMock(return_value=False)
    monkeypatch.setattr(
        report, "get_route_service",
        lambda: SimpleNamespace(switch_account_to_alternate_node=switch),
    )

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert result["fail"] == 1
    assert service.check_account_status.await_count == 2
    switch.assert_awaited_once_with("alpha")
    assert "暂无可用备用节点" in report.report_chunks(result["rows"])[0]


@pytest.mark.asyncio
async def test_midnight_removed_account_is_rechecked_without_creating_route(
    report_env, monkeypatch,
):
    _, service, _, _ = report_env
    service.check_account_status.return_value = {
        "ok": False, "status": "not_found", "code": "ACCOUNT_NOT_FOUND",
    }
    route_service = Mock()
    monkeypatch.setattr(report, "get_route_service", route_service)

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert service.check_account_status.await_count == 2
    route_service.assert_not_called()
    assert "账户已移除" in report.report_chunks(result["rows"])[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("code,status", [
    ("ACCOUNT_SESSION_INVALID", "invalid"),
    ("API_CREDENTIALS_MISSING", "error"),
    ("STORAGE_PERMISSION_DENIED", "checking"),
    ("FLOOD_WAIT", "checking"),
])
async def test_midnight_does_not_switch_route_for_non_network_failures(
    report_env, monkeypatch, code, status,
):
    _, service, _, _ = report_env
    service.check_account_status.return_value = {
        "ok": False, "status": status, "code": code,
        "needs_relogin": status == "invalid",
    }
    switch = AsyncMock()
    monkeypatch.setattr(
        report, "get_route_service",
        lambda: SimpleNamespace(switch_account_to_alternate_node=switch),
    )
    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )
    assert result["fail"] == 1
    assert service.check_account_status.await_count == 2
    switch.assert_not_awaited()
    assert "换线无法修复" in report.report_chunks(result["rows"])[0]


@pytest.mark.asyncio
async def test_report_probes_multiple_accounts_with_bounded_concurrency(report_env, monkeypatch):
    _, service, _, _ = report_env
    service.list_accounts.return_value = [{"name": str(i)} for i in range(12)]
    monkeypatch.setattr(report, "REPORT_CONCURRENCY", 3)
    active = 0
    peak = 0

    async def probe(*_args, **_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return {"ok": True, "status": "connected"}

    service.check_account_status.side_effect = probe
    result = await report.AccountStatusReportService().run(send_report=False)
    assert result["checked"] == 12
    assert peak == 3


@pytest.mark.asyncio
async def test_midnight_account_removed_after_retry_does_not_switch_route(
    report_env, monkeypatch,
):
    _, service, _, _ = report_env
    service.check_account_status.return_value = {
        "ok": False, "status": "checking", "code": "TIMEOUT",
    }
    service.account_exists.return_value = False
    route_service = Mock()
    monkeypatch.setattr(report, "get_route_service", route_service)

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert service.check_account_status.await_count == 2
    route_service.assert_not_called()
    assert result["rows"][0]["status"] == "not_found"
    assert "复检时账户已移除" in report.report_chunks(result["rows"])[0]


@pytest.mark.asyncio
async def test_midnight_switch_error_is_reported_without_stopping_scan(
    report_env, monkeypatch,
):
    _, service, _, _ = report_env
    service.check_account_status.return_value = {
        "ok": False, "status": "checking", "code": "CONNECTION_ERROR",
    }
    switch = AsyncMock(side_effect=RuntimeError("private route details"))
    monkeypatch.setattr(
        report, "get_route_service",
        lambda: SimpleNamespace(switch_account_to_alternate_node=switch),
    )

    result = await report.AccountStatusReportService().run(
        send_report=False, midnight_recovery=True,
    )

    assert result["fail"] == 1
    assert service.check_account_status.await_count == 2
    assert "备用节点切换失败" in report.report_chunks(result["rows"])[0]


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
    service.list_accounts.assert_called_once_with(force_refresh=True, strict=True)
    assert service.check_account_status.await_args_list == [
        call(name, timeout_seconds=8.0, no_updates=True)
        for name in ["alpha", "expired", "slow", "broken", "omega"]
    ]
    message = send.await_args.kwargs
    assert message["chat_id"] == "123"
    assert message["message_thread_id"] == 7
    assert "parse_mode" not in message
    assert "总计 5 · 正常 2 · 异常 3" in message["text"]
    assert "🟢 @telegram_alpha — 账户正常" in message["text"]
    assert "🟢 omega — 账户正常" in message["text"]
    assert "🔴 expired — 账户异常（会话失效，请重新登录）" in message["text"]
    assert "🔴 slow — 账户异常（检测超时）" in message["text"]
    assert "🔴 broken — 账户异常（检测失败）" in message["text"]
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
        assert rows.count(f"🟢 {name} — 账户正常") == 1
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
async def test_explicit_midnight_report_sends_with_legacy_quiet_settings(report_env):
    config, _, send, _ = report_env
    config.update({
        "telegram_bot_quiet_hours_enabled": True,
        "telegram_bot_quiet_hours_start": "23:00",
        "telegram_bot_quiet_hours_end": "07:00",
    })
    await report.AccountStatusReportService().run()
    send.assert_awaited_once()


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
    assert "🔴 slow — 账户异常（检测超时）" in send.await_args.kwargs["text"]
    assert "🟢 ready — 账户正常" in send.await_args.kwargs["text"]
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
async def test_removed_account_failure_does_not_restore_metadata(report_env):
    _, service, _, persist = report_env
    service.check_account_status.side_effect = RuntimeError("transport unavailable")
    service.account_exists.return_value = False

    result = await report.AccountStatusReportService().run(send_report=False)

    assert result["fail"] == 1
    persist.assert_not_called()


@pytest.mark.asyncio
async def test_account_inventory_error_never_becomes_empty_normal_report(report_env):
    _, service, send, _ = report_env
    service.list_accounts.side_effect = OSError("session volume unavailable")

    with pytest.raises(OSError):
        await report.AccountStatusReportService().run()

    send.assert_not_awaited()


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
    lines = ["header", "🟢 @" + "🙂" * 5000 + " — 正常", "🔴 last — 账户异常"]
    chunks = report._message_chunks(lines)
    assert all(len(text.encode("utf-16-le")) // 2 <= 3500 for text in chunks)
    # Row-separator newlines may be consumed at message boundaries.
    assert "".join(chunks).replace("\n", "") == "".join(lines)


def test_shared_report_service_is_reused(monkeypatch):
    monkeypatch.setattr(report, "_service", None)
    assert report.get_account_status_report_service() is report.get_account_status_report_service()
