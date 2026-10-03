"""Shared Telegram client lifecycle for account management."""
from __future__ import annotations

from tg_signer.core.client import (
    _CLIENT_ASYNC_LOCKS,
    _CLIENT_INSTANCES,
    _CLIENT_REFS,
    Client,
    _is_callback_confirmation_unavailable,
    _is_callback_data_invalid,
    _patched_invoke,  # noqa: F401 — 副作用导入：触发 monkey-patch 装配
    _patched_sqlite3_connect,  # noqa: F401 — 副作用导入：触发 monkey-patch 装配
    close_client_by_name,
    get_api_config,
    get_client,
    get_now,
    get_proxy,
    get_task_timezone,
    make_dirs,
    readable_chat,
    readable_message,
)

__all__ = [
    "Client",
    "get_client",
    "close_client_by_name",
    "get_api_config",
    "get_proxy",
    "get_now",
    "get_task_timezone",
    "make_dirs",
    "readable_chat",
    "readable_message",
    "_CLIENT_INSTANCES",
    "_CLIENT_REFS",
    "_CLIENT_ASYNC_LOCKS",
    "_is_callback_confirmation_unavailable",
    "_is_callback_data_invalid",
    "_patched_invoke",
    "_patched_sqlite3_connect",
]
