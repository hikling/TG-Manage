"""Private Bot: on-demand 777000 codes and local account labels only."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from backend.services import official_code_bot as bot


@pytest.fixture(autouse=True)
def _fresh_command_gate(monkeypatch):
    monkeypatch.setattr(bot, "_command_gate", bot._CommandGate())


def _stamp(minutes_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _update(target: int, *, sender: int | None = None, kind: str = "private", text: str = "/code account", minutes_ago: int = 0):
    return {"message": {
        "chat": {"id": target, "type": kind},
        "from": {"id": sender if sender is not None else target},
        "date": int((datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).timestamp()),
        "text": text,
    }}


def test_code_parser_and_expiry():
    assert bot.parse_code("Login code: 12345. Never share it") == "12345"
    assert bot.parse_code("12345") is None
    assert bot.latest_code([{"id": 2, "date": _stamp(6), "text": "Code: 12345"}]) is None
    assert bot.latest_code([{"id": 3, "date": _stamp(1), "text": "验证码 654321"}]) == "654321"
    assert bot.private_target({"telegram_bot_chat_id": "-100123"}) is None
    assert bot.private_target({"telegram_bot_chat_id": "12345"}) == 12345
    assert bot.private_target({"telegram_bot_chat_id": str(1 << 63)}) is None


def test_only_exact_private_sender_is_authorized():
    assert bot.authorized(_update(12345), 12345)
    assert not bot.authorized(_update(12345, sender=9), 12345)
    assert not bot.authorized(_update(12345, kind="group"), 12345)
    assert not bot.authorized(_update(9), 12345)


@pytest.mark.asyncio
async def test_bot_api_error_never_exposes_token():
    token = "12345:very-secret-token"

    class Client:
        async def post(self, url, json):
            raise httpx.ConnectError(f"failed to connect to {url}")

    with pytest.raises(bot.CodeBotError) as error:
        await bot._bot_call(Client(), token, "getUpdates", {})
    assert token not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 409, 500])
async def test_bot_api_response_is_closed_after_parse_or_error(status_code):
    response = SimpleNamespace(status_code=status_code, json=lambda: {"ok": True, "result": []}, aclose=AsyncMock())

    class Client:
        async def post(self, url, json):
            return response

    if status_code == 200:
        assert await bot._bot_call(Client(), "token", "getUpdates", {}) == []
    else:
        with pytest.raises(bot.CodeBotError):
            await bot._bot_call(Client(), "token", "getUpdates", {})
    response.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_or_changed_configuration_never_sends(monkeypatch):
    monkeypatch.setattr(bot, "enabled_config", lambda: None)
    bot_call = AsyncMock()
    monkeypatch.setattr(bot, "_bot_call", bot_call)
    await bot._send(None, ("old-token", 12345), "Login code: 12345")
    bot_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_bot_never_reads_any_account_history(monkeypatch):
    monkeypatch.setattr(bot, "enabled_config", lambda: ("token", 12345))
    monkeypatch.setattr("backend.scheduler.instance_lock.has_scheduler_lock", lambda: True)
    service = SimpleNamespace(list_accounts=Mock(), list_official_messages=AsyncMock())
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)

    async def fake_call(client, token, method, payload):
        return {"url": ""} if method == "getWebhookInfo" else []

    monkeypatch.setattr(bot, "_bot_call", fake_call)

    idle_ticks = 0

    async def stop_after_idle(_seconds):
        nonlocal idle_ticks
        idle_ticks += 1
        if idle_ticks >= 50:
            raise asyncio.CancelledError()

    monkeypatch.setattr(bot.asyncio, "sleep", stop_after_idle)
    with pytest.raises(asyncio.CancelledError):
        await bot.run_code_bot()
    assert idle_ticks == 50
    service.list_accounts.assert_not_called()
    service.list_official_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_update_is_silent_and_expired_command_gets_no_code(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    history = [{"id": 8, "date": _stamp(6), "text": "Login code: 12345", "outgoing": False}]
    service = SimpleNamespace(
        account_exists=lambda name: name == "account",
        list_accounts=Mock(),
        list_official_messages=AsyncMock(return_value=history),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)

    await bot._handle_update(None, config, _update(12345, sender=9))
    await bot._handle_update(None, config, _update(12345, kind="group", text="/me"))
    await bot._handle_update(None, config, _update(12345, minutes_ago=6))
    send.assert_not_awaited()
    service.list_accounts.assert_not_called()
    service.list_official_messages.assert_not_awaited()

    await bot._handle_update(None, config, _update(12345))
    send.assert_awaited_once_with(None, config, "暂无有效验证码")
    service.list_official_messages.assert_awaited_once_with("account", limit=20)


@pytest.mark.asyncio
async def test_authorized_code_reads_only_named_account(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(
        account_exists=lambda name: name == "second",
        list_official_messages=AsyncMock(return_value=[{"date": _stamp(), "text": "Code: 56789", "outgoing": False}]),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)
    await bot._handle_update(None, config, _update(12345, text="/code second"))
    service.list_official_messages.assert_awaited_once_with("second", limit=20)
    send.assert_awaited_once_with(None, config, "second 的 Telegram 验证码：56789")


@pytest.mark.asyncio
async def test_me_reads_only_local_name_and_remark(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(
        list_accounts=Mock(return_value=[
            {"name": "zeta", "remark": "工作", "proxy": "secret-proxy", "session_file": "secret-session"},
            {"name": "alpha", "remark": "", "api_hash": "secret-hash"},
        ]),
        list_official_messages=AsyncMock(),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)

    await bot._handle_update(None, config, _update(12345, sender=9, text="/me"))
    send.assert_not_awaited()
    service.list_accounts.assert_not_called()

    await bot._handle_update(None, config, _update(12345, text="/me"))
    service.list_accounts.assert_called_once_with()
    service.list_official_messages.assert_not_awaited()
    message = send.await_args.args[2]
    assert message == "账号管理中的账号：\nalpha — 无备注\nzeta — 工作"
    assert "secret" not in message


def test_me_chunks_many_accounts_without_sensitive_fields():
    lines = bot._account_lines([{"name": f"account-{i:03d}", "remark": "r" * 80} for i in range(100)])
    chunks = bot._message_chunks(lines)
    assert len(chunks) > 1
    assert all(len(chunk) <= bot.MAX_BOT_MESSAGE_CHARS for chunk in chunks)
    assert sum(chunk.count("account-") for chunk in chunks) == 100


@pytest.mark.asyncio
async def test_me_and_code_share_success_cooldown_without_repeat_account_reads(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    clock = [100.0]
    monkeypatch.setattr(bot.time, "monotonic", lambda: clock[0])
    service = SimpleNamespace(
        list_accounts=Mock(return_value=[{"name": "account", "remark": "工作"}]),
        account_exists=Mock(return_value=True),
        list_official_messages=AsyncMock(return_value=[{"date": _stamp(), "text": "Code: 56789"}]),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)

    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 1
    await bot._handle_update(None, config, _update(12345, text="/code account"))
    await bot._handle_update(None, config, _update(12345, text="/code account"))
    assert service.account_exists.call_count == 0
    service.list_official_messages.assert_not_awaited()
    assert send.await_count == 2  # /me response and one cooldown notice
    assert "45 秒" in send.await_args.args[2]

    clock[0] += 45
    await bot._handle_update(None, config, _update(12345, text="/code account"))
    service.list_official_messages.assert_awaited_once_with("account", limit=20)
    assert "56789" in send.await_args.args[2]


@pytest.mark.asyncio
async def test_failed_or_skipped_delivery_does_not_start_command_cooldown(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(list_accounts=Mock(return_value=[]))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(side_effect=[False, True])
    monkeypatch.setattr(bot, "_send", send)
    await bot._handle_update(None, config, _update(12345, text="/me"))
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 2
    assert send.await_count == 2


@pytest.mark.asyncio
async def test_in_flight_duplicate_gets_one_notice_and_no_history_read(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    started = asyncio.Event()
    release = asyncio.Event()
    service = SimpleNamespace(
        account_exists=Mock(return_value=True),
        list_official_messages=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    messages: list[str] = []

    async def send(_client, _config, text):
        messages.append(text)
        if text == "暂无有效验证码":
            started.set()
            await release.wait()
        return True

    monkeypatch.setattr(bot, "_send", send)
    first = asyncio.create_task(bot._handle_update(None, config, _update(12345)))
    await started.wait()
    await bot._handle_update(None, config, _update(12345, text="/me"))
    await bot._handle_update(None, config, _update(12345, text="/code account"))
    assert service.list_official_messages.await_count == 1
    assert messages.count("操作过于频繁，请 45 秒后再发送 /me 或 /code") == 1
    release.set()
    await first
    # A notice already sent while the request was in flight is not repeated
    # during the cooldown started by its successful delivery.
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert messages.count("操作过于频繁，请 45 秒后再发送 /me 或 /code") == 1


@pytest.mark.asyncio
async def test_invalid_code_reply_is_throttled_but_never_reads_accounts(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(account_exists=Mock(), list_official_messages=AsyncMock())
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)
    for _ in range(10):
        await bot._handle_update(None, config, _update(12345, text="/code ../invalid"))
    assert send.await_count == 2  # invalid-name reply and one interval notice
    service.account_exists.assert_not_called()
    service.list_official_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_bare_code_command_is_treated_as_invalid_and_cooled_down(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(account_exists=Mock(), list_official_messages=AsyncMock())
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)
    await bot._handle_update(None, config, _update(12345, text="/code"))
    await bot._handle_update(None, config, _update(12345, text="/code"))
    assert send.await_args_list[0].args[2] == "账号名无效"
    assert "45 秒" in send.await_args_list[1].args[2]
    service.account_exists.assert_not_called()


@pytest.mark.asyncio
async def test_failed_bot_delivery_is_not_retried_or_cooled_down(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(list_accounts=Mock(return_value=[]))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(side_effect=[bot.CodeBotError("send failed"), True])
    monkeypatch.setattr(bot, "_send", send)
    with pytest.raises(bot.CodeBotError):
        await bot._handle_update(None, config, _update(12345, text="/me"))
    assert send.await_count == 1
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 2
    assert send.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 409])
@pytest.mark.parametrize("error_type", [httpx.ReadError, RuntimeError])
async def test_bot_api_close_failure_is_sanitized(status_code, error_type, caplog):
    secret = "https://api.telegram.org/bot12345:secret-token/sendMessage code 56789"
    response = SimpleNamespace(
        status_code=status_code,
        json=lambda: {"ok": True, "result": []},
        aclose=AsyncMock(side_effect=error_type(secret)),
    )
    client = SimpleNamespace(post=AsyncMock(return_value=response))
    if status_code == 200:
        assert await bot._bot_call(client, "12345:secret-token", "sendMessage", {}) == []
    else:
        with pytest.raises(bot.CodeBotError) as error:
            await bot._bot_call(client, "12345:secret-token", "sendMessage", {})
        assert "secret-token" not in str(error.value)
        assert "56789" not in str(error.value)
    assert "secret-token" not in caplog.text
    assert "56789" not in caplog.text
    assert error_type.__name__ in caplog.text
    response.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_config", [None, ("new-token", 67890)])
async def test_configuration_change_during_send_does_not_start_old_cooldown(monkeypatch, changed_config):
    config = ("token", 12345)
    active = [config]
    monkeypatch.setattr(bot, "enabled_config", lambda: active[0])
    service = SimpleNamespace(list_accounts=Mock(return_value=[]))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)

    async def change_during_send(_client, _token, _method, _payload):
        active[0] = changed_config
        return {"message_id": 1}

    monkeypatch.setattr(bot, "_bot_call", change_during_send)
    await bot._handle_update(None, config, _update(12345, text="/me"))
    active[0] = config
    call = AsyncMock(return_value={"message_id": 2})
    monkeypatch.setattr(bot, "_bot_call", call)
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 2
    assert call.await_args.args[3]["text"] == "账号管理中暂无账号"


@pytest.mark.asyncio
@pytest.mark.parametrize("changed_config", [None, ("new-token", 67890)])
async def test_configuration_change_during_history_read_suppresses_old_reply(monkeypatch, changed_config):
    config = ("token", 12345)
    active = [config]
    monkeypatch.setattr(bot, "enabled_config", lambda: active[0])

    async def history(_account, *, limit):
        active[0] = changed_config
        return [{"date": _stamp(), "text": "Code: 56789"}]

    service = SimpleNamespace(account_exists=Mock(return_value=True), list_official_messages=AsyncMock(side_effect=history))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    call = AsyncMock()
    monkeypatch.setattr(bot, "_bot_call", call)
    await bot._handle_update(None, config, _update(12345))
    call.assert_not_awaited()
    service.list_official_messages.assert_awaited_once_with("account", limit=20)


@pytest.mark.asyncio
async def test_disabling_bot_resets_cooldown_when_same_target_is_reenabled(monkeypatch):
    config = ("token", 12345)
    active = [config]
    monkeypatch.setattr(bot, "enabled_config", lambda: active[0])
    monkeypatch.setattr("backend.scheduler.instance_lock.has_scheduler_lock", lambda: True)
    service = SimpleNamespace(list_accounts=Mock(return_value=[]))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)
    await bot._handle_update(None, config, _update(12345, text="/me"))
    active[0] = None

    async def stop_disabled_loop(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(bot.asyncio, "sleep", stop_disabled_loop)
    with pytest.raises(asyncio.CancelledError):
        await bot.run_code_bot()
    active[0] = config
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 2
    assert send.await_args.args[2] == "账号管理中暂无账号"


@pytest.mark.asyncio
async def test_cancelled_cooldown_notice_can_be_delivered_by_next_repeat(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(list_accounts=Mock(return_value=[]))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(side_effect=[True, asyncio.CancelledError(), True])
    monkeypatch.setattr(bot, "_send", send)
    await bot._handle_update(None, config, _update(12345, text="/me"))
    with pytest.raises(asyncio.CancelledError):
        await bot._handle_update(None, config, _update(12345, text="/me"))
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert send.await_count == 3
    assert "秒后再发送" in send.await_args.args[2]
    service.list_accounts.assert_called_once_with()


@pytest.mark.asyncio
async def test_cancelled_history_read_releases_command_without_cooldown(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(
        account_exists=Mock(return_value=True),
        list_official_messages=AsyncMock(side_effect=[asyncio.CancelledError(), []]),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)
    with pytest.raises(asyncio.CancelledError):
        await bot._handle_update(None, config, _update(12345))
    send.assert_not_awaited()
    await bot._handle_update(None, config, _update(12345))
    assert service.list_official_messages.await_count == 2
    send.assert_awaited_once_with(None, config, "暂无有效验证码")


@pytest.mark.asyncio
@pytest.mark.parametrize("command, reply", [("/me", "读取账号清单失败，请稍后重试"), ("/code account", "验证码读取失败，请稍后重试")])
async def test_delivered_read_error_reply_starts_cooldown_without_repeated_reads(monkeypatch, command, reply, caplog):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    service = SimpleNamespace(
        list_accounts=Mock(side_effect=RuntimeError("secret account data")),
        account_exists=Mock(return_value=True),
        list_official_messages=AsyncMock(side_effect=RuntimeError("secret code 56789")),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(bot, "_send", send)
    for _ in range(10):
        await bot._handle_update(None, config, _update(12345, text=command))
    assert send.await_count == 2
    assert send.await_args_list[0].args[2] == reply
    assert service.list_accounts.call_count == (1 if command == "/me" else 0)
    assert service.account_exists.call_count == (0 if command == "/me" else 1)
    assert service.list_official_messages.await_count == (0 if command == "/me" else 1)
    assert "secret" not in caplog.text
    assert "56789" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("send_error", [bot.CodeBotError("send failed"), asyncio.CancelledError()])
async def test_incomplete_me_chunks_release_command_without_cooldown(monkeypatch, send_error):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    accounts = [{"name": f"account-{i}", "remark": "r" * 80} for i in range(100)]
    service = SimpleNamespace(list_accounts=Mock(return_value=accounts))
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock(side_effect=[True, send_error])
    monkeypatch.setattr(bot, "_send", send)
    with pytest.raises(type(send_error)):
        await bot._handle_update(None, config, _update(12345, text="/me"))
    send.side_effect = None
    send.return_value = True
    await bot._handle_update(None, config, _update(12345, text="/me"))
    assert service.list_accounts.call_count == 2
    assert send.await_count == 2 + len(bot._message_chunks(bot._account_lines(accounts)))


@pytest.mark.asyncio
async def test_old_send_completion_does_not_release_new_command_after_target_changes_back(monkeypatch):
    config = ("token", 12345)
    other_config = ("token", 67890)
    active = [config]
    monkeypatch.setattr(bot, "enabled_config", lambda: active[0])
    service = SimpleNamespace(list_accounts=Mock(return_value=[]), account_exists=Mock(), list_official_messages=AsyncMock())
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    old_started, old_release = asyncio.Event(), asyncio.Event()
    new_started, new_release = asyncio.Event(), asyncio.Event()
    sends = 0

    async def send(_client, target_config, text):
        nonlocal sends
        sends += 1
        if target_config == config and text == "账号管理中暂无账号":
            if sends == 1:
                old_started.set()
                await old_release.wait()
                return False
            new_started.set()
            await new_release.wait()
        return True

    monkeypatch.setattr(bot, "_send", send)
    old_command = asyncio.create_task(bot._handle_update(None, config, _update(12345, text="/me")))
    new_command = None
    try:
        await old_started.wait()
        active[0] = other_config
        await bot._handle_update(None, other_config, _update(67890, text="/me"))
        active[0] = config
        new_command = asyncio.create_task(bot._handle_update(None, config, _update(12345, text="/me")))
        await new_started.wait()
        old_release.set()
        await old_command
        await bot._handle_update(None, config, _update(12345))
        service.account_exists.assert_not_called()
        service.list_official_messages.assert_not_awaited()
        new_release.set()
        await new_command
        await bot._handle_update(None, config, _update(12345, text="/me"))
        assert sends == 4
        assert service.list_accounts.call_count == 3
    finally:
        old_release.set()
        new_release.set()
        pending = [old_command] + ([new_command] if new_command else [])
        await asyncio.gather(*pending, return_exceptions=True)
