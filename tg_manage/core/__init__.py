"""Shared Telegram client lifecycle for account management."""
from __future__ import annotations

from tg_manage.core.client import (
    _CLIENT_ASYNC_LOCKS,
    _CLIENT_INSTANCES,
    _CLIENT_REFS,
    Client,
    _patched_invoke,  # noqa: F401 — 副作用导入：触发 monkey-patch 装配
    _patched_sqlite3_connect,  # noqa: F401 — 副作用导入：触发 monkey-patch 装配
    close_client_by_name,
    get_client,
    get_proxy,
)

__all__ = [
    "Client",
    "get_client",
    "close_client_by_name",
    "get_proxy",
    "_CLIENT_INSTANCES",
    "_CLIENT_REFS",
    "_CLIENT_ASYNC_LOCKS",
    "_patched_invoke",
    "_patched_sqlite3_connect",
]
