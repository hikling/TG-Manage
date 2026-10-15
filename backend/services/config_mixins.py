"""ConfigService 领域 Mixin（从 config.py 拆分）。

管理全局设置。
共享的 JSON 读写、路径解析与单例组装仍留在 config.py。
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict

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
    """Ignore removed controls, including the legacy account proxy fallback."""
    return key.startswith(("sign_task_", "ai_vision_", "telegram_bot_task_", "telegram_bot_quiet_hours_")) or key in {
        "sign_interval", "global_proxy", "auto_backup_enabled",
        "auto_backup_interval_hours", "auto_backup_keep", "webdav_url",
        "webdav_username", "webdav_password", "webdav_remote_dir",
    }

# 全局设置数值钳制表：字段名 -> (下限, 上限)；值为 None 的字段保持 None
_GLOBAL_SETTING_INT_CLAMPS = {
    "device_keepalive_interval_days": (1, 170),
}
_HEX_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$", re.IGNORECASE)
_GLOBAL_SETTING_POSITION_FIELDS = ("hero_position_x", "hero_position_y")


def normalize_global_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """钳制/归一化全局设置字段（路由层 fields_set 过滤后透传，服务层统一钳制）。

    - 数值字段按既定范围钳制，None 允许的字段保持 None
    - telegram_bot_token 空串表示不修改（移除键保留旧值）
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

    if "appearance_accent_color" in normalized:
        color = str(normalized["appearance_accent_color"] or "").strip().lower()
        if not _HEX_COLOR_RE.fullmatch(color):
            raise ValueError("主题色必须是六位十六进制颜色")
        normalized["appearance_accent_color"] = color

    for key in _GLOBAL_SETTING_POSITION_FIELDS:
        if key in normalized:
            try:
                value = float(normalized[key])
            except (TypeError, ValueError) as exc:
                raise ValueError("封面位置必须是 0 到 100 之间的数字") from exc
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("封面位置必须是 0 到 100 之间的数字")
            normalized[key] = round(max(0.0, min(value, 100.0)), 2)

    # Token 空串不修改；非空去空白（与原路由行为一致）
    if "telegram_bot_token" in normalized:
        tok = normalized["telegram_bot_token"]
        if tok is None or str(tok).strip() == "":
            normalized.pop("telegram_bot_token")
        else:
            normalized["telegram_bot_token"] = str(tok).strip()

    if "telegram_bot_code_enabled" in normalized:
        value = normalized["telegram_bot_code_enabled"]
        if isinstance(value, str):
            if value.strip().lower() not in {"true", "false", "1", "0"}:
                raise ValueError("验证码机器人开关必须是布尔值")
            normalized["telegram_bot_code_enabled"] = value.strip().lower() in {"true", "1"}
        else:
            normalized["telegram_bot_code_enabled"] = bool(value)
    if "telegram_bot_chat_id" in normalized and normalized["telegram_bot_chat_id"] is not None:
        normalized["telegram_bot_chat_id"] = str(normalized["telegram_bot_chat_id"]).strip() or None

    return normalized


class GlobalSettingsMixin:
    """全局设置读写。"""

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
            "tg_global_concurrency": None,  # None uses env or cgroup-aware CPU default
            "device_keepalive_enabled": True,
            "device_keepalive_interval_days": 30,
            "telegram_bot_notify_enabled": False,
            "telegram_bot_login_notify_enabled": False,
            "telegram_bot_code_enabled": False,
            "telegram_bot_token": None,
            "telegram_bot_chat_id": None,
            "telegram_bot_message_thread_id": None,
            "appearance_accent_color": "#3d6fa8",
            "hero_position_x": 50.0,
            "hero_position_y": 50.0,
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
        # 时区：文件值优先，否则回退环境/核心配置
        if not settings.get("timezone"):
            try:
                settings["timezone"] = get_settings().timezone
            except Exception:
                settings.setdefault("timezone", "Asia/Hong_Kong")
        self._global_settings_cache().set(str(config_file), settings)
        return settings

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
        if merged.get("telegram_bot_code_enabled"):
            from backend.services.official_code_bot import private_target

            if private_target(merged) is None:
                raise ValueError("验证码机器人需要正整数的私人目标 ID")
            if not merged.get("telegram_bot_token"):
                raise ValueError("验证码机器人需要先设置 Bot Token")
        for key in list(merged):
            if _is_retired_setting(key):
                merged.pop(key)

        # 服务层统一校验时区格式。
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

        # Keep the old on-disk value for rollback, but never project or update it.
        stored = self._read_json_file(config_file)
        if isinstance(stored, dict) and "global_proxy" in stored:
            merged["global_proxy"] = stored["global_proxy"]
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
                from backend.utils.tg_session import (
                    _resolve_concurrency_limit,
                    update_global_semaphore,
                )
                update_global_semaphore(_resolve_concurrency_limit())
            except Exception as exc:
                # 已写盘成功但运行时未生效，必须可观测，避免面板显示与运行不一致
                _logger.warning(
                    "应用 tg_global_concurrency=%s 到运行时信号量失败: %s",
                    merged.get("tg_global_concurrency"),
                    exc,
                )

        return True


