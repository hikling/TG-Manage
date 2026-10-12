from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler: AsyncIOScheduler | None = None
ACCOUNT_STATUS_REPORT_JOB_ID = "system-account-status-report"


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



async def _job_auto_backup() -> None:
    """按全局设置执行自动备份。"""
    from pathlib import Path

    logger = logging.getLogger("backend.scheduler")
    cfg: dict = {}
    try:
        from backend.core.config import get_settings
        from backend.services.backup_archive import (
            auto_backup_keep,
            run_auto_backup,
            should_run_auto_backup,
        )
        from backend.services.config import get_config_service
        from backend.services.push_notifications import (
            send_auto_backup_failure_notification,
        )

        cfg = get_config_service().get_global_settings()
        if not should_run_auto_backup(cfg):
            return
        data_dir = Path(get_settings().resolve_base_dir())
        # 打包 + WebDAV 上传均为同步阻塞操作，放入线程池避免冻结事件循环
        # （数据目录大时打包可能耗时数十秒，阻塞期间 API/SSE/调度全部停摆）
        result = await asyncio.to_thread(
            run_auto_backup,
            data_dir,
            keep=auto_backup_keep(cfg),
            webdav_settings=cfg,
        )
        wd = result.get("webdav") or {}
        logger.info(
            "Auto backup finished: path=%s size=%s pruned=%s remote_pruned=%s "
            "local_removed=%s webdav=%s webdav_error=%s",
            result.get("path"),
            result.get("size_bytes"),
            result.get("pruned"),
            result.get("remote_pruned"),
            result.get("local_removed"),
            wd.get("success"),
            wd.get("error"),
        )
        # 打包失败，或配置了 WebDAV 但上传失败 → 通知
        fail_reason = ""
        if not result.get("success"):
            fail_reason = str(result.get("error") or "备份打包失败")
        elif (cfg.get("webdav_url") or "").strip() and wd.get("success") is False:
            fail_reason = str(wd.get("error") or "WebDAV 上传失败")
        if fail_reason:
            await send_auto_backup_failure_notification(
                cfg,
                error=fail_reason,
                detail=f"path={result.get('path') or '-'}",
            )
    except Exception as exc:
        # 顶层兜底：自动备份 Job 失败不能阻塞调度器，但要推送告警
        logger.error("自动备份任务失败: %s", exc, exc_info=True)
        try:
            from backend.services.push_notifications import (
                send_auto_backup_failure_notification,
            )

            if cfg:
                await send_auto_backup_failure_notification(
                    cfg, error=str(exc), detail="scheduler exception"
                )
        except Exception:
            logger.exception("自动备份失败通知也发送失败")


def _sync_auto_backup_job() -> None:
    """根据全局设置注册/移除自动备份 interval job。"""
    global scheduler
    if scheduler is None:
        return

    from apscheduler.jobstores.base import JobLookupError
    from apscheduler.triggers.interval import IntervalTrigger

    logger = logging.getLogger("backend.scheduler")
    job_id = "system-auto-backup"
    try:
        from backend.services.backup_archive import (
            auto_backup_interval_hours,
            should_run_auto_backup,
        )
        from backend.services.config import get_config_service

        cfg = get_config_service().get_global_settings()
        if should_run_auto_backup(cfg):
            hours = auto_backup_interval_hours(cfg)
            scheduler.add_job(
                _job_auto_backup,
                trigger=IntervalTrigger(hours=hours),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("自动备份任务已注册：每 %s 小时", hours)
        else:
            try:
                scheduler.remove_job(job_id)
            except JobLookupError:
                # job 不存在时静默忽略
                pass
    except (ImportError, AttributeError, ValueError, KeyError, RuntimeError) as exc:
        logger.warning("同步自动备份任务失败: %s", exc)
    except Exception:
        # 兜底：未知异常不阻塞 sync 流程，记录完整堆栈便于排障
        logger.exception("同步自动备份任务发生未知异常")


async def _job_account_status_report() -> None:
    logger = logging.getLogger("backend.scheduler")
    timezone = _resolve_scheduler_timezone() or (
        scheduler.timezone if scheduler is not None else None
    )
    now = datetime.now(timezone)
    if now.hour != 0 or now.minute != 0:
        # A delayed or stale trigger must not begin a new all-account scan.
        return
    try:
        from backend.services.account_status_report import (
            get_account_status_report_service,
        )

        result = await get_account_status_report_service().run()
        logger.info("Midnight account status report finished: %s", result)
    except Exception as exc:
        logger.error("零点账户状态日报失败（%s）", type(exc).__name__)


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
            if job.id == "system-device-keepalive" or str(job.id).startswith(
                ("tb-", "sign-", "db-")
            ):
                scheduler.remove_job(job.id)


async def sync_jobs() -> None:
    """Refresh system jobs; remove jobs from the retired task orchestration."""
    _remove_retired_jobs()
    _sync_auto_backup_job()
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

        _sync_auto_backup_job()
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
