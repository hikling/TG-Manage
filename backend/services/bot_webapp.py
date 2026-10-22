"""Private Telegram bot menu and signed Mini App login validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from urllib.parse import parse_qsl, urlsplit

import httpx

logger = logging.getLogger("backend.bot_webapp")
INIT_DATA_MAX_AGE_SECONDS = 120
_PRIVATE_ID = re.compile(r"[1-9][0-9]{0,18}\Z")


def private_target(settings: dict) -> int | None:
    value = str(settings.get("telegram_bot_chat_id") or "").strip()
    if not _PRIVATE_ID.fullmatch(value):
        return None
    target = int(value)
    return target if target <= (1 << 63) - 1 else None


def menu_url(settings: dict) -> str | None:
    raw = str(settings.get("telegram_bot_web_url") or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or any(ord(char) < 32 for char in raw)
    ):
        raise ValueError("机器人 Web 地址必须是网站根目录的 HTTPS URL")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("机器人 Web 地址端口无效") from exc
    return f"{parsed.scheme}://{parsed.netloc}/bot"


def validate_init_data(init_data: str, settings: dict, *, now: int | None = None) -> bool:
    """Fail closed on missing, stale, duplicate or incorrectly signed fields."""
    token = str(settings.get("telegram_bot_token") or "").strip()
    target = private_target(settings)
    try:
        configured_url = menu_url(settings)
    except ValueError:
        return False
    if not token or target is None or not configured_url:
        return False
    if not isinstance(init_data, str) or not 1 <= len(init_data) <= 4096:
        return False
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            return False
        supplied_hash = fields.pop("hash", "")
        if len(supplied_hash) != 64:
            return False
        auth_date = int(fields["auth_date"])
        current = int(time.time()) if now is None else now
        if not 0 <= current - auth_date <= INIT_DATA_MAX_AGE_SECONDS:
            return False
        user = json.loads(fields["user"])
        if not isinstance(user, dict) or type(user.get("id")) is not int or user["id"] != target:
            return False
        data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_hash, supplied_hash)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


async def _set_button(client: httpx.AsyncClient, token: str, payload: dict) -> None:
    response = await client.post(
        f"https://api.telegram.org/bot{token}/setChatMenuButton",
        json=payload,
        timeout=10,
    )
    if response.status_code != 200 or not response.json().get("ok"):
        raise RuntimeError("Telegram 菜单设置失败")


async def sync_menu_button(settings: dict, previous: dict | None = None) -> bool:
    """Only the configured private target receives the Web App entry."""
    token = str(settings.get("telegram_bot_token") or "").strip()
    target = private_target(settings)
    url = menu_url(settings)
    old_token = str((previous or {}).get("telegram_bot_token") or "").strip()
    old_target = private_target(previous or {})
    if not url and not (previous or {}).get("telegram_bot_web_url"):
        return True
    async with httpx.AsyncClient() as client:
        old_menu_cleared = True
        try:
            if old_token and old_target and (old_token != token or old_target != target or not url):
                await _set_button(client, old_token, {
                    "chat_id": old_target, "menu_button": {"type": "commands"},
                })
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            old_menu_cleared = False
            logger.warning("旧机器人 Web 菜单清理失败（%s）", type(exc).__name__)
        if not token:
            return old_menu_cleared
        try:
            # Clear any BotFather global Web App: all other users see only the default command menu.
            await _set_button(client, token, {"menu_button": {"type": "commands"}})
            if target and url:
                await _set_button(client, token, {
                    "chat_id": target,
                    "menu_button": {"type": "web_app", "text": "打开WEB", "web_app": {"url": url}},
                })
            return old_menu_cleared
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            logger.warning("机器人 Web 菜单同步失败（%s）", type(exc).__name__)
            return False
