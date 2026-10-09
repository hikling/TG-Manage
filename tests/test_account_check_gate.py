"""Shared account check reservations bound repeated Telegram work."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from backend.services import account_check_gate as gate_mod


def test_success_blocks_for_45_seconds_and_failure_does_not(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(gate_mod.time, "monotonic", lambda: clock[0])
    gate = gate_mod.AccountCheckGate()

    reservation = gate.reserve(["one"])
    with pytest.raises(gate_mod.AccountCheckBusy, match="正在检测"):
        gate.reserve(["one"])
    reservation.finish("one", success=True)
    with pytest.raises(gate_mod.AccountCheckBusy) as error:
        gate.reserve(["one"])
    assert error.value.remaining_seconds == 45
    clock[0] += 44.1
    with pytest.raises(gate_mod.AccountCheckBusy) as error:
        gate.reserve(["one"])
    assert error.value.remaining_seconds == 1
    clock[0] += 0.9
    retry = gate.reserve(["one"])
    retry.finish("one", success=False)
    gate.reserve(["one"]).release()


def test_batch_reservation_is_atomic_and_release_clears_unfinished():
    gate = gate_mod.AccountCheckGate()
    held = gate.reserve(["second"])
    with pytest.raises(gate_mod.AccountCheckBusy) as error:
        gate.reserve(["first", "second", "third"])
    assert error.value.account == "second"
    gate.reserve(["first", "third"]).release()
    held.release()
    all_names = gate.reserve(["first", "second", "third"])
    all_names.finish("first", success=True)
    all_names.release()
    gate.reserve(["second", "third"]).release()
    with pytest.raises(gate_mod.AccountCheckBusy):
        gate.reserve(["first"])



def test_simultaneous_reservations_have_only_one_owner():
    gate = gate_mod.AccountCheckGate()
    barrier = Barrier(12)

    def reserve():
        barrier.wait(timeout=5)
        try:
            return gate.reserve(["same-account"])
        except gate_mod.AccountCheckBusy:
            return None

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(lambda _: reserve(), range(12)))
    owners = [reservation for reservation in results if reservation is not None]
    assert len(owners) == 1
    owners[0].release()
    gate.reserve(["same-account"]).release()


def test_repeated_200_account_batches_do_not_accumulate_gate_state(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(gate_mod.time, "monotonic", lambda: clock[0])
    gate = gate_mod.AccountCheckGate()
    for cycle in range(100):
        names = [f"cycle-{cycle}-account-{i}" for i in range(200)]
        reservation = gate.reserve(names)
        for name in names:
            reservation.finish(name, success=True)
        reservation.release()
        assert len(gate._deadlines) == 200
        assert not gate._in_flight
        with pytest.raises(gate_mod.AccountCheckBusy):
            gate.reserve(names)
        clock[0] += gate_mod.COOLDOWN_SECONDS
    gate.reserve([]).release()
    assert not gate._deadlines
