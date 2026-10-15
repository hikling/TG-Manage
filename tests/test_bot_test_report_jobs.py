"""Explicit Bot test report job lifecycle without live Telegram traffic."""
from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

import backend.services.bot_test_report_jobs as reports
from backend.services.background_job import BackgroundJobStore


@pytest.mark.asyncio
@pytest.mark.parametrize("successful", [True, False])
async def test_background_report_job_tracks_actual_delivery(monkeypatch, tmp_path, successful):
    store = BackgroundJobStore(tmp_path / "jobs")
    target = ("token", "123", None)
    monkeypatch.setattr(reports, "get_bot_test_report_store", lambda: store)
    monkeypatch.setattr(reports, "_enabled_target", lambda: target)

    async def run_report():
        await asyncio.sleep(0)
        return {"success": successful, "checked": 2, "messages_sent": 3 if successful else 1}

    task = asyncio.create_task(run_report())
    start = Mock(return_value=task)
    monkeypatch.setattr(reports.scheduling, "start_manual_account_report", start)
    created = reports.start_bot_test_report_job()
    assert created["status"] == "running"
    start.assert_called_once_with(target)

    await task
    await asyncio.sleep(0)
    saved = reports.get_bot_test_report_job(created["job_id"])
    assert saved["status"] == ("completed" if successful else "failed")
    if successful:
        assert saved["summary"]["checked"] == 2
        assert saved["summary"]["messages_sent"] == 3
    else:
        assert "未完整完成" in saved["error"]


def test_background_report_job_rejects_missing_target_or_overlap(monkeypatch, tmp_path):
    store = BackgroundJobStore(tmp_path / "jobs")
    monkeypatch.setattr(reports, "get_bot_test_report_store", lambda: store)
    monkeypatch.setattr(reports, "_enabled_target", lambda: None)
    start = Mock(return_value=None)
    monkeypatch.setattr(reports.scheduling, "start_manual_account_report", start)
    with pytest.raises(ValueError, match="Bot Token"):
        reports.start_bot_test_report_job()
    start.assert_not_called()

    monkeypatch.setattr(reports, "_enabled_target", lambda: ("token", "123", None))
    with pytest.raises(ValueError, match="正在运行"):
        reports.start_bot_test_report_job()
    assert store.list_jobs() == []
