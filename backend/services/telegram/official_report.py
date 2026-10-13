"""Bounded, operation-owned Telegram reads for the admitted midnight report."""
from __future__ import annotations

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, TypeVar

from backend.utils.account_locks import get_account_lock
from backend.utils.tg_session import get_global_semaphore

MEDIA_CHUNK_BYTES = 1024 * 1024
OFFICIAL_PAGE_SIZE = 100
_DOWNLOADABLE = (
    "audio", "document", "photo", "sticker", "animation", "video", "voice",
    "video_note", "new_chat_photo",
)
_CONTENT_FIELDS = {
    "contact": ("phone_number", "first_name", "last_name", "user_id", "vcard"),
    "location": ("latitude", "longitude", "horizontal_accuracy", "live_period", "heading", "proximity_alert_radius"),
    "venue": ("title", "address", "foursquare_id", "foursquare_type", "google_place_id", "google_place_type"),
    "poll": ("id", "question", "explanation", "total_voter_count", "is_closed", "is_anonymous", "type", "allows_multiple_answers", "correct_option_id"),
    "dice": ("emoji", "value"),
    "web_page": ("url", "display_url", "type", "site_name", "title", "description", "author"),
    "game": ("title", "short_name", "description"),
    "invoice": ("title", "description", "currency", "total_amount", "start_parameter"),
    "story": ("id", "date", "expire_date", "caption"),
    "paid_media": ("star_count",),
    "checklist": ("title",),
}
_SERVICE_FIELDS = (
    "name", "title", "text", "description", "button_text", "data", "duration",
    "start_date", "date", "months", "currency", "total_amount", "amount",
    "star_count", "stars", "message", "domain", "is_unclaimed", "is_via_giveaway",
)
logger = logging.getLogger("backend.telegram.official_report")
_T = TypeVar("_T")


class OfficialReadError(RuntimeError):
    """Safe read failure whose message never contains Telegram source content."""


@dataclass(frozen=True)
class OfficialMedia:
    kind: str
    file_id: str
    file_unique_id: str
    file_size: int | None
    file_name: str
    mime_type: str
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class OfficialMessage:
    id: int
    date_epoch: float
    text: str
    caption: str
    outgoing: bool
    media: OfficialMedia | None
    unsupported_kind: str | None = None
    content_details: str = ""


def _positive_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def _string(value: Any) -> str:
    # Pyrogram Str subclasses str. Never stringify raw messages or clients.
    return value if isinstance(value, str) else ""


def _kind(value: Any) -> str:
    return _string(getattr(value, "value", value)) or "unknown"


def _scalar(value: Any) -> str | None:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    enum_value = getattr(value, "value", None)
    return str(enum_value) if isinstance(enum_value, (str, int)) else None


def _field_details(kind: str, content: Any, fields: tuple[str, ...]) -> list[str]:
    rows = [f"内容类型：{kind}"]
    scalar = _scalar(content)
    if scalar is not None:
        rows.append(scalar)
    else:
        for field in fields:
            value = _scalar(getattr(content, field, None))
            if value is not None:
                rows.append(f"{field}: {value}")
    return rows


def _content_details(message: Any) -> tuple[str, str | None]:
    rows: list[str] = []
    unsupported = None
    for kind, fields in _CONTENT_FIELDS.items():
        content = getattr(message, kind, None)
        if content is None:
            continue
        unsupported = kind
        rows.extend(_field_details(kind, content, fields))
        if kind == "venue":
            location = getattr(content, "location", None)
            if location is not None:
                rows.extend(_field_details("location", location, _CONTENT_FIELDS["location"]))
        if kind in {"poll", "checklist"}:
            children = getattr(content, "options" if kind == "poll" else "tasks", None) or []
            for child in children:
                rows.extend(_field_details("option" if kind == "poll" else "task", child, ("id", "text", "voter_count")))
    service = getattr(message, "service", None)
    if service is not None:
        kind = _kind(service)
        rows.extend(_field_details(f"service:{kind}", getattr(message, kind, None), _SERVICE_FIELDS))
        # A type label is not proof of a complete non-downloadable service payload.
        if kind != "new_chat_photo":
            unsupported = f"service:{kind}"
    return "\n".join(rows), unsupported


def _project_message(message: Any) -> OfficialMessage:
    message_id = _positive_int(getattr(message, "id", None))
    date = getattr(message, "date", None)
    if message_id is None or not isinstance(date, datetime) or getattr(message, "empty", False):
        raise OfficialReadError("official_message_metadata_unavailable")
    chat = getattr(message, "chat", None)
    if chat is not None and getattr(chat, "id", None) != 777000:
        raise OfficialReadError("official_source_changed")
    # Installed Kurigram uses datetime.fromtimestamp() without a timezone.
    # timestamp() recovers that source epoch; relabeling naive dates as UTC loses it.
    epoch = date.timestamp()
    if not math.isfinite(epoch):
        raise OfficialReadError("official_message_date_unavailable")
    details, unsupported = _content_details(message)
    media = None
    for kind in _DOWNLOADABLE:
        payload = getattr(message, kind, None)
        if payload is None:
            continue
        media = OfficialMedia(
            kind=kind,
            file_id=_string(getattr(payload, "file_id", None)),
            file_unique_id=_string(getattr(payload, "file_unique_id", None)),
            file_size=_positive_int(getattr(payload, "file_size", None)),
            file_name=_string(getattr(payload, "file_name", None)),
            mime_type=_string(getattr(payload, "mime_type", None)),
            width=_positive_int(getattr(payload, "width", None)),
            height=_positive_int(getattr(payload, "height", None)),
        )
        break
    if media is None and getattr(message, "media", None) is not None and unsupported is None:
        unsupported = _kind(message.media)
    if getattr(message, "has_protected_content", False):
        unsupported = "protected_content"
    text = _string(getattr(message, "text", None))
    caption = _string(getattr(message, "caption", None))
    if not text and not caption and media is None and not details and unsupported is None:
        unsupported = "empty_content"
    return OfficialMessage(
        id=message_id, date_epoch=epoch,
        text=text, caption=caption,
        outgoing=bool(getattr(message, "outgoing", False)),
        media=media, unsupported_kind=unsupported, content_details=details,
    )


def _boundary_epoch(value: datetime) -> float:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OfficialReadError("official_window_requires_timezone")
    epoch = value.timestamp()
    if not math.isfinite(epoch):
        raise OfficialReadError("official_window_invalid")
    return epoch


def _assert_in_window(message: OfficialMessage, start: datetime, end: datetime) -> None:
    lower, upper = _boundary_epoch(start), _boundary_epoch(end)
    if lower >= upper or message.outgoing or not math.isfinite(message.date_epoch) or not lower <= message.date_epoch < upper:
        raise OfficialReadError("official_message_outside_window")


def _account_name(service: Any, account: str) -> str:
    name = service._normalize_account_name(account)
    if not service.account_exists(name):
        raise OfficialReadError("official_account_unavailable")
    return name


@asynccontextmanager
async def _client_for_account(service: Any, account: str):
    # Same canonical ordering as chat operations, while retaining report-specific
    # typed failures instead of translating them into browser HTTP responses.
    async with get_account_lock(account):
        async with get_global_semaphore():
            client, _ = service._build_account_client(account, no_updates=True)
            primary: BaseException | None = None
            try:
                async with client:
                    try:
                        yield client
                    except BaseException as exc:
                        primary = exc
                        raise
            except Exception as exc:
                if primary is not None and exc is not primary:
                    logger.warning("Official client cleanup failed (%s)", type(exc).__name__)
                    # Preserve the admitted operation's failure/cancellation even
                    # if shared-client context exit has a secondary failure.
                    raise primary from None
                raise


async def _bounded(operation: Awaitable[_T], timeout_seconds: float) -> _T:
    try:
        deadline = float(timeout_seconds)
        if not math.isfinite(deadline) or deadline <= 0:
            raise ValueError
    except (TypeError, ValueError):
        # These operations are owned coroutines; invalid admission must not leave
        # one unawaited or start a client.
        close = getattr(operation, "close", None)
        if close is not None:
            close()
        raise OfficialReadError("official_timeout_invalid") from None
    try:
        return await asyncio.wait_for(operation, timeout=deadline)
    except OfficialReadError:
        raise
    except asyncio.TimeoutError:
        raise OfficialReadError("official_read_timeout") from None
    except Exception:
        raise OfficialReadError("official_read_failed") from None


async def _close_iterator(iterator: Any, *, failed: bool = False) -> None:
    close = getattr(iterator, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception as exc:
            logger.warning("Official iterator cleanup failed (%s)", type(exc).__name__)
            # Cleanup must not replace cancellation or a typed primary failure.
            # If reading otherwise succeeded, failed closure is incomplete work.
            if not failed:
                raise OfficialReadError("official_iterator_cleanup_failed") from None


async def read_official_page(
    service: Any, account: str, *, end: datetime, offset_id: int = 0,
    timeout_seconds: float = 30.0,
) -> list[OfficialMessage]:
    """Read one page and release every Telegram resource before returning it."""
    async def read() -> list[OfficialMessage]:
        _boundary_epoch(end)
        if not isinstance(offset_id, int) or isinstance(offset_id, bool) or offset_id < 0:
            raise OfficialReadError("official_cursor_invalid")
        name = _account_name(service, account)
        async with _client_for_account(service, name) as client:
            iterator = client.get_chat_history(
                777000, limit=OFFICIAL_PAGE_SIZE, offset_id=offset_id,
                offset_date=end.astimezone(timezone.utc),
            )
            rows: list[OfficialMessage] = []
            failed = False
            try:
                async for raw_message in iterator:
                    rows.append(_project_message(raw_message))
                    if len(rows) == OFFICIAL_PAGE_SIZE:
                        break
            except BaseException:
                failed = True
                raise
            finally:
                await _close_iterator(iterator, failed=failed)
            return rows

    return await _bounded(read(), timeout_seconds)


def _assert_same_payload(original: OfficialMessage, fresh: OfficialMessage) -> None:
    old, new = original.media, fresh.media
    if fresh.id != original.id or fresh.date_epoch != original.date_epoch or old is None or new is None:
        raise OfficialReadError("official_source_changed")
    if not old.file_unique_id or new.file_unique_id != old.file_unique_id or new.kind != old.kind:
        raise OfficialReadError("official_media_identity_changed")
    if old.file_size is not None and old.file_size != new.file_size:
        raise OfficialReadError("official_media_size_changed")
    if not new.file_id or new.file_size is None or original.unsupported_kind is not None or fresh.unsupported_kind is not None:
        raise OfficialReadError("official_media_unavailable")


async def _refresh_with_client(client: Any, message: OfficialMessage, start: datetime, end: datetime) -> OfficialMessage:
    _assert_in_window(message, start, end)
    raw_message = await client.get_messages(777000, message.id, replies=0)
    fresh = _project_message(raw_message)
    _assert_in_window(fresh, start, end)
    _assert_same_payload(message, fresh)
    return fresh


async def refresh_official_message(
    service: Any, account: str, message: OfficialMessage, *, start: datetime,
    end: datetime, timeout_seconds: float = 30.0,
) -> OfficialMessage:
    """Refresh references/unknown size without changing the original payload."""
    async def refresh() -> OfficialMessage:
        _assert_in_window(message, start, end)
        name = _account_name(service, account)
        async with _client_for_account(service, name) as client:
            return await _refresh_with_client(client, message, start, end)

    return await _bounded(refresh(), timeout_seconds)


async def download_official_part(
    service: Any, account: str, message: OfficialMessage, destination: Path, *,
    start: datetime, end: datetime, offset_bytes: int, length_bytes: int,
    timeout_seconds: float = 120.0,
) -> None:
    """Write exactly one range; caller owns its generated, exclusive temp path."""
    async def download() -> None:
        created = completed = False
        try:
            _assert_in_window(message, start, end)
            if (
                not isinstance(offset_bytes, int) or isinstance(offset_bytes, bool)
                or offset_bytes < 0 or offset_bytes % MEDIA_CHUNK_BYTES
                or not isinstance(length_bytes, int) or isinstance(length_bytes, bool)
                or length_bytes <= 0
            ):
                raise OfficialReadError("official_media_range_invalid")
            name = _account_name(service, account)
            async with _client_for_account(service, name) as client:
                fresh = await _refresh_with_client(client, message, start, end)
                media = fresh.media
                assert media is not None and media.file_size is not None
                if offset_bytes + length_bytes > media.file_size:
                    raise OfficialReadError("official_media_range_invalid")
                # A short range is valid only at EOF; interior parts align to chunks.
                if length_bytes % MEDIA_CHUNK_BYTES and offset_bytes + length_bytes != media.file_size:
                    raise OfficialReadError("official_media_range_invalid")
                iterator = client.stream_media(
                    media, limit=math.ceil(length_bytes / MEDIA_CHUNK_BYTES),
                    offset=offset_bytes // MEDIA_CHUNK_BYTES,
                )
                received = chunks = 0
                failed = False
                try:
                    with destination.open("xb") as output:
                        created = True
                        async for chunk in iterator:
                            remaining = length_bytes - received
                            expected = min(MEDIA_CHUNK_BYTES, remaining)
                            if not isinstance(chunk, bytes) or len(chunk) != expected or expected <= 0:
                                raise OfficialReadError("official_media_incomplete")
                            output.write(chunk)
                            received += len(chunk)
                            chunks += 1
                        if received != length_bytes or chunks != math.ceil(length_bytes / MEDIA_CHUNK_BYTES):
                            raise OfficialReadError("official_media_incomplete")
                except BaseException:
                    failed = True
                    raise
                finally:
                    await _close_iterator(iterator, failed=failed)
            # Client/permit/lock are released before a verified part reaches Bot code.
            if destination.stat().st_size != length_bytes:
                raise OfficialReadError("official_media_incomplete")
            completed = True
        finally:
            if created and not completed:
                try:
                    destination.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("Official temporary part cleanup failed (%s)", type(exc).__name__)

    await _bounded(download(), timeout_seconds)
