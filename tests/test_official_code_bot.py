"""Private 777000 code bot: authorization, freshness and no-replay cursors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from backend.services import official_code_bot as bot
from backend.utils.atomic_io import read_json_safe


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


def test_malformed_cursor_state_is_ignored(tmp_path, monkeypatch):
    path = tmp_path / "cursors.json"
    monkeypatch.setattr(bot, "_state_path", lambda: path)
    path.write_text('["unexpected"]')
    assert bot._load_state() == ({}, 0)
    path.write_text('{"message_ids": [1, 2], "update_offset": "oops"}')
    assert bot._load_state() == ({}, 0)


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
async def test_history_baseline_and_at_most_once(tmp_path, monkeypatch):
    state_file = tmp_path / "cursors.json"
    monkeypatch.setattr(bot, "_state_path", lambda: state_file)
    history = [{"id": 10, "date": _stamp(), "text": "Login code: 12345", "outgoing": False}]
    service = SimpleNamespace(
        list_accounts=lambda: [{"name": "account"}],
        list_official_messages=AsyncMock(side_effect=lambda *args, **kwargs: list(reversed(history))),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    monkeypatch.setattr(bot, "enabled_config", lambda: ("token", 12345))
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)
    cursors = {"account": 9}
    baselined_accounts: set[str] = set()

    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert cursors["account"] == 10
    send.assert_not_awaited()  # no old code after enable/restart

    history.append({"id": 11, "date": _stamp(), "text": "Login code: 67890", "outgoing": False})
    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert send.await_count == 1
    persisted = read_json_safe(state_file)
    assert persisted == {"message_ids": {"account": 11}, "update_offset": 0}
    assert "67890" not in state_file.read_text()


@pytest.mark.asyncio
async def test_failed_first_history_read_baselines_when_it_recovers(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "_state_path", lambda: tmp_path / "cursors.json")
    history = [{"id": 12, "date": _stamp(), "text": "Login code: 12345", "outgoing": False}]
    fetch = AsyncMock(side_effect=[RuntimeError("offline"), history])
    service = SimpleNamespace(list_accounts=lambda: [{"name": "account"}], list_official_messages=fetch)
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)
    baselined_accounts: set[str] = set()
    cursors = {"account": 9}

    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert not baselined_accounts
    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert cursors["account"] == 12
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_code_after_empty_history_is_forwarded(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "_state_path", lambda: tmp_path / "cursors.json")
    fetch = AsyncMock(side_effect=[[], [{"id": 1, "date": _stamp(), "text": "Login code: 54321", "outgoing": False}]])
    service = SimpleNamespace(list_accounts=lambda: [{"name": "account"}], list_official_messages=fetch)
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)
    baselined_accounts: set[str] = set()
    cursors: dict[str, int] = {}

    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert cursors["account"] == 0
    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    send.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_history_does_not_reset_existing_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "_state_path", lambda: tmp_path / "cursors.json")
    fetch = AsyncMock(side_effect=[[], [{"id": 10, "date": _stamp(), "text": "Login code: 54321", "outgoing": False}]])
    service = SimpleNamespace(list_accounts=lambda: [{"name": "account"}], list_official_messages=fetch)
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)
    baselined_accounts = {"account"}
    cursors = {"account": 10}

    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    assert cursors["account"] == 10
    await bot._scan_accounts(None, ("token", 12345), cursors, 0, baselined_accounts=baselined_accounts)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_unauthorized_update_is_silent_and_expired_command_gets_no_code(monkeypatch):
    config = ("token", 12345)
    monkeypatch.setattr(bot, "enabled_config", lambda: config)
    history = [{"id": 8, "date": _stamp(6), "text": "Login code: 12345", "outgoing": False}]
    service = SimpleNamespace(
        account_exists=lambda name: name == "account",
        list_official_messages=AsyncMock(return_value=history),
    )
    monkeypatch.setattr(bot, "get_telegram_service", lambda: service)
    send = AsyncMock()
    monkeypatch.setattr(bot, "_send", send)

    await bot._handle_update(None, config, _update(12345, sender=9))
    await bot._handle_update(None, config, _update(12345, kind="group"))
    await bot._handle_update(None, config, _update(12345, minutes_ago=6))
    send.assert_not_awaited()
    service.list_official_messages.assert_not_awaited()

    await bot._handle_update(None, config, _update(12345))
    send.assert_awaited_once_with(None, config, "暂无有效验证码")
