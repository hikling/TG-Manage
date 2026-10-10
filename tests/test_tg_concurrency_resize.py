"""Runtime semaphore resizing keeps active and queued Telegram ownership."""
from __future__ import annotations

import asyncio

import pytest

from backend.utils import tg_session


@pytest.fixture
def runtime_gate(monkeypatch):
    monkeypatch.setattr(tg_session, '_GLOBAL_SEMAPHORE', None)
    monkeypatch.setattr(tg_session, '_MEDIA_UPLOAD_SEMAPHORE', None)

    def create(limit):
        tg_session.update_global_semaphore(limit)
        return tg_session.get_global_semaphore()

    return create


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [1, 8, 1000])
async def test_unchanged_limit_keeps_in_flight_and_queued_permits(runtime_gate, limit):
    gate = runtime_gate(limit)
    assert isinstance(gate, asyncio.Semaphore)
    for _ in range(limit):
        assert await gate.acquire() is True
    started = asyncio.Event()

    async def wait():
        async with tg_session.get_global_semaphore():
            started.set()

    waiter = asyncio.create_task(wait())
    try:
        await asyncio.sleep(0)
        tg_session.update_global_semaphore(limit)
        assert tg_session.get_global_semaphore() is gate
        await asyncio.sleep(0)
        assert not started.is_set()
        assert gate.locked()
        gate.release()
        await asyncio.wait_for(waiter, 1)
        for _ in range(limit - 1):
            gate.release()
        assert gate._value == limit
        assert not gate.locked()
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


@pytest.mark.asyncio
async def test_lower_limit_drains_active_debt_before_admitting_waiters(runtime_gate):
    gate = runtime_gate(3)
    for _ in range(3):
        await gate.acquire()
    started = asyncio.Event()

    async def wait():
        async with gate:
            started.set()

    waiter = asyncio.create_task(wait())
    try:
        await asyncio.sleep(0)
        tg_session.update_global_semaphore(1)
        assert tg_session.get_global_semaphore() is gate
        for _ in range(2):
            gate.release()
            await asyncio.sleep(0)
            assert not started.is_set()
            assert gate.locked()
        gate.release()
        await asyncio.wait_for(waiter, 1)
        assert started.is_set()
        assert gate._value == 1
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


@pytest.mark.asyncio
async def test_increasing_limit_wakes_queued_operations_and_keeps_acquire_release_api(runtime_gate):
    gate = runtime_gate(1)
    await gate.acquire()
    entered = []
    complete = asyncio.Event()

    async def wait(label):
        async with gate:
            entered.append(label)
            await complete.wait()

    tasks = [asyncio.create_task(wait(label)) for label in range(3)]
    try:
        await asyncio.sleep(0)
        tg_session.update_global_semaphore(3)
        await asyncio.sleep(0)
        assert entered == [0, 1]
        assert tg_session.get_global_semaphore() is gate
        assert gate.locked()
        complete.set()
        gate.release()
        await asyncio.wait_for(asyncio.gather(*tasks), 1)
        assert entered == [0, 1, 2]
        assert gate._value == 3
    finally:
        complete.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('awaken_before_cancel', [False, True])
async def test_cancelled_waiter_restores_capacity_after_resize(runtime_gate, awaken_before_cancel):
    gate = runtime_gate(1)
    await gate.acquire()
    waiter = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    if awaken_before_cancel:
        # Reserve a permit for a waiter, lower capacity before it resumes,
        # and cancel it. That permit must pay off debt rather than wake others.
        tg_session.update_global_semaphore(2)
        tg_session.update_global_semaphore(1)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert gate.locked()
    gate.release()
    assert gate._value == 1
    assert await asyncio.wait_for(gate.acquire(), 1) is True
    gate.release()
    assert gate._value == 1


@pytest.mark.asyncio
async def test_new_waiters_cannot_bypass_shrink_debt_or_fifo(runtime_gate):
    gate = runtime_gate(3)
    for _ in range(3):
        await gate.acquire()
    entered = []
    leave = asyncio.Event()

    async def wait(label):
        async with gate:
            entered.append(label)
            await leave.wait()

    first = asyncio.create_task(wait('first'))
    await asyncio.sleep(0)
    tg_session.update_global_semaphore(1)
    second = asyncio.create_task(wait('second'))
    try:
        await asyncio.sleep(0)
        for _ in range(2):
            gate.release()
            await asyncio.sleep(0)
            assert not entered
        gate.release()
        await asyncio.sleep(0)
        assert entered == ['first']
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        await asyncio.sleep(0)
        assert entered == ['first', 'second']
        leave.set()
        await asyncio.wait_for(second, 1)
        assert gate._value == 1
    finally:
        leave.set()
        for task in (first, second):
            task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_reserved_permit_repays_debt_before_next_waiter(runtime_gate):
    gate = runtime_gate(1)
    await gate.acquire()
    waiters = [asyncio.create_task(gate.acquire()) for _ in range(2)]
    try:
        await asyncio.sleep(0)
        tg_session.update_global_semaphore(2)
        tg_session.update_global_semaphore(1)
        waiters[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiters[0]
        await asyncio.sleep(0)
        assert not waiters[1].done()
        gate.release()
        assert await asyncio.wait_for(waiters[1], 1) is True
        gate.release()
        assert gate._value == 1
    finally:
        for task in waiters:
            task.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)


@pytest.mark.asyncio
async def test_resize_owns_scheduling_without_base_private_wakeup(runtime_gate, monkeypatch):
    def unexpected_wakeup(_self):
        raise AssertionError('must not depend on CPython private waiter scheduling')

    monkeypatch.setattr(asyncio.Semaphore, '_wake_up_next', unexpected_wakeup)
    gate = runtime_gate(1)
    assert await gate.__aenter__() is None
    waiter = asyncio.create_task(gate.acquire())
    await asyncio.sleep(0)
    tg_session.update_global_semaphore(2)
    assert await asyncio.wait_for(waiter, 1) is True
    tg_session.update_global_semaphore(1)
    gate.release()
    assert gate.locked()
    await gate.__aexit__(None, None, None)
    async with gate:
        assert gate.locked()
    assert gate._value == 1


@pytest.mark.asyncio
async def test_multiple_accounts_share_resized_gate_and_cancel_releases_client(runtime_gate, monkeypatch):
    from backend.services import communications

    gate = runtime_gate(1)
    locks = {name: asyncio.Lock() for name in ('alpha', 'beta', 'gamma')}
    started = {name: asyncio.Event() for name in locks}
    finished = asyncio.Event()
    exits = []
    built = []

    class Client:
        def __init__(self, name):
            self.name = name

        async def __aenter__(self):
            started[self.name].set()
            return self

        async def __aexit__(self, *_args):
            exits.append(self.name)

    class Service:
        def _build_account_client(self, name, **_kwargs):
            assert locks[name].locked()
            built.append(name)
            return Client(name), None

    monkeypatch.setattr(communications, 'checked_account', lambda name: (Service(), name))
    monkeypatch.setattr(communications, 'get_account_lock', locks.__getitem__)

    async def operate(name):
        async with communications.account_client(name):
            await finished.wait()

    tasks = {name: asyncio.create_task(operate(name)) for name in locks}
    try:
        await asyncio.wait_for(started['alpha'].wait(), 1)
        assert built == ['alpha']
        tg_session.update_global_semaphore(1)
        await asyncio.sleep(0)
        assert built == ['alpha']
        tg_session.update_global_semaphore(2)
        await asyncio.wait_for(started['beta'].wait(), 1)
        assert built == ['alpha', 'beta']
        tasks['alpha'].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks['alpha']
        await asyncio.wait_for(started['gamma'].wait(), 1)
        finished.set()
        await asyncio.wait_for(asyncio.gather(tasks['beta'], tasks['gamma']), 1)
        assert sorted(exits) == ['alpha', 'beta', 'gamma']
        assert gate._value == 2
        assert all(not lock.locked() for lock in locks.values())
    finally:
        finished.set()
        for task in tasks.values():
            task.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
