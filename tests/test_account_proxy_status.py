"""SOCKS5 route health is explicit, bounded and independent of login status."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services import account_proxy_status as proxy_status


@pytest.fixture
def health_env(monkeypatch):
    current = {"proxy_status": "pending", "proxy_status_code": None, "proxy_checked_at": None}
    saved = Mock(return_value=True)
    monkeypatch.setattr(proxy_status, "get_account_proxy", lambda _name: "socks5://proxy.example:1080")
    monkeypatch.setattr(proxy_status, "get_account_proxy_status", lambda _name: current)
    monkeypatch.setattr(proxy_status, "set_account_proxy_status", saved)
    return current, saved


def stream(monkeypatch, payload: bytes):
    reader = asyncio.StreamReader()
    reader.feed_data(payload)
    reader.feed_eof()
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(proxy_status.asyncio, "open_connection", connect)
    monkeypatch.setattr(proxy_status, "_telegram_endpoint", lambda: ("149.154.167.51", 443))
    return connect, writer


@pytest.mark.asyncio
async def test_no_proxy_has_zero_network_or_persistence(health_env, monkeypatch):
    current, saved = health_env
    current["proxy_status"] = "unconfigured"
    monkeypatch.setattr(proxy_status, "get_account_proxy", lambda _name: None)
    connect = AsyncMock()
    monkeypatch.setattr(proxy_status.asyncio, "open_connection", connect)
    assert await proxy_status.check_account_proxy("account") == current
    connect.assert_not_awaited()
    saved.assert_not_called()


@pytest.mark.asyncio
async def test_health_requires_full_socks5_connect_to_telegram(health_env, monkeypatch):
    _, saved = health_env
    connect, writer = stream(monkeypatch, b"\x05\x00\x05\x00\x00\x01\x00\x00\x00\x00\x01\xbb")
    result = await proxy_status.check_account_proxy("account")
    assert result["proxy_status"] == "healthy"
    assert result["proxy_status_code"] == "PROXY_OK"
    assert result["proxy_checked_at"]
    connect.assert_awaited_once_with("proxy.example", 1080)
    assert writer.write.call_args_list[0].args[0] == b"\x05\x01\x00"
    assert writer.write.call_args_list[1].args[0] == b"\x05\x01\x00\x01\x95\x9a\xa7\x33\x01\xbb"
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
    assert saved.call_args.kwargs["expected_proxy"] == "socks5://proxy.example:1080"
    assert saved.call_args.kwargs["status"] == "healthy"


@pytest.mark.asyncio
async def test_authenticated_socks5_handshake(health_env, monkeypatch):
    monkeypatch.setattr(proxy_status, "get_account_proxy", lambda _: "socks5://alice:secret@proxy.example:1080")
    _, writer = stream(monkeypatch, b"\x05\x02\x01\x00\x05\x00\x00\x03\x03abc\x01\xbb")
    assert (await proxy_status.check_account_proxy("account"))["proxy_status"] == "healthy"
    assert writer.write.call_args_list[0].args[0] == b"\x05\x01\x02"
    assert writer.write.call_args_list[1].args[0] == b"\x01\x05alice\x06secret"


@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "code"), [
    (b"\x05\xff", "PROXY_AUTH_FAILED"),
    (b"\x05\x00\x05\x05\x00\x01", "PROXY_TELEGRAM_UNREACHABLE"),
    (b"\x05\x00\x04\x00\x00\x01", "PROXY_PROTOCOL_ERROR"),
    (b"\x05\x00\x05\x00\x00\x07", "PROXY_PROTOCOL_ERROR"),
    (b"\x05\x00\x05\x00\x00\x01", "PROXY_CONNECTION_FAILED"),
])
async def test_open_port_or_partial_tunnel_is_not_healthy(health_env, monkeypatch, payload, code):
    _, writer = stream(monkeypatch, payload)
    result = await proxy_status.check_account_proxy("account")
    assert result["proxy_status"] == "error"
    assert result["proxy_status_code"] == code
    writer.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "code"), [
    ("socks5://bad", "PROXY_INVALID"), ("http://proxy.example:1080", "PROXY_NOT_SOCKS5"),
])
async def test_invalid_or_other_proxy_never_uses_direct_connection(health_env, monkeypatch, raw, code):
    monkeypatch.setattr(proxy_status, "get_account_proxy", lambda _: raw)
    connect = AsyncMock()
    monkeypatch.setattr(proxy_status.asyncio, "open_connection", connect)
    assert (await proxy_status.check_account_proxy("account"))["proxy_status_code"] == code
    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_closes_tunnel(health_env, monkeypatch):
    reader = asyncio.StreamReader()
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    monkeypatch.setattr(proxy_status.asyncio, "open_connection", AsyncMock(return_value=(reader, writer)))
    result = await asyncio.wait_for(proxy_status.check_account_proxy("account", timeout_seconds=1), 2.5)
    assert result["proxy_status_code"] == "PROXY_TIMEOUT"
    writer.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_closes_without_publishing_health(health_env, monkeypatch):
    _, saved = health_env
    waiting = asyncio.Event()
    reader = Mock()
    async def read(_size):
        waiting.set()
        await asyncio.Event().wait()
    reader.readexactly = read
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    monkeypatch.setattr(proxy_status.asyncio, "open_connection", AsyncMock(return_value=(reader, writer)))
    task = asyncio.create_task(proxy_status.check_account_proxy("account"))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    writer.close.assert_called_once()
    saved.assert_not_called()


@pytest.mark.asyncio
async def test_changed_proxy_discards_stale_result(health_env, monkeypatch):
    current, saved = health_env
    saved.return_value = False
    monkeypatch.setattr(proxy_status, "_probe_socks5", AsyncMock())
    assert await proxy_status.check_account_proxy("account") == current


@pytest.mark.asyncio
async def test_errors_do_not_leak_proxy_credentials(health_env, monkeypatch, caplog):
    monkeypatch.setattr(proxy_status, "_probe_socks5", AsyncMock(side_effect=RuntimeError("socks5://alice:SECRET@private:1080")))
    result = await proxy_status.check_account_proxy("account")
    assert result["proxy_status_code"] == "PROXY_CHECK_FAILED"
    assert "SECRET" not in caplog.text + str(result)
