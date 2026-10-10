"""Temporary chat media buffers must close on every completion path."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, RuntimeError, asyncio.CancelledError])
async def test_send_media_closes_stream_and_client_on_success_error_and_cancel(failure):
    from backend.services import communications

    streams = []
    exited = 0

    class Client:
        async def send_document(self, peer, stream, **kwargs):
            assert peer == 12345
            assert stream.read() == b"small attachment"
            streams.append(stream)
            if failure is not None:
                raise failure()
            return object()

    @asynccontextmanager
    async def client_context(account):
        nonlocal exited
        assert account == "alpha"
        try:
            yield Client()
        finally:
            exited += 1

    with patch.object(communications, "account_client", client_context), patch.object(communications, "message_data", return_value={"id": 1}):
        if failure is None:
            assert await communications.send_media("alpha", "12345", b"small attachment", "sample.txt", "", None) == {"id": 1}
        else:
            with pytest.raises(failure):
                await communications.send_media("alpha", "12345", b"small attachment", "sample.txt", "", None)
    assert exited == 1
    assert len(streams) == 1
    assert streams[0].closed


@pytest.mark.asyncio
async def test_chat_client_acquires_account_lock_then_global_telegram_permit(monkeypatch):
    from backend.services import communications

    order = []

    class Context:
        def __init__(self, name):
            self.name = name

        async def __aenter__(self):
            order.append(f'{self.name}:enter')
            return self

        async def __aexit__(self, *_args):
            order.append(f'{self.name}:exit')

    class Service:
        def _build_account_client(self, _account, *, no_updates):
            assert no_updates is True
            return Context('client'), None

    monkeypatch.setattr(communications, 'checked_account', lambda _account: (Service(), 'alpha'))
    monkeypatch.setattr(communications, 'get_account_lock', lambda _account: Context('account'))
    monkeypatch.setattr(communications, 'get_global_semaphore', lambda: Context('telegram'))
    async with communications.account_client('alpha'):
        order.append('operation')
    assert order == [
        'account:enter', 'telegram:enter', 'client:enter', 'operation',
        'client:exit', 'telegram:exit', 'account:exit',
    ]


@pytest.mark.asyncio
async def test_media_upload_waits_for_admission_before_reading_and_sending(monkeypatch):
    from backend.api.routes import communications as route

    active_admissions = 0
    upload_slots = asyncio.Semaphore(1)
    first_send_started = asyncio.Event()
    allow_first_send = asyncio.Event()
    read_order = []
    sent = []

    @asynccontextmanager
    async def admission(_account):
        nonlocal active_admissions
        async with upload_slots:
            active_admissions += 1
            try:
                yield 'first' if not sent else 'second'
            finally:
                active_admissions -= 1

    class File:
        filename = 'attachment.txt'

        def __init__(self, label):
            self.label = label
            self.closed = False
            self.read_limit = None

        async def read(self, size):
            assert active_admissions == 1
            self.read_limit = size
            read_order.append(self.label)
            return self.label.encode()

        async def close(self):
            self.closed = True

    async def send(client, _chat, data, *_args):
        assert active_admissions == 1
        assert data in {b'first', b'second'}
        if client == 'first':
            first_send_started.set()
            await allow_first_send.wait()
        sent.append(client)
        return {'client': client}

    first, second = File('first'), File('second')
    with patch.object(route.service, 'MAX_MEDIA_BYTES', 16), \
         patch.object(route.service, 'media_upload_admission', admission), \
         patch.object(route.service, 'send_media_with_client', send):
        task1 = asyncio.create_task(route.upload('alpha', '12345', first, '', None))
        await first_send_started.wait()
        task2 = asyncio.create_task(route.upload('alpha', '12345', second, '', None))
        await asyncio.sleep(0)
        assert read_order == ['first']
        allow_first_send.set()
        assert await task1 == {'client': 'first'}
        assert await task2 == {'client': 'second'}

    assert read_order == ['first', 'second']
    assert first.read_limit == second.read_limit == 17
    assert first.closed and second.closed
    assert active_admissions == 0


@pytest.mark.asyncio
async def test_oversized_upload_releases_admission_and_closes_file():
    from backend.api.routes import communications as route

    active = False
    send = AsyncMock()

    @asynccontextmanager
    async def admission(_account):
        nonlocal active
        active = True
        try:
            yield object()
        finally:
            active = False

    class File:
        filename = 'large.bin'
        closed = False

        async def read(self, size):
            assert active
            return b'x' * size

        async def close(self):
            self.closed = True

    file = File()
    with patch.object(route.service, 'MAX_MEDIA_BYTES', 16), \
         patch.object(route.service, 'media_upload_admission', admission), \
         patch.object(route.service, 'send_media_with_client', send):
        with pytest.raises(HTTPException) as error:
            await route.upload('alpha', '12345', file, '', None)
    assert error.value.status_code == 413
    assert file.closed and not active
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [1, 32])
async def test_upload_admission_preserves_in_flight_permits_across_settings_updates(monkeypatch, limit):
    from backend.utils import tg_session

    monkeypatch.setattr(tg_session, '_GLOBAL_SEMAPHORE', None)
    monkeypatch.setattr(tg_session, '_MEDIA_UPLOAD_SEMAPHORE', None)
    monkeypatch.setattr(tg_session, '_resolve_concurrency_limit', lambda: limit)
    gate = tg_session.get_media_upload_semaphore()
    slots = min(limit, 2)
    for _ in range(slots):
        await gate.__aenter__()
    started = asyncio.Event()

    async def waiting_upload():
        async with tg_session.get_media_upload_semaphore():
            started.set()

    waiter = asyncio.create_task(waiting_upload())
    try:
        await asyncio.sleep(0)
        for _ in range(3):
            tg_session.update_global_semaphore(limit)
            assert tg_session.get_media_upload_semaphore() is gate
            await asyncio.sleep(0)
            assert not started.is_set()
        await gate.__aexit__(None, None, None)
        slots -= 1
        await asyncio.wait_for(waiter, timeout=1)
        assert started.is_set()
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        for _ in range(slots):
            await gate.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_upload_admission_shrink_waits_for_retained_permits_to_drain(monkeypatch):
    from backend.utils import tg_session

    monkeypatch.setattr(tg_session, '_GLOBAL_SEMAPHORE', None)
    monkeypatch.setattr(tg_session, '_MEDIA_UPLOAD_SEMAPHORE', None)
    tg_session.update_global_semaphore(32)
    gate = tg_session.get_media_upload_semaphore()
    await gate.__aenter__()
    await gate.__aenter__()
    slots = 2
    started = asyncio.Event()

    async def waiting_upload():
        async with gate:
            started.set()

    waiter = asyncio.create_task(waiting_upload())
    try:
        await asyncio.sleep(0)
        tg_session.update_global_semaphore(1)
        assert tg_session.get_media_upload_semaphore() is gate
        await gate.__aexit__(None, None, None)
        slots -= 1
        await asyncio.sleep(0)
        assert not started.is_set()
        await gate.__aexit__(None, None, None)
        slots -= 1
        await asyncio.wait_for(waiter, timeout=1)
        assert started.is_set()
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        for _ in range(slots):
            await gate.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_upload_admission_growth_and_cancellation_release_capacity(monkeypatch):
    from backend.utils import tg_session

    monkeypatch.setattr(tg_session, '_GLOBAL_SEMAPHORE', None)
    monkeypatch.setattr(tg_session, '_MEDIA_UPLOAD_SEMAPHORE', None)
    tg_session.update_global_semaphore(1)
    gate = tg_session.get_media_upload_semaphore()
    started = asyncio.Event()
    leave = asyncio.Event()

    async def waiting_upload():
        async with gate:
            started.set()
            await leave.wait()

    async with gate:
        waiter = asyncio.create_task(waiting_upload())
        try:
            await asyncio.sleep(0)
            assert not started.is_set()
            tg_session.update_global_semaphore(32)
            await asyncio.wait_for(started.wait(), timeout=1)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            # Cancellation while holding a permit makes the second slot reusable.
            async with gate:
                pass
        finally:
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
    # Cancellation while waiting must not consume capacity on the next acquire.
    tg_session.update_global_semaphore(1)
    async with gate:
        waiter = asyncio.create_task(waiting_upload())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
    async with gate:
        pass


@pytest.mark.asyncio
async def test_canceled_chat_waiter_does_not_build_or_cache_an_unstarted_client(monkeypatch):
    from backend.services import communications

    account_lock = asyncio.Lock()
    global_permit = asyncio.Semaphore(1)
    service = Mock()
    monkeypatch.setattr(communications, 'checked_account', lambda _account: (service, 'alpha'))
    monkeypatch.setattr(communications, 'get_account_lock', lambda _account: account_lock)
    monkeypatch.setattr(communications, 'get_global_semaphore', lambda: global_permit)

    async def waiting_chat():
        async with communications.account_client('alpha'):
            pytest.fail('Canceled waiter must not enter a client context')

    async with global_permit:
        waiter = asyncio.create_task(waiting_chat())
        await asyncio.sleep(0)
        assert account_lock.locked()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert not account_lock.locked()
        assert global_permit.locked()
    service._build_account_client.assert_not_called()


@pytest.mark.asyncio
async def test_canceled_upload_waiter_closes_file_without_reading():
    from backend.api.routes import communications as route

    upload_slots = asyncio.Semaphore(1)
    file = Mock(filename='cancelled.bin', read=AsyncMock(), close=AsyncMock())

    @asynccontextmanager
    async def admission(_account):
        async with upload_slots:
            yield object()

    async with upload_slots:
        with patch.object(route.service, 'media_upload_admission', admission):
            waiter = asyncio.create_task(route.upload('alpha', '12345', file, '', None))
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            assert upload_slots.locked()
    file.read.assert_not_awaited()
    file.close.assert_awaited_once()
