"""Fresh account checks and bounded Telegram Bot status reports."""
from __future__ import annotations

import asyncio
import logging
import time
from html import escape
from typing import Any

from backend.services.account_check_gate import AccountCheckBusy, account_check_gate
from backend.services.account_routes import account_route_status, get_route_service
from backend.services.config import get_config_service
from backend.services.push_notifications import _bot_config, send_telegram_bot_message
from backend.services.telegram import get_telegram_service
from backend.utils.tg_session import set_account_status
from backend.utils.time import utc_now_iso_z

logger = logging.getLogger("backend.account_status_report")
PROBE_TIMEOUT_SECONDS = 8.0
INTER_DELAY_SECONDS = 0.15
MAX_MESSAGE_UNITS = 3500
REPORT_CONCURRENCY = 6
_ROUTE_RECOVERABLE_CODES = {"TIMEOUT", "CONNECTION_ERROR"}


def _failure_reason(result: dict[str, Any]) -> str:
    if result.get("status") == "not_found" or result.get("code") == "ACCOUNT_NOT_FOUND":
        return "账户已移除"
    if result.get("needs_relogin") or result.get("status") == "invalid":
        return "会话失效，请重新登录"
    return {
        "TIMEOUT": "检测超时",
        "CONNECTION_ERROR": "连接失败",
        "STORAGE_PERMISSION_DENIED": "会话文件不可读写",
        "API_CREDENTIALS_MISSING": "缺少 API 凭据",
    }.get(result.get("code"), "检测失败")


async def _probe_account_status(service: Any, name: str) -> dict[str, Any]:
    try:
        result = await asyncio.wait_for(
            service.check_account_status(
                name, timeout_seconds=PROBE_TIMEOUT_SECONDS, no_updates=True,
            ),
            # Also bound waits for a shared account client lock.
            timeout=PROBE_TIMEOUT_SECONDS + 1.0,
        )
        if not isinstance(result, dict):
            raise TypeError("Invalid account status result")
        return result
    except Exception as exc:
        logger.warning("账户日报检测失败（%s）", type(exc).__name__)
        return {
            "ok": False,
            "status": "checking" if isinstance(exc, asyncio.TimeoutError) else "error",
            "code": "TIMEOUT" if isinstance(exc, asyncio.TimeoutError) else "STATUS_CHECK_FAILED",
            "checked_at": utc_now_iso_z(),
            "needs_relogin": False,
        }


async def _probe_with_midnight_recovery(service: Any, name: str) -> dict[str, Any]:
    result = await _probe_account_status(service, name)
    if result.get("ok"):
        return result

    result = await _probe_account_status(service, name)
    if result.get("ok"):
        return {**result, "midnight_recovery": "retry_recovered"}
    if result.get("status") == "not_found":
        return {**result, "midnight_recovery": "account_removed"}
    if result.get("needs_relogin") or result.get("status") == "invalid" or result.get("code") not in _ROUTE_RECOVERABLE_CODES:
        return {**result, "midnight_recovery": "not_route_related"}

    try:
        if not service.account_exists(name):
            return {
                **result, "ok": False, "status": "not_found",
                "code": "ACCOUNT_NOT_FOUND", "midnight_recovery": "account_removed",
            }
        switched = await get_route_service().switch_account_to_alternate_node(name)
    except Exception as exc:
        logger.warning("账户日报备用节点切换失败（%s）", type(exc).__name__)
        return {**result, "midnight_recovery": "switch_error"}
    if not switched:
        return {**result, "midnight_recovery": "no_alternate"}

    result = await _probe_account_status(service, name)
    return {
        **result,
        "midnight_recovery": "route_recovered" if result.get("ok") else "route_failed",
    }


def _message_chunks(lines: list[str]) -> list[str]:
    """Keep every row, including oversized names, within a UTF-16 budget."""
    chunks: list[str] = []
    current: list[str] = []
    units = 0
    for character in "\n".join(lines):
        size = 2 if ord(character) > 0xFFFF else 1
        if units + size > MAX_MESSAGE_UNITS:
            # Prefer a row boundary when the current row fits in one message.
            text = "".join(current)
            boundary = text.rfind("\n")
            if boundary > 0:
                chunks.append(text[:boundary])
                tail = text[boundary + 1:]
                current = list(tail)
                units = len(tail.encode("utf-16-le")) // 2
            else:
                chunks.append(text)
                current = []
                units = 0
        current.append(character)
        units += size
    if current:
        chunks.append("".join(current))
    return chunks


def _html_message_chunks(lines: list[str]) -> list[str]:
    """Split complete HTML lines without cutting tags or escaped characters."""
    headings = {"零点账户状态与官方消息日报", "零点机场订阅节点报告"}
    chunks: list[str] = []
    current = ""
    current_units = 0

    for line in lines:
        bold = line in headings
        wrapper_units = len("<b></b>") if bold else 0
        max_line_units = MAX_MESSAGE_UNITS - wrapper_units
        part = ""
        part_units = 0
        parts: list[str] = []
        for character in line:
            encoded = escape(character, quote=False)
            units = len(encoded.encode("utf-16-le")) // 2
            if part and part_units + units > max_line_units:
                parts.append(part)
                part = ""
                part_units = 0
            part += encoded
            part_units += units
        parts.append(part)

        for part in parts:
            rendered = f"<b>{part}</b>" if bold else part
            units = len(rendered.encode("utf-16-le")) // 2
            if current and current_units + 1 + units > MAX_MESSAGE_UNITS:
                chunks.append(current)
                current = ""
                current_units = 0
            if current:
                current += "\n" + rendered
                current_units += 1 + units
            else:
                current = rendered
                current_units = units
    if current:
        chunks.append(current)
    return chunks


def _configured_target(config: dict[str, Any] | None = None) -> tuple[str, str, int | None] | None:
    if config is None:
        config = get_config_service().get_global_settings()
    token, chat_id, thread_id = _bot_config(config)
    return (token, chat_id, thread_id) if token and chat_id else None


def _enabled_target() -> tuple[str, str, int | None] | None:
    config = get_config_service().get_global_settings()
    return _configured_target(config) if config.get("telegram_bot_notify_enabled") else None


def report_chunks(
    results: list[dict[str, Any]], official_status: dict[str, str] | None = None,
    *, title: str | None = None, subscription_text: str | None = None,
    status_error: bool = False,
) -> list[str]:
    def healthy(result: dict[str, Any]) -> bool:
        return (
            bool(result.get("ok"))
            and result.get("route_mode") != "setup_required"
            and result.get("route_status") != "error"
            and (official_status is None or official_status.get(result["account_name"]) == "empty")
        )

    heading = title or (
        "零点账户状态与官方消息日报"
        if official_status is not None else "账户状态日报（零点检测）"
    )
    ok_count = sum(healthy(result) for result in results)
    lines = [heading]
    if status_error:
        lines.extend(["账户状态检测失败，暂无可用结果", ""])
    else:
        lines.extend([
            f"总计 {len(results)} · 正常 {ok_count} · 异常 {len(results) - ok_count}",
            "",
        ])
    for result in results:
        username = " ".join(str(result.get("username") or "").split())
        name = f"@{username.lstrip('@')}" if username else result["account_name"]
        name = " ".join(str(name).split())
        notes = []
        if not result.get("ok"):
            notes.append(f"账户异常（{_failure_reason(result)}）")
        else:
            notes.append("账户正常")
        route_label = {
            "primary": "主订阅", "fallback": "兜底订阅",
            "direct": "直出", "setup_required": "待配置订阅",
        }.get(result.get("route_mode"), "路由待确认")
        notes.append(route_label)
        if official_status is None:
            notes.append(result.get("exit_ip") or "IP 未知")
        if official_status is not None:
            official = official_status.get(result["account_name"])
            notes.append({"empty": "无官方新消息", "messages": "有官方新消息"}.get(
                official, "官方消息检测异常"))
        recovery = {
            "retry_recovered": "复检恢复",
            "account_removed": "复检时账户已移除",
            "no_alternate": "复检后仍异常，暂无可用备用节点（出口 IP 未核验或相同）",
            "switch_error": "复检后仍异常，备用节点切换失败",
            "not_route_related": "复检后仍异常，换线无法修复",
            "route_recovered": "换线后恢复",
            "route_failed": "换线复检后仍异常",
        }.get(result.get("midnight_recovery"))
        if recovery:
            notes.append(recovery)
        row = f"{'🟢' if healthy(result) else '🔴'} {name} — {' · '.join(notes)}"
        lines.append(row)
    if not results and not status_error:
        lines.append("暂无账户")
    if subscription_text is not None:
        lines.extend(["", *subscription_text.splitlines()])
        return _html_message_chunks(lines)
    return _message_chunks(lines)


async def _send_report(
    results: list[dict[str, Any]], official_status: dict[str, str] | None = None,
    *, title: str | None = None, subscription_text: str | None = None,
    status_error: bool = False,
) -> int:
    target = _enabled_target()
    if target is None:
        return 0

    sent = 0
    for text in report_chunks(
        results, official_status, title=title,
        subscription_text=subscription_text, status_error=status_error,
    ):
        # Unlike event notifications, this explicitly scheduled report ignores
        # quiet hours. Stop if credentials/target/topic change or are disabled.
        if _enabled_target() != target:
            break
        try:
            await send_telegram_bot_message(
                bot_token=target[0],
                chat_id=target[1],
                message_thread_id=target[2],
                text=text,
                **({"parse_mode": "HTML"} if subscription_text is not None else {}),
            )
        except Exception as exc:
            logger.warning("账户状态日报发送失败（%s）", type(exc).__name__)
            break
        sent += 1
    return sent


def subscription_report_text(
    settings: dict[str, Any], *, refresh_interrupted: bool = False,
) -> str:
    """Summarize the sanitized subscription projection after the midnight refresh."""
    lines = ["零点机场订阅节点报告"]
    if refresh_interrupted:
        lines.append("本次刷新中断，以下为保留节点的状态")
    for source, label in (("primary", "主订阅"), ("fallback", "兜底订阅")):
        item = settings.get(source) or {}
        if not item.get("configured"):
            state = "未配置"
        elif refresh_interrupted or item.get("status") != "ready":
            state = "刷新失败，沿用上次节点"
        else:
            state = "已刷新"
        usable = max(0, int(item.get("usable_count") or 0))
        unavailable = max(0, int(item.get("unsupported_count") or 0))
        lines.append(
            f"{label}（{state}）：可用 {usable} · 不可用/不支持 {unavailable}"
        )
    return "\n".join(lines)


class AccountStatusReportService:
    def __init__(self) -> None:
        self._running_lock = asyncio.Lock()

    async def run(
        self, *, send_report: bool = True, midnight_recovery: bool = False,
    ) -> dict[str, Any]:
        """Check every account with bounded concurrency and no interactive cap."""
        if self._running_lock.locked():
            return {"skipped": True, "checked": 0, "messages_sent": 0}
        async with self._running_lock:
            return await self._run(
                send_report=send_report, midnight_recovery=midnight_recovery,
            )

    async def _run(
        self, *, send_report: bool = True, midnight_recovery: bool = False,
    ) -> dict[str, Any]:
        service = get_telegram_service()
        names = dict.fromkeys(
            str(account.get("name") or "").strip()
            for account in service.list_accounts(force_refresh=True, strict=True)
            if str(account.get("name") or "").strip()
        )
        pending = [(name, 0.0) for name in names]
        results: dict[str, dict[str, Any]] = {}
        semaphore = asyncio.Semaphore(REPORT_CONCURRENCY)

        async def check_one(name: str, ready_at: float) -> tuple[str, dict[str, Any] | float]:
            async with semaphore:
                if ready_at > time.monotonic():
                    return name, ready_at
                try:
                    reservation = account_check_gate.reserve([name])
                except AccountCheckBusy as exc:
                    return name, time.monotonic() + exc.remaining_seconds
                try:
                    result = await (
                        _probe_with_midnight_recovery(service, name)
                        if midnight_recovery else _probe_account_status(service, name)
                    )
                    result = {**result, "account_name": name}
                    # The existing probe persists healthy/invalid sessions.
                    # Persist other fresh failures too, but never recreate a
                    # removed account's local metadata.
                    if not result.get("ok") and result.get("status") not in {
                        "invalid", "not_found",
                    }:
                        try:
                            from backend.utils.account_locks import get_account_lock

                            lock = get_account_lock(name)
                            await asyncio.wait_for(lock.acquire(), timeout=0.5)
                            try:
                                if service.account_exists(name):
                                    set_account_status(
                                        name,
                                        status=result.get("status") or "error",
                                        message=_failure_reason(result),
                                        code=result.get("code") or "STATUS_CHECK_FAILED",
                                        needs_relogin=bool(result.get("needs_relogin")),
                                    )
                            finally:
                                lock.release()
                        except Exception as exc:
                            logger.warning("保存账户日报状态失败（%s）", type(exc).__name__)
                    try:
                        result.update(account_route_status(name))
                    except Exception as exc:
                        logger.warning("账户日报线路状态读取失败（%s）", type(exc).__name__)
                        result["route_status"] = "error"
                    reservation.finish(name, success=bool(result.get("ok")))
                    await asyncio.sleep(INTER_DELAY_SECONDS)
                    return name, result
                finally:
                    reservation.release()

        async def check_one_safely(name: str, ready_at: float) -> tuple[str, dict[str, Any] | float]:
            try:
                return await check_one(name, ready_at)
            except Exception as exc:
                logger.warning("账户日报处理失败（%s）", type(exc).__name__)
                return name, {
                    "account_name": name, "ok": False, "status": "error",
                    "code": "STATUS_CHECK_FAILED", "checked_at": utc_now_iso_z(),
                    "needs_relogin": False, "route_status": "error",
                }

        while pending:
            deferred: list[tuple[str, float]] = []
            # asyncio.gather also supports the project's Python 3.10 minimum.
            outcomes = await asyncio.gather(
                *(check_one_safely(name, ready_at) for name, ready_at in pending)
            )
            for name, outcome in outcomes:
                if isinstance(outcome, dict):
                    results[name] = outcome
                else:
                    deferred.append((name, outcome))
            pending = deferred
            if pending:
                await asyncio.sleep(max(0.0, min(ready for _, ready in pending) - time.monotonic()))

        ordered = [results[name] for name in names]
        sent = await _send_report(ordered) if send_report else 0
        ok_count = sum(bool(result.get("ok")) for result in ordered)
        summary = {
            "checked": len(ordered),
            "ok": ok_count,
            "fail": len(ordered) - ok_count,
            "messages_sent": sent,
        }
        if not send_report:
            summary["rows"] = ordered
        return summary


_service: AccountStatusReportService | None = None


def get_account_status_report_service() -> AccountStatusReportService:
    global _service
    if _service is None:
        _service = AccountStatusReportService()
    return _service
