"""Telegram API 凭据解析（api_id / api_hash 统一入口）。

解析优先级：环境变量 TG_API_ID / TG_API_HASH > 配置服务 telegram 配置。
缺失或无效时抛 ValueError，由调用方决定如何降级或报错。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


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


def resolve_telegram_api_credentials(
    tg_config: Dict[str, Any],
    *,
    env_api_id: Optional[str] = None,
    env_api_hash: Optional[str] = None,
) -> tuple[int, str]:
    """解析 api_id / api_hash；无效时抛 ValueError。"""
    raw_id = env_api_id or tg_config.get("api_id")
    raw_hash = env_api_hash or tg_config.get("api_hash")
    try:
        api_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        api_id = None
    if isinstance(raw_hash, str):
        raw_hash = raw_hash.strip()
    if not api_id or not raw_hash:
        raise ValueError("未配置 Telegram API ID 或 API Hash")
    return api_id, str(raw_hash)
