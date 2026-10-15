"""Fresh account checks and bounded Telegram Bot status reports."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.services.account_check_gate import AccountCheckBusy, account_check_gate
from backend.services.account_routes import account_route_status
from backend.services.config import get_config_service
from backend.services.push_notifications import _bot_config, send_telegram_bot_message
from backend.services.telegram import get_telegram_service
from backend.utils.tg_session import set_account_status
from backend.utils.time import utc_now_iso_z

logger = logging.getLogger("backend.account_status_report")
PROBE_TIMEOUT_SECONDS = 8.0
INTER_DELAY_SECONDS = 0.15
MAX_MESSAGE_UNITS = 3500
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
    *, title: str | None = None,
) -> list[str]:
    def healthy(result: dict[str, Any]) -> bool:
        return (
            bool(result.get("ok"))
            and result.get("route_mode") != "setup_required"
            and result.get("route_status") != "error"
            and (official_status is None or official_status.get(result["account_name"]) == "empty")
        )

    ok_count = sum(healthy(result) for result in results)
    lines = [
        title or ("零点账户状态与官方消息日报" if official_status is not None else "账户状态日报（零点检测）"),
        f"总计 {len(results)} · 正常 {ok_count} · 异常 {len(results) - ok_count}",
        "",
    ]
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
        row = f"{'🟢' if healthy(result) else '🔴'} {name} — {' · '.join(notes)}"
        lines.append(row)
    if not results:
        lines.append("暂无账户")
    return _message_chunks(lines)


async def _send_report(
    results: list[dict[str, Any]], official_status: dict[str, str] | None = None,
    *, title: str | None = None,
) -> int:
    target = _enabled_target()
    if target is None:
        return 0

    sent = 0
    for text in report_chunks(results, official_status, title=title):
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
            )
        except Exception as exc:
            logger.warning("账户状态日报发送失败（%s）", type(exc).__name__)
            break
        sent += 1
    return sent


class AccountStatusReportService:
    def __init__(self) -> None:
        self._running_lock = asyncio.Lock()

    async def run(self, *, send_report: bool = True) -> dict[str, Any]:
        """Check the fresh inventory sequentially, without the interactive cap."""
        if self._running_lock.locked():
            return {"skipped": True, "checked": 0, "messages_sent": 0}
        async with self._running_lock:
            return await self._run(send_report=send_report)

    async def _run(self, *, send_report: bool = True) -> dict[str, Any]:
        service = get_telegram_service()
        names = dict.fromkeys(
            str(account.get("name") or "").strip()
            for account in service.list_accounts(force_refresh=True, strict=True)
            if str(account.get("name") or "").strip()
        )
        pending = [(name, 0.0) for name in names]
        results: dict[str, dict[str, Any]] = {}
        while pending:
            deferred: list[tuple[str, float]] = []
            for name, ready_at in pending:
                if ready_at > time.monotonic():
                    deferred.append((name, ready_at))
                    continue
                try:
                    reservation = account_check_gate.reserve([name])
                except AccountCheckBusy as exc:
                    deferred.append((name, time.monotonic() + exc.remaining_seconds))
                    continue
                try:
                    try:
                        result = await asyncio.wait_for(
                            service.check_account_status(
                                name,
                                timeout_seconds=PROBE_TIMEOUT_SECONDS,
                                no_updates=True,
                            ),
                            # Also bound waits for a shared account client lock.
                            timeout=PROBE_TIMEOUT_SECONDS + 1.0,
                        )
                        if not isinstance(result, dict):
                            raise TypeError("Invalid account status result")
                    except Exception as exc:
                        logger.warning("账户日报检测失败（%s）", type(exc).__name__)
                        result = {
                            "ok": False,
                            "status": "checking" if isinstance(exc, asyncio.TimeoutError) else "error",
                            "code": "TIMEOUT" if isinstance(exc, asyncio.TimeoutError) else "STATUS_CHECK_FAILED",
                            "checked_at": utc_now_iso_z(),
                            "needs_relogin": False,
                        }
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
                    result.update(account_route_status(name))
                    reservation.finish(name, success=bool(result.get("ok")))
                    results[name] = result
                finally:
                    reservation.release()
                await asyncio.sleep(INTER_DELAY_SECONDS)
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
