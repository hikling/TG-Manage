"""Panel API contracts: auth, validation and bot-token confidentiality."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.test_api import _auth, _login, api_client, db  # noqa: F401


def test_panel_routes_require_auth(api_client, db):  # noqa: F811
    for path in (
        "/api/communications/proxies", "/api/communications/a/dialogs",
        "/api/telebox",
    ):
        assert api_client.get(path).status_code in {401, 403}


def test_invalid_chat_input_never_calls_telegram(api_client, db):  # noqa: F811
    token = _login(api_client)
    with patch("backend.api.routes.communications.service.send_message", new_callable=AsyncMock) as send:
        response = api_client.post(
            "/api/communications/account/messages",
            json={"chat_id": "https://example.com", "text": "hello"},
            headers=_auth(token),
        )
    assert response.status_code == 422
    send.assert_not_awaited()


def test_bot_center_endpoint_is_removed(api_client, db):  # noqa: F811
    token = _login(api_client)
    assert api_client.get("/api/bots", headers=_auth(token)).status_code == 404


def test_private_code_bot_rejects_group_target(api_client, db):  # noqa: F811
    token = _login(api_client)
    response = api_client.post(
        "/api/config/settings",
        json={
            "telegram_bot_code_enabled": True,
            "telegram_bot_chat_id": "-1001234567890",
            "telegram_bot_token": "12345:test-token",
        },
        headers=_auth(token),
    )
    assert response.status_code == 400
    assert "私人目标 ID" in response.json()["detail"]


def test_peer_id_rejects_urls_and_path_traversal():
    from backend.services.communications import peer_id

    assert peer_id("-10012345") == -10012345
    assert peer_id("@account_name") == "account_name"
    for invalid in ("https://t.me/test", "../../session", "0", "  "):
        with pytest.raises(HTTPException) as exc:
            peer_id(invalid)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_dialog_pagination_and_group_filter():
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from backend.services import communications

    def dialog(number, kind):
        chat = SimpleNamespace(id=number, type=SimpleNamespace(value=kind), title=f"Group {number}", username=None)
        return SimpleNamespace(chat=chat, top_message=None, unread_messages_count=0)

    class Client:
        async def get_dialogs(self, *, from_archive):
            assert from_archive is False
            for item in (dialog(1, "private"), dialog(2, "group"), dialog(3, "supergroup"), dialog(4, "group")):
                yield item

    @asynccontextmanager
    async def fake_client(account):
        assert account == "first-account"
        yield Client()

    with patch.object(communications, "account_client", fake_client):
        page = await communications.dialogs("first-account", offset=1, limit=1, kind="groups")
    assert [item["id"] for item in page["items"]] == ["3"]
    assert page["next_offset"] == 2
    assert page["has_more"] is True


def test_telebox_account_directories_and_redaction(tmp_path):
    from backend.services.telebox import TeleBoxService, redact

    service = TeleBoxService(root=tmp_path)
    assert service.directory("one") != service.directory("two")
    assert service.directory("one").parent == tmp_path
    assert "private-password" not in redact("password=private-password", ["private-password"])
