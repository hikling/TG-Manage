"""Private Bot: on-demand 777000 codes and local account labels only."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from backend.services import official_code_bot as bot


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
