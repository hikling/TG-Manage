"""Explicit SOCKS5 health checks for manual status actions and midnight reports."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any

from backend.utils.proxy import build_proxy_dict
from backend.utils.tg_session import (
    get_account_proxy,
    get_account_proxy_status,
    set_account_proxy_status,
)
from backend.utils.time import utc_now_iso_z

logger = logging.getLogger("backend.account_proxy_status")


class ProxyCheckError(Exception):
    """A fixed public error code, never a proxy URL or server-provided text."""


def _telegram_endpoint() -> tuple[str, int]:
    # Use the installed Telegram client's production endpoint definition. The
    # check establishes a SOCKS tunnel only; it never logs in or reads history.
    from pyrogram.session.internals.data_center import DataCenter

    return DataCenter(2, False, False, False)


async def _probe_socks5(proxy: dict[str, Any]) -> None:
    reader, writer = await asyncio.open_connection(proxy["hostname"], proxy["port"])
    try:
        username = str(proxy.get("username") or "").encode("utf-8")
        password = str(proxy.get("password") or "").encode("utf-8")
        authenticated = bool(username or password)
        if authenticated and (not username or len(username) > 255 or len(password) > 255):
            raise ProxyCheckError("PROXY_INVALID")
        method = 2 if authenticated else 0
        writer.write(bytes((5, 1, method)))
        await writer.drain()
        if await reader.readexactly(2) != bytes((5, method)):
            raise ProxyCheckError("PROXY_AUTH_FAILED")
        if authenticated:
            writer.write(bytes((1, len(username))) + username + bytes((len(password),)) + password)
            await writer.drain()
            if await reader.readexactly(2) != b"\x01\x00":
                raise ProxyCheckError("PROXY_AUTH_FAILED")

        host, port = _telegram_endpoint()
        address = ipaddress.ip_address(host)
        writer.write(bytes((5, 1, 0, 1 if address.version == 4 else 4)) + address.packed + port.to_bytes(2, "big"))
        await writer.drain()
        version, reply, reserved, address_type = await reader.readexactly(4)
        if version != 5 or reserved != 0:
            raise ProxyCheckError("PROXY_PROTOCOL_ERROR")
        if reply != 0:
            raise ProxyCheckError("PROXY_TELEGRAM_UNREACHABLE")
        if address_type == 1:
            address_length = 4
        elif address_type == 4:
            address_length = 16
        elif address_type == 3:
            address_length = (await reader.readexactly(1))[0]
        else:
            raise ProxyCheckError("PROXY_PROTOCOL_ERROR")
        await reader.readexactly(address_length + 2)
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
        except (OSError, asyncio.TimeoutError):
            pass


async def check_account_proxy(account_name: str, *, timeout_seconds: float = 8.0) -> dict[str, Any]:
    """Probe once, persisting only if the account still has this exact proxy.

    Call only after admission by an explicit manual account-status action or
    the midnight report. Getters, login and ordinary account work must not call
    this function. Cancellation propagates and does not publish a result.
    """
    raw = ""
    try:
        raw = get_account_proxy(account_name)
        if not raw:
            return get_account_proxy_status(account_name)
        proxy = build_proxy_dict(raw)
        if proxy is None:
            raise ProxyCheckError("PROXY_INVALID")
        if proxy.get("scheme") != "socks5":
            raise ProxyCheckError("PROXY_NOT_SOCKS5")
        await asyncio.wait_for(_probe_socks5(proxy), timeout=max(1.0, min(20.0, timeout_seconds)))
        state, code = "healthy", "PROXY_OK"
    except ProxyCheckError as exc:
        state, code = "error", str(exc)
    except asyncio.TimeoutError:
        state, code = "error", "PROXY_TIMEOUT"
    except (OSError, asyncio.IncompleteReadError):
        state, code = "error", "PROXY_CONNECTION_FAILED"
    except Exception as exc:
        logger.warning("代理状态检测失败（%s）", type(exc).__name__)
        state, code = "error", "PROXY_CHECK_FAILED"
    checked_at = utc_now_iso_z()
    result = {"proxy_status": state, "proxy_status_code": code, "proxy_checked_at": checked_at}
    if not raw:
        return result
    try:
        if not set_account_proxy_status(
            account_name, expected_proxy=raw, status=state, code=code, checked_at=checked_at,
        ):
            return get_account_proxy_status(account_name)
    except Exception as exc:
        logger.warning("保存代理状态失败（%s）", type(exc).__name__)
        return {"proxy_status": "error", "proxy_status_code": "PROXY_STATUS_SAVE_FAILED", "proxy_checked_at": None}
    return result
