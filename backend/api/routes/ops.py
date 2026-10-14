"""
运维辅助 API：调度预览、进程指标。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.core.config import get_settings
from backend.models.user import User
from backend.scheduler.instance_lock import has_scheduler_lock

logger = logging.getLogger("backend.ops")

router = APIRouter()


class ScheduledJobOut(BaseModel):
    id: str
    name: str = ""
    next_run_time: Optional[str] = None
    trigger: str = ""
    kind: str = Field(
        "other", description="sign / legacy_db / system / other"
    )
    execution_mode: Optional[str] = None
    range_start: Optional[str] = None
    range_end: Optional[str] = None
    task_name: Optional[str] = None
    account_name: Optional[str] = None


class ScheduledJobsResponse(BaseModel):
    jobs: List[ScheduledJobOut]
    total: int
    timezone: str = ""


class MemoryStatsResponse(BaseModel):
    available: bool
    stats: Dict[str, Any] = Field(default_factory=dict)


@router.get("/scheduled-jobs", response_model=ScheduledJobsResponse)
def list_scheduled_jobs(current_user: User = Depends(get_current_user)):
    """Show system maintenance jobs."""
    from backend.scheduler import scheduler

    if scheduler is None:
        return ScheduledJobsResponse(jobs=[], total=0, timezone="")
    jobs = []
    for job in scheduler.get_jobs():
        identifier = str(job.id)
        jobs.append(ScheduledJobOut(
            id=identifier, name=str(job.name or identifier),
            next_run_time=job.next_run_time.isoformat() if job.next_run_time else None,
            trigger=str(job.trigger), kind="system",
        ))
    jobs.sort(key=lambda item: item.next_run_time or "9999")
    return ScheduledJobsResponse(jobs=jobs, total=len(jobs), timezone=str(scheduler.timezone))


@router.get("/memory", response_model=MemoryStatsResponse)
def memory_stats(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """返回内存监控统计（若已启动）。"""
    try:
        monitor = getattr(request.app.state, "memory_monitor", None)
        if monitor is None:
            return MemoryStatsResponse(available=False, stats={})
        return MemoryStatsResponse(available=True, stats=monitor.get_stats())
    except Exception as exc:
        logger.debug("读取内存统计失败: %s", exc)
        return MemoryStatsResponse(available=False, stats={"error": str(exc)})


class RuntimeStatusResponse(BaseModel):
    ready: bool
    scheduler_lock_held: bool = False
    scheduler_role: str = "replica"
    legacy_tasks_writable: bool = False
    legacy_tasks_removed: bool = True
    database_is_sqlite: bool = True
    monitor_shard: str = ""
    monitor_allowlist: str = ""
    uptime_seconds: int = 0


@router.get("/runtime-status", response_model=RuntimeStatusResponse)
def runtime_status(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """面板/运维用运行时摘要（需登录）。"""
    settings = get_settings()
    lock_held = has_scheduler_lock()
    start_time = getattr(request.app.state, "start_time", None)
    uptime_seconds = int(time.time() - start_time) if start_time else 0

    return RuntimeStatusResponse(
        ready=bool(getattr(request.app.state, "ready", False)),
        scheduler_lock_held=lock_held,
        scheduler_role="primary" if lock_held else "replica",
        legacy_tasks_writable=False,
        legacy_tasks_removed=True,
        database_is_sqlite=settings.is_sqlite,
        monitor_shard=os.getenv("APP_MONITOR_SHARD", "") or "",
        monitor_allowlist=os.getenv("APP_MONITOR_ACCOUNT_ALLOWLIST", "") or "",
        uptime_seconds=uptime_seconds,
    )


class VersionInfoResponse(BaseModel):
    version: str
    git_sha: str = ""
    git_branch: str = ""
    build_time: str = ""
    app_name: str = ""
    os_platform: str = ""
    python: str = ""
    update_check_enabled: bool = True


class UpdateCheckInfo(BaseModel):
    enabled: bool
    latest_version: Optional[str] = None
    latest_url: Optional[str] = None
    update_available: bool = False
    checked_at: Optional[str] = None
    error: Optional[str] = None
    source: str = "github_releases"
    cached: bool = False


class VersionCheckResponse(VersionInfoResponse):
    update_check: UpdateCheckInfo


@router.get("/version", response_model=VersionInfoResponse)
def get_version(current_user: User = Depends(get_current_user)):
    """返回本地版本与构建元数据（无外网请求）。"""
    from backend.utils.version_info import get_local_version_info

    return VersionInfoResponse(**get_local_version_info())


@router.post("/version/check", response_model=VersionCheckResponse)
def check_version(
    force: bool = False,
    current_user: User = Depends(get_current_user),
):
    """本地版本 + 可选远程更新检查。

    force=true 时跳过服务端缓存。远程失败 soft-fail，HTTP 仍 200。
    """
    from backend.utils.version_info import (
        check_remote_update,
        get_local_version_info,
    )

    local = get_local_version_info()
    remote = check_remote_update(force=force)
    return VersionCheckResponse(
        **local,
        update_check=UpdateCheckInfo(**remote),
    )

