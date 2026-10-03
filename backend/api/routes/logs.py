from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.login_log import LoginLog
from backend.models.user import User

router = APIRouter()


class LoginLogItem(BaseModel):
    id: int
    username: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    detail: Optional[str] = None
    success: bool
    created_at: str


class TaskHistoryLogItem(BaseModel):
    id: int
    account_name: str
    task_name: str
    message: str
    summary: Optional[str] = None
    bot_message: Optional[str] = None
    success: bool
    created_at: str
    flow_line_count: int = 0
    failure_category: Optional[str] = None


class TaskHistoryLogDetailItem(TaskHistoryLogItem):
    flow_logs: list[str] = []
    flow_truncated: bool = False
    last_target_message: Optional[str] = None


class ClearLogsResponse(BaseModel):
    success: bool
    cleared: int
    message: str


class DeleteLogResponse(BaseModel):
    success: bool
    message: str


def _normalize_date_filter(date: Optional[str]) -> Optional[datetime]:
    if not date:
        return None
    try:
        return datetime.strptime(str(date).strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="INVALID_DATE_FILTER",
        ) from exc


@router.get("/login", response_model=list[LoginLogItem])
def get_login_logs(
    limit: int = 100,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    from tg_signer.utils import clamp

    limit = clamp(limit, 1, 500)

    filter_date = _normalize_date_filter(date)
    query = db.query(LoginLog)
    if filter_date is not None:
        next_day = filter_date + timedelta(days=1)
        query = query.filter(
            LoginLog.created_at >= filter_date,
            LoginLog.created_at < next_day,
        )

    rows = query.order_by(LoginLog.created_at.desc()).limit(limit).all()
    return [
        LoginLogItem(
            id=row.id,
            username=row.username,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            detail=row.detail,
            success=bool(row.success),
            # 存储为 naive UTC，序列化时补时区标记，避免前端按本地时区误解析偏差 8 小时
            created_at=(
                row.created_at.replace(tzinfo=timezone.utc).isoformat()
                if row.created_at is not None
                else None
            ),
        )
        for row in rows
    ]


@router.post("/login/clear", response_model=ClearLogsResponse)
def clear_login_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user

    cleared = db.query(LoginLog).delete()
    db.commit()
    return ClearLogsResponse(success=True, cleared=cleared, message="Login logs cleared")


@router.delete("/login/{log_id}", response_model=DeleteLogResponse)
def delete_login_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user

    row = db.query(LoginLog).filter(LoginLog.id == log_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOGIN_LOG_NOT_FOUND")

    db.delete(row)
    db.commit()
    return DeleteLogResponse(success=True, message="Login log deleted")
