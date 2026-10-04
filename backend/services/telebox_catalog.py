"""Bounded, cached view of the official TeleBox plugin index."""
from __future__ import annotations

import asyncio
import re
import time

import httpx

CATALOG_URL = "https://raw.githubusercontent.com/TeleBoxOrg/TeleBox-Plugins/main/plugins.json"
SOURCE_URL = "https://github.com/TeleBoxOrg/TeleBox-Plugins"
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_cache: dict | None = None
_expires_at = 0.0
_lock = asyncio.Lock()


async def catalog() -> dict:
    """Return names and descriptions only; installation still goes through TPM."""
    global _cache, _expires_at
    if _cache is not None and time.monotonic() < _expires_at:
        return {**_cache, "stale": False}
    async with _lock:
        if _cache is not None and time.monotonic() < _expires_at:
            return {**_cache, "stale": False}
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                response = await client.get(CATALOG_URL)
                response.raise_for_status()
                if len(response.content) > 512_000:
                    raise ValueError("插件目录超过大小限制")
                raw = response.json()
            if not isinstance(raw, dict):
                raise ValueError("插件目录格式无效")
            items = [
                {"name": name, "description": info.get("desc", "")[:240]}
                for name, info in raw.items()
                if isinstance(name, str) and _NAME.fullmatch(name) and name.lower() != "all"
                and isinstance(info, dict) and isinstance(info.get("desc", ""), str)
            ]
            items.sort(key=lambda item: item["name"].casefold())
            _cache = {"source": SOURCE_URL, "items": items}
            _expires_at = time.monotonic() + 600
            return {**_cache, "stale": False}
        except (httpx.HTTPError, ValueError) as exc:
            if _cache is not None:
                return {**_cache, "stale": True}
            raise ValueError("官方插件目录暂时不可用，请稍后重试") from exc
