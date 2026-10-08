"""Persist the dashboard cover within the existing backed-up work directory."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from backend.core.config import get_settings

MAX_HERO_BYTES = 5 * 1024 * 1024
MAX_HERO_UPLOAD_BYTES = 1 * 1024 * 1024


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
    if path.parent.is_symlink() or not path.is_file() or path.is_symlink():
        return None
    if path.stat().st_size > MAX_HERO_BYTES:
        return None
    data = path.read_bytes()
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
