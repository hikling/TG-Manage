"""Exercise actual report, reader and multipart delivery together without Telegram."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest

from backend.services import official_message_report as report
from backend.services import official_report_delivery as delivery
from backend.services.telegram import official_report as reader


@pytest.mark.asyncio
@pytest.mark.parametrize("broken_last_part", [False, True])
async def test_complete_pipeline_preserves_source_bytes_and_rejects_partial_media(
    tmp_path, monkeypatch, broken_last_part,
):
    end = datetime(2026, 10, 14, tzinfo=timezone.utc)
    start = end - timedelta(hours=24)
    chunk_bytes = 64 * 1024
    monkeypatch.setattr(reader, "MEDIA_CHUNK_BYTES", chunk_bytes)
    monkeypatch.setattr(report, "MEDIA_PART_BYTES", chunk_bytes * 2)
    payloads = {
        "photo": b"\xff\xd8source-photo\xff\xd9",
        "video": b"source-video-original-bytes",
        "document": bytes(range(256)) * 769 + b"\x00END\n",
    }
    full_text = "\nOfficial notice <raw> 😀\n\n" * 250
    full_caption = "\nOriginal caption 😀\n" * 90

    def source(message_id, kind=None, *, date=None, outgoing=False, text="", caption=""):
        message = SimpleNamespace(
            id=message_id, date=date or end - timedelta(hours=1),
            text=text, caption=caption, outgoing=outgoing,
            chat=SimpleNamespace(id=777000), media=None,
        )
        if kind:
            message.media = SimpleNamespace(value=kind)
            setattr(message, kind, SimpleNamespace(
                file_id=f"source-{kind}", file_unique_id=kind,
                file_size=len(payloads[kind]), file_name=f"original.{kind}",
                mime_type="application/octet-stream",
            ))
        return message

    rows = [
        source(105, "photo", date=end, text="NEXT-WINDOW-NOTICE"),
        source(104, "photo", outgoing=True, text="OUTGOING-NOTICE"),
        source(103, "photo", text=full_text, caption=full_caption),
        source(102, "video", caption="Video caption"),
        source(101, "document"),
        source(100, "photo", date=start - timedelta(seconds=1), text="OLD-NOTICE"),
    ]
    locks = {name: asyncio.Lock() for name in ("alpha", "quiet")}
    permit = asyncio.Semaphore(1)

    class Client:
        def __init__(self, name):
            self.name = name
            self.active = 0
            self.refreshed = []
            self.streams_closed = 0

        async def __aenter__(self):
            assert locks[self.name].locked() and permit.locked()
            self.active += 1
            return self

        async def __aexit__(self, *_args):
            self.active -= 1

        async def get_chat_history(self, peer, *, limit, offset_id, offset_date):
            assert peer == 777000 and limit == 100 and offset_date == end
            for message in rows if self.name == "alpha" else []:
                if not offset_id or message.id < offset_id:
                    yield message

        async def get_messages(self, peer, message_id, *, replies):
            assert peer == 777000 and replies == 0
            # Outgoing, next-window and old media must never reach download admission.
            assert message_id in {101, 102, 103}
            self.refreshed.append(message_id)
            return next(message for message in rows if message.id == message_id)

        async def stream_media(self, media, *, limit, offset):
            assert self.active == 1 and locks[self.name].locked()
            data = payloads[media.file_unique_id]
            begin = offset * chunk_bytes
            finish = min(len(data), begin + limit * chunk_bytes)
            if broken_last_part and media.file_unique_id == "document" and offset:
                # Match Kurigram's dangerous behavior: an incomplete stream can
                # finish normally after swallowing a transfer failure.
                finish = min(finish, begin + 7)
            try:
                for position in range(begin, finish, chunk_bytes):
                    yield data[position:min(finish, position + chunk_bytes)]
            finally:
                self.streams_closed += 1

    clients = {name: Client(name) for name in locks}

    class Service:
        def list_accounts(self, *, force_refresh):
            assert force_refresh is True
            return [{"name": name} for name in clients]

        def _normalize_account_name(self, name):
            return name

        def account_exists(self, name):
            return name in clients

        def _build_account_client(self, name, *, no_updates):
            assert no_updates is True and locks[name].locked() and permit.locked()
            return clients[name], None

    service = Service()
    target = ("test-pipeline-token", "42", 7)
    monkeypatch.setattr(report, "get_telegram_service", lambda: service)
    monkeypatch.setattr(reader, "get_account_lock", lambda name: locks[name])
    monkeypatch.setattr(reader, "get_global_semaphore", lambda: permit)
    monkeypatch.setattr(report, "current_report_target", lambda: target)
    monkeypatch.setattr(delivery, "current_report_target", lambda: target)

    async def skip_pacing(self, _deadline):
        # Pacing itself has transport-unit coverage. Keep this full pipeline fast
        # while retaining the sender's real configuration ownership checks.
        self._require_current()

    monkeypatch.setattr(delivery.OfficialReportDelivery, "_wait_until", skip_pacing)
    temporary_directory = report.TemporaryDirectory
    monkeypatch.setattr(
        report, "TemporaryDirectory",
        lambda **kwargs: temporary_directory(dir=tmp_path, **kwargs),
    )
    texts, uploads, responses = [], [], []

    async def receive(request):
        # The actual HTTPX multipart sender must run after Telegram ownership exits.
        assert all(client.active == 0 for client in clients.values())
        assert not permit.locked() and all(not lock.locked() for lock in locks.values())
        body = await request.aread()
        method = request.url.path.rsplit("/", 1)[-1]
        if method == "sendMessage":
            content = json.loads(body)
            assert content["chat_id"] == "42" and content["message_thread_id"] == 7
            texts.append(content["text"])
        else:
            message = BytesParser(policy=policy.default).parsebytes(
                b"Content-Type: " + request.headers["content-type"].encode()
                + b"\r\nMIME-Version: 1.0\r\n\r\n" + body,
            )
            parts = list(message.iter_parts())
            uploaded = next(part for part in parts if part.get_filename() is not None)
            fields = {
                part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                for part in parts if part.get_filename() is None
            }
            assert fields["chat_id"] == b"42" and fields["message_thread_id"] == b"7"
            assert "账户：alpha" in fields["caption"].decode()
            uploads.append((method, uploaded.get_filename(), uploaded.get_payload(decode=True)))
        response = httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        responses.append(response)
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        monkeypatch.setattr(delivery, "_get_shared_http_client", lambda: client)
        result = await report.OfficialMessageReportService().run(
            start=start, end=end, timezone="Asia/Shanghai",
        )

    assert result["accounts"] == 2 and result["messages"] == 3
    assert result["empty"] == 1 and result["failed"] == int(broken_last_part)
    assert result["messages_sent"] == len(texts) + len(uploads)
    assert result["stopped"] is False
    assert all(response.is_closed for response in responses)
    assert all(client.active == 0 for client in clients.values())
    assert not permit.locked() and all(not lock.locked() for lock in locks.values())
    assert not list(tmp_path.iterdir())
    assert clients["alpha"].streams_closed == 4
    rendered = "\n".join(texts)
    assert not any(value in rendered for value in ("OLD-NOTICE", "OUTGOING-NOTICE", "NEXT-WINDOW-NOTICE"))
    assert "账户：quiet" in next(text for text in texts if "账户正常" in text)
    assert not any("账户：alpha" in text and "账户正常" in text for text in texts)
    for label, original in (("文字", full_text), ("原始说明", full_caption)):
        chunks = [text.split("\n\n", 1)[1] for text in texts if "#103\n" in text and f"{label} · 分段" in text]
        assert "".join(chunks) == original
    assert uploads[0][0] == "sendPhoto" and uploads[0][2] == payloads["photo"]
    assert uploads[1][0] == "sendVideo" and uploads[1][2] == payloads["video"]
    document_parts = [entry for entry in uploads if entry[0] == "sendDocument"]
    if broken_last_part:
        assert len(document_parts) == 1
        assert "🔴" in rendered and "可能未完整转发" in rendered
        assert "附件全部 2 个分卷已发送" not in rendered
    else:
        assert [entry[1] for entry in document_parts] == [
            "original.document.part0001-of-0002", "original.document.part0002-of-0002",
        ]
        assert b"".join(entry[2] for entry in document_parts) == payloads["document"]
        assert "附件全部 2 个分卷已发送" in rendered
