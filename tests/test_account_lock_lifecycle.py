"""Account lock cache must remain exclusive without retaining old names."""
from __future__ import annotations

import asyncio
import gc

import pytest

from backend.utils import account_locks


@pytest.mark.asyncio
async def test_lock_identity_survives_churn_while_held_or_waited():
    lock = account_locks.get_account_lock("shared")
    await lock.acquire()
    entered = asyncio.Event()

    async def waiter():
        async with account_locks.get_account_lock("shared"):
            entered.set()

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    for index in range(account_locks._MAX_LOCKS + 50):
        account_locks.get_account_lock(f"historical-{index}")
    gc.collect()
    assert account_locks.get_account_lock("shared") is lock
    assert not entered.is_set()

    lock.release()
    await asyncio.wait_for(task, 1)
    assert entered.is_set()


@pytest.mark.asyncio
async def test_temporary_acquired_lock_has_strong_reference_until_release():
    await account_locks.get_account_lock("temporary").acquire()
    gc.collect()
    held = account_locks.get_account_lock("temporary")
    assert held.locked()
    assert account_locks._HELD_ACCOUNT_LOCKS["temporary"] is held

    held.release()
    assert "temporary" not in account_locks._HELD_ACCOUNT_LOCKS
    del held
    gc.collect()
    assert "temporary" not in account_locks._ACCOUNT_LOCKS


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leave_lock_references():
    lock = account_locks.get_account_lock("cancelled")
    await lock.acquire()
    waiter = asyncio.create_task(account_locks.get_account_lock("cancelled").acquire())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    lock.release()
    del lock, waiter
    # Let the event loop drop its just-completed Task reference.
    await asyncio.sleep(0)
    gc.collect()
    assert "cancelled" not in account_locks._ACCOUNT_LOCKS
    assert "cancelled" not in account_locks._HELD_ACCOUNT_LOCKS
