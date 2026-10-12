"""Private, on-demand access to Telegram 777000 codes and local account labels.

The bot never scans account histories in the background. Startup discards queued
commands; neither verification codes nor account lists are persisted here.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.services.config import get_config_service
from backend.services.telegram import get_telegram_service
from backend.utils.names import validate_storage_name

logger = logging.getLogger("backend.official_code_bot")
CODE_AGE_SECONDS = 5 * 60
BOT_REQUEST_TIMEOUT_SECONDS = 10
POLL_TIMEOUT_SECONDS = 30
POLL_BACKOFF_SECONDS = 3
POLL_CONFLICT_BACKOFF_SECONDS = 5
CODE_READ_TIMEOUT_SECONDS = 12
MAX_BOT_MESSAGE_CHARS = 3500
COMMAND_COOLDOWN_SECONDS = 45
_CODE_PATTERN = re.compile(
    r"(?:code|验证码|登录码|登入码)[^0-9]{0,32}([0-9]{5,8})(?![0-9])",
    re.IGNORECASE,
)
_PRIVATE_ID = re.compile(r"[1-9][0-9]{0,18}\Z")
_status = "未启用"


@dataclass
class _CommandState:
    deadline: float = 0.0
    notice: object | None = None


class _CommandGate:
    """Serialize reads and retain only expiring command keys and local names."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config: tuple[str, int] | None = None
        self._commands: dict[str, _CommandState] = {}
        self._in_flight: tuple[object, str] | None = None
        self._busy_notice: object | None = None
        self._account_names: tuple[str, ...] | None = None

    def _sync_locked(self, config: tuple[str, int] | None) -> None:
        if config != self._config:
            self._config = config
            self._commands.clear()
            self._in_flight = None
            self._busy_notice = None
            self._account_names = None

    def sync(self, config: tuple[str, int] | None) -> None:
        with self._lock:
            self._sync_locked(config)

    def begin(self, config: tuple[str, int], command: str) -> tuple[object | None, int, object | None]:
        with self._lock:
            self._sync_locked(config)
            now = time.monotonic()
            active_command = self._in_flight[1] if self._in_flight else None
            self._commands = {
                key: state for key, state in self._commands.items()
                if state.deadline > now or key == active_command
            }
            state = self._commands.get(command)
            remaining = max(0, math.ceil(state.deadline - now)) if state else 0
            if remaining or command == active_command:
                assert state is not None
                notice = None if state.notice else object()
                if notice is not None:
                    state.notice = notice
                return None, remaining or COMMAND_COOLDOWN_SECONDS, notice
            if self._in_flight:
                notice = None if self._busy_notice else object()
                if notice is not None:
                    self._busy_notice = notice
                return None, 0, notice
            reservation = object()
            self._in_flight = reservation, command
            self._commands[command] = _CommandState()
            self._busy_notice = None
            if command == "/me":
                # A partial new list cannot safely share the old numbering.
                self._account_names = None
            return reservation, 0, None

    def account_names(self, config: tuple[str, int], reservation: object) -> tuple[str, ...] | None:
        with self._lock:
            if config == self._config and self._in_flight and reservation is self._in_flight[0]:
                return self._account_names
            return None

    def finish(
        self, config: tuple[str, int], reservation: object, *, delivered: bool,
        account_names: tuple[str, ...] | None = None,
    ) -> None:
        with self._lock:
            # A target can change away and back while an older send is pending.
            if config != self._config or not self._in_flight or reservation is not self._in_flight[0]:
                return
            command = self._in_flight[1]
            self._in_flight = None
            self._busy_notice = None
            if delivered:
                self._commands[command].deadline = time.monotonic() + COMMAND_COOLDOWN_SECONDS
                if command == "/me" and account_names is not None:
                    self._account_names = account_names
            else:
                self._commands.pop(command, None)

    def notice_failed(self, config: tuple[str, int], command: str, notice: object) -> None:
        with self._lock:
            if config != self._config:
                return
            state = self._commands.get(command)
            if state and notice is state.notice:
                state.notice = None
            if notice is self._busy_notice:
                self._busy_notice = None


_command_gate = _CommandGate()


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
    response: httpx.Response | None = None
    try:
        timeout = httpx.Timeout(
            POLL_TIMEOUT_SECONDS + 5 if method == "getUpdates" and payload.get("timeout") else BOT_REQUEST_TIMEOUT_SECONDS,
            connect=5,
        )
        response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload, timeout=timeout)
        if response.status_code == 409:
            raise CodeBotError("Bot 更新接收冲突：请停用现有 Webhook 或其他 getUpdates 轮询器")
        if response.status_code >= 400:
            raise CodeBotError(f"Bot API 返回 HTTP {response.status_code}")
        body = response.json()
        if not body.get("ok"):
            raise CodeBotError("Bot API 请求失败")
        return body.get("result")
    except CodeBotError:
        raise
    except (httpx.RequestError, ValueError) as exc:
        raise CodeBotError(f"Bot API 网络或响应错误（{type(exc).__name__}）") from None
    finally:
        if response is not None:
            try:
                await response.aclose()
            except Exception as exc:
                # Preserve a known delivery result and sanitize close errors.
                logger.warning("Bot API 响应关闭失败（%s）", type(exc).__name__)


async def _send(client: httpx.AsyncClient, config: tuple[str, int], text: str) -> bool:
    # Recheck configuration at the last possible moment; never deliver to an old target.
    if enabled_config() != config:
        return False
    token, target = config
    await _bot_call(client, token, "sendMessage", {"chat_id": target, "text": text})
    return enabled_config() == config


def _account_rows(accounts: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Project local account metadata only; never include proxy or session data."""
    rows: list[tuple[str, str]] = []
    for item in accounts:
        try:
            name = validate_storage_name(str(item.get("name") or ""), field_name="account_name")
        except ValueError:
            continue
        remark = " ".join(str(item.get("remark") or "").split()) or "无备注"
        rows.append((name, remark))
    # Digit runs sort numerically: account2 comes before account10.
    return sorted(rows, key=lambda row: (
        tuple(int(part) if index % 2 else part.casefold()
              for index, part in enumerate(re.split(r"([0-9]+)", row[0]))),
        row[0],
    ))


def _account_lines(rows: list[tuple[str, str]]) -> list[str]:
    return [f"{index}. {' '.join(name.split())} — {remark}" for index, (name, remark) in enumerate(rows, 1)]


def _normalized_command(text: str) -> str | None:
    parts = text.split(maxsplit=1)
    if not parts or parts[0] not in {"/me", "/code"}:
        return None
    if parts[0] == "/me":
        return "/me" if len(parts) == 1 else None
    argument = parts[1].strip() if len(parts) > 1 else ""
    if re.fullmatch(r"[0-9]+", argument):
        # Avoid integer conversion limits on malformed enormous arguments.
        argument = argument.lstrip("0") or "0"
    return f"/code {argument}".rstrip()


def _message_chunks(lines: list[str]) -> list[str]:
    if not lines:
        return ["账号管理中暂无账号"]
    chunks: list[str] = []
    header = "账号管理中的账号："
    header_units = len(header.encode("utf-16-le")) // 2
    current = header
    current_units = header_units
    for line in lines:
        # A single malformed legacy remark must not exceed Telegram's limit.
        budget = MAX_BOT_MESSAGE_CHARS - header_units - 1
        line = line.encode("utf-16-le", errors="replace")[:budget * 2].decode("utf-16-le", errors="ignore")
        line_units = len(line.encode("utf-16-le")) // 2
        if current_units + line_units + 1 > MAX_BOT_MESSAGE_CHARS:
            chunks.append(current)
            current = header
            current_units = header_units
        current += f"\n{line}"
        current_units += line_units + 1
    chunks.append(current)
    return chunks


async def _handle_update(client: httpx.AsyncClient, config: tuple[str, int], update: dict[str, Any]) -> None:
    active = enabled_config()
    _command_gate.sync(active)
    if active != config or not authorized(update, config[1]):
        return
    message = update["message"]
    if not fresh(datetime.fromtimestamp(message.get("date", 0), timezone.utc).isoformat()):
        return
    command = _normalized_command(str(message.get("text") or "").strip())
    if command is None:
        return
    accepted, remaining, notify = _command_gate.begin(config, command)
    if not accepted:
        if notify:
            try:
                reply = f"操作过于频繁，请 {remaining} 秒后再发送同一指令" if remaining else "上一条指令正在处理，请稍后重试"
                sent = await _send(client, config, reply)
            except BaseException:
                _command_gate.notice_failed(config, command, notify)
                raise
            if not sent:
                _command_gate.notice_failed(config, command, notify)
        return
    delivered = False
    account_names = None
    try:
        if command == "/me":
            try:
                rows = _account_rows(get_telegram_service().list_accounts())
                lines = _account_lines(rows)
                chunks = _message_chunks(lines)
                account_names = tuple(name for name, _remark in rows)
            except Exception as exc:
                logger.warning("读取本地账号清单失败（%s）", type(exc).__name__)
                chunks = ["读取账号清单失败，请稍后重试"]
            for chunk in chunks:
                if not await _send(client, config, chunk):
                    return
            delivered = True
            return
        argument = command.partition(" ")[2]
        numeric = bool(re.fullmatch(r"[0-9]+", argument))
        if numeric:
            names = _command_gate.account_names(config, accepted)
            if names is None:
                delivered = await _send(client, config, "请先发送 /me 获取账号序号，再发送 /code 序号")
                return
            if len(argument) > len(str(len(names))) or not 1 <= int(argument) <= len(names):
                delivered = await _send(client, config, "账号序号无效，请发送 /me 查看清单")
                return
            argument = names[int(argument) - 1]
        try:
            account = validate_storage_name(argument, field_name="account_name")
        except ValueError:
            reply = "账号名无效"
        else:
            service = get_telegram_service()
            if not service.account_exists(account):
                reply = "该序号的账号已不存在，请发送 /me 刷新清单" if numeric else "账号不存在"
            else:
                try:
                    messages = await asyncio.wait_for(
                        service.list_official_messages(account, limit=20),
                        timeout=CODE_READ_TIMEOUT_SECONDS,
                    )
                    code = latest_code(messages)
                    reply = f"{account} 的 Telegram 验证码：{code}" if code else "暂无有效验证码"
                except Exception as exc:
                    logger.warning("按需读取验证码失败（%s）", type(exc).__name__)
                    reply = "验证码读取失败，请稍后重试"
        delivered = await _send(client, config, reply)
    finally:
        active = enabled_config()
        _command_gate.sync(active)
        _command_gate.finish(config, accepted, delivered=delivered and active == config, account_names=account_names)


async def run_code_bot() -> None:
    """Run only in the scheduler-lock owner; poll without enabling a webhook."""
    global _status
    from backend.scheduler.instance_lock import has_scheduler_lock

    offset = 0
    current: tuple[str, int] | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(POLL_TIMEOUT_SECONDS + 5, connect=5)) as client:
        while True:
            try:
                config = enabled_config() if has_scheduler_lock() else None
                _command_gate.sync(config)
                if config is None:
                    current = None
                    _status = "未启用或当前实例未取得调度锁"
                    await asyncio.sleep(1)
                    continue
                if config != current:
                    current = config
                    offset = 0
                    webhook = await _bot_call(client, config[0], "getWebhookInfo", {})
                    if webhook.get("url"):
                        current = None
                        _status = "检测到已有 Webhook；请先在该 Bot 的原管理端停用 Webhook"
                        await asyncio.sleep(POLL_CONFLICT_BACKOFF_SECONDS)
                        continue
                    backlog = await _bot_call(client, config[0], "getUpdates", {"offset": -1, "limit": 1, "timeout": 0, "allowed_updates": ["message"]})
                    offset = max((int(item["update_id"]) for item in backlog), default=offset - 1) + 1
                updates = await _bot_call(client, config[0], "getUpdates", {"offset": offset, "limit": 20, "timeout": POLL_TIMEOUT_SECONDS, "allowed_updates": ["message"]})
                for update in updates:
                    offset = max(offset, int(update["update_id"]) + 1)
                    await _handle_update(client, config, update)
                _status = "运行中（按需查询）"
            except asyncio.CancelledError:
                raise
            except CodeBotError as exc:
                _status = str(exc)
                conflict = "Webhook" in _status or "冲突" in _status
                if conflict:
                    current = None  # re-baseline queued commands when the conflict clears
                logger.warning("私人验证码机器人：%s", _status)
                await asyncio.sleep(POLL_CONFLICT_BACKOFF_SECONDS if conflict else POLL_BACKOFF_SECONDS)
            except Exception as exc:
                _status = "运行异常，请检查服务日志"
                logger.warning("私人验证码机器人运行异常（%s）", type(exc).__name__)
                await asyncio.sleep(POLL_BACKOFF_SECONDS)
