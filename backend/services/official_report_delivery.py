"""Complete, paced Bot delivery for the explicitly scheduled official report."""
from __future__ import annotations

import asyncio
import logging
import math
import mimetypes
import os
import stat
import time
from pathlib import Path
from typing import Any, BinaryIO

import httpx

from backend.services.account_status_report import _enabled_target
from backend.services.push_notifications import _get_shared_http_client

logger = logging.getLogger("backend.official_report_delivery")

ReportTarget = tuple[str, str, int | None]
MAX_TEXT_UNITS = 4096
MAX_CAPTION_UNITS = 1024
MAX_UPLOAD_BYTES = 50_000_000
PHOTO_MAX_BYTES = 10_000_000
MAX_ATTEMPTS = 3
TEXT_TIMEOUT_SECONDS = 35.0
UPLOAD_TIMEOUT_SECONDS = 300.0


class OfficialReportStopped(RuntimeError):
    """Delivery was disabled or its recipient/credentials/topic changed."""


class OfficialReportDeliveryError(RuntimeError):
    """Safe error containing no remote response, token, URL or message body."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: int | None = None,
        native_format_rejected: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.native_format_rejected = native_format_rejected


def current_report_target() -> ReportTarget | None:
    """Use the same enablement and settings policy as the status report."""
    return _enabled_target()


def _within_budget(value: str, budget: int) -> bool:
    return sum(2 if ord(character) > 0xFFFF else 1 for character in value) <= budget


def _display_filename(filename: str) -> str:
    # This is a multipart display label, never a path used to read/write data.
    name = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join("_" if ord(character) < 32 or ord(character) == 127 else character for character in name)
    return name if name not in {"", ".", ".."} else "attachment"


def _positive_retry_after(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        return None
    value = parameters.get("retry_after")
    # Bot API declares an integer duration. Strings, booleans, negatives and
    # non-finite numbers must not become arbitrary retry sleeps.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    try:
        delay = float(value)
    except OverflowError:
        return None
    return delay if math.isfinite(delay) else None


def _native_format_rejected(method: str, payload: Any, code: int) -> bool:
    if method not in {"sendPhoto", "sendVideo"} or code != 400 or not isinstance(payload, dict):
        return False
    description = payload.get("description")
    if not isinstance(description, str):
        return False
    description = description.lower()
    # Restrict fallback to media-format failures. Permission, protected-content,
    # recipient and ambiguous network failures must remain failures.
    markers = {
        "sendPhoto": (
            "photo_invalid_dimensions",
            "photo_invalid",
            "image_process_failed",
            "photo_ext_invalid",
            "wrong type of the web page content",
        ),
        "sendVideo": (
            "video_content_type_invalid",
            "video_file_invalid",
            "video_invalid",
            "wrong file type",
        ),
    }
    return any(marker in description for marker in markers[method])


class OfficialReportDelivery:
    def __init__(self, target: ReportTarget) -> None:
        self.target = target
        self._send_lock = asyncio.Lock()
        self._next_attempt_at = 0.0
        chat_id = target[1]
        self._interval = 3.1 if chat_id.startswith(("-", "@")) else 1.0

    def target_is_current(self) -> bool:
        return current_report_target() == self.target

    def _require_current(self) -> None:
        if not self.target_is_current():
            raise OfficialReportStopped("官方消息日报推送配置已变更")

    async def _wait_until(self, deadline: float) -> None:
        self._require_current()
        while (remaining := deadline - time.monotonic()) > 0:
            # Revalidate during long flood waits as well as immediately before
            # the next attempt. Cancellation never becomes a delivery failure.
            await asyncio.sleep(min(remaining, 30.0))
            self._require_current()

    def _payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": self.target[1]}
        if self.target[2] is not None:
            payload["message_thread_id"] = self.target[2]
        return payload

    async def send_text(self, text: str) -> None:
        if not isinstance(text, str) or not text or not _within_budget(text, MAX_TEXT_UNITS):
            raise OfficialReportDeliveryError("官方消息日报文字超出单条预算或为空")
        payload = {**self._payload(), "text": text}
        async with self._send_lock:
            await self._send("sendMessage", payload)

    async def send_media(
        self, path: Path, *, kind: str, filename: str, caption: str
    ) -> None:
        if not isinstance(caption, str) or not _within_budget(caption, MAX_CAPTION_UNITS):
            raise OfficialReportDeliveryError("官方消息日报附件说明超出单条预算")
        path = Path(path)
        try:
            file_stat = path.stat()
        except OSError as exc:
            raise OfficialReportDeliveryError(f"官方消息日报附件不可读取（{type(exc).__name__}）") from None
        if not stat.S_ISREG(file_stat.st_mode) or not 0 < file_stat.st_size <= MAX_UPLOAD_BYTES:
            raise OfficialReportDeliveryError("官方消息日报附件大小无效或超出单次上传限制")
        method = {
            "photo": "sendPhoto" if file_stat.st_size <= PHOTO_MAX_BYTES else "sendDocument",
            "video": "sendVideo",
        }.get(kind, "sendDocument")
        payload = {**self._payload(), "caption": caption}
        async with self._send_lock:
            try:
                await self._send(method, payload, path=path, filename=_display_filename(filename))
            except OfficialReportDeliveryError as exc:
                if not exc.native_format_rejected:
                    raise
                # Retry the same original bytes; do not re-encode media to make
                # a native endpoint accept it or discard a complete attachment.
                await self._send("sendDocument", payload, path=path, filename=_display_filename(filename))

    async def _post(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        path: Path | None,
        filename: str,
    ) -> httpx.Response:
        self._require_current()
        client = _get_shared_http_client()
        url = f"https://api.telegram.org/bot{self.target[0]}/{method}"
        if path is None:
            return await asyncio.wait_for(
                client.post(url, json=payload, timeout=httpx.Timeout(TEXT_TIMEOUT_SECONDS, connect=5.0)),
                timeout=TEXT_TIMEOUT_SECONDS,
            )
        try:
            with path.open("rb") as stream:
                self._validate_open_file(stream)
                field = {"sendPhoto": "photo", "sendVideo": "video"}.get(method, "document")
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                return await asyncio.wait_for(
                    client.post(
                        url,
                        data=payload,
                        files={field: (filename, stream, content_type)},
                        timeout=httpx.Timeout(UPLOAD_TIMEOUT_SECONDS, connect=10.0, pool=15.0),
                    ),
                    timeout=UPLOAD_TIMEOUT_SECONDS,
                )
        except asyncio.TimeoutError:
            # wait_for's TimeoutError is also an OSError on supported Python;
            # leave it to the bounded network retry policy, not file handling.
            raise
        except OSError as exc:
            raise OfficialReportDeliveryError(f"官方消息日报附件不可读取（{type(exc).__name__}）") from None

    @staticmethod
    def _validate_open_file(stream: BinaryIO) -> None:
        file_stat = os.fstat(stream.fileno())
        if not stat.S_ISREG(file_stat.st_mode) or not 0 < file_stat.st_size <= MAX_UPLOAD_BYTES:
            raise OfficialReportDeliveryError("官方消息日报附件大小无效或超出单次上传限制")

    async def _send(
        self,
        method: str,
        payload: dict[str, Any],
        *,
        path: Path | None = None,
        filename: str = "",
    ) -> None:
        for attempt in range(MAX_ATTEMPTS):
            await self._wait_until(self._next_attempt_at)
            self._require_current()
            self._next_attempt_at = time.monotonic() + self._interval
            response: httpx.Response | None = None
            retry_delay: float | None = None
            try:
                response = await self._post(method, payload, path=path, filename=filename)
                self._require_current()
                status = response.status_code
                try:
                    result = response.json()
                except (ValueError, UnicodeError):
                    result = None
                if 200 <= status < 300 and isinstance(result, dict) and result.get("ok") is True:
                    return
                code = result.get("error_code") if isinstance(result, dict) else None
                if isinstance(code, bool) or not isinstance(code, int):
                    code = status
                if status == 429 or code == 429:
                    retry_delay = _positive_retry_after(result)
                    if retry_delay is None or attempt + 1 == MAX_ATTEMPTS:
                        raise OfficialReportDeliveryError("官方消息日报发送被限流且无法继续重试", status_code=status, error_code=code)
                elif status >= 500 or code >= 500:
                    if attempt + 1 == MAX_ATTEMPTS:
                        raise OfficialReportDeliveryError("Telegram Bot API 暂时不可用，官方消息日报发送失败", status_code=status, error_code=code)
                    retry_delay = float(attempt + 1)
                else:
                    raise OfficialReportDeliveryError(
                        "Telegram Bot API 拒绝官方消息日报发送",
                        status_code=status,
                        error_code=code,
                        native_format_rejected=_native_format_rejected(method, result, code),
                    )
            except (httpx.RequestError, asyncio.TimeoutError) as exc:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise OfficialReportDeliveryError(f"官方消息日报网络发送失败（{type(exc).__name__}）") from None
                retry_delay = float(attempt + 1)
            except (OfficialReportDeliveryError, OfficialReportStopped):
                raise
            except Exception as exc:
                raise OfficialReportDeliveryError(f"官方消息日报发送失败（{type(exc).__name__}）") from None
            finally:
                if response is not None:
                    try:
                        await response.aclose()
                    except Exception as exc:
                        logger.warning("关闭官方消息日报 HTTP 响应失败（%s）", type(exc).__name__)
            # Release response/file ownership before pacing or flood backoff.
            if retry_delay is not None:
                self._next_attempt_at = max(self._next_attempt_at, time.monotonic() + retry_delay)
        raise OfficialReportDeliveryError("官方消息日报发送失败")
