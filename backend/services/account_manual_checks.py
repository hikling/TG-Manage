"""Bounded, account-scoped resource inspection for manual account checks."""
from __future__ import annotations

import logging
from typing import Any

from backend.services.account_routes import account_route_status, refresh_account_exit
from backend.services.telebox import get_telebox_service

logger = logging.getLogger("backend.account_manual_checks")


async def inspect_account_resources(
    account_name: str, *, fresh_after: float | None = None,
) -> dict[str, Any]:
    """Read one TeleBox and refresh only this account's route exit IP."""
    try:
        route = await refresh_account_exit(account_name, fresh_after=fresh_after)
    except Exception as exc:
        logger.warning("账户 IP 检测失败 account=%s type=%s", account_name, type(exc).__name__)
        route = {
            **account_route_status(account_name),
            "exit_ip": None, "exit_country": None, "exit_region": None,
            "exit_checked_at": None, "exit_lookup_status": "failed",
        }
    try:
        telebox = get_telebox_service().status(account_name)
    except Exception as exc:
        logger.warning("TeleBox 状态检测失败 account=%s type=%s", account_name, type(exc).__name__)
        telebox = {"account": account_name, "status": "unknown", "enabled": False,
                   "authorized": False, "message": "TeleBox status unavailable"}
    return {**route, "telebox": telebox}
