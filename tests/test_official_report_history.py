"""Daily official reads preserve source time/bytes and bounded client ownership."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.services.telegram import official_report as reader

END = datetime(2026, 10, 13, tzinfo=timezone.utc)
START = END - timedelta(hours=24)


def raw_message(message_id=8, *, date=None, kind=None, data=b"abcdefghijk", **kwargs):
    fields = {
        "id": message_id, "date": date or END - timedelta(seconds=1), "outgoing": False,
        "text": "full text\n🙂", "caption": "independent caption\n ", "chat": SimpleNamespace(id=777000),
    }
    if kind:
        fields[kind] = SimpleNamespace(
            file_id="access-reference", file_unique_id="immutable-payload-id",
            file_size=len(data), file_name="../../original name.bin",
            mime_type="application/octet-stream", width=123, height=456,
        )
    fields.update(kwargs)
    return SimpleNamespace(**fields)


class Client:
    def __init__(self, lock, permit):
        self.lock, self.permit = lock, permit
        self.references = self.enters = self.exits = 0
        self.history_closed = self.stream_closed = 0
        self.history_calls = []
        self.stream_calls = []
        self.pages = {0: []}
        self.refresh = raw_message(kind="document")
        self.refresh_calls = []
        self.payload = b"abcdefghijk"
        self.stream_override = None
        self.block_history = self.block_stream = False
        self.history_started = asyncio.Event()
        self.stream_started = asyncio.Event()
        self.failure = None

    async def __aenter__(self):
        assert self.lock.locked() and self.permit.locked()
        self.references += 1
        self.enters += 1
        return self

    async def __aexit__(self, *_args):
        self.references -= 1
        self.exits += 1

    async def get_chat_history(self, chat_id, **kwargs):
        assert chat_id == 777000
        self.history_calls.append(kwargs)
        try:
            self.history_started.set()
            if self.block_history:
                await asyncio.Event().wait()
            if self.failure:
                raise self.failure
            for row in self.pages[kwargs["offset_id"]]:
                yield row
        finally:
            self.history_closed += 1

    async def get_messages(self, chat_id, message_id, *, replies):
        assert chat_id == 777000 and replies == 0
        self.refresh_calls.append(message_id)
        return self.refresh

    async def stream_media(self, media, *, limit, offset):
        self.stream_calls.append((media, limit, offset))
        try:
            self.stream_started.set()
            if self.block_stream:
                yield self.payload[:reader.MEDIA_CHUNK_BYTES]
                await asyncio.Event().wait()
            if self.failure:
                raise self.failure
            if self.stream_override is not None:
                for chunk in self.stream_override:
                    yield chunk
                return
            start = offset * reader.MEDIA_CHUNK_BYTES
            stop = min(len(self.payload), start + limit * reader.MEDIA_CHUNK_BYTES)
            for position in range(start, stop, reader.MEDIA_CHUNK_BYTES):
                yield self.payload[position:min(stop, position + reader.MEDIA_CHUNK_BYTES)]
        finally:
            self.stream_closed += 1


@pytest.fixture
def context(monkeypatch):
    lock, permit = asyncio.Lock(), asyncio.Semaphore(1)
    client = Client(lock, permit)
    builds = []

    class Service:
        def _normalize_account_name(self, name):
            return name.strip()

        def account_exists(self, name):
            return name == "alpha"

        def _build_account_client(self, name, *, no_updates):
            assert name == "alpha" and no_updates is True
            assert lock.locked() and permit.locked()
            builds.append(name)
            return client, None

    monkeypatch.setattr(reader, "get_account_lock", lambda name: lock)
    monkeypatch.setattr(reader, "get_global_semaphore", lambda: permit)
    return SimpleNamespace(service=Service(), client=client, lock=lock, permit=permit, builds=builds)


def assert_released(context):
    assert not context.lock.locked()
    assert not context.permit.locked()
    assert context.client.references == 0
    assert context.client.enters == context.client.exits


async def download(context, tmp_path, message=None, *, offset=0, length=11, **kwargs):
    if message is None:
        message = reader._project_message(context.client.refresh)
    destination = tmp_path / "generated-part.bin"
    await reader.download_official_part(
        context.service, "alpha", message, destination, start=START, end=END,
        offset_bytes=offset, length_bytes=length, **kwargs,
    )
    return destination


@pytest.mark.asyncio
async def test_all_pages_are_read_without_manual_fifty_item_cap(context):
    all_rows = [raw_message(i) for i in range(250, 0, -1)]
    # A short intermediate page is followed by more history, not an EOF.
    context.client.pages = {
        0: all_rows[:100], 151: all_rows[100:125],
        126: all_rows[125:225], 26: all_rows[225:], 1: [],
    }
    rows, offset = [], 0
    while True:
        page = await reader.read_official_page(context.service, " alpha ", end=END, offset_id=offset)
        assert_released(context)
        if not page:
            break
        rows.extend(page)
        offset = min(row.id for row in page)
    assert [row.id for row in rows] == list(range(250, 0, -1))
    assert all(call["limit"] == 100 and call["offset_date"] == END for call in context.client.history_calls)
    assert context.client.history_closed == 5


@pytest.mark.asyncio
async def test_page_caps_memory_and_closes_generator_at_limit(context):
    context.client.pages[0] = [raw_message(i) for i in range(101, 0, -1)]
    rows = await reader.read_official_page(context.service, "alpha", end=END)
    assert len(rows) == 100 and rows[-1].id == 2
    assert context.client.history_closed == 1
    assert_released(context)


@pytest.mark.asyncio
async def test_page_preserves_complete_text_caption_and_filtering_metadata(context):
    times = [START - timedelta(seconds=1), START, END - timedelta(seconds=1), END, END + timedelta(seconds=1)]
    context.client.pages[0] = [raw_message(i, date=date, outgoing=i == 2) for i, date in enumerate(times, 1)]
    page = await reader.read_official_page(context.service, "alpha", end=END)
    assert [row.date_epoch for row in page] == [date.timestamp() for date in times]
    assert page[1].outgoing is True
    assert all(row.text == "full text\n🙂" and row.caption == "independent caption\n " for row in page)
    assert context.client.stream_calls == []


@pytest.mark.asyncio
async def test_naive_host_local_dates_use_their_source_timestamp(context):
    class HostLocalDate(datetime):
        def timestamp(self):
            if self.tzinfo is None:
                return (END - timedelta(seconds=1)).timestamp()
            return super().timestamp()

    # Model installed-library naive UTC+8 clock components; relabeling UTC gives
    # an epoch eight hours later and must never be used by this reader.
    local_date = HostLocalDate(2026, 10, 13, 7, 59, 59)
    assert local_date.replace(tzinfo=timezone.utc).timestamp() == END.timestamp() - 1 + 8 * 3600
    context.client.pages[0] = [raw_message(date=local_date), raw_message(7, date=datetime.fromtimestamp(START.timestamp()))]
    page = await reader.read_official_page(context.service, "alpha", end=END)
    assert page[0].date_epoch == END.timestamp() - 1
    assert page[1].date_epoch == START.timestamp()


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [(2026, 3, 9), (2026, 11, 2)])
async def test_aware_dst_dates_keep_exact_elapsed_window(context, day):
    local_end = datetime(*day, tzinfo=ZoneInfo("America/New_York"))
    utc_end = local_end.astimezone(timezone.utc)
    utc_start = utc_end - timedelta(hours=24)
    context.client.pages[0] = [raw_message(date=utc_start.astimezone(ZoneInfo("America/New_York")))]
    rows = await reader.read_official_page(context.service, "alpha", end=local_end)
    assert rows[0].date_epoch == utc_end.timestamp() - 86400
    assert context.client.history_calls[0]["offset_date"] == utc_end


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"date": None}, {"id": None}, {"empty": True}, {"chat": SimpleNamespace(id=123)}])
async def test_unavailable_metadata_is_failure_not_empty(context, changes):
    row = raw_message()
    for key, value in changes.items():
        setattr(row, key, value)
    context.client.pages[0] = [row]
    with pytest.raises(reader.OfficialReadError):
        await reader.read_official_page(context.service, "alpha", end=END)
    assert context.client.history_closed == 1
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["photo", "video", "document", "audio", "voice", "sticker", "animation", "video_note", "new_chat_photo"])
async def test_downloadable_media_types_preserve_bytes_metadata(context, tmp_path, kind):
    context.client.refresh = raw_message(kind=kind)
    context.client.pages[0] = [context.client.refresh]
    message = (await reader.read_official_page(context.service, "alpha", end=END))[0]
    assert message.media.kind == kind
    assert message.media.file_size == 11
    assert message.media.file_name == "../../original name.bin"
    assert message.media.width == 123 and message.media.height == 456
    destination = await download(context, tmp_path, message)
    assert destination.read_bytes() == context.client.payload
    assert context.client.stream_calls[0][0].file_unique_id == "immutable-payload-id"
    assert_released(context)


@pytest.mark.asyncio
async def test_typed_non_downloadable_and_service_fields_never_dump_raw_objects(context):
    contact = SimpleNamespace(phone_number="+1234", first_name="Name", vcard="FULL\nVCARD\n", raw="SECRET")
    context.client.pages[0] = [
        raw_message(contact=contact, text="", caption=""),
        raw_message(7, service="new_chat_title", new_chat_title="whole title\n🙂", text="", caption=""),
        raw_message(6, media="unsupported", text="", caption=""),
    ]
    page = await reader.read_official_page(context.service, "alpha", end=END)
    assert page[0].unsupported_kind == "contact"
    assert "+1234" in page[0].content_details and "FULL\nVCARD\n" in page[0].content_details
    assert "SECRET" not in page[0].content_details and "namespace(" not in page[0].content_details
    assert "whole title\n🙂" in page[1].content_details
    assert page[1].unsupported_kind == "service:new_chat_title"
    assert page[2].unsupported_kind == "unsupported"


@pytest.mark.asyncio
async def test_part_offsets_reconstruct_all_bytes_and_release_before_caller(context, tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "MEDIA_CHUNK_BYTES", 8)
    context.client.payload = bytes(range(21))
    context.client.refresh = raw_message(kind="document", data=context.client.payload)
    message = reader._project_message(context.client.refresh)
    parts = []
    for index, (offset, length) in enumerate([(0, 16), (16, 5)]):
        destination = tmp_path / f"generated-{index}.bin"
        await reader.download_official_part(
            context.service, "alpha", message, destination, start=START, end=END,
            offset_bytes=offset, length_bytes=length,
        )
        assert_released(context)  # Bot upload/retry may start here without Telegram resources.
        parts.append(destination.read_bytes())
        destination.unlink()
    assert b"".join(parts) == context.client.payload
    assert [(limit, offset) for _, limit, offset in context.client.stream_calls] == [(2, 0), (1, 2)]
    assert context.client.stream_closed == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [[], [b"short"], [b"a" * 12], [b"a" * 11, b"extra"], [bytearray(b"a" * 11)]])
async def test_suppressed_stream_error_truncation_and_extra_bytes_fail_and_remove_file(context, tmp_path, chunks):
    context.client.stream_override = chunks
    with pytest.raises(reader.OfficialReadError, match="official_media_incomplete"):
        await download(context, tmp_path)
    assert list(tmp_path.iterdir()) == []
    assert context.client.stream_closed == 1
    assert_released(context)


@pytest.mark.asyncio
async def test_unknown_size_and_expired_reference_refresh_only_same_payload(context, tmp_path):
    original = reader._project_message(raw_message(kind="document"))
    original = replace(original, media=replace(original.media, file_id="expired", file_size=None))
    context.client.refresh.document.file_id = "fresh-reference"
    fresh = await reader.refresh_official_message(context.service, "alpha", original, start=START, end=END)
    assert fresh.media.file_size == 11 and fresh.media.file_id == "fresh-reference"
    destination = await download(context, tmp_path, fresh)
    assert destination.read_bytes() == context.client.payload
    assert context.client.stream_calls[0][0].file_id == "fresh-reference"
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["unique_id", "size", "kind", "id", "time", "outgoing", "deleted", "protected", "missing_size", "missing_reference", "chat"])
async def test_refresh_rejects_changed_deleted_unverifiable_sources(context, tmp_path, change):
    original = reader._project_message(raw_message(kind="document"))
    fresh = context.client.refresh
    if change == "unique_id":
        fresh.document.file_unique_id = "different-payload"
    elif change == "size":
        fresh.document.file_size = 12
    elif change == "kind":
        fresh.photo, fresh.document = fresh.document, None
    elif change == "id":
        fresh.id = 9
    elif change == "time":
        fresh.date = END - timedelta(seconds=2)
    elif change == "outgoing":
        fresh.outgoing = True
    elif change == "deleted":
        fresh.empty = True
    elif change == "protected":
        fresh.has_protected_content = True
    elif change == "missing_size":
        fresh.document.file_size = None
    elif change == "missing_reference":
        fresh.document.file_id = ""
    elif change == "chat":
        fresh.chat.id = 123
    with pytest.raises(reader.OfficialReadError):
        await download(context, tmp_path, original)
    assert context.client.stream_calls == []
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("epoch", [START.timestamp() - 1, END.timestamp(), END.timestamp() + 1])
async def test_excluded_media_never_acquires_client_refreshes_or_downloads(context, tmp_path, epoch):
    original = reader._project_message(raw_message(kind="document", date=datetime.fromtimestamp(epoch, timezone.utc)))
    with pytest.raises(reader.OfficialReadError, match="official_message_outside_window"):
        await download(context, tmp_path, original)
    assert context.builds == context.client.refresh_calls == context.client.stream_calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("epoch", [START.timestamp(), END.timestamp() - 1])
async def test_download_accepts_only_inclusive_lower_and_exclusive_upper_window(context, tmp_path, epoch):
    context.client.refresh.date = datetime.fromtimestamp(epoch, timezone.utc)
    destination = await download(context, tmp_path)
    assert destination.read_bytes() == context.client.payload
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["lock", "permit"])
async def test_timeout_waiting_for_admission_never_constructs_client(context, gate):
    held = getattr(context, gate)
    await held.acquire()
    try:
        with pytest.raises(reader.OfficialReadError, match="official_read_timeout"):
            await reader.read_official_page(context.service, "alpha", end=END, timeout_seconds=0.01)
        assert context.builds == []
    finally:
        held.release()
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["history", "stream"])
async def test_cancel_active_operation_closes_iterator_client_and_partial_file(context, tmp_path, operation):
    if operation == "history":
        context.client.block_history = True
        task = asyncio.create_task(reader.read_official_page(context.service, "alpha", end=END))
        await context.client.history_started.wait()
    else:
        context.client.block_stream = True
        task = asyncio.create_task(download(context, tmp_path))
        await context.client.stream_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert context.client.history_closed + context.client.stream_closed == 1
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
async def test_preexisting_destination_is_preserved_and_iterator_closed(context, tmp_path):
    destination = tmp_path / "generated-part.bin"
    destination.write_bytes(b"belongs to another operation")
    with pytest.raises(reader.OfficialReadError):
        await download(context, tmp_path)
    assert destination.read_bytes() == b"belongs to another operation"
    assert context.client.stream_calls == []
    assert_released(context)


@pytest.mark.asyncio
async def test_safe_error_never_contains_network_message_or_token(context):
    context.client.failure = RuntimeError("secret body https://api.telegram.org/botTOKEN source")
    with pytest.raises(reader.OfficialReadError) as error:
        await reader.read_official_page(context.service, "alpha", end=END)
    assert str(error.value) == "official_read_failed"
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("gate", ["lock", "permit"])
async def test_canceled_admission_never_caches_a_dormant_client(context, gate):
    held = getattr(context, gate)
    await held.acquire()
    task = asyncio.create_task(reader.read_official_page(context.service, "alpha", end=END))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert context.builds == []
    finally:
        held.release()
    assert_released(context)


@pytest.mark.asyncio
async def test_active_download_timeout_removes_partial_file(context, tmp_path):
    context.client.block_stream = True
    with pytest.raises(reader.OfficialReadError, match="official_read_timeout"):
        await download(context, tmp_path, timeout_seconds=0.01)
    assert context.client.stream_closed == 1
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
async def test_client_exit_failure_never_leaves_apparently_completed_part(context, tmp_path, monkeypatch):
    original_exit = Client.__aexit__

    async def failing_exit(self, *args):
        await original_exit(self, *args)
        raise RuntimeError("private connection details")

    monkeypatch.setattr(Client, "__aexit__", failing_exit)
    with pytest.raises(reader.OfficialReadError, match="official_read_failed"):
        await download(context, tmp_path)
    assert context.client.stream_closed == 1
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("offset,length", [(1, 10), (-8, 8), (0, 0), (0, 12), (0, 5)])
async def test_invalid_part_ranges_never_write_or_stream(context, tmp_path, offset, length):
    with pytest.raises(reader.OfficialReadError, match="official_media_range_invalid"):
        await download(context, tmp_path, offset=offset, length=length)
    assert context.client.stream_calls == []
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [None, 0, -1, True, 11.0])
async def test_unverifiable_source_size_never_reports_download_complete(context, tmp_path, size):
    original = reader._project_message(raw_message(kind="document"))
    original = replace(original, media=replace(original.media, file_size=None))
    context.client.refresh.document.file_size = size
    with pytest.raises(reader.OfficialReadError, match="official_media_unavailable"):
        await download(context, tmp_path, original)
    assert context.client.stream_calls == []
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
async def test_missing_original_unique_identity_cannot_be_replaced_by_fresh_payload(context, tmp_path):
    original = reader._project_message(raw_message(kind="document"))
    original = replace(original, media=replace(original.media, file_unique_id="", file_size=None))
    with pytest.raises(reader.OfficialReadError, match="official_media_identity_changed"):
        await download(context, tmp_path, original)
    assert context.client.stream_calls == []
    assert list(tmp_path.iterdir()) == []
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), "invalid"])
async def test_invalid_timeout_does_not_start_or_leak_operation(context, timeout):
    with pytest.raises(reader.OfficialReadError, match="official_timeout_invalid"):
        await reader.read_official_page(context.service, "alpha", end=END, timeout_seconds=timeout)
    assert context.builds == []
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["history", "stream"])
@pytest.mark.parametrize("canceled", [False, True])
async def test_iterator_cleanup_preserves_primary_failure_and_cancellation(
    context, tmp_path, monkeypatch, caplog, operation, canceled,
):
    primary = asyncio.CancelledError() if canceled else reader.OfficialReadError("primary_read_failure")

    class BrokenIterator:
        closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise primary

        async def aclose(self):
            self.closed = True
            raise RuntimeError("private body https://api.telegram.org/botSECRET")

    iterator = BrokenIterator()
    method = "get_chat_history" if operation == "history" else "stream_media"
    monkeypatch.setattr(context.client, method, lambda *args, **kwargs: iterator)
    with pytest.raises(type(primary)) as error:
        if operation == "history":
            await reader.read_official_page(context.service, "alpha", end=END)
        else:
            await download(context, tmp_path)
    # Python 3.10's wait_for may reconstruct CancelledError at the task
    # boundary. The cancellation type and cleanup behavior are the contract.
    if canceled:
        assert isinstance(error.value, asyncio.CancelledError)
    else:
        assert error.value is primary
    assert iterator.closed
    assert list(tmp_path.iterdir()) == []
    assert "RuntimeError" in caplog.text and "SECRET" not in caplog.text
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["history", "stream"])
async def test_iterator_cleanup_failure_never_returns_success(
    context, tmp_path, monkeypatch, caplog, operation,
):
    class BrokenClose:
        def __init__(self, iterator):
            self.iterator = iterator
            self.closed = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.iterator.__anext__()

        async def aclose(self):
            await self.iterator.aclose()
            self.closed = True
            raise RuntimeError("private body https://api.telegram.org/botSECRET")

    iterator = BrokenClose(
        context.client.get_chat_history(777000, offset_id=0)
        if operation == "history" else
        context.client.stream_media(None, limit=1, offset=0)
    )
    method = "get_chat_history" if operation == "history" else "stream_media"
    monkeypatch.setattr(context.client, method, lambda *args, **kwargs: iterator)
    with pytest.raises(reader.OfficialReadError, match="official_iterator_cleanup_failed"):
        if operation == "history":
            await reader.read_official_page(context.service, "alpha", end=END)
        else:
            await download(context, tmp_path)
    assert iterator.closed
    assert list(tmp_path.iterdir()) == []
    assert "RuntimeError" in caplog.text and "SECRET" not in caplog.text
    assert_released(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["history", "refresh", "stream"])
@pytest.mark.parametrize("canceled", [False, True])
async def test_client_exit_cleanup_preserves_primary_failure_and_cancellation(
    context, tmp_path, monkeypatch, caplog, operation, canceled,
):
    primary = asyncio.CancelledError() if canceled else reader.OfficialReadError("primary_read_failure")
    original_exit = Client.__aexit__

    async def failing_exit(self, *args):
        await original_exit(self, *args)
        raise RuntimeError("private body https://api.telegram.org/botSECRET")

    monkeypatch.setattr(Client, "__aexit__", failing_exit)
    if operation == "refresh":
        async def failing_refresh(*args, **kwargs):
            raise primary
        monkeypatch.setattr(context.client, "get_messages", failing_refresh)
    else:
        context.client.failure = primary
    with pytest.raises(type(primary)) as error:
        if operation == "history":
            await reader.read_official_page(context.service, "alpha", end=END)
        elif operation == "refresh":
            await reader.refresh_official_message(
                context.service, "alpha", reader._project_message(context.client.refresh),
                start=START, end=END,
            )
        else:
            await download(context, tmp_path)
    # Python 3.10's wait_for may reconstruct CancelledError at the task
    # boundary. Non-cancellation failures still retain their original object.
    if canceled:
        assert isinstance(error.value, asyncio.CancelledError)
    else:
        assert error.value is primary
    assert list(tmp_path.iterdir()) == []
    assert "RuntimeError" in caplog.text and "SECRET" not in caplog.text
    assert_released(context)
