"""The periodic 777000 reader must release its ref-counted Telegram client."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.services.telegram.devices import TelegramDevicesMixin


@pytest.mark.asyncio
async def test_official_history_uses_client_context():
    class Client:
        enters = 0
        exits = 0

        async def __aenter__(self):
            self.enters += 1
            return self

        async def __aexit__(self, *_):
            self.exits += 1

        async def get_chat_history(self, chat_id, limit):
            assert chat_id == 777000
            assert limit == 2
            yield SimpleNamespace(
                id=4,
                date=datetime.now(timezone.utc),
                text="Login code: 12345",
                caption=None,
                outgoing=False,
            )

    client = Client()
    service = TelegramDevicesMixin()
    service._normalize_account_name = lambda name: name
    service.account_exists = lambda name: True
    service._build_account_client = lambda name, no_updates: (client, None)
    messages = await service.list_official_messages("account", limit=2)
    assert messages[0]["id"] == 4
    assert client.enters == client.exits == 1
