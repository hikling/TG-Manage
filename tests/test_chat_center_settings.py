from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.api.routes import accounts, communications, router
from backend.services import avatar_cache


def test_chat_center_disabled_blocks_regular_reads_but_official_route_remains(monkeypatch):
    monkeypatch.setattr(
        communications, "get_config_service",
        lambda: type("Config", (), {"get_global_settings": lambda _: {"chat_center_enabled": False}})(),
    )
    with pytest.raises(HTTPException) as exc:
        communications.require_chat_center()
    assert exc.value.status_code == 403
    paths = {route.path for route in router.routes}
    assert "/accounts/{account_name}/official-messages" in paths
    assert accounts.list_account_official_messages is not None


def test_chat_center_guard_covers_read_and_write_routes():
    protected = {
        "/communications/{account}/dialogs",
        "/communications/{account}/messages",
        "/communications/{account}/messages/{message_id}",
        "/communications/{account}/media",
        "/communications/{account}/avatar/{chat_id}",
        "/communications/{account}/dialogs/action",
    }
    for route in router.routes:
        if route.path not in protected:
            continue
        assert any(
            dependency.call is communications.require_chat_center
            for dependency in route.dependant.dependencies
        ), f"Missing chat-center guard: {route.path} {route.methods}"


def test_avatar_chat_cache_clears_above_five_mebibytes(tmp_path: Path):
    cache = tmp_path / "chats"
    cache.mkdir()
    (cache / "one.jpg").write_bytes(b"a" * (5 * 1024 * 1024))
    assert avatar_cache.enforce_chat_cache_limit(cache) is False
    (cache / "two.jpg").write_bytes(b"b")
    assert avatar_cache.enforce_chat_cache_limit(cache) is True
    assert list(cache.iterdir()) == []
