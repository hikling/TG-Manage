"""Only the lock-owned configured-midnight trigger may start an automatic scan."""
from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

import backend.scheduler as scheduling
from backend.scheduler import instance_lock


@pytest.fixture
def scheduler_env(monkeypatch):
    config = {"timezone": "Asia/Shanghai"}
    monkeypatch.setattr(scheduling, "scheduler", None)
    monkeypatch.setattr(
        "backend.core.config.get_settings",
        lambda: SimpleNamespace(timezone="Asia/Hong_Kong"),
    )
    monkeypatch.setattr(
        "backend.services.config.get_config_service",
        lambda: SimpleNamespace(get_global_settings=lambda: dict(config)),
    )
    monkeypatch.setattr(scheduling, "_sync_auto_backup_job", Mock())
    monkeypatch.setattr(instance_lock, "try_acquire_scheduler_lock", Mock(return_value=True))
    monkeypatch.setattr(instance_lock, "has_scheduler_lock", Mock(return_value=True))
    monkeypatch.setattr(instance_lock, "release_scheduler_lock", Mock())
    yield config
    scheduling.shutdown_scheduler()


@pytest.fixture
def scheduler_clock(monkeypatch):
    now = [datetime(2026, 10, 12, 16, 0, tzinfo=ZoneInfo("UTC"))]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now[0].astimezone(tz) if tz else now[0].replace(tzinfo=None)

    monkeypatch.setattr(scheduling, "datetime", FrozenDateTime)
    return now


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_on_startup", [False, True])
async def test_single_midnight_job_has_explicit_timezone_and_limits(
    scheduler_env, sync_on_startup, monkeypatch,
):
    report_service = Mock()
    keepalive_service = Mock()
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        report_service,
    )
    monkeypatch.setattr(
        "backend.services.device_keepalive.get_device_keepalive_service",
        keepalive_service,
    )
    scheduler = await scheduling.init_scheduler(sync_on_startup=sync_on_startup)
    try:
        job = scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID)
        assert job.func is scheduling._job_account_status_report
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 59
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        now = datetime(2026, 10, 12, 23, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run == datetime(2026, 10, 13, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        await scheduling.sync_jobs()
        await scheduling.sync_jobs()
        assert sum(j.id == job.id for j in scheduler.get_jobs()) == 1
        assert scheduler.get_job("system-device-keepalive") is None
        report_service.assert_not_called()
        keepalive_service.assert_not_called()
    finally:
        scheduling.shutdown_scheduler()


@pytest.mark.asyncio
async def test_saved_timezone_reschedules_midnight_without_replacing_job(scheduler_env):
    scheduler = await scheduling.init_scheduler()
    try:
        job = scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID)
        old_next_run = job.next_run_time
        await scheduling.sync_jobs()
        assert job.next_run_time == old_next_run
        scheduler_env["timezone"] = "America/Los_Angeles"
        await scheduling.sync_jobs()
        assert scheduler.get_job(job.id) is job
        assert str(job.trigger.timezone) == "America/Los_Angeles"
        assert str(scheduler.timezone) == "Asia/Shanghai"
        now = datetime(2026, 10, 12, 23, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        assert job.trigger.get_next_fire_time(None, now) == datetime(
            2026, 10, 13, 0, 0, tzinfo=ZoneInfo("America/Los_Angeles")
        )
        assert job.max_instances == 1 and job.coalesce
        assert job.misfire_grace_time == 59
    finally:
        scheduling.shutdown_scheduler()


@pytest.mark.asyncio
async def test_missing_saved_timezone_uses_application_default(scheduler_env):
    scheduler_env["timezone"] = ""
    scheduler = await scheduling.init_scheduler()
    try:
        job = scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID)
        assert str(job.trigger.timezone) == "Asia/Hong_Kong"
    finally:
        scheduling.shutdown_scheduler()


@pytest.mark.asyncio
async def test_process_without_scheduler_lock_does_not_register_report(scheduler_env, monkeypatch):
    monkeypatch.setattr(instance_lock, "try_acquire_scheduler_lock", Mock(return_value=False))
    monkeypatch.setattr(instance_lock, "has_scheduler_lock", Mock(return_value=False))
    scheduler = await scheduling.init_scheduler()
    try:
        await scheduling.sync_jobs()
        assert scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID) is None
        assert scheduler.get_job("system-device-keepalive") is None
    finally:
        scheduling.shutdown_scheduler()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "init", "init_without_sync"])
async def test_retired_keepalive_job_removed_without_replacing_midnight(scheduler_env, entry):
    scheduler = await scheduling.init_scheduler(sync_on_startup=False)
    report_job = scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID)
    scheduler.add_job(
        lambda: None,
        trigger="cron", hour=3, minute=30,
        id="system-device-keepalive",
    )
    scheduler.add_job(lambda: None, trigger="interval", days=1, id="unrelated-job")

    if entry == "sync":
        await scheduling.sync_jobs()
    else:
        await scheduling.init_scheduler(sync_on_startup=entry == "init")

    assert scheduler.get_job("system-device-keepalive") is None
    assert scheduler.get_job("unrelated-job") is not None
    assert scheduler.get_job(report_job.id) is report_job


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("utc_time", "starts"),
    [
        ((16, 0, 0), True),
        ((16, 0, 59), True),
        ((16, 1, 0), False),
        ((16, 59, 59), False),
        ((19, 30, 0), False),
        ((4, 0, 0), False),
        ((0, 0, 0), False),
    ],
)
async def test_job_only_starts_within_configured_midnight_minute(
    scheduler_env, scheduler_clock, monkeypatch, utc_time, starts,
):
    scheduler_clock[0] = datetime(2026, 10, 12, *utc_time, tzinfo=ZoneInfo("UTC"))
    run = AsyncMock(return_value={"checked": 1})
    service = Mock(return_value=SimpleNamespace(run=run))
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        service,
    )

    await scheduling._job_account_status_report()

    if starts:
        run.assert_awaited_once()
        service.assert_called_once()
    else:
        run.assert_not_awaited()
        service.assert_not_called()


@pytest.mark.asyncio
async def test_midnight_guard_uses_updated_saved_timezone(
    scheduler_env, scheduler_clock, monkeypatch,
):
    scheduler = await scheduling.init_scheduler()
    scheduler_env["timezone"] = "America/Los_Angeles"
    scheduler_clock[0] = datetime(2026, 10, 13, 7, 0, tzinfo=ZoneInfo("UTC"))
    assert str(scheduler.timezone) == "Asia/Shanghai"
    run = AsyncMock(return_value={"checked": 1})
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=run),
    )

    await scheduling._job_account_status_report()

    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_midnight_run_can_finish_after_the_start_window(
    scheduler_env, scheduler_clock, monkeypatch,
):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def report_run():
        entered.set()
        await finish.wait()
        return {"checked": 1}

    run = AsyncMock(side_effect=report_run)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=run),
    )
    task = asyncio.create_task(scheduling._job_account_status_report())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        scheduler_clock[0] = datetime(2026, 10, 12, 16, 2, tzinfo=ZoneInfo("UTC"))
        finish.set()
        await asyncio.wait_for(task, 1)
        run.assert_awaited_once()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_job_cancellation_propagates(scheduler_env, scheduler_clock, monkeypatch):
    run = AsyncMock(side_effect=asyncio.CancelledError)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=run),
    )
    with pytest.raises(asyncio.CancelledError):
        await scheduling._job_account_status_report()
    run.assert_awaited_once()


@pytest.mark.asyncio
async def test_job_invokes_report_and_contains_sanitized_failures(
    scheduler_env, scheduler_clock, monkeypatch, caplog,
):
    run = AsyncMock(return_value={"checked": 2, "ok": 1, "fail": 1, "messages_sent": 1})
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=run),
    )
    await scheduling._job_account_status_report()
    run.assert_awaited_once()
    run.side_effect = RuntimeError("https://api.telegram.org/botSECRET/sendMessage")
    await scheduling._job_account_status_report()
    assert "RuntimeError" in caplog.text
    assert "SECRET" not in caplog.text


def test_sync_report_before_scheduler_exists_is_noop(monkeypatch):
    monkeypatch.setattr(scheduling, "scheduler", None)
    scheduling._sync_account_status_report_job()
