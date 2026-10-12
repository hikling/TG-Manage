"""One lock-owned midnight job follows saved application timezone changes."""
from __future__ import annotations

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


@pytest.mark.asyncio
@pytest.mark.parametrize("sync_on_startup", [False, True])
async def test_single_midnight_job_has_explicit_timezone_and_limits(scheduler_env, sync_on_startup):
    scheduler = await scheduling.init_scheduler(sync_on_startup=sync_on_startup)
    try:
        job = scheduler.get_job(scheduling.ACCOUNT_STATUS_REPORT_JOB_ID)
        assert job.func is scheduling._job_account_status_report
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 3600
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        now = datetime(2026, 10, 12, 23, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
        next_run = job.trigger.get_next_fire_time(None, now)
        assert next_run == datetime(2026, 10, 13, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        await scheduling.sync_jobs()
        await scheduling.sync_jobs()
        assert sum(j.id == job.id for j in scheduler.get_jobs()) == 1
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
    finally:
        scheduling.shutdown_scheduler()


@pytest.mark.asyncio
async def test_job_invokes_report_and_contains_sanitized_failures(monkeypatch, caplog):
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
