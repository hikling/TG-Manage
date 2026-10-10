"""Persist the dashboard cover within the existing backed-up work directory."""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

from backend.core.config import get_settings

MAX_HERO_UPLOAD_BYTES = 1 * 1024 * 1024
MAX_HERO_BYTES = MAX_HERO_UPLOAD_BYTES
DEFAULT_HERO_POSITION = (50.0, 50.0)


def image_media_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def hero_path() -> Path:
    root = get_settings().resolve_workdir()
    return root / "appearance" / "dashboard-hero.bin"


def read_hero() -> tuple[bytes, str] | None:
    path = hero_path()
    try:
        if path.parent.is_symlink() or not path.is_file() or path.is_symlink():
            return None
        if path.stat().st_size > MAX_HERO_BYTES:
            return None
        with path.open('rb') as stream:
            data = stream.read(MAX_HERO_BYTES + 1)
    except OSError:
        # A concurrent reset can remove the optional cover after the stat check.
        return None
    media_type = image_media_type(data)
    return (data, media_type) if media_type and len(data) <= MAX_HERO_BYTES else None


def save_hero(data: bytes) -> None:
    if not data or len(data) > MAX_HERO_UPLOAD_BYTES or image_media_type(data) is None:
        raise ValueError("仅支持不超过 1 MB 的 JPEG、PNG 或 WebP 图片")
    path = hero_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise ValueError("封面目录不可为符号链接")
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".hero-", delete=False) as handle:
            temporary = handle.name
            os.chmod(temporary, 0o600)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def delete_hero() -> None:
    path = hero_path()
    if path.is_symlink():
        raise ValueError("封面文件不可为符号链接")
    path.unlink(missing_ok=True)


def _normalize_position(value: object, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    if not math.isfinite(parsed):
        return fallback
    return round(max(0.0, min(parsed, 100.0)), 2)


def get_hero_position() -> tuple[float, float]:
    from backend.services.config import get_config_service

    settings = get_config_service().get_global_settings()
    return (
        _normalize_position(settings.get("hero_position_x"), DEFAULT_HERO_POSITION[0]),
        _normalize_position(settings.get("hero_position_y"), DEFAULT_HERO_POSITION[1]),
    )


def save_hero_position(x: float, y: float) -> None:
    from backend.services.config import get_config_service

    get_config_service().save_global_settings(
        {"hero_position_x": x, "hero_position_y": y}
    )
