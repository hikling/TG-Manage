"""账号状态批量检测 Job 测试。"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.services import account_status_jobs as jobs_mod
from backend.services.account_check_gate import AccountCheckBusy, account_check_gate
from backend.services.background_job import BackgroundJobStore


@pytest.fixture(autouse=True)
def _reset_store(tmp_path: Path, monkeypatch):
    store = BackgroundJobStore(tmp_path / "jobs")
    monkeypatch.setattr(jobs_mod, "_store", store)
    monkeypatch.setattr(jobs_mod, "get_account_status_job_store", lambda: store)
    yield
    jobs_mod._store = None


@pytest.mark.asyncio
async def test_run_status_check_updates_progress_and_results(tmp_path: Path):
    store = jobs_mod.get_account_status_job_store()
    created = store.create_job(
        kind=jobs_mod.KIND,
        payload={"account_names": ["a", "b"]},
        progress={"total": 2, "done": 0, "ok": 0, "fail": 0},
    )
    job_id = created["job_id"]

    async def _fake_check(name, timeout_seconds=8.0):
        return {
            "account_name": name,
            "ok": name == "a",
            "status": "connected" if name == "a" else "invalid",
            "message": "ok" if name == "a" else "expired",
            "needs_relogin": name != "a",
        }

    with patch("backend.services.telegram.get_telegram_service") as mock_get:
        mock_svc = mock_get.return_value
        mock_svc.check_account_status = AsyncMock(side_effect=_fake_check)
        # 缩短间隔
        with patch.object(jobs_mod, "INTER_DELAY_SECONDS", 0):
            await jobs_mod._run_status_check(job_id, ["a", "b"], 5.0)

    job = store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["summary"]["ok"] == 1
    assert job["summary"]["fail"] == 1
    assert len(job["results"]) == 2
    # 过程中应已写入 results（最终态仍保留）
    assert job["results"][0]["account_name"] == "a"


def test_start_rejects_when_already_running(monkeypatch):
    store = jobs_mod.get_account_status_job_store()
    store.create_job(kind=jobs_mod.KIND, progress={"total": 1, "done": 0})

    with patch.object(jobs_mod, "_normalize_names", return_value=["a"]):
        with pytest.raises(ValueError, match="已有批量状态检测"):
            jobs_mod.start_account_status_check_job(account_names=["a"])


def test_start_rejects_account_in_card_cooldown(monkeypatch):
    reservation = account_check_gate.reserve(["shared_a"])
    reservation.finish("shared_a", success=True)
    with patch.object(jobs_mod, "_normalize_names", return_value=["shared_a", "other"]):
        with pytest.raises(AccountCheckBusy) as error:
            jobs_mod.start_account_status_check_job(account_names=["shared_a", "other"])
    assert error.value.remaining_seconds == 45
    assert jobs_mod.get_account_status_job_store().list_jobs() == []
    # The rejected batch must not leave "other" reserved.
    account_check_gate.reserve(["other"]).release()


@pytest.mark.asyncio
async def test_cancel_before_runner_starts_releases_all_reservations(monkeypatch):
    with patch.object(jobs_mod, "_normalize_names", return_value=["prestart_a", "prestart_b"]):
        job = jobs_mod.start_account_status_check_job(account_names=["prestart_a", "prestart_b"])
    task = jobs_mod.get_account_status_job_store()._tasks[job["job_id"]]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)  # run BackgroundJobStore and reservation callbacks
    account_check_gate.reserve(["prestart_a", "prestart_b"]).release()


@pytest.mark.asyncio
async def test_canceled_batch_releases_unprocessed_reservations():
    store = jobs_mod.get_account_status_job_store()
    created = store.create_job(kind=jobs_mod.KIND, progress={"total": 2, "done": 0})
    job_id = created["job_id"]
    reservation = account_check_gate.reserve(["first", "second"])
    store.request_cancel(job_id)
    with patch("backend.services.telegram.get_telegram_service") as mock_get:
        await jobs_mod._run_status_check(job_id, ["first", "second"], 5.0, reservation)
    mock_get.return_value.check_account_status.assert_not_called()
    account_check_gate.reserve(["first", "second"]).release()


def test_normalize_names_dedupe_and_limit(monkeypatch):
    with patch("backend.services.telegram.get_telegram_service") as mock_get:
        mock_get.return_value.list_accounts.return_value = []
        names = jobs_mod._normalize_names(["a", "a", " b ", ""])
        assert names == ["a", "b"]

    with patch("backend.services.telegram.get_telegram_service") as mock_get:
        mock_get.return_value.list_accounts.return_value = []
        with pytest.raises(ValueError, match="最多"):
            jobs_mod._normalize_names([f"acc{i}" for i in range(jobs_mod.MAX_ACCOUNTS + 1)])


def test_normalize_names_rejects_path_segments():
    with patch("backend.services.telegram.get_telegram_service") as mock_get:
        mock_get.return_value.list_accounts.return_value = []
        names = jobs_mod._normalize_names(["ok", "../evil", "a/b", "good"])
        assert names == ["ok", "good"]


@pytest.mark.asyncio
async def test_start_failure_releases_reservation_and_allows_next_job():
    store = jobs_mod.get_account_status_job_store()
    with patch.object(jobs_mod, "_normalize_names", return_value=["startup"]), patch.object(
        store, "start_background", side_effect=RuntimeError("cannot schedule")
    ):
        with pytest.raises(RuntimeError, match="cannot schedule"):
            jobs_mod.start_account_status_check_job(account_names=["startup"])
    assert store.list_jobs()[0]["status"] == "failed"
    account_check_gate.reserve(["startup"]).release()
    with patch.object(jobs_mod, "_normalize_names", return_value=["startup"]), patch(
        "backend.services.telegram.get_telegram_service"
    ) as get_service:
        get_service.return_value.check_account_status = AsyncMock(return_value={
            "account_name": "startup", "ok": True, "status": "connected",
        })
        job = jobs_mod.start_account_status_check_job(account_names=["startup"])
        await store._tasks[job["job_id"]]
    assert store.get_job(job["job_id"])["status"] == "completed"


@pytest.mark.asyncio
async def test_cancel_during_probe_releases_remaining_accounts():
    store = jobs_mod.get_account_status_job_store()
    started = asyncio.Event()

    async def probe(name, timeout_seconds):
        started.set()
        await asyncio.Future()

    with patch.object(jobs_mod, "_normalize_names", return_value=["probing", "pending"]), patch(
        "backend.services.telegram.get_telegram_service"
    ) as get_service:
        get_service.return_value.check_account_status = AsyncMock(side_effect=probe)
        job = jobs_mod.start_account_status_check_job(account_names=["probing", "pending"])
        task = store._tasks[job["job_id"]]
        await started.wait()
        with pytest.raises(AccountCheckBusy):
            account_check_gate.reserve(["pending"])
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)
    account_check_gate.reserve(["probing", "pending"]).release()
    get_service.return_value.check_account_status.assert_awaited_once()
