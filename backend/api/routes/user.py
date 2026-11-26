from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass
from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.auth import (
    create_access_token,
    get_current_user,
    get_user_by_username,
    require_standard_admin_user,
    verify_totp,
)
from backend.core.database import get_db
from backend.core.rate_limit import compose_rate_limit_key, get_rate_limiter
from backend.core.security import hash_password, verify_password
from backend.models.user import User

try:
    import qrcode
except Exception:  # pragma: no cover - optional dependency fallback
    qrcode = None

router = APIRouter()
rate_limiter = get_rate_limiter()

_FALLBACK_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_PENDING_TOTP_TTL_SECONDS = 10 * 60


@dataclass
class PendingTOTPSecret:
    secret: str
    created_at: float


_pending_totp_lock = threading.Lock()
_pending_totp_secrets: dict[int, PendingTOTPSecret] = {}


def _cleanup_expired_pending_totp_secrets_locked(now: Optional[float] = None) -> None:
    current = time.monotonic() if now is None else now
    expired_user_ids = [
        user_id
        for user_id, entry in _pending_totp_secrets.items()
        if current - entry.created_at >= _PENDING_TOTP_TTL_SECONDS
    ]
    for user_id in expired_user_ids:
        _pending_totp_secrets.pop(user_id, None)


def _set_pending_totp_secret(user_id: int, secret: str) -> None:
    with _pending_totp_lock:
        _cleanup_expired_pending_totp_secrets_locked()
        _pending_totp_secrets[user_id] = PendingTOTPSecret(
            secret=secret,
            created_at=time.monotonic(),
        )


def get_pending_totp_secret(user_id: int) -> Optional[str]:
    with _pending_totp_lock:
        _cleanup_expired_pending_totp_secrets_locked()
        entry = _pending_totp_secrets.get(user_id)
        if entry is None:
            return None
        return entry.secret


def clear_pending_totp_secret(user_id: int) -> None:
    with _pending_totp_lock:
        _pending_totp_secrets.pop(user_id, None)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str
    access_token: str


class ChangeUsernameRequest(BaseModel):
    new_username: str
    password: str


class ChangeUsernameResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None


class EnableTOTPRequest(BaseModel):
    totp_code: str


class EnableTOTPResponse(BaseModel):
    success: bool
    message: str
    access_token: str


class DisableTOTPRequest(BaseModel):
    totp_code: str


class DisableTOTPResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None


class TOTPStatusResponse(BaseModel):
    enabled: bool
    secret: Optional[str] = None


@router.put("/password", response_model=ChangePasswordResponse)
def change_password(
    request: ChangePasswordRequest,
    http_request: Request,
    current_user: User = Depends(require_standard_admin_user),
    db: Session = Depends(get_db),
):
    limit_key = compose_rate_limit_key(http_request, str(current_user.id))
    rate_limiter.hit(
        scope="user.password",
        key=limit_key,
        max_attempts=5,
        window_seconds=300,
        block_seconds=900,
        detail="Too many password change attempts. Please try again later.",
    )
    if not verify_password(request.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    if len(request.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码长度至少为 6 个字符",
        )
    if len(request.new_password.encode("utf-8")) > 72:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码长度不能超过 72 字节",
        )

    current_user.password_hash = hash_password(request.new_password)
    current_user.auth_version = (current_user.auth_version or 0) + 1
    db.commit()
    rate_limiter.reset("user.password", limit_key)

    return ChangePasswordResponse(
        success=True, message="密码修改成功",
        access_token=create_access_token({"sub": current_user.username, "auth_version": current_user.auth_version}),
    )


@router.put("/username", response_model=ChangeUsernameResponse)
def change_username(
    request: ChangeUsernameRequest,
    http_request: Request,
    current_user: User = Depends(require_standard_admin_user),
    db: Session = Depends(get_db),
):
    limit_key = compose_rate_limit_key(http_request, str(current_user.id))
    rate_limiter.hit(
        scope="user.username",
        key=limit_key,
        max_attempts=5,
        window_seconds=300,
        block_seconds=900,
        detail="Too many username change attempts. Please try again later.",
    )
    if not verify_password(request.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码错误",
        )

    new_username = request.new_username.strip()
    if len(new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度至少为 3 个字符",
        )
    if len(new_username) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度最多为 50 个字符",
        )

    existing_user = get_user_by_username(db, new_username)
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该用户名已被使用",
        )

    current_user.username = new_username
    current_user.auth_version = (current_user.auth_version or 0) + 1
    db.commit()
    rate_limiter.reset("user.username", limit_key)

    new_token = create_access_token(data={"sub": new_username, "auth_version": current_user.auth_version})
    return ChangeUsernameResponse(
        success=True,
        message="用户名修改成功",
        access_token=new_token,
    )


@router.get("/totp/status", response_model=TOTPStatusResponse)
def get_totp_status(current_user: User = Depends(get_current_user)):
    return TOTPStatusResponse(
        enabled=bool(current_user.totp_secret),
        secret=None,
    )


@router.post("/totp/setup", response_model=TOTPStatusResponse)
def setup_totp(current_user: User = Depends(require_standard_admin_user)):
    if current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 已启用，如需重新设置请先禁用",
        )

    secret = pyotp.random_base32()
    _set_pending_totp_secret(current_user.id, secret)
    return TOTPStatusResponse(enabled=False, secret=secret)


@router.get("/totp/qrcode")
def get_totp_qrcode(
    current_user: User = Depends(require_standard_admin_user),
):
    secret = get_pending_totp_secret(current_user.id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先调用 /totp/setup 设置 2FA",
        )

    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="TG Manage")

    if qrcode is None:
        img_io = io.BytesIO(_FALLBACK_PNG)
    else:
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_io = io.BytesIO()
        img.save(img_io, "PNG")
        img_io.seek(0)

    return StreamingResponse(
        img_io,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/totp/enable", response_model=EnableTOTPResponse)
def enable_totp(
    request: EnableTOTPRequest,
    http_request: Request,
    current_user: User = Depends(require_standard_admin_user),
    db: Session = Depends(get_db),
):
    limit_key = compose_rate_limit_key(http_request, str(current_user.id))
    rate_limiter.hit(
        scope="user.totp.enable",
        key=limit_key,
        max_attempts=5,
        window_seconds=300,
        block_seconds=900,
        detail="Too many 2FA attempts. Please try again later.",
    )
    pending_secret = get_pending_totp_secret(current_user.id)
    if not pending_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 设置已过期，请重新执行 setup",
        )

    if not verify_totp(pending_secret, request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    current_user.totp_secret = pending_secret
    current_user.auth_version = (current_user.auth_version or 0) + 1
    db.commit()
    clear_pending_totp_secret(current_user.id)
    rate_limiter.reset("user.totp.enable", limit_key)

    return EnableTOTPResponse(
        success=True, message="两步验证已启用",
        access_token=create_access_token({"sub": current_user.username, "auth_version": current_user.auth_version}),
    )


@router.post("/totp/cancel", response_model=DisableTOTPResponse)
def cancel_totp_setup(current_user: User = Depends(require_standard_admin_user)):
    clear_pending_totp_secret(current_user.id)
    return DisableTOTPResponse(success=True, message="2FA 设置已取消")


@router.post("/totp/disable", response_model=DisableTOTPResponse)
def disable_totp(
    request: DisableTOTPRequest,
    http_request: Request,
    current_user: User = Depends(require_standard_admin_user),
    db: Session = Depends(get_db),
):
    limit_key = compose_rate_limit_key(http_request, str(current_user.id))
    rate_limiter.hit(
        scope="user.totp.disable",
        key=limit_key,
        max_attempts=5,
        window_seconds=300,
        block_seconds=900,
        detail="Too many 2FA attempts. Please try again later.",
    )
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA 未启用",
        )

    if not verify_totp(current_user.totp_secret, request.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误",
        )

    current_user.totp_secret = None
    current_user.auth_version = (current_user.auth_version or 0) + 1
    db.commit()
    clear_pending_totp_secret(current_user.id)
    rate_limiter.reset("user.totp.disable", limit_key)

    return DisableTOTPResponse(
        success=True, message="两步验证已禁用",
        access_token=create_access_token({"sub": current_user.username, "auth_version": current_user.auth_version}),
    )
