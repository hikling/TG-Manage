"""Configuration API routes."""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.models.user import User
from backend.services.config import get_config_service

router = APIRouter()

logger = logging.getLogger("backend.config_api")


class GlobalSettingsSaveResponse(BaseModel):
    success: bool
    message: str


class GlobalSettingsRequest(BaseModel):
    chat_center_enabled: Optional[bool] = None
    log_retention_days: Optional[int] = None
    data_dir: Optional[str] = None
    tg_global_concurrency: Optional[int] = None
    device_keepalive_enabled: Optional[bool] = None
    device_keepalive_interval_days: Optional[int] = None
    telegram_bot_notify_enabled: Optional[bool] = None
    telegram_bot_login_notify_enabled: Optional[bool] = None
    telegram_bot_code_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_bot_chat_id: Optional[str] = None
    telegram_bot_message_thread_id: Optional[int] = None
    timezone: Optional[str] = None
    appearance_accent_color: Optional[str] = None
    hero_position_x: Optional[float] = None
    hero_position_y: Optional[float] = None


class GlobalSettingsResponse(BaseModel):
    chat_center_enabled: bool = False
    log_retention_days: int = 7
    data_dir: Optional[str] = None
    tg_global_concurrency: Optional[int] = None
    device_keepalive_enabled: bool = True
    device_keepalive_interval_days: int = 30
    telegram_bot_notify_enabled: bool = False
    telegram_bot_login_notify_enabled: bool = False
    telegram_bot_code_enabled: bool = False
    telegram_bot_code_status: str = "未启用"
    telegram_bot_token: Optional[str] = None
    telegram_bot_token_set: bool = False
    telegram_bot_chat_id: Optional[str] = None
    telegram_bot_message_thread_id: Optional[int] = None
    timezone: str = "Asia/Hong_Kong"
    appearance_accent_color: str = "#3d6fa8"
    hero_position_x: float = 50.0
    hero_position_y: float = 50.0


class SubscriptionSourceStatus(BaseModel):
    configured: bool = False
    status: str = "unconfigured"
    last_refreshed_at: Optional[str] = None
    usable_count: int = 0
    unsupported_count: int = 0
    label: Optional[str] = None


class ProxySubscriptionsResponse(BaseModel):
    primary: SubscriptionSourceStatus = Field(default_factory=SubscriptionSourceStatus)
    fallback: SubscriptionSourceStatus = Field(default_factory=SubscriptionSourceStatus)
    latency_threshold_ms: int = 800
    route_mode: Literal["primary", "fallback", "direct", "setup_required", "mixed"] = "setup_required"


class ProxySubscriptionsUpdate(BaseModel):
    primary_url: Optional[str] = None
    fallback_url: Optional[str] = None
    latency_threshold_ms: Optional[int] = Field(default=None, ge=100, le=10000)


@router.get("/settings/proxy-subscriptions", response_model=ProxySubscriptionsResponse)
async def get_proxy_subscriptions(current_user: User = Depends(get_current_user)):
    from backend.services.account_routes import get_route_service

    return await get_route_service().get_subscription_settings()


@router.put("/settings/proxy-subscriptions", response_model=ProxySubscriptionsResponse)
async def put_proxy_subscriptions(
    request: ProxySubscriptionsUpdate, current_user: User = Depends(get_current_user),
):
    from backend.services.account_routes import get_route_service

    fields_set = getattr(request, "model_fields_set", None) or getattr(request, "__fields_set__", set())
    changes = {name: getattr(request, name) for name in fields_set}
    try:
        await get_route_service().update_subscription_settings(changes)
    except ValueError:
        raise HTTPException(status_code=400, detail="INVALID_SUBSCRIPTION_SETTINGS") from None
    except Exception as exc:
        logger.warning("Subscription settings update failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="SUBSCRIPTION_UPDATE_FAILED") from None
    return await get_route_service().get_subscription_settings()


@router.post("/settings/proxy-subscriptions/refresh", response_model=ProxySubscriptionsResponse)
async def refresh_proxy_subscriptions(current_user: User = Depends(get_current_user)):
    from backend.services.account_routes import get_route_service

    try:
        await get_route_service().refresh_subscriptions()
    except Exception as exc:
        logger.warning("Subscription refresh failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="SUBSCRIPTION_REFRESH_FAILED") from None
    return await get_route_service().get_subscription_settings()


@router.get("/settings", response_model=GlobalSettingsResponse)
def get_global_settings(current_user: User = Depends(get_current_user)):
    try:
        settings = dict(get_config_service().get_global_settings())
        from backend.core.config import get_settings
        settings.setdefault("timezone", get_settings().timezone)
        # API 响应不暴露 Bot Token 明文
        raw_token = settings.get("telegram_bot_token")
        settings["telegram_bot_token_set"] = bool(
            raw_token is not None and str(raw_token).strip() != ""
        )
        settings["telegram_bot_token"] = None
        from backend.services.official_code_bot import runtime_status
        settings["telegram_bot_code_status"] = runtime_status()
        return GlobalSettingsResponse(**settings)
    except Exception as e:
        logger.error("读取全局设置失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SETTINGS_READ_FAILED",
        )


@router.post("/settings", response_model=GlobalSettingsSaveResponse)
async def save_global_settings(
    request: GlobalSettingsRequest, current_user: User = Depends(get_current_user)
):
    try:
        # 只更新前端实际发送的字段，避免默认值覆盖已有配置；
        # 数值钳制与字符串归一化统一由服务层 normalize_global_settings 处理
        fields_set = getattr(request, "model_fields_set", None) or getattr(request, "__fields_set__", set())
        settings = {
            field_name: getattr(request, field_name)
            for field_name in fields_set
        }

        if not settings:
            return GlobalSettingsSaveResponse(success=True, message="No settings to update")

        if not get_config_service().save_global_settings(settings):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SETTINGS_SAVE_FAILED",
            )
        # 时区变更时同步调度器（后台执行，不阻塞响应）
        if "timezone" in settings:
            import asyncio

            from backend.scheduler import sync_jobs

            async def _safe_tz_sync():
                try:
                    await sync_jobs()
                except Exception as e:
                    logger.warning("设置变更调度同步失败: %s", e)
            asyncio.ensure_future(_safe_tz_sync())
        return GlobalSettingsSaveResponse(success=True, message="Global settings saved")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("保存全局设置失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SETTINGS_SAVE_FAILED",
        )


class DeviceKeepaliveResponse(BaseModel):
    success: bool
    enabled: bool = True
    checked: int = 0
    kept_alive: int = 0
    skipped: int = 0
    failed: int = 0
    interval_days: Optional[int] = None
    results: list[dict] = Field(default_factory=list)
    # 并发冲突等场景下服务层返回的提示信息
    message: Optional[str] = None


@router.post("/settings/device-keepalive/run", response_model=DeviceKeepaliveResponse)
async def run_device_keepalive(current_user: User = Depends(get_current_user)):
    """立即执行一次设备保活。"""
    try:
        from backend.services.device_keepalive import get_device_keepalive_service

        result = await get_device_keepalive_service().run_due(force=True)
        return DeviceKeepaliveResponse(**result)
    except Exception as e:
        logger.error("设备保活失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="设备保活失败",
        )


class BotTestResponse(BaseModel):
    success: bool
    message: str


@router.post("/bot/test-connection", response_model=BotTestResponse)
async def test_bot_connection(current_user: User = Depends(get_current_user)):
    """Send one test message using saved Bot settings, without checking accounts."""
    from backend.services.push_notifications import (
        TelegramBotDeliveryError,
        _bot_config,
        send_telegram_bot_message,
    )

    try:
        token, chat_id, thread_id = _bot_config(get_config_service().get_global_settings())
        if not token or not chat_id:
            return BotTestResponse(success=False, message="请先保存机器人 Token 和目标 ID")
        await send_telegram_bot_message(
            bot_token=token,
            chat_id=chat_id,
            message_thread_id=thread_id,
            text="✅ TG Manage 机器人连接测试成功",
            verify_response=True,
        )
        return BotTestResponse(success=True, message="机器人连接测试成功")
    except TelegramBotDeliveryError as exc:
        return BotTestResponse(success=False, message=str(exc))
    except Exception as exc:
        return BotTestResponse(success=False, message=f"机器人连接测试失败: {type(exc).__name__}")




