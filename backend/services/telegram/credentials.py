"""校验登录时提供的账号专属 Telegram API 凭据。"""
from __future__ import annotations

from typing import Any


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
