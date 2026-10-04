"""ConfigService 领域 Mixin（从 config.py 拆分）。

按配置领域划分：签到任务/导出导入和全局设置。
共享的 JSON 读写、路径解析与单例组装仍留在 config.py。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from backend.core.config import get_settings
from backend.utils.cache import TTLCache
from backend.utils.storage import (
    clear_data_dir_override,
    is_writable_dir,
    load_data_dir_override,
    save_data_dir_override,
)

_logger = logging.getLogger("backend.config")

# 全局设置短 TTL 缓存：关键词命中/通知等热路径每次调用都读盘全量 JSON，
# 2 秒窗口内复用，保存路径显式失效，兼顾响应实时性与磁盘 I/O
GLOBAL_SETTINGS_CACHE_TTL = 2.0

def _is_retired_setting(key: str) -> bool:
    """Ignore values left by the removed task runner and AI vision controls."""
    return key.startswith(("sign_task_", "ai_vision_", "telegram_bot_task_")) or key == "sign_interval"

# 全局设置数值钳制表：字段名 -> (下限, 上限)；值为 None 的字段保持 None
_GLOBAL_SETTING_INT_CLAMPS = {
    "device_keepalive_interval_days": (1, 170),
    "auto_backup_interval_hours": (1, 168),
    "auto_backup_keep": (1, 30),
}


def normalize_global_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """钳制/归一化全局设置字段（路由层 fields_set 过滤后透传，服务层统一钳制）。

    - 数值字段按既定范围钳制，None 允许的字段保持 None
    - telegram_bot_token/webdav_password 空串表示不修改（移除键保留旧值）
    - webdav_url/webdav_username/webdav_remote_dir 去首尾空白并兜底默认值
    """
    normalized = dict(settings)
    for key in list(normalized):
        if _is_retired_setting(key):
            normalized.pop(key)

    for key, (low, high) in _GLOBAL_SETTING_INT_CLAMPS.items():
        if key in normalized:
            value = normalized[key]
            normalized[key] = (
                None if value is None else max(low, min(int(value), high))
            )

    # Token 空串不修改；非空去空白（与原路由行为一致）
    if "telegram_bot_token" in normalized:
        tok = normalized["telegram_bot_token"]
        if tok is None or str(tok).strip() == "":
            normalized.pop("telegram_bot_token")
        else:
            normalized["telegram_bot_token"] = str(tok).strip()

    # WebDAV 密码：空串不修改；保留原值（不去空白，避免改动密码本身）
    if "webdav_password" in normalized:
        pwd = normalized["webdav_password"]
        if pwd is None or str(pwd).strip() == "":
            normalized.pop("webdav_password")
        else:
            normalized["webdav_password"] = str(pwd)

    # WebDAV 地址/用户名：去空白，空值归一为 None
    for key in ("webdav_url", "webdav_username"):
        if key in normalized:
            stripped = (normalized[key] or "").strip()
            normalized[key] = stripped or None

    # WebDAV 目录：去空白，空值回落默认目录
    if "webdav_remote_dir" in normalized:
        stripped = (normalized["webdav_remote_dir"] or "").strip()
        normalized["webdav_remote_dir"] = stripped or "tg-signpulse-backups"

    return normalized


class ConfigExportMixin:
    """Portable settings export/import. Legacy task definitions are never activated."""

    SECRET_MASKS = frozenset({"***MASKED***", "***", "MASKED", "REDACTED"})

    def export_all_configs(self) -> str:
        settings = dict(self.get_global_settings())
        settings = {key: value for key, value in settings.items()
                    if not _is_retired_setting(key)}
        masked = {key: bool(settings.get(key)) for key in ("webdav_password", "telegram_bot_token")}
        for key in ("webdav_password", "telegram_bot_token"):
            if settings.get(key):
                settings[key] = "***MASKED***"
        return json.dumps({
            "_meta": {"format": "tg-signpulse-config-export", "version": 2,
                      "includes": ["settings"],
                      "webdav_password_masked": masked["webdav_password"],
                      "telegram_bot_token_masked": masked["telegram_bot_token"],
                      "excludes": ["sessions", "db.sqlite", "history", "account_login_state", "telebox-tasks.json"]},
            "settings": {"global": settings},
        }, ensure_ascii=False, indent=2)

    def import_all_configs(self, json_str: str, overwrite: bool = False) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "signs_imported": 0, "signs_skipped": 0, "monitors_imported": 0,
            "monitors_skipped": 0, "settings_imported": 0, "settings_skipped": 0,
            "errors": [], "warnings": [],
        }
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            result["errors"].append(f"Invalid JSON format: {exc}")
            return result
        if not isinstance(data, dict):
            result["errors"].append("配置根节点必须是对象")
            return result
        for key, counter in (("signs", "signs_skipped"), ("monitors", "monitors_skipped")):
            value = data.get(key)
            if value is not None and not isinstance(value, dict):
                result["errors"].append(f"{key} 字段格式无效")
            elif value:
                result[counter] = len(value)
                result["warnings"].append(f"Retired {key} skipped")
        settings = data.get("settings") or {}
        if not isinstance(settings, dict):
            result["errors"].append("settings 字段格式无效")
            return result
        global_settings = settings.get("global")
        if global_settings is not None:
            if not isinstance(global_settings, dict):
                result["errors"].append("global settings 字段格式无效")
            else:
                values = dict(global_settings)
                for key in ("webdav_password", "telegram_bot_token"):
                    if str(values.get(key) or "").strip() in self.SECRET_MASKS | {""}:
                        values.pop(key, None)
                # Removed task parameters in historical portable exports cannot return.
                values = {key: value for key, value in values.items()
                          if not _is_retired_setting(key)}
                if self.save_global_settings(values):
                    result["settings_imported"] = 1
                else:
                    result["errors"].append("Failed to import global settings")
        for retired in ("ai", "telegram"):
            if retired in settings:
                result["settings_skipped"] += 1
                result["warnings"].append(f"Retired {retired} settings skipped")
        return result

class GlobalSettingsMixin:
    """全局设置读写与导入预览。"""

    def _global_settings_cache(self) -> TTLCache:
        """全局设置 TTL 缓存（惰性初始化，避免 Mixin 无 __init__ 时失效）。"""
        cache = getattr(self, "_gs_cache", None)
        if cache is None:
            cache = TTLCache(maxsize=2, ttl=GLOBAL_SETTINGS_CACHE_TTL)
            self._gs_cache = cache
        return cache

    def _get_global_settings_file(self) -> Path:
        """获取全局设置文件路径"""
        return self.workdir / ".global_settings.json"


    def get_global_settings(self) -> Dict:
        """
        获取全局设置

        Returns:
            设置字典
        """
        config_file = self._get_global_settings_file()
        cached = self._global_settings_cache().get(str(config_file))
        if cached is not None:
            return cached

        override_data_dir = load_data_dir_override()
        default_settings = {
            "chat_center_enabled": False,
            "log_retention_days": 7,
            "data_dir": str(override_data_dir) if override_data_dir else None,
            "global_proxy": None,
            "tg_global_concurrency": None,  # None uses env or cgroup-aware CPU default
            "device_keepalive_enabled": True,
            "device_keepalive_interval_days": 30,
            "telegram_bot_notify_enabled": False,
            "telegram_bot_login_notify_enabled": False,
            "telegram_bot_quiet_hours_enabled": False,
            "telegram_bot_quiet_hours_start": "23:00",
            "telegram_bot_quiet_hours_end": "07:00",
            "telegram_bot_token": None,
            "telegram_bot_chat_id": None,
            "telegram_bot_message_thread_id": None,
            "auto_backup_enabled": False,
            "auto_backup_interval_hours": 24,
            "auto_backup_keep": 3,
            "webdav_url": None,
            "webdav_username": None,
            "webdav_password": None,
            "webdav_remote_dir": "tg-signpulse-backups",
        }

        settings = self._read_json_file(config_file)
        if settings is None or not isinstance(settings, dict):
            settings = dict(default_settings)
        else:
            settings = {key: value for key, value in settings.items()
                        if not _is_retired_setting(key)}
            # 合并默认设置
            for key, value in default_settings.items():
                if key not in settings:
                    settings[key] = value
        # 时区：文件值优先，否则回退环境/核心配置（静默时段等依赖）
        if not settings.get("timezone"):
            try:
                settings["timezone"] = get_settings().timezone
            except Exception:
                settings.setdefault("timezone", "Asia/Hong_Kong")
        self._global_settings_cache().set(str(config_file), settings)
        return settings

    def get_global_proxy(self) -> Optional[str]:
        """读取全局代理（global_proxy），未配置返回 None。

        统一入口：各模块需要"账号代理优先、全局兜底"时先取此值，
        避免直接散落 ``get_global_settings().get("global_proxy")`` 魔法键。
        """
        return self.get_global_settings().get("global_proxy")

    def save_global_settings(self, settings: Dict) -> bool:
        """
        保存全局设置

        Args:
            settings: 设置字典

        Returns:
            是否成功保存
        """
        settings = normalize_global_settings(settings)
        config_file = self._get_global_settings_file()
        merged = dict(self.get_global_settings())
        merged.update(settings)
        for key in list(merged):
            if _is_retired_setting(key):
                merged.pop(key)

        # 校验时区格式（防止导入配置等绕过路由层校验）
        tz_value = merged.get("timezone")
        if tz_value:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(str(tz_value))
            except Exception:
                raise ValueError(f"无效的时区: {tz_value}")

        data_dir_value = merged.get("data_dir")
        if isinstance(data_dir_value, str):
            data_dir_value = data_dir_value.strip()
        if data_dir_value:
            resolved = Path(str(data_dir_value)).expanduser()
            resolved.mkdir(parents=True, exist_ok=True)
            if not is_writable_dir(resolved):
                raise ValueError(f"数据路径不可写: {resolved}")
            save_data_dir_override(resolved)
            merged["data_dir"] = str(resolved)
        elif data_dir_value is None or data_dir_value == "":
            clear_data_dir_override()
            merged["data_dir"] = None

        if not self._write_json_file(config_file, merged):
            return False

        # 写盘成功后失效缓存，保证后续读取拿到最新值
        self._global_settings_cache().delete(str(config_file))
        if merged.get("chat_center_enabled") is False:
            from backend.services.avatar_cache import clear_chat_cache
            clear_chat_cache(get_settings().resolve_workdir() / "avatars" / "chats")

        # Apply the resolved limit as well when an explicit panel value is cleared.
        if "tg_global_concurrency" in settings:
            try:
                from backend.utils.tg_session import _resolve_concurrency_limit, update_global_semaphore
                update_global_semaphore(_resolve_concurrency_limit())
            except Exception as exc:
                # 已写盘成功但运行时未生效，必须可观测，避免面板显示与运行不一致
                _logger.warning(
                    "应用 tg_global_concurrency=%s 到运行时信号量失败: %s",
                    merged.get("tg_global_concurrency"),
                    exc,
                )

        return True


    def preview_import_all(self, json_str: str) -> Dict[str, Any]:
        """Preview settings import; report retired task definitions without reviving them."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            return {"signs_count": 0, "monitors_count": 0, "settings_keys": [],
                    "conflicts": [], "errors": [str(exc)]}
        if not isinstance(data, dict):
            return {"signs_count": 0, "monitors_count": 0, "settings_keys": [],
                    "conflicts": [], "errors": ["配置根节点必须是对象"]}
        errors = []
        counts = {}
        for key in ("signs", "monitors"):
            value = data.get(key) or {}
            if not isinstance(value, dict):
                errors.append(f"{key} 字段格式无效")
                value = {}
            counts[key] = len(value)
        settings = data.get("settings") or {}
        if not isinstance(settings, dict):
            errors.append("settings 字段格式无效")
            settings = {}
        return {"signs_count": counts["signs"], "monitors_count": counts["monitors"],
                "settings_keys": [key for key in ("global", "ai", "telegram") if settings.get(key)],
                "conflicts": [], "errors": errors}
