"""Opt-in, private delivery of short-lived Telegram 777000 login codes.

Only message IDs and Bot API offsets are persisted. Message text/code is never
written to a job, cache, file, or log. Startup always establishes a fresh
history baseline, so codes received while the process was down are not replayed.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.core.config import get_settings
from backend.services.config import get_config_service
from backend.services.telegram import get_telegram_service
from backend.utils.atomic_io import read_json_safe, write_json_atomic
from backend.utils.names import validate_storage_name

logger = logging.getLogger("backend.official_code_bot")
CODE_AGE_SECONDS = 5 * 60
POLL_SECONDS = 20
_CODE_PATTERN = re.compile(
    r"(?:code|验证码|登录码|登入码)[^0-9]{0,32}([0-9]{5,8})(?![0-9])",
    re.IGNORECASE,
)
_PRIVATE_ID = re.compile(r"[1-9][0-9]{0,18}\Z")
_status = "未启用"


class CodeBotError(Exception):
    """Safe error text: never contains a Bot API URL, token, or message body."""


def runtime_status() -> str:
    return _status


def private_target(settings: dict[str, Any]) -> int | None:
    value = str(settings.get("telegram_bot_chat_id") or "").strip()
    if not _PRIVATE_ID.fullmatch(value):
        return None
    target = int(value)
    return target if target <= (1 << 63) - 1 else None


def enabled_config() -> tuple[str, int] | None:
    settings = get_config_service().get_global_settings()
    token = str(settings.get("telegram_bot_token") or "").strip()
    target = private_target(settings)
    if settings.get("telegram_bot_code_enabled") and token and target:
        return token, target
    return None


def parse_code(text: str) -> str | None:
    match = _CODE_PATTERN.search(text)
    return match.group(1) if match else None


def fresh(date_value: Any, *, now: datetime | None = None) -> bool:
    try:
        stamp = datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        return 0 <= age <= CODE_AGE_SECONDS
    except (TypeError, ValueError):
        return False


def latest_code(messages: list[dict[str, Any]]) -> str | None:
    for item in messages:
        if item.get("outgoing") or not fresh(item.get("date")):
            continue
        code = parse_code(str(item.get("text") or ""))
        if code:
            return code
    return None


def authorized(update: dict[str, Any], target: int) -> bool:
    message = update.get("message")
    if not isinstance(message, dict):
        return False
    chat, sender = message.get("chat"), message.get("from")
    return (
        isinstance(chat, dict)
        and isinstance(sender, dict)
        and chat.get("type") == "private"
        and chat.get("id") == target
        and sender.get("id") == target
    )


async def _bot_call(client: httpx.AsyncClient, token: str, method: str, payload: dict[str, Any]) -> Any:
    try:
        response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
        if response.status_code == 409:
            raise CodeBotError("Bot 更新接收冲突：请停用现有 Webhook 或其他 getUpdates 轮询器")
        if response.status_code >= 400:
            raise CodeBotError(f"Bot API 返回 HTTP {response.status_code}")
        body = response.json()
        if not body.get("ok"):
            raise CodeBotError("Bot API 请求失败")
        return body.get("result")
    except (httpx.RequestError, ValueError) as exc:
        raise CodeBotError(f"Bot API 网络或响应错误（{type(exc).__name__}）") from None


async def _send(client: httpx.AsyncClient, config: tuple[str, int], text: str) -> None:
    # Recheck configuration at the last possible moment; never deliver to an old target.
    if enabled_config() != config:
        return
    token, target = config
    await _bot_call(client, token, "sendMessage", {"chat_id": target, "text": text})


def _state_path():
    return get_settings().resolve_workdir() / "bots" / "official-code-cursors.json"


def _save_state(cursors: dict[str, int], offset: int) -> None:
    write_json_atomic(_state_path(), {"message_ids": cursors, "update_offset": offset})


def _load_state() -> tuple[dict[str, int], int]:
    state = read_json_safe(_state_path(), {})
    if not isinstance(state, dict):
        state = {}
    raw_ids = state.get("message_ids")
    if not isinstance(raw_ids, dict):
        raw_ids = {}
    cursors = {str(k): int(v) for k, v in raw_ids.items() if str(v).isdigit()}
    raw_offset = state.get("update_offset")
    offset = int(raw_offset) if str(raw_offset).isdigit() else 0
    return cursors, offset


async def _scan_accounts(
    client: httpx.AsyncClient,
    config: tuple[str, int],
    cursors: dict[str, int],
    offset: int,
    *,
    baselined_accounts: set[str],
) -> int:
    service = get_telegram_service()
    names = [str(item.get("name") or "") for item in service.list_accounts()]
    semaphore = asyncio.Semaphore(3)
    errors = 0

    async def scan(name: str) -> None:
        nonlocal errors
        if not name:
            return
        async with semaphore:
            try:
                history = await service.list_official_messages(name, limit=20)
                message_ids = [int(item["id"]) for item in history if item.get("id") is not None]
                if not message_ids:
                    if name not in cursors:
                        cursors[name] = 0
                        _save_state(cursors, offset)
                    baselined_accounts.add(name)
                    return
                previous = cursors.get(name)
                newest = max(message_ids)
                if name not in baselined_accounts or previous is None:
                    cursors[name] = newest
                    _save_state(cursors, offset)
                    baselined_accounts.add(name)
                    return
                for item in sorted(history, key=lambda entry: int(entry.get("id") or 0)):
                    message_id = int(item.get("id") or 0)
                    if message_id <= previous:
                        continue
                    # Persist before sending: a crash can miss a code, but cannot replay it.
                    cursors[name] = message_id
                    _save_state(cursors, offset)
                    if item.get("outgoing") or not fresh(item.get("date")):
                        continue
                    code = parse_code(str(item.get("text") or ""))
                    if code:
                        await _send(client, config, f"{name} 的 Telegram 验证码：{code}（5 分钟内有效）")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Telegram exception details can include message content/session data.
                errors += 1
                logger.warning("账号 %s 的验证码检查失败（%s）", name, type(exc).__name__)

    await asyncio.gather(*(scan(name) for name in names))
    return errors


async def _handle_update(client: httpx.AsyncClient, config: tuple[str, int], update: dict[str, Any]) -> None:
    if enabled_config() != config or not authorized(update, config[1]):
        return
    message = update["message"]
    if not fresh(datetime.fromtimestamp(message.get("date", 0), timezone.utc).isoformat()):
        return
    text = str(message.get("text") or "").strip()
    if not text.startswith("/code "):
        return
    account = text.partition(" ")[2].strip()
    try:
        account = validate_storage_name(account, field_name="account_name")
    except ValueError:
        await _send(client, config, "账号名无效")
        return
    service = get_telegram_service()
    if not service.account_exists(account):
        await _send(client, config, "账号不存在")
        return
    try:
        messages = await service.list_official_messages(account, limit=20)
        code = latest_code(messages)
        await _send(client, config, f"{account} 的 Telegram 验证码：{code}" if code else "暂无有效验证码")
    except Exception as exc:
        logger.warning("按需读取验证码失败（%s）", type(exc).__name__)
        await _send(client, config, "验证码读取失败，请稍后重试")


async def run_code_bot() -> None:
    """Run only in the scheduler-lock owner; poll without enabling a webhook."""
    global _status
    from backend.scheduler.instance_lock import has_scheduler_lock

    cursors, offset = _load_state()
    current: tuple[str, int] | None = None
    baselined_accounts: set[str] = set()
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as client:
        while True:
            try:
                config = enabled_config() if has_scheduler_lock() else None
                if config is None:
                    current = None
                    baselined_accounts.clear()
                    _status = "未启用或当前实例未取得调度锁"
                    await asyncio.sleep(5)
                    continue
                if config != current:
                    current = config
                    baselined_accounts.clear()
                    offset = 0
                    webhook = await _bot_call(client, config[0], "getWebhookInfo", {})
                    if webhook.get("url"):
                        current = None
                        _status = "检测到已有 Webhook；请先在该 Bot 的原管理端停用 Webhook"
                        await asyncio.sleep(POLL_SECONDS)
                        continue
                    backlog = await _bot_call(client, config[0], "getUpdates", {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]})
                    offset = max((int(item["update_id"]) for item in backlog), default=offset - 1) + 1
                    _save_state(cursors, offset)
                webhook = await _bot_call(client, config[0], "getWebhookInfo", {})
                if webhook.get("url"):
                    _status = "检测到已有 Webhook；请先在该 Bot 的原管理端停用 Webhook"
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                scan_errors = await _scan_accounts(client, config, cursors, offset, baselined_accounts=baselined_accounts)
                updates = await _bot_call(client, config[0], "getUpdates", {"offset": offset, "limit": 20, "timeout": 1, "allowed_updates": ["message"]})
                for update in updates:
                    offset = max(offset, int(update["update_id"]) + 1)
                    _save_state(cursors, offset)
                    await _handle_update(client, config, update)
                _status = "运行中（部分账号检查失败）" if scan_errors else "运行中"
                await asyncio.sleep(POLL_SECONDS)
            except asyncio.CancelledError:
                raise
            except CodeBotError as exc:
                _status = str(exc)
                if "Webhook" in _status or "冲突" in _status:
                    current = None  # re-baseline queued commands when the conflict clears
                logger.warning("私人验证码机器人：%s", _status)
                await asyncio.sleep(POLL_SECONDS)
            except Exception as exc:
                _status = "运行异常，请检查服务日志"
                logger.warning("私人验证码机器人运行异常（%s）", type(exc).__name__)
                await asyncio.sleep(POLL_SECONDS)
