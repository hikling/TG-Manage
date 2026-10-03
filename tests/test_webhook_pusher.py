"""Webhook notification adapters still work after the retired Python plugin removal."""

from unittest.mock import AsyncMock

import pytest

from backend.services import push_notifications


@pytest.mark.asyncio
async def test_empty_webhook_does_not_send(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(push_notifications, "_http_post_retry_once", send)
    await push_notifications.send_wecom_message("", "title", "message")
    await push_notifications.send_feishu_message(" ", "title", "message")
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_webhook_formats_and_bounds_payload(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(push_notifications, "_http_post_retry_once", send)
    await push_notifications.send_wecom_message(" https://example.com/hook ", "title", "m" * 5000)
    payload = send.await_args.kwargs
    assert payload["url"] == "https://example.com/hook"
    assert payload["channel"] == "WeCom"
    assert payload["json_body"]["msgtype"] == "markdown"
    assert len(payload["json_body"]["markdown"]["content"]) <= 4000


@pytest.mark.asyncio
async def test_feishu_webhook_formats_card(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(push_notifications, "_http_post_retry_once", send)
    await push_notifications.send_feishu_message("https://example.com/hook", "hello", "body")
    payload = send.await_args.kwargs
    assert payload["channel"] == "Feishu"
    assert payload["json_body"]["card"]["elements"][0]["text"]["content"] == "body"
