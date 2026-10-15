"""Background ownership for explicit full Bot test reports."""
from __future__ import annotations

import logging
from typing import Any

import backend.scheduler as scheduling
from backend.core.config import get_settings
from backend.services.account_status_report import _enabled_target
from backend.services.background_job import BackgroundJobStore

logger = logging.getLogger("backend.bot_test_report_jobs")
_store: BackgroundJobStore | None = None


def get_bot_test_report_store() -> BackgroundJobStore:
    global _store
    root = get_settings().resolve_workdir() / "jobs" / "bot_test_report"
    if _store is None or _store.root != root:
        _store = BackgroundJobStore(root)
    return _store


def start_bot_test_report_job() -> dict[str, Any]:
    target = _enabled_target()
    if target is None:
        raise ValueError("请先启用机器人通知并配置 Bot Token 和目标 ID")

    store = get_bot_test_report_store()
    task = scheduling.start_manual_account_report(target)
    if task is None:
        raise ValueError("账户日报检测正在运行，请等待完成")

    try:
        created = store.create_job(kind="bot_test_full_report")
    except Exception:
        task.cancel()
        raise
    job_id = created["job_id"]

    def finish(done) -> None:
        if done.cancelled():
            store.mark_failed(job_id, "检测任务已取消")
            return
        try:
            result = done.result()
        except Exception as exc:
            logger.error("即时账户日报失败（%s）", type(exc).__name__)
            store.mark_failed(job_id, "检测未完成，请查看服务器日志")
            return
        if result["success"]:
            store.mark_completed(job_id, summary=result)
        else:
            store.mark_failed(job_id, "检测或发送未完整完成，请查看已推送的消息和服务器日志")

    task.add_done_callback(finish)
    store.attach_task(job_id, task)
    return created


def get_bot_test_report_job(job_id: str) -> dict[str, Any] | None:
    return get_bot_test_report_store().get_job(job_id)
