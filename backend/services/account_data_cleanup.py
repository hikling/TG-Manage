"""Remove account-local leftovers after an explicit full check.

The session inventory is read from durable storage before anything is removed.
A failed or ambiguous inventory must never turn into an empty-account cleanup.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.services.device_keepalive import get_device_keepalive_service
from backend.services.telegram import get_telegram_service
from backend.services.telegram.pending_session import cleanup_orphan_pending_files
from backend.services.telegram.sessions import _login_sessions, _qr_login_sessions
from backend.utils.account_locks import get_account_lock
from backend.utils.names import validate_storage_name
from backend.utils.tg_session import (
    delete_account_session_string,
    is_string_session_mode,
)

logger = logging.getLogger("backend.account_data_cleanup")
_reconcile_lock = asyncio.Lock()
_MAX_ACCOUNT_STORE_BYTES = 32 * 1024 * 1024


def _safe_name(name: str) -> bool:
    try:
        return validate_storage_name(name, field_name="account_name") == name
    except ValueError:
        return False


def _pending_names() -> set[str]:
    names: set[str] = set()
    for store in (_login_sessions, _qr_login_sessions):
        for value in tuple(store.values()):
            if not isinstance(value, dict):
                continue
            name = value.get("account_name")
            if isinstance(name, str) and _safe_name(name):
                names.add(name)
    return names


def _trusted_inventory(service: Any) -> tuple[set[str], set[str]]:
    """Return durable login names and metadata names, or raise without cleanup."""
    session_dir = Path(service.session_dir)
    if not session_dir.is_dir():
        raise RuntimeError("Telegram session directory is unavailable")

    store_path = session_dir / "accounts.json"
    metadata_names: set[str] = set()
    string_names: set[str] = set()
    if store_path.is_symlink():
        raise RuntimeError("Telegram account store is linked")
    if store_path.exists():
        if store_path.stat().st_size > _MAX_ACCOUNT_STORE_BYTES:
            raise RuntimeError("Telegram account store is too large to reconcile")
        data = json.loads(store_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
            raise ValueError("Invalid Telegram account store")
        for name, entry in data["accounts"].items():
            if not isinstance(name, str) or not _safe_name(name):
                continue
            metadata_names.add(name)
            if isinstance(entry, dict) and isinstance(entry.get("session_string"), str):
                # A string session is sensitive login state. Preserve it even
                # when the deployment currently uses file-session mode.
                if entry["session_string"].strip():
                    string_names.add(name)

    durable_names = set(string_names)
    # Iterate the directory directly: an I/O error must propagate instead of
    # being silently interpreted as zero accounts.
    for path in session_dir.iterdir():
        if not path.is_file():
            continue
        name = None
        if path.name.endswith(".session"):
            name = path.name[:-len(".session")]
        elif path.name.endswith(".session_string"):
            name = path.name[:-len(".session_string")]
        if name and _safe_name(name):
            durable_names.add(name)

    # Cross-check the same fresh view used by Account Management. The strict
    # option prevents list_accounts' UI fallback from authorizing deletion.
    listed = service.list_accounts(force_refresh=True, strict=True)
    listed_names = {
        item.get("name") for item in listed
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    if not listed_names <= durable_names:
        raise RuntimeError("Account list and durable session inventory disagree")
    if is_string_session_mode():
        # In string mode the store can include old profile-only entries; those
        # must not become live accounts merely because metadata exists.
        durable_names |= listed_names
    return durable_names | _pending_names(), metadata_names


async def reconcile_orphan_account_data() -> dict[str, int]:
    """Sync TeleBox, metadata, keepalive state and avatars on manual full check."""
    async with _reconcile_lock:
        service = get_telegram_service()
        live_names, metadata_names = _trusted_inventory(service)
        if not live_names and not (Path(service.session_dir) / "accounts.json").exists():
            # An empty directory can also mean a missing/unmounted session
            # volume. Without a durable store document, do not interpret it
            # as permission to erase every other account-local data source.
            logger.warning("Skipping orphan cleanup: empty account inventory has no store document")
            return {"telebox": 0, "metadata": 0, "keepalive": 0, "avatars": 0, "pending": 0}
        from backend.services.telebox import get_telebox_service

        active_pending_paths = {
            value["pending_path"] for store in (_login_sessions, _qr_login_sessions)
            for value in tuple(store.values())
            if isinstance(value, dict) and isinstance(value.get("pending_path"), Path)
        }
        pending_removed = cleanup_orphan_pending_files(
            Path(service.session_dir), active_paths=active_pending_paths,
            older_than_seconds=30 * 60,
        )
        telebox_removed = await get_telebox_service().reconcile_orphan_data(live_names)
        metadata_removed = 0
        for name in sorted(metadata_names - live_names):
            lock = get_account_lock(name)
            try:
                await asyncio.wait_for(lock.acquire(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                if name not in _pending_names() and not service.account_exists(name):
                    delete_account_session_string(name)
                    metadata_removed += 1
            finally:
                lock.release()

        keepalive_removed = get_device_keepalive_service().prune_account_state(
            live_names, account_exists=service.account_exists,
        )
        avatar_removed = 0
        avatar_dir = get_settings().resolve_workdir() / "avatars"
        if avatar_dir.is_dir() and not avatar_dir.is_symlink():
            for path in avatar_dir.iterdir():
                if not path.is_file() or path.is_symlink():
                    continue
                suffix = next(
                    (part for part in (".jpg", ".no_avatar") if path.name.endswith(part)),
                    None,
                )
                if suffix is None:
                    continue
                name = path.name[:-len(suffix)]
                if not _safe_name(name) or name in live_names:
                    continue
                if name in _pending_names() or service.account_exists(name):
                    continue
                path.unlink()
                avatar_removed += 1
        logger.info(
            "Account orphan reconciliation complete: telebox=%d metadata=%d keepalive=%d avatars=%d pending=%d",
            len(telebox_removed), metadata_removed, keepalive_removed, avatar_removed, pending_removed,
        )
        return {
            "telebox": len(telebox_removed),
            "metadata": metadata_removed,
            "keepalive": keepalive_removed,
            "avatars": avatar_removed,
            "pending": pending_removed,
        }
