"""Official plugin catalog is bounded, authenticated and safe for display."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.services import telebox_catalog
from tests.test_api import _auth, _login, api_client, db  # noqa: F401


def test_catalog_requires_login(api_client, db):  # noqa: F811
    assert api_client.get("/api/telebox/catalog").status_code in {401, 403}


def test_catalog_returns_official_items_to_authenticated_user(api_client, db):  # noqa: F811
    token = _login(api_client)
    with patch("backend.api.routes.telebox.get_plugin_catalog", new_callable=AsyncMock) as fetch:
        fetch.return_value = {"source": telebox_catalog.SOURCE_URL,
                              "items": [{"name": "checkin", "description": "自动签到"}],
                              "stale": False}
        response = api_client.get("/api/telebox/catalog", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["items"][0]["name"] == "checkin"


@pytest.mark.asyncio
async def test_catalog_filters_untrusted_fields_and_caches(monkeypatch):
    telebox_catalog._cache = None
    telebox_catalog._expires_at = 0
    calls = []

    class Response:
        content = b'{"safe":{"desc":"Automatic reply"}}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"safe": {"desc": "Automatic reply", "url": "https://elsewhere"},
                    "../unsafe": {"desc": "bad"},
                    "invalid": {"desc": 123}}

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get(self, url):
            calls.append(url)
            return Response()

    monkeypatch.setattr(telebox_catalog.httpx, "AsyncClient", Client)
    first = await telebox_catalog.catalog()
    second = await telebox_catalog.catalog()
    assert first["items"] == [{"name": "safe", "description": "Automatic reply"}]
    assert first["source"] == "https://github.com/TeleBoxOrg/TeleBox-Plugins"
    assert first["stale"] is False
    assert second == first
    assert calls == [telebox_catalog.CATALOG_URL]
    telebox_catalog._cache = None
    telebox_catalog._expires_at = 0
