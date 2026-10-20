from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

scheduler: AsyncIOScheduler | None = None
ACCOUNT_STATUS_REPORT_JOB_ID = "system-account-status-report"
ROUTE_HEALTH_JOB_ID = "system-account-route-health"
SUBSCRIPTION_REFRESH_JOB_ID = "system-account-subscription-refresh"
_midnight_workflow_running = False


def _parse_clock_time(value: str):
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid clock time: {value}")


def _resolve_scheduler_timezone():
    """解析调度器使用的时区（Web UI 全局设置优先，回退环境变量）；失败返回 None。"""
    try:
        from backend.core.config import get_settings
        from backend.services.config import get_config_service

        saved_settings = get_config_service().get_global_settings()
        tz_name = saved_settings.get("timezone") or get_settings().timezone
        if not tz_name:
            return None
        from zoneinfo import ZoneInfo

        return ZoneInfo(str(tz_name))
    except Exception as exc:
        logging.getLogger("backend.scheduler").debug(
            "解析调度器时区失败，使用本地时区: %s", exc
        )
        return None


def create_cron_trigger(cron_str: str, timezone: str = "") -> CronTrigger:
    """自动解析格式并创建 CronTrigger，支持 5位和6位 cron 表达式以及 HH:MM 或 HH:MM:SS"""
    if ":" in cron_str:
        parts = cron_str.split(":")
        try:
            if len(parts) == 2:
                hour, minute = parts
                cron_str = f"0 {int(minute)} {int(hour)} * * *"
            elif len(parts) == 3:
                hour, minute, second = parts
                cron_str = f"{int(second)} {int(minute)} {int(hour)} * * *"
        except ValueError as exc:
            logging.getLogger("backend.scheduler").debug(
                "clock-time cron parse failed for %r: %s", cron_str, exc
            )

    # 获取有效时区：优先使用传入参数，否则从全局配置回退到环境变量
    tz = timezone
    if not tz:
        try:
            from backend.core.config import get_settings
            from backend.services.config import get_config_service
            saved_settings = get_config_service().get_global_settings()
            tz = saved_settings.get("timezone") or get_settings().timezone
        except (ImportError, AttributeError, ValueError, KeyError) as exc:
            logging.getLogger("backend.scheduler").debug(
                "读取全局时区配置失败，使用调度器默认时区: %s", exc
            )
            tz = ""

    parts = cron_str.split()
    if len(parts) == 6:
        return CronTrigger(
            second=parts[0],
            minute=parts[1],
            hour=parts[2],
            day=parts[3],
            month=parts[4],
            day_of_week=parts[5],
            timezone=tz or None,
        )
    return CronTrigger.from_crontab(cron_str, timezone=tz or None)



async def _job_account_status_report() -> None:
    global _midnight_workflow_running
    timezone = _resolve_scheduler_timezone() or (
        scheduler.timezone if scheduler is not None else None
    )
    now = datetime.now(timezone).astimezone(timezone)
    if now.hour != 0 or now.minute != 0:
        # A delayed or stale trigger must not begin a new all-account scan.
        return
    if _midnight_workflow_running:
        return
    _midnight_workflow_running = True
    try:
        await _run_combined_report(now.replace(second=0, microsecond=0))
    finally:
        _midnight_workflow_running = False


async def _run_combined_report(now: datetime) -> dict[str, int | bool]:
    """Run the scheduled midnight report for its fixed preceding 24 hours."""
    logger = logging.getLogger("backend.scheduler")
    subscriptions_ok, subscription_messages = await _refresh_midnight_subscriptions()
    end = now.astimezone(datetime_timezone.utc)
    start = end - timedelta(hours=24)
    status_rows = None
    official_status = None
    official_result = None
    status_failed = False
    official_failed = False
    try:
        from backend.services.account_status_report import (
            get_account_status_report_service,
        )

        result = await get_account_status_report_service().run(
            send_report=False, midnight_recovery=True,
        )
        status_rows = result.get("rows")
        status_failed = bool(result.get("skipped")) or status_rows is None
        logger.info("Account status check finished: checked=%s", result.get("checked"))
    except Exception as exc:
        status_failed = True
        logger.error("账户状态日报失败（%s）", type(exc).__name__)
    try:
        from backend.services.official_message_report import (
            get_official_message_report_service,
        )

        official_result = await get_official_message_report_service().run(
            start=start, end=end, timezone=now.tzinfo, send_normal_summary=False,
            account_names=[row["account_name"] for row in status_rows] if status_rows is not None else None,
        )
        official_status = official_result.get("account_status")
        official_failed = (
            bool(official_result.get("skipped"))
            or bool(official_result.get("stopped"))
            or bool(official_result.get("failed"))
            or official_status is None
        )
        logger.info("Official message check finished: accounts=%s", official_result.get("accounts"))
    except Exception as exc:
        official_failed = True
        logger.error("官方消息日报失败（%s）", type(exc).__name__)
    sent = 0
    expected_chunks = 0
    if status_rows is not None:
        try:
            from backend.services.account_status_report import (
                _send_report,
                report_chunks,
            )
            combined_official_status = official_status or {}
            expected_chunks = len(report_chunks(status_rows, combined_official_status))
            sent = await _send_report(status_rows, combined_official_status)
        except Exception as exc:
            logger.error("合并日报发送失败（%s）", type(exc).__name__)
    return {
        "success": subscriptions_ok and not status_failed and not official_failed and sent == expected_chunks,
        "checked": len(status_rows or []),
        "messages_sent": subscription_messages + sent + int((official_result or {}).get("messages_sent") or 0),
    }


async def _refresh_midnight_subscriptions() -> tuple[bool, int]:
    """Refresh both sources before account checks and report their saved counts."""
    logger = logging.getLogger("backend.scheduler")
    try:
        from backend.services.account_routes import get_route_service

        route_service = get_route_service()
    except Exception as exc:
        logger.error("零点订阅服务不可用（%s）", type(exc).__name__)
        return False, 0

    refresh_interrupted = False
    try:
        await route_service.refresh_subscriptions()
    except Exception as exc:
        refresh_interrupted = True
        logger.error("零点订阅刷新中断（%s）", type(exc).__name__)

    try:
        settings = await route_service.get_subscription_settings()
    except Exception as exc:
        logger.error("零点订阅状态读取失败（%s）", type(exc).__name__)
        return False, 0

    sources_ready = all(
        not (settings.get(source) or {}).get("configured")
        or (settings.get(source) or {}).get("status") == "ready"
        for source in ("primary", "fallback")
    )
    from backend.services.account_status_report import _send_subscription_report

    sent = await _send_subscription_report(
        settings, refresh_interrupted=refresh_interrupted,
    )
    return not refresh_interrupted and sources_ready, sent


def _sync_account_status_report_job() -> None:
    if scheduler is None:
        return
    from backend.scheduler.instance_lock import has_scheduler_lock

    if not has_scheduler_lock():
        return
    timezone = _resolve_scheduler_timezone() or scheduler.timezone
    trigger = CronTrigger(hour=0, minute=0, second=0, timezone=timezone)
    job = scheduler.get_job(ACCOUNT_STATUS_REPORT_JOB_ID)
    if job is None:
        scheduler.add_job(
            _job_account_status_report,
            trigger=trigger,
            id=ACCOUNT_STATUS_REPORT_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=59,
        )
    elif str(job.trigger.timezone) != str(timezone):
        # Preserve running-job admission limits; only update the next midnight.
        scheduler.reschedule_job(ACCOUNT_STATUS_REPORT_JOB_ID, trigger=trigger)


async def _job_route_health() -> None:
    from backend.scheduler.instance_lock import has_scheduler_lock
    from backend.services.account_routes import get_route_service

    if has_scheduler_lock():
        await get_route_service().health_tick()


async def _job_subscription_refresh() -> None:
    from backend.scheduler.instance_lock import has_scheduler_lock
    from backend.services.account_routes import get_route_service

    if has_scheduler_lock():
        await get_route_service().subscription_tick()


def _sync_route_jobs() -> None:
    if scheduler is None:
        return
    from backend.scheduler.instance_lock import has_scheduler_lock

    if not has_scheduler_lock():
        for job_id in (ROUTE_HEALTH_JOB_ID, SUBSCRIPTION_REFRESH_JOB_ID):
            if scheduler.get_job(job_id) is not None:
                scheduler.remove_job(job_id)
        return
    for job_id, func, minutes in (
        (ROUTE_HEALTH_JOB_ID, _job_route_health, 5),
        (SUBSCRIPTION_REFRESH_JOB_ID, _job_subscription_refresh, 60),
    ):
        if scheduler.get_job(job_id) is None:
            scheduler.add_job(
                func,
                trigger=IntervalTrigger(minutes=minutes, jitter=20),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=30,
            )


def _remove_retired_jobs() -> None:
    if scheduler is not None:
        for job in scheduler.get_jobs():
            if job.id in {"system-device-keepalive", "system-auto-backup"} or str(job.id).startswith(
                ("tb-", "sign-", "db-")
            ):
                scheduler.remove_job(job.id)


async def sync_jobs() -> None:
    """Refresh system jobs; remove jobs from the retired task orchestration."""
    _remove_retired_jobs()
    _sync_account_status_report_job()
    _sync_route_jobs()


async def init_scheduler(sync_on_startup: bool = True) -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        from backend.core.config import get_settings
        from backend.scheduler.instance_lock import try_acquire_scheduler_lock
        from backend.services.config import get_config_service

        settings = get_settings()
        # 优先使用 Web UI 保存的时区，否则使用环境变量
        tz = settings.timezone
        try:
            saved_settings = get_config_service().get_global_settings()
            saved_tz = saved_settings.get("timezone")
            if saved_tz:
                tz = saved_tz
        except (ImportError, AttributeError, ValueError, KeyError) as exc:
            logging.getLogger("backend.scheduler").warning(
                "读取全局时区设置失败，使用默认时区 %s: %s", settings.timezone, exc
            )

        # 多实例场景：仅锁持有者注册业务调度
        try_acquire_scheduler_lock()

        scheduler = AsyncIOScheduler(
            timezone=tz,
            job_defaults={
                "misfire_grace_time": 3600,  # 允许任务延迟 1 小时执行
                "coalesce": True,  # 合并积压的执行
                "max_instances": 10,  # 增加并发实例数，避免多账号任务相互阻塞
            },
        )
        scheduler.start()

        _sync_account_status_report_job()
        _sync_route_jobs()

        if sync_on_startup:
            await sync_jobs()
    _remove_retired_jobs()
    return scheduler


def shutdown_scheduler() -> None:
    global scheduler
    if scheduler:
        try:
            if getattr(scheduler, "running", False):
                scheduler.shutdown(wait=False)
        except RuntimeError as exc:
            # 调度器已停止或未运行时静默忽略
            logging.getLogger("backend.scheduler").debug(
                "调度器关闭时已停止运行: %s", exc
            )
        except Exception:
            logging.getLogger("backend.scheduler").exception(
                "调度器关闭发生未知异常"
            )
        scheduler = None
    try:
        from backend.scheduler.instance_lock import release_scheduler_lock

        release_scheduler_lock()
    except Exception:
        logging.getLogger("backend.scheduler").exception(
            "释放调度锁发生未知异常"
        )
        scheduler = None
