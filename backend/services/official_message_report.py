"""Complete, attributed 24-hour official notices for the admitted midnight run."""
from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, tzinfo
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from zoneinfo import ZoneInfo

from backend.services.official_report_delivery import (
    MAX_CAPTION_UNITS,
    OfficialReportDelivery,
    OfficialReportStopped,
    current_report_target,
)
from backend.services.telegram import get_telegram_service
from backend.services.telegram.official_report import (
    OfficialMessage,
    OfficialReadError,
    download_official_part,
    read_official_page,
    refresh_official_message,
)

logger = logging.getLogger("backend.official_message_report")
MAX_CONTENT_UNITS = 3500
MEDIA_PART_BYTES = 40 * 1024 * 1024


def _units(text: str) -> int:
    return sum(2 if ord(character) > 0xFFFF else 1 for character in text)


def _slices(text: str, budget: int) -> Iterator[str]:
    """Preserve every character, including separators, without splitting emoji."""
    if budget < 2:
        raise ValueError("Official report attribution exceeds text budget")
    start, units = 0, 0
    for index, character in enumerate(text):
        size = 2 if ord(character) > 0xFFFF else 1
        if units + size > budget:
            yield text[start:index]
            start, units = index, 0
        units += size
    if start < len(text):
        yield text[start:]


def _content_chunks(header: str, content: str, label: str) -> Iterator[str]:
    # Reserve enough part-number digits before slicing, so framing cannot cause
    # truncation. Unlike status rows, raw bodies must retain boundary newlines.
    digits = len(str(max(1, len(content))))
    framing = f"{header}\n{label} · 分段 {'9' * digits}/{'9' * digits}\n\n"
    budget = MAX_CONTENT_UNITS - _units(framing)
    count = sum(1 for _ in _slices(content, budget))
    for index, part in enumerate(_slices(content, budget), 1):
        yield f"{header}\n{label} · 分段 {index}/{count}\n\n{part}"


def _message_header(account: str, message: OfficialMessage, timezone: tzinfo) -> str:
    original_time = datetime.fromtimestamp(message.date_epoch, timezone)
    return (
        f"账户：{account}\nTelegram 官方消息 #{message.id}\n"
        f"原消息时间：{original_time.strftime('%Y-%m-%d %H:%M:%S %z')}"
    )


def _upload_filename(name: str, message_id: int) -> str:
    # A Telegram filename is a display label, never a local destination path.
    leaf = name.replace("\\", "/").rsplit("/", 1)[-1]
    leaf = "".join(character for character in leaf if ord(character) >= 32)
    return leaf if leaf not in {"", ".", ".."} else f"official-{message_id}.bin"


def _require_current(delivery: OfficialReportDelivery) -> None:
    if not delivery.target_is_current():
        raise OfficialReportStopped("Official report target changed")


@contextmanager
def _owned_temporary_directory() -> Iterator[Path]:
    directory = TemporaryDirectory(prefix="tg-official-")
    failed = False
    try:
        yield Path(directory.name)
    except BaseException:
        failed = True
        raise
    finally:
        try:
            directory.cleanup()
        except OSError as exc:
            logger.warning("清理官方消息临时目录失败（%s）", type(exc).__name__)
            # A cleanup error must not replace cancellation or another primary
            # failure. Successful work with failed cleanup is incomplete.
            if not failed:
                raise OfficialReadError("Official media temporary cleanup failed")


class OfficialMessageReportService:
    def __init__(self) -> None:
        self._running_lock = asyncio.Lock()

    async def run(
        self, *, start: datetime, end: datetime, timezone: str | tzinfo,
    ) -> dict[str, Any]:
        target = current_report_target()
        result = {
            "accounts": 0, "messages": 0, "empty": 0, "failed": 0,
            "messages_sent": 0, "stopped": False,
        }
        # Disabled notifications must not cause official-history or media work.
        if target is None or self._running_lock.locked():
            return {**result, "skipped": True}
        if (
            start.utcoffset() is None or end.utcoffset() is None
            or end.timestamp() - start.timestamp() != 24 * 60 * 60
        ):
            raise ValueError("Official report requires an aware, exact 24-hour window")
        display_timezone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone
        async with self._running_lock:
            delivery = OfficialReportDelivery(target)
            try:
                _require_current(delivery)
                service = get_telegram_service()
                names = dict.fromkeys(
                    str(account.get("name") or "").strip()
                    for account in service.list_accounts(force_refresh=True)
                    if str(account.get("name") or "").strip()
                )
                for name in names:
                    _require_current(delivery)
                    result["accounts"] += 1
                    failed, count = await self._account(
                        service, delivery, name, start, end, display_timezone, result,
                    )
                    result["failed"] += int(failed)
                    if not failed and count == 0:
                        try:
                            await self._send_content(
                                delivery, f"账户：{name}",
                                "🟢 账户正常（最近24小时无官方消息）", "零点官方消息日报", result,
                            )
                            result["empty"] += 1
                        except OfficialReportStopped:
                            raise
                        except Exception as exc:
                            result["failed"] += 1
                            logger.warning("官方消息空记录通知发送失败（%s）", type(exc).__name__)
                            await self._failure(delivery, f"账户：{name}", "通知转发失败", result)
            except OfficialReportStopped:
                result["stopped"] = True
            return result

    async def _send_content(
        self, delivery: OfficialReportDelivery, header: str, content: str,
        label: str, result: dict[str, Any],
    ) -> None:
        for text in _content_chunks(header, content, label):
            _require_current(delivery)
            await delivery.send_text(text)
            result["messages_sent"] += 1

    async def _failure(
        self, delivery: OfficialReportDelivery, header: str, reason: str,
        result: dict[str, Any],
    ) -> None:
        try:
            await self._send_content(
                delivery, header, f"🔴 {reason}；此账户的官方消息可能未完整转发。",
                "转发结果", result,
            )
        except OfficialReportStopped:
            raise
        except Exception as exc:
            logger.warning("官方消息失败通知发送失败（%s）", type(exc).__name__)

    async def _account(
        self, service: Any, delivery: OfficialReportDelivery, account: str,
        start: datetime, end: datetime, timezone: tzinfo, result: dict[str, Any],
    ) -> tuple[bool, int]:
        offset_id, count, failed = 0, 0, False
        start_epoch, end_epoch = start.timestamp(), end.timestamp()
        while True:
            try:
                _require_current(delivery)
                page = await read_official_page(service, account, end=end, offset_id=offset_id)
                _require_current(delivery)
                if not page:
                    break
                ids = [message.id for message in page]
                if any(not isinstance(item, int) or item <= 0 for item in ids):
                    raise OfficialReadError("Invalid official history cursor")
                next_offset = min(ids)
                if offset_id and next_offset >= offset_id:
                    raise OfficialReadError("Official history cursor did not progress")
                seen: set[int] = set()
                reached_start = False
                for message in page:
                    if not math.isfinite(message.date_epoch):
                        raise OfficialReadError("Official history date unavailable")
                    if message.date_epoch < start_epoch:
                        reached_start = True
                    # Offset overlaps and duplicates cannot cause double delivery.
                    if message.id in seen or (offset_id and message.id >= offset_id):
                        continue
                    seen.add(message.id)
                    if message.outgoing or not start_epoch <= message.date_epoch < end_epoch:
                        continue
                    count += 1
                    result["messages"] += 1
                    header = _message_header(account, message, timezone)
                    try:
                        await self._message(
                            service, delivery, account, message, header, start, end, result,
                        )
                    except OfficialReportStopped:
                        raise
                    except Exception as exc:
                        failed = True
                        logger.warning("官方消息读取或转发失败（%s）", type(exc).__name__)
                        await self._failure(delivery, header, "消息读取或转发失败", result)
                if reached_start:
                    break
                offset_id = next_offset
            except OfficialReportStopped:
                raise
            except Exception as exc:
                failed = True
                logger.warning("官方消息历史读取失败（%s）", type(exc).__name__)
                await self._failure(delivery, f"账户：{account}", "官方消息历史读取失败", result)
                break
        return failed, count

    async def _message(
        self, service: Any, delivery: OfficialReportDelivery, account: str,
        message: OfficialMessage, header: str, start: datetime, end: datetime,
        result: dict[str, Any],
    ) -> None:
        for label, content in (
            ("文字", message.text), ("原始说明", message.caption),
            ("官方消息详情", message.content_details),
        ):
            if content:
                await self._send_content(delivery, header, content, label, result)
        if message.media is not None:
            await self._media(service, delivery, account, message, header, start, end, result)
        if message.unsupported_kind is not None:
            raise OfficialReadError("Official message payload unsupported or unavailable")
        if not (message.text or message.caption or message.content_details or message.media):
            raise OfficialReadError("Official message content unavailable")

    async def _media(
        self, service: Any, delivery: OfficialReportDelivery, account: str,
        message: OfficialMessage, header: str, start: datetime, end: datetime,
        result: dict[str, Any],
    ) -> None:
        _require_current(delivery)
        message = await refresh_official_message(service, account, message, start=start, end=end)
        _require_current(delivery)
        media = message.media
        if media is None or not isinstance(media.file_size, int) or media.file_size <= 0:
            raise OfficialReadError("Official media size unavailable")
        size = media.file_size
        parts = (size + MEDIA_PART_BYTES - 1) // MEDIA_PART_BYTES
        source_name = media.file_name or f"official-{message.id}.bin"
        filename = _upload_filename(source_name, message.id)
        if parts > 1:
            await self._send_content(
                delivery, header,
                f"附件：{source_name}\n原始大小：{size} 字节\n共 {parts} 个分卷。"
                "下载全部分卷后，按分卷编号从小到大依次拼接原始字节，即可还原原文件；"
                "分卷不是压缩包。未收到全部分卷时文件不完整。",
                "附件还原说明", result,
            )
        with _owned_temporary_directory() as directory:
            for index in range(parts):
                _require_current(delivery)
                offset = index * MEDIA_PART_BYTES
                length = min(MEDIA_PART_BYTES, size - offset)
                destination = directory / f"payload-{index}"
                part_failed = False
                try:
                    await download_official_part(
                        service, account, message, destination, start=start, end=end,
                        offset_bytes=offset, length_bytes=length,
                    )
                    _require_current(delivery)
                    if destination.stat().st_size != length:
                        raise OfficialReadError("Official media part size mismatch")
                    caption = (
                        f"{header}\n附件 {index + 1}/{parts} · 字节 {offset + 1}–{offset + length}/{size}"
                    )
                    named_caption = f"{caption}\n原始文件名：{source_name}"
                    if _units(named_caption) <= MAX_CAPTION_UNITS:
                        caption = named_caption
                    elif parts == 1:
                        await self._send_content(delivery, header, source_name, "原始文件名", result)
                    if _units(caption) > MAX_CAPTION_UNITS:
                        raise OfficialReadError("Official media attribution too long")
                    upload_name = filename if parts == 1 else f"{filename}.part{index + 1:04d}-of-{parts:04d}"
                    await delivery.send_media(
                        destination, kind=media.kind if parts == 1 else "document",
                        filename=upload_name, caption=caption,
                    )
                    result["messages_sent"] += 1
                except BaseException:
                    part_failed = True
                    raise
                finally:
                    try:
                        destination.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning("清理官方消息临时分卷失败（%s）", type(exc).__name__)
                        if not part_failed:
                            # Stop before allocating another part if the prior
                            # part could not be removed; keep disk usage bounded.
                            raise OfficialReadError("Official media part cleanup failed")
        if parts > 1:
            await self._send_content(
                delivery, header, f"附件全部 {parts} 个分卷已发送，共 {size} 字节。",
                "附件转发完成", result,
            )


_service: OfficialMessageReportService | None = None


def get_official_message_report_service() -> OfficialMessageReportService:
    global _service
    if _service is None:
        _service = OfficialMessageReportService()
    return _service
