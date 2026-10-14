from __future__ import annotations

import logging
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler: AsyncIOScheduler | None = None
ACCOUNT_STATUS_REPORT_JOB_ID = "system-account-status-report"
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
    logger = logging.getLogger("backend.scheduler")
    timezone = _resolve_scheduler_timezone() or (
        scheduler.timezone if scheduler is not None else None
    )
    now = datetime.now(timezone).astimezone(timezone)
    if now.hour != 0 or now.minute != 0:
        # A delayed or stale trigger must not begin a new all-account scan.
        return
    if _midnight_workflow_running:
        return
    # Capture once before status work. UTC subtraction describes exactly 24
    # elapsed hours even in timezones with daylight-saving transitions.
    end = now.replace(second=0, microsecond=0).astimezone(datetime_timezone.utc)
    start = end - timedelta(hours=24)
    _midnight_workflow_running = True
    try:
        try:
            from backend.services.account_status_report import (
                get_account_status_report_service,
            )

            result = await get_account_status_report_service().run()
            logger.info("Midnight account status report finished: %s", result)
        except Exception as exc:
            logger.error("零点账户状态日报失败（%s）", type(exc).__name__)
        try:
            from backend.services.official_message_report import (
                get_official_message_report_service,
            )

            result = await get_official_message_report_service().run(
                start=start, end=end, timezone=now.tzinfo,
            )
            logger.info("Midnight official message report finished: %s", result)
        except Exception as exc:
            logger.error("零点官方消息日报失败（%s）", type(exc).__name__)
    finally:
        _midnight_workflow_running = False


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
