from __future__ import annotations

import asyncio
from weakref import WeakValueDictionary


class _AccountLock(asyncio.Lock):
    def __init__(self, account_name: str) -> None:
        super().__init__()
        self._account_name = account_name

    async def acquire(self) -> bool:
        acquired = await super().acquire()
        if acquired:
            # A caller may acquire a temporary lock without retaining it.
            _HELD_ACCOUNT_LOCKS[self._account_name] = self
        return acquired

    def release(self) -> None:
        super().release()
        if _HELD_ACCOUNT_LOCKS.get(self._account_name) is self:
            _HELD_ACCOUNT_LOCKS.pop(self._account_name, None)


# Idle locks remain shared while a caller still refers to them, including one
# waiting in acquire(). Historical account names disappear automatically.
_ACCOUNT_LOCKS: WeakValueDictionary[str, _AccountLock] = WeakValueDictionary()
_HELD_ACCOUNT_LOCKS: dict[str, _AccountLock] = {}

# Retained for the existing cache-size check. Concurrent owners may temporarily
# exceed this many entries; it is not safe to evict an in-use lock.
_MAX_LOCKS = 500


def get_account_lock(account_name: str) -> asyncio.Lock:
    lock = _ACCOUNT_LOCKS.get(account_name)
    if lock is None:
        lock = _AccountLock(account_name)
        _ACCOUNT_LOCKS[account_name] = lock
    return lock
