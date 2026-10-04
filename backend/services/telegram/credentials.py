"""Telegram 登录凭据：账号输入优先，兼容旧版服务器配置。"""
from __future__ import annotations

import os
from typing import Any

from backend.core.config import get_settings
from backend.utils.atomic_io import read_json_safe

# 旧版面板公开的默认应用凭据；保留普通登录免填 API ID/Hash 的行为。
# 多账号共享该应用的限额，生产环境仍建议配置自己的应用凭据。
LEGACY_DEFAULT_API_ID = 611335
LEGACY_DEFAULT_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


def validate_telegram_api_credentials(api_id: Any, api_hash: Any) -> tuple[int, str]:
    try:
        parsed_id = int(api_id)
    except (ValueError, TypeError):
        raise ValueError("Telegram API ID 无效") from None
    if parsed_id <= 0 or not isinstance(api_hash, str) or len(api_hash.strip()) != 32:
        raise ValueError("Telegram API ID 或 API Hash 无效")
    cleaned_hash = api_hash.strip().lower()
    if any(char not in "0123456789abcdef" for char in cleaned_hash):
        raise ValueError("Telegram API Hash 无效")
    return parsed_id, cleaned_hash


def resolve_login_api_credentials(api_id: Any = None, api_hash: Any = None) -> tuple[int, str]:
    """Resolve new and legacy configuration without mixing halves of two pairs."""
    if bool(api_id) != bool(api_hash):
        raise ValueError("Telegram API ID 和 API Hash 必须同时填写")
    if api_id and api_hash:
        return validate_telegram_api_credentials(api_id, api_hash)

    for id_key, hash_key in (
        ("SIGNPULSE_TG_API_ID", "SIGNPULSE_TG_API_HASH"),
        ("TG_API_ID", "TG_API_HASH"),
    ):
        raw_id, raw_hash = os.getenv(id_key), os.getenv(hash_key)
        if raw_id or raw_hash:
            if not raw_id or not raw_hash:
                raise ValueError(f"{id_key} 和 {hash_key} 必须同时配置")
            return validate_telegram_api_credentials(raw_id, raw_hash)

    # 升级前在设置页保存的凭据仍位于持久化数据目录。
    legacy = read_json_safe(get_settings().resolve_workdir() / ".telegram_api.json", {})
    if isinstance(legacy, dict) and legacy.get("api_id") and legacy.get("api_hash"):
        return validate_telegram_api_credentials(legacy["api_id"], legacy["api_hash"])
    return LEGACY_DEFAULT_API_ID, LEGACY_DEFAULT_API_HASH
