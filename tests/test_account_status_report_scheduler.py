"""Only the lock-owned configured-midnight trigger may start an automatic scan."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest

import backend.scheduler as scheduling
from backend.scheduler import instance_lock
from backend.services import account_data_cleanup


@pytest.fixture
def scheduler_env(monkeypatch):
    config = {"timezone": "Asia/Shanghai"}
    monkeypatch.setattr(scheduling, "scheduler", None)
    monkeypatch.setattr(scheduling, "_midnight_workflow_running", False)
    monkeypatch.setattr(
        "backend.core.config.get_settings",
        lambda: SimpleNamespace(timezone="Asia/Hong_Kong"),
    )
    monkeypatch.setattr(
        "backend.services.config.get_config_service",
        lambda: SimpleNamespace(get_global_settings=lambda: dict(config)),
    )
    monkeypatch.setattr(instance_lock, "try_acquire_scheduler_lock", Mock(return_value=True))
    monkeypatch.setattr(instance_lock, "has_scheduler_lock", Mock(return_value=True))
    monkeypatch.setattr(instance_lock, "release_scheduler_lock", Mock())
    yield config
    scheduling.shutdown_scheduler()


@pytest.fixture(autouse=True)
def official_run(monkeypatch):
    # Existing scheduler tests must never connect to Telegram in the new phase.
    run = AsyncMock(return_value={"accounts": 0, "messages_sent": 0})
    monkeypatch.setattr(
        "backend.services.official_message_report.get_official_message_report_service",
        lambda: SimpleNamespace(run=run),
    )
    return run


@pytest.fixture(autouse=True)
def cleanup_run(monkeypatch):
    run = AsyncMock(return_value={"telebox": 0, "metadata": 0, "keepalive": 0, "avatars": 0})
    monkeypatch.setattr(account_data_cleanup, "reconcile_orphan_account_data", run)
    return run


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
    scheduler_env, scheduler_clock, monkeypatch, utc_time, starts, official_run,
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
        official_run.assert_awaited_once()
    else:
        run.assert_not_awaited()
        service.assert_not_called()
        official_run.assert_not_awaited()


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
    scheduler_env, scheduler_clock, monkeypatch, official_run,
):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def report_run(**_kwargs):
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
        window = official_run.await_args.kwargs
        assert window["end"] == datetime(2026, 10, 12, 16, tzinfo=timezone.utc)
        assert window["start"] == datetime(2026, 10, 11, 16, tzinfo=timezone.utc)
        assert str(window["timezone"]) == "Asia/Shanghai"
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
    assert scheduling._midnight_workflow_running is False


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


@pytest.mark.asyncio
async def test_midnight_sends_one_combined_summary_after_official_scan(
    scheduler_env, scheduler_clock, monkeypatch, official_run,
):
    rows = [{"account_name": "quiet", "ok": True, "route_mode": "primary", "route_status": "healthy"}]
    status_run = AsyncMock(return_value={"checked": 1, "rows": rows})
    send_combined = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=status_run),
    )
    monkeypatch.setattr("backend.services.account_status_report._send_report", send_combined)
    official_run.return_value = {"accounts": 1, "account_status": {"quiet": "empty"}}

    await scheduling._job_account_status_report()

    status_run.assert_awaited_once_with(send_report=False)
    assert official_run.await_args.kwargs["send_normal_summary"] is False
    assert official_run.await_args.kwargs["account_names"] == ["quiet"]
    send_combined.assert_awaited_once_with(rows, {"quiet": "empty"})
    from backend.services.account_status_report import report_chunks

    assert "🟢 quiet — 账户正常 · 主订阅 · IP 未知 · 官方消息无新消息" in report_chunks(
        rows, {"quiet": "empty"},
    )[0]


@pytest.mark.asyncio
async def test_partial_midnight_summary_is_reported_as_incomplete(
    scheduler_env, scheduler_clock, monkeypatch, official_run, cleanup_run,
):
    rows = [{"account_name": "quiet", "ok": True, "route_mode": "direct", "route_status": "healthy"}]
    status_run = AsyncMock(return_value={"checked": 1, "rows": rows})
    send_combined = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=status_run),
    )
    monkeypatch.setattr("backend.services.account_status_report._send_report", send_combined)
    monkeypatch.setattr(
        "backend.services.account_status_report.report_chunks",
        Mock(return_value=["第一段", "第二段"]),
    )
    official_run.return_value = {"accounts": 1, "account_status": {"quiet": "empty"}}

    result = await scheduling._run_combined_report(
        datetime(2026, 10, 13, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    send_combined.assert_awaited_once_with(rows, {"quiet": "empty"})
    assert result["success"] is False
    cleanup_run.assert_not_awaited()


def test_sync_report_before_scheduler_exists_is_noop(monkeypatch):
    monkeypatch.setattr(scheduling, "scheduler", None)
    scheduling._sync_account_status_report_job()


@pytest.mark.asyncio
async def test_status_failure_still_runs_official_report(
    scheduler_env, scheduler_clock, monkeypatch, official_run, caplog,
):
    run = AsyncMock(side_effect=RuntimeError("secret status source"))
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=run),
    )
    await scheduling._job_account_status_report()
    official_run.assert_awaited_once()
    assert "secret status source" not in caplog.text
    assert not scheduling._midnight_workflow_running


@pytest.mark.asyncio
async def test_official_failure_is_contained_and_cancellation_propagates(
    scheduler_env, scheduler_clock, monkeypatch, official_run, caplog,
):
    status = AsyncMock(return_value={"checked": 0})
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=status),
    )
    official_run.side_effect = RuntimeError("secret official source")
    await scheduling._job_account_status_report()
    assert "RuntimeError" in caplog.text and "secret official source" not in caplog.text
    assert not scheduling._midnight_workflow_running
    official_run.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await scheduling._job_account_status_report()
    assert not scheduling._midnight_workflow_running
    assert status.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["status", "official"])
async def test_whole_workflow_single_flight_survives_timezone_sync(
    scheduler_env, scheduler_clock, monkeypatch, official_run, phase,
):
    entered, finish = asyncio.Event(), asyncio.Event()

    async def blocked(**_kwargs):
        entered.set()
        await finish.wait()
        return {}

    status = AsyncMock(side_effect=blocked if phase == "status" else None, return_value={})
    if phase == "official":
        async def official_blocked(**kwargs):
            return await blocked()
        official_run.side_effect = official_blocked
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=status),
    )
    await scheduling.init_scheduler()
    task = asyncio.create_task(scheduling._job_account_status_report())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await scheduling._job_account_status_report()
        scheduler_env["timezone"] = "Asia/Hong_Kong"
        await scheduling.sync_jobs()
        await scheduling._job_account_status_report()
        assert scheduling._midnight_workflow_running
        assert status.await_count == 1
        assert official_run.await_count == (1 if phase == "official" else 0)
        finish.set()
        await asyncio.wait_for(task, 1)
        assert official_run.await_count == 1
        assert not scheduling._midnight_workflow_running
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("end_day", [(2026, 3, 9), (2026, 11, 2)])
async def test_dst_window_uses_24_elapsed_hours(
    scheduler_env, scheduler_clock, monkeypatch, official_run, end_day,
):
    scheduler_env["timezone"] = "America/New_York"
    admitted = datetime(*end_day, 0, 0, 59, tzinfo=ZoneInfo("America/New_York"))
    scheduler_clock[0] = admitted.astimezone(timezone.utc)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=AsyncMock(return_value={})),
    )
    await scheduling._job_account_status_report()
    window = official_run.await_args.kwargs
    assert window["end"] == admitted.replace(second=0).astimezone(timezone.utc)
    assert window["end"] - window["start"] == timedelta(hours=24)
    assert window["end"].tzinfo is timezone.utc
    assert window["start"].astimezone(ZoneInfo("America/New_York")).hour in {1, 23}


@pytest.mark.asyncio
async def test_manual_report_runs_full_workflow_outside_midnight(
    scheduler_env, scheduler_clock, monkeypatch, official_run, cleanup_run,
):
    scheduler_clock[0] = datetime(2026, 10, 13, 6, 34, 12, tzinfo=timezone.utc)
    rows = [{"account_name": "alpha", "ok": True, "route_mode": "primary", "route_status": "healthy"}]
    status_run = AsyncMock(return_value={"checked": 1, "rows": rows})
    send = AsyncMock(return_value=1)
    target = ("token", "123", None)
    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=status_run),
    )
    monkeypatch.setattr("backend.services.account_status_report._enabled_target", lambda: target)
    monkeypatch.setattr("backend.services.account_status_report._send_report", send)
    official_run.return_value = {
        "accounts": 1, "messages_sent": 2, "account_status": {"alpha": "messages"},
    }

    task = scheduling.start_manual_account_report(target)
    assert task is not None
    result = await task

    assert result == {"success": True, "checked": 1, "messages_sent": 3}
    cleanup_run.assert_awaited_once_with()
    status_run.assert_awaited_once_with(send_report=False)
    window = official_run.await_args.kwargs
    assert window["end"] == scheduler_clock[0]
    assert window["start"] == scheduler_clock[0] - timedelta(hours=24)
    assert window["account_names"] == ["alpha"]
    assert window["send_normal_summary"] is False
    send.assert_awaited_once_with(
        rows, {"alpha": "messages"}, title="账户状态与官方消息即时检测报告",
    )
    assert not scheduling._midnight_workflow_running


@pytest.mark.asyncio
async def test_manual_report_rejects_overlap_and_target_change(
    scheduler_env, scheduler_clock, monkeypatch, official_run,
):
    entered, finish = asyncio.Event(), asyncio.Event()
    target = ("token", "123", None)
    current_target = [target]

    async def blocked_status(**_kwargs):
        entered.set()
        await finish.wait()
        return {"checked": 0, "rows": []}

    monkeypatch.setattr(
        "backend.services.account_status_report.get_account_status_report_service",
        lambda: SimpleNamespace(run=blocked_status),
    )
    monkeypatch.setattr("backend.services.account_status_report._enabled_target", lambda: current_target[0])
    task = scheduling.start_manual_account_report(target)
    assert task is not None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert scheduling.start_manual_account_report(target) is None
        await scheduling._job_account_status_report()
        current_target[0] = ("token", "456", None)
        finish.set()
        result = await asyncio.wait_for(task, 1)
        assert result["success"] is False
        official_run.assert_not_awaited()
    finally:
        finish.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert not scheduling._midnight_workflow_running
