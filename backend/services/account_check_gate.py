"""Process-local, shared cooldown for user-triggered account status checks."""
from __future__ import annotations

import math
import threading
import time
from collections.abc import Iterable

COOLDOWN_SECONDS = 45


class AccountCheckBusy(Exception):
    def __init__(self, account: str, remaining_seconds: int) -> None:
        self.account = account
        self.remaining_seconds = remaining_seconds
        super().__init__(f"{account} 正在检测或冷却中，请 {remaining_seconds} 秒后重试")


class AccountCheckGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._in_flight: set[str] = set()
        self._deadlines: dict[str, float] = {}

    def reserve(self, names: Iterable[str]) -> "AccountCheckReservation":
        requested = tuple(dict.fromkeys(names))
        now = time.monotonic()
        with self._lock:
            self._deadlines = {name: until for name, until in self._deadlines.items() if until > now}
            for name in requested:
                if name in self._in_flight:
                    raise AccountCheckBusy(name, COOLDOWN_SECONDS)
                until = self._deadlines.get(name, 0)
                if until > now:
                    raise AccountCheckBusy(name, max(1, math.ceil(until - now)))
            self._in_flight.update(requested)
        return AccountCheckReservation(self, requested)

    def finish(self, name: str, *, success: bool) -> None:
        with self._lock:
            self._in_flight.discard(name)
            if success:
                self._deadlines[name] = time.monotonic() + COOLDOWN_SECONDS


class AccountCheckReservation:
    def __init__(self, gate: AccountCheckGate, names: tuple[str, ...]) -> None:
        self._gate = gate
        self._pending = set(names)

    def finish(self, name: str, *, success: bool) -> None:
        if name in self._pending:
            self._pending.remove(name)
            self._gate.finish(name, success=success)

    def release(self) -> None:
        for name in tuple(self._pending):
            self.finish(name, success=False)


account_check_gate = AccountCheckGate()
