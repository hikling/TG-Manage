"""Complete official-report transport, safe retry and resource ownership."""
from __future__ import annotations

import asyncio
import json
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest

from backend.services import official_report_delivery as delivery

TARGET = ("token-secret", "12345", 17)
SECRET = "token-secret https://api.telegram.org/bottoken-secret/sendMessage raw-body"
_REAL_CURRENT_TARGET = delivery.current_report_target


class Response:
    def __init__(self, status=200, payload=None, *, json_error=None, close_error=None):
        self.status_code = status
        self.payload = {"ok": True, "result": {"message_id": 1}} if payload is None else payload
        self.json_error = json_error
        self.close_error = close_error
        self.closed = False

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload

    async def aclose(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class Client:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [Response()])
        self.calls = []
        self.streams = []

    async def post(self, url, **kwargs):
        if "files" in kwargs:
            field, (filename, stream, mime) = next(iter(kwargs["files"].items()))
            self.streams.append(stream)
            kwargs = {**kwargs, "upload": (field, filename, stream.read(), mime)}
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def target_config(monkeypatch):
    monkeypatch.setattr(delivery, "current_report_target", lambda: TARGET)


@pytest.fixture
def clock(monkeypatch):
    fake = SimpleNamespace(now=100.0, waits=[], on_sleep=None)
    real_sleep = asyncio.sleep

    async def sleep(seconds):
        fake.waits.append(seconds)
        fake.now += seconds
        if fake.on_sleep:
            fake.on_sleep()
        await real_sleep(0)

    monkeypatch.setattr(delivery, "time", SimpleNamespace(monotonic=lambda: fake.now))
    monkeypatch.setattr(delivery.asyncio, "sleep", sleep)
    return fake


def install_client(monkeypatch, client):
    monkeypatch.setattr(delivery, "_get_shared_http_client", lambda: client)
    return client


def assert_safe(error):
    message = str(error)
    assert "token-secret" not in message
    assert "https://" not in message
    assert "raw-body" not in message


def test_current_target_reuses_status_report_policy(monkeypatch):
    monkeypatch.setattr(delivery, "current_report_target", _REAL_CURRENT_TARGET)
    monkeypatch.setattr(delivery, "_enabled_target", lambda: TARGET)
    assert delivery.current_report_target() == TARGET
    monkeypatch.setattr(delivery, "_enabled_target", lambda: None)
    assert delivery.current_report_target() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["a" * 4096, "😀" * 2048, " \n完整 <b>文字</b>\n😀 "])
async def test_text_is_plain_complete_and_response_closed(monkeypatch, text):
    response = Response()
    client = install_client(monkeypatch, Client([response]))
    await delivery.OfficialReportDelivery(TARGET).send_text(text)
    payload = client.calls[0][1]["json"]
    assert payload == {"chat_id": TARGET[1], "message_thread_id": 17, "text": text}
    assert "parse_mode" not in payload
    assert response.closed
    assert client.calls[0][1]["timeout"].read == delivery.TEXT_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_html_report_text_sets_parse_mode_without_changing_content(monkeypatch):
    client = install_client(monkeypatch, Client())
    text = "账户：A\n\n<b>Telegram 官方消息 #1</b>\n<blockquote>&lt;raw&gt;</blockquote>"
    await delivery.OfficialReportDelivery(TARGET).send_text(text, parse_mode="HTML")
    assert client.calls[0][1]["json"]["text"] == text
    assert client.calls[0][1]["json"]["parse_mode"] == "HTML"


@pytest.mark.asyncio
async def test_unknown_text_parse_mode_rejected_before_send(monkeypatch):
    client = install_client(monkeypatch, Client())
    with pytest.raises(delivery.OfficialReportDeliveryError):
        await delivery.OfficialReportDelivery(TARGET).send_text("notice", parse_mode="MarkdownV2")
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "a" * 4097, "😀" * 2049, "a" * 4095 + "😀", None])
async def test_oversize_and_empty_text_rejected_before_send(monkeypatch, text):
    client = install_client(monkeypatch, Client())
    with pytest.raises(delivery.OfficialReportDeliveryError):
        await delivery.OfficialReportDelivery(TARGET).send_text(text)
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, field", [("photo", "photo"), ("video", "video"), ("document", "document"), ("voice", "document")])
async def test_actual_multipart_upload_preserves_original_bytes(monkeypatch, tmp_path, kind, field):
    original = bytes(range(256)) * 11 + b"\x00\xffcomplete attachment\r\n"
    source = tmp_path / "owned-source"
    source.write_bytes(original)
    requests = []
    responses = []

    async def receive(request):
        body = await request.aread()
        parsed = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {request.headers['content-type']}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        parts = {part.get_param("name", header="content-disposition"): part for part in parsed.iter_parts()}
        requests.append((request, parts))
        response = httpx.Response(200, json={"ok": True})
        responses.append(response)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        install_client(monkeypatch, client)
        await delivery.OfficialReportDelivery(TARGET).send_media(
            source, kind=kind, filename="../../unsafe\\original.bin", caption="账户 A · 原消息 8"
        )
    request, parts = requests[0]
    assert parts[field].get_payload(decode=True) == original
    assert parts[field].get_filename() == "original.bin"
    assert parts["caption"].get_payload(decode=True).decode() == "账户 A · 原消息 8"
    assert parts["chat_id"].get_payload(decode=True) == b"12345"
    assert parts["message_thread_id"].get_payload(decode=True) == b"17"
    assert request.url.path.endswith({"photo": "sendPhoto", "video": "sendVideo"}.get(kind, "sendDocument"))
    assert responses[0].is_closed
    assert source.read_bytes() == original  # Path belongs to the orchestration caller.


@pytest.mark.asyncio
@pytest.mark.parametrize("caption", ["a" * 1025, "😀" * 513])
async def test_caption_budget_rejected_without_file_open(monkeypatch, tmp_path, caption):
    source = tmp_path / "owned"
    source.write_bytes(b"payload")
    client = install_client(monkeypatch, Client())
    with pytest.raises(delivery.OfficialReportDeliveryError):
        await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="document", filename="file", caption=caption)
    assert client.calls == []
    assert client.streams == []


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, delivery.MAX_UPLOAD_BYTES + 1])
async def test_invalid_upload_size_rejected_without_request(monkeypatch, tmp_path, size):
    source = tmp_path / "owned"
    with source.open("wb") as stream:
        stream.truncate(size)
    client = install_client(monkeypatch, Client())
    with pytest.raises(delivery.OfficialReportDeliveryError):
        await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="document", filename="file", caption="")
    assert client.calls == []


@pytest.mark.asyncio
async def test_missing_file_error_is_safe(monkeypatch, tmp_path):
    client = install_client(monkeypatch, Client())
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_media(tmp_path / "token-secret", kind="document", filename="file", caption="")
    assert_safe(error.value)
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, rejection", [("photo", "Bad Request: PHOTO_INVALID_DIMENSIONS"), ("video", "Bad Request: VIDEO_CONTENT_TYPE_INVALID")])
async def test_native_format_rejection_falls_back_to_same_document_bytes(monkeypatch, tmp_path, clock, kind, rejection):
    source = tmp_path / "owned"
    original = b"all original bytes\x00\xff"
    source.write_bytes(original)
    first = Response(400, {"ok": False, "error_code": 400, "description": rejection})
    second = Response()
    client = install_client(monkeypatch, Client([first, second]))
    await delivery.OfficialReportDelivery(TARGET).send_media(source, kind=kind, filename="source.bin", caption="账户 A")
    assert client.calls[1][0].endswith("/sendDocument")
    assert [call[1]["upload"][2] for call in client.calls] == [original, original]
    assert all(stream.closed for stream in client.streams)
    assert first.closed and second.closed
    assert clock.waits == [1.0]


@pytest.mark.asyncio
@pytest.mark.parametrize("status, description", [(400, "Bad Request: chat not found"), (400, "Bad Request: protected content"), (403, "Forbidden: bot was blocked by the user")])
async def test_native_permission_content_and_target_failures_do_not_fallback(monkeypatch, tmp_path, status, description):
    source = tmp_path / "owned"
    source.write_bytes(b"all bytes")
    response = Response(status, {"ok": False, "error_code": status, "description": description + SECRET})
    client = install_client(monkeypatch, Client([response]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="photo", filename="file.jpg", caption="")
    assert_safe(error.value)
    assert len(client.calls) == 1
    assert response.closed
    assert all(stream.closed for stream in client.streams)


@pytest.mark.asyncio
async def test_large_photo_uses_original_document_without_reencoding(monkeypatch, tmp_path):
    source = tmp_path / "owned"
    with source.open("wb") as stream:
        stream.truncate(delivery.PHOTO_MAX_BYTES + 1)
    client = install_client(monkeypatch, Client())
    await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="photo", filename="file.jpg", caption="")
    assert client.calls[0][0].endswith("/sendDocument")
    assert len(client.calls[0][1]["upload"][2]) == delivery.PHOTO_MAX_BYTES + 1
    assert client.calls[0][1]["timeout"].write == delivery.UPLOAD_TIMEOUT_SECONDS
    assert client.streams[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_id, interval", [("12345", 1.0), ("-10012345", 3.1), ("@channel", 3.1)])
async def test_paces_one_target_and_serializes_concurrent_sends(monkeypatch, clock, chat_id, interval):
    target = (TARGET[0], chat_id, None)
    monkeypatch.setattr(delivery, "current_report_target", lambda: target)
    client = install_client(monkeypatch, Client([Response(), Response(), Response()]))
    sender = delivery.OfficialReportDelivery(target)
    await asyncio.gather(*(sender.send_text(f"消息 {index}") for index in range(3)))
    assert len(client.calls) == 3
    assert clock.waits == pytest.approx([interval, interval])
    assert "message_thread_id" not in client.calls[0][1]["json"]


@pytest.mark.asyncio
@pytest.mark.parametrize("http_status", [200, 429])
async def test_retry_after_then_success_closes_response_before_wait(monkeypatch, clock, http_status):
    first = Response(http_status, {"ok": False, "error_code": 429, "parameters": {"retry_after": 7}})
    second = Response()
    client = install_client(monkeypatch, Client([first, second]))
    clock.on_sleep = lambda: pytest.fail("response was retained during retry wait") if not first.closed else None
    await delivery.OfficialReportDelivery(TARGET).send_text("完整内容")
    assert clock.waits == [7.0]
    assert len(client.calls) == 2
    assert first.closed and second.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("retry_after", [None, 0, -1, True, "7", 1.5, float("inf")])
async def test_invalid_retry_after_is_safe_failure_without_retry(monkeypatch, clock, retry_after):
    response = Response(429, {"ok": False, "parameters": {"retry_after": retry_after}, "description": SECRET})
    client = install_client(monkeypatch, Client([response]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert_safe(error.value)
    assert len(client.calls) == 1
    assert clock.waits == []
    assert response.closed


@pytest.mark.asyncio
async def test_flood_retry_attempts_are_bounded(monkeypatch, clock):
    responses = [Response(429, {"ok": False, "parameters": {"retry_after": 2}}) for _ in range(3)]
    client = install_client(monkeypatch, Client(responses))
    with pytest.raises(delivery.OfficialReportDeliveryError):
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert len(client.calls) == 3
    assert clock.waits == [2.0, 2.0]
    assert all(response.closed for response in responses)


@pytest.mark.asyncio
@pytest.mark.parametrize("pause", ["pacing", "flood"])
async def test_target_change_during_wait_stops_without_second_send(monkeypatch, clock, pause):
    response = Response() if pause == "pacing" else Response(429, {"ok": False, "parameters": {"retry_after": 61}})
    client = install_client(monkeypatch, Client([response]))
    sender = delivery.OfficialReportDelivery(TARGET)
    if pause == "pacing":
        await sender.send_text("first")
    clock.on_sleep = lambda: monkeypatch.setattr(delivery, "current_report_target", lambda: None)
    with pytest.raises(delivery.OfficialReportStopped):
        await sender.send_text("second")
    assert len(client.calls) == 1
    assert response.closed
    assert clock.waits == ([1.0] if pause == "pacing" else [30.0])


@pytest.mark.asyncio
async def test_target_change_while_http_is_in_flight_closes_response(monkeypatch):
    response = Response()

    class ChangingClient:
        async def post(self, *_args, **_kwargs):
            monkeypatch.setattr(delivery, "current_report_target", lambda: ("new", "888", None))
            return response

    install_client(monkeypatch, ChangingClient())
    with pytest.raises(delivery.OfficialReportStopped):
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert response.closed


@pytest.mark.asyncio
async def test_disabled_target_sends_nothing(monkeypatch):
    client = install_client(monkeypatch, Client())
    monkeypatch.setattr(delivery, "current_report_target", lambda: None)
    with pytest.raises(delivery.OfficialReportStopped):
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"ok": False, "description": SECRET}, [], {"ok": 1}, {"description": SECRET}])
async def test_http_200_without_true_ok_is_not_delivery_success(monkeypatch, payload):
    response = Response(payload=payload)
    client = install_client(monkeypatch, Client([response]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert_safe(error.value)
    assert response.closed
    assert len(client.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("json_error", [ValueError(SECRET), RuntimeError(SECRET)])
async def test_json_error_is_safe_and_response_closed(monkeypatch, json_error):
    response = Response(json_error=json_error)
    install_client(monkeypatch, Client([response]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert_safe(error.value)
    assert response.closed


@pytest.mark.asyncio
async def test_close_failure_preserves_success_and_sanitizes_logs(monkeypatch, caplog):
    response = Response(close_error=RuntimeError(SECRET))
    install_client(monkeypatch, Client([response]))
    await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert response.closed
    assert "RuntimeError" in caplog.text
    assert "token-secret" not in caplog.text
    assert "raw-body" not in caplog.text
    assert "https://" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["network", "server"])
async def test_transient_failure_retries_then_success(monkeypatch, clock, failure):
    first = httpx.ConnectError(SECRET) if failure == "network" else Response(503, json_error=ValueError(SECRET))
    second = Response()
    client = install_client(monkeypatch, Client([first, second]))
    await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert len(client.calls) == 2
    assert clock.waits == [1.0]
    assert second.closed
    if isinstance(first, Response):
        assert first.closed


@pytest.mark.asyncio
async def test_media_network_failure_reopens_files_without_document_fallback(monkeypatch, tmp_path, clock):
    source = tmp_path / "owned"
    original = b"whole video"
    source.write_bytes(original)
    client = install_client(monkeypatch, Client([httpx.ReadTimeout(SECRET) for _ in range(3)]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="video", filename="file.mp4", caption="")
    assert_safe(error.value)
    assert len(client.calls) == 3
    assert all(call[0].endswith("/sendVideo") for call in client.calls)
    assert [call[1]["upload"][2] for call in client.calls] == [original] * 3
    assert all(stream.closed for stream in client.streams)
    assert clock.waits == [1.0, 2.0]
    source.unlink()  # Windows cannot unlink an open upload file.


@pytest.mark.asyncio
async def test_cancellation_while_uploading_closes_file_and_unlocks(monkeypatch, tmp_path):
    source = tmp_path / "owned"
    source.write_bytes(b"complete bytes")
    entered = asyncio.Event()
    captured = []

    class BlockingClient:
        async def post(self, _url, *, files, **_kwargs):
            captured.append(next(iter(files.values()))[1])
            entered.set()
            await asyncio.Event().wait()

    install_client(monkeypatch, BlockingClient())
    sender = delivery.OfficialReportDelivery(TARGET)
    task = asyncio.create_task(sender.send_media(source, kind="document", filename="file", caption=""))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert captured[0].closed
    assert not sender._send_lock.locked()
    source.unlink()


@pytest.mark.asyncio
async def test_cancellation_during_flood_wait_retains_no_file_or_response(monkeypatch, tmp_path):
    source = tmp_path / "owned"
    source.write_bytes(b"complete bytes")
    response = Response(429, {"ok": False, "parameters": {"retry_after": 60}})
    client = install_client(monkeypatch, Client([response]))
    waiting = asyncio.Event()

    async def blocked_sleep(_seconds):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(delivery.asyncio, "sleep", blocked_sleep)
    sender = delivery.OfficialReportDelivery(TARGET)
    task = asyncio.create_task(sender.send_media(source, kind="document", filename="file", caption=""))
    await waiting.wait()
    assert response.closed
    assert client.streams[0].closed
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not sender._send_lock.locked()
    source.unlink()


@pytest.mark.asyncio
async def test_document_retry_after_reopens_complete_bytes(monkeypatch, tmp_path, clock):
    source = tmp_path / "owned"
    original = b"byte-for-byte part 2/5"
    source.write_bytes(original)
    first = Response(429, {"ok": False, "parameters": {"retry_after": 5}})
    client = install_client(monkeypatch, Client([first, Response()]))
    clock.on_sleep = lambda: pytest.fail("upload file retained during backoff") if any(not stream.closed for stream in client.streams) else None
    await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="document", filename="original.part002", caption="part 2/5")
    assert [call[1]["upload"][2] for call in client.calls] == [original, original]
    assert all(stream.closed for stream in client.streams)
    assert clock.waits == [5.0]


@pytest.mark.asyncio
async def test_real_plain_json_preserves_unicode_bytes(monkeypatch):
    text = "账户 A\n\t😀 <code>原文</code>\n "
    requests = []

    async def receive(request):
        requests.append(json.loads(await request.aread()))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        install_client(monkeypatch, client)
        await delivery.OfficialReportDelivery(TARGET).send_text(text)
    assert requests[0]["text"] == text


@pytest.mark.asyncio
async def test_whole_upload_timeout_is_network_retry_and_closes_each_file(monkeypatch, tmp_path, clock):
    source = tmp_path / "owned"
    source.write_bytes(b"complete bytes")
    client = install_client(monkeypatch, Client([asyncio.TimeoutError(SECRET), Response()]))
    await delivery.OfficialReportDelivery(TARGET).send_media(source, kind="document", filename="file", caption="")
    assert len(client.calls) == 2
    assert all(stream.closed for stream in client.streams)
    assert clock.waits == [1.0]


@pytest.mark.asyncio
async def test_unexpected_http_error_is_sanitized(monkeypatch):
    client = install_client(monkeypatch, Client([RuntimeError(SECRET)]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert_safe(error.value)
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_close_failure_preserves_api_rejection(monkeypatch, caplog):
    response = Response(403, {"ok": False, "error_code": 403}, close_error=RuntimeError(SECRET))
    install_client(monkeypatch, Client([response]))
    with pytest.raises(delivery.OfficialReportDeliveryError) as error:
        await delivery.OfficialReportDelivery(TARGET).send_text("content")
    assert error.value.error_code == 403
    assert response.closed
    assert_safe(error.value)
    assert "RuntimeError" in caplog.text
    assert "token-secret" not in caplog.text
