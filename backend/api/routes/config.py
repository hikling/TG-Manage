"""Configuration API routes."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.models.user import User
from backend.services.config import get_config_service

router = APIRouter()

logger = logging.getLogger("backend.config_api")


class ImportAllRequest(BaseModel):
    config_json: str
    overwrite: bool = False


class ImportAllResponse(BaseModel):
    signs_imported: int
    signs_skipped: int
    monitors_imported: int
    monitors_skipped: int
    settings_imported: int
    settings_skipped: int = 0
    errors: list[str]
    warnings: list[str] = []
    message: str


@router.get("/export/all")
def export_all_configs(current_user: User = Depends(get_current_user)):
    try:
        config_json = get_config_service().export_all_configs()
        return Response(
            content=config_json.encode("utf-8"),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="tg_manage_all_configs.json"'
            },
        )
    except Exception as e:
        logger.error("导出全部配置失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CONFIG_EXPORT_FAILED",
        )


@router.post("/import/all", response_model=ImportAllResponse)
async def import_all_configs(
    request: ImportAllRequest, current_user: User = Depends(get_current_user)
):
    try:
        raw = json.loads(request.config_json)
        if not isinstance(raw, dict):
            raise ValueError("配置根节点必须是对象")
        # Historical sign/monitor definitions are data only. Never re-import
        # them as executable jobs after switching to TeleBox tasks.
        skipped = sum(len(raw.get(key)) for key in ("signs", "monitors") if isinstance(raw.get(key), dict))
        result = get_config_service().import_all_configs(
            json.dumps({"settings": raw.get("settings") or {}}), request.overwrite
        )
        if skipped:
            result["warnings"].append(f"旧任务/监听配置已跳过：{skipped} 项")

        message_parts = []
        if result.get("signs_imported", 0) > 0:
            message_parts.append(f"sign tasks imported: {result['signs_imported']}")
        if result.get("signs_skipped", 0) > 0:
            message_parts.append(f"sign tasks skipped: {result['signs_skipped']}")
        if result.get("monitors_imported", 0) > 0:
            message_parts.append(
                f"monitor tasks imported: {result['monitors_imported']}"
            )
        if result.get("monitors_skipped", 0) > 0:
            message_parts.append(f"monitor tasks skipped: {result['monitors_skipped']}")
        if result.get("settings_imported", 0) > 0:
            message_parts.append(f"settings imported: {result['settings_imported']}")
        if result.get("settings_skipped", 0) > 0:
            message_parts.append(f"settings skipped: {result['settings_skipped']}")
        if result.get("warnings"):
            message_parts.append(f"warnings: {len(result['warnings'])}")

        message = "; ".join(message_parts) if message_parts else "No config imported"
        # 导入成功后已同步调度；提示前端刷新
        if not result.get("errors"):
            message = f"{message}; scheduler synced" if message_parts else "scheduler synced"

        from backend.scheduler import sync_jobs

        await sync_jobs()
        return ImportAllResponse(
            signs_imported=int(result.get("signs_imported", 0)),
            signs_skipped=int(result.get("signs_skipped", 0)),
            monitors_imported=int(result.get("monitors_imported", 0)),
            monitors_skipped=int(result.get("monitors_skipped", 0)),
            settings_imported=int(result.get("settings_imported", 0)),
            settings_skipped=int(result.get("settings_skipped", 0)),
            errors=[str(item) for item in result.get("errors", [])],
            warnings=[str(item) for item in result.get("warnings", [])],
            message=message,
        )
    except Exception as e:
        logger.error("导入全部配置失败: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CONFIG_IMPORT_FAILED",
        )


class AIConfigSaveResponse(BaseModel):
    success: bool
    message: str


class GlobalSettingsRequest(BaseModel):
    chat_center_enabled: Optional[bool] = None
    log_retention_days: Optional[int] = None
    data_dir: Optional[str] = None
    global_proxy: Optional[str] = None
    tg_global_concurrency: Optional[int] = None
    device_keepalive_enabled: Optional[bool] = None
    device_keepalive_interval_days: Optional[int] = None
    telegram_bot_notify_enabled: Optional[bool] = None
    telegram_bot_login_notify_enabled: Optional[bool] = None
    telegram_bot_code_enabled: Optional[bool] = None
    telegram_bot_quiet_hours_enabled: Optional[bool] = None
    telegram_bot_quiet_hours_start: Optional[str] = None
    telegram_bot_quiet_hours_end: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_bot_chat_id: Optional[str] = None
    telegram_bot_message_thread_id: Optional[int] = None
    timezone: Optional[str] = None
    auto_backup_enabled: Optional[bool] = None
    auto_backup_interval_hours: Optional[int] = None
    auto_backup_keep: Optional[int] = None
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    webdav_remote_dir: Optional[str] = None


class GlobalSettingsResponse(BaseModel):
    chat_center_enabled: bool = False
    log_retention_days: int = 7
    data_dir: Optional[str] = None
    global_proxy: Optional[str] = None
    tg_global_concurrency: Optional[int] = None
    device_keepalive_enabled: bool = True
    device_keepalive_interval_days: int = 30
    telegram_bot_notify_enabled: bool = False
    telegram_bot_login_notify_enabled: bool = False
    telegram_bot_code_enabled: bool = False
    telegram_bot_code_status: str = "未启用"
    telegram_bot_quiet_hours_enabled: bool = False
    telegram_bot_quiet_hours_start: Optional[str] = "23:00"
    telegram_bot_quiet_hours_end: Optional[str] = "07:00"
    telegram_bot_token: Optional[str] = None
    telegram_bot_token_set: bool = False
    telegram_bot_chat_id: Optional[str] = None
    telegram_bot_message_thread_id: Optional[int] = None
    timezone: str = "Asia/Hong_Kong"
    auto_backup_enabled: bool = False
    auto_backup_interval_hours: Optional[int] = 24
    auto_backup_keep: Optional[int] = 3
    webdav_url: Optional[str] = None
    webdav_username: Optional[str] = None
    # GET 永不回传明文密码；用 webdav_password_set 表示已落盘
    webdav_password: Optional[str] = None
    webdav_password_set: bool = False
    webdav_remote_dir: Optional[str] = "tg-manage-backups"


@router.get("/settings", response_model=GlobalSettingsResponse)
def get_global_settings(current_user: User = Depends(get_current_user)):
    try:
        settings = dict(get_config_service().get_global_settings())
        from backend.core.config import get_settings
        settings.setdefault("timezone", get_settings().timezone)
        # 脱敏：API 响应不暴露 WebDAV 密码 / Bot Token 明文
        raw_pwd = settings.get("webdav_password")
        settings["webdav_password_set"] = bool(
            raw_pwd is not None and str(raw_pwd).strip() != ""
        )
        settings["webdav_password"] = None
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


@router.post("/settings", response_model=AIConfigSaveResponse)
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
            return AIConfigSaveResponse(success=True, message="No settings to update")

        if not get_config_service().save_global_settings(settings):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SETTINGS_SAVE_FAILED",
            )
        # 时区/自动备份变更时同步调度器（后台执行，不阻塞响应）
        if "timezone" in settings or "auto_backup_enabled" in settings or "auto_backup_interval_hours" in settings:
            import asyncio

            from backend.scheduler import sync_jobs

            async def _safe_tz_sync():
                try:
                    await sync_jobs()
                except Exception as e:
                    logger.warning("设置变更调度同步失败: %s", e)
            asyncio.ensure_future(_safe_tz_sync())
        return AIConfigSaveResponse(success=True, message="Global settings saved")
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


class BotTestRequest(BaseModel):
    message: Optional[str] = None


class BotTestResponse(BaseModel):
    success: bool
    message: str


@router.post("/bot/test", response_model=BotTestResponse)
async def test_bot_notification(
    request: BotTestRequest = BotTestRequest(),
    current_user: User = Depends(get_current_user),
):
    """使用已保存的 Bot 配置发送测试消息。"""
    cfg = get_config_service().get_global_settings()
    bot_token = (cfg.get("telegram_bot_token") or "").strip()
    chat_id = (cfg.get("telegram_bot_chat_id") or "").strip()
    if not bot_token or not chat_id:
        return BotTestResponse(success=False, message="未配置 Bot Token 或 Chat ID")
    raw_msg = (request.message or "").strip()
    text = raw_msg or "TG Manage 通知测试：连接正常"
    # 限制长度，避免误填超大文本导致 Telegram API 失败
    text = text[:3900]
    try:
        from backend.services.push_notifications import send_telegram_bot_message

        thread_id = cfg.get("telegram_bot_message_thread_id")
        try:
            thread_id = int(thread_id) if thread_id not in (None, "") else None
        except (TypeError, ValueError):
            thread_id = None
        await send_telegram_bot_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=text,
            message_thread_id=thread_id,
        )
        return BotTestResponse(success=True, message="测试消息已发送")
    except Exception as e:
        # 不回传完整异常栈，避免 token/网络细节外泄到前端
        err = type(e).__name__
        return BotTestResponse(success=False, message=f"发送失败: {err}")


class ImportPreviewRequest(BaseModel):
    config_json: str


class ImportPreviewResponse(BaseModel):
    signs_count: int = 0
    monitors_count: int = 0
    settings_keys: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


@router.post("/import-preview", response_model=ImportPreviewResponse)
def import_preview(
    request: ImportPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """预览配置导入，不写盘。"""
    try:
        result = get_config_service().preview_import_all(request.config_json)
        return ImportPreviewResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入预览失败: {e}",
        )
