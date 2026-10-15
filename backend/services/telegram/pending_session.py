"""Keep an in-progress login separate from an already authorized account session."""
from __future__ import annotations

import re
import secrets
import time
from pathlib import Path

from backend.utils.names import validate_storage_name

_PENDING_FILE = re.compile(r"^(?P<name>.+)-(?P<nonce>[0-9a-f]{16})\.session(?:-(?:journal|wal|shm))?$")


def new_pending_session_path(session_dir: Path, account_name: str) -> Path:
    pending_dir = session_dir / ".pending-logins"
    pending_dir.mkdir(parents=True, exist_ok=True)
    return pending_dir / f"{account_name}-{secrets.token_hex(8)}"


def cleanup_pending_session(path: Path | None) -> None:
    if path is None:
        return
    for suffix in (".session", ".session-journal", ".session-wal", ".session-shm"):
        (path.parent / f"{path.name}{suffix}").unlink(missing_ok=True)


def cleanup_orphan_pending_files(
    session_dir: Path, *, account_name: str | None = None,
    active_paths: set[Path] | None = None, older_than_seconds: float = 0,
) -> int:
    """Remove exact pending-session file groups without traversing links.

    Deletion supplies account_name and removes all of that account's crashed
    leftovers. Manual reconciliation supplies a 30-minute age floor and skips
    temporary sessions still held by this process.
    """
    if account_name is not None:
        validate_storage_name(account_name, field_name="account_name")
    pending_dir = session_dir / ".pending-logins"
    if pending_dir.is_symlink() or bool(getattr(pending_dir, "is_junction", lambda: False)()):
        raise ValueError("待登录数据目录不能是链接")
    if not pending_dir.exists():
        return 0
    if not pending_dir.is_dir():
        raise ValueError("待登录数据目录不是目录")
    active = {path.resolve() for path in (active_paths or set())}
    cutoff = time.time() - max(0.0, older_than_seconds)
    groups: set[Path] = set()
    for path in pending_dir.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        match = _PENDING_FILE.fullmatch(path.name)
        if not match or (account_name is not None and match["name"] != account_name):
            continue
        base = pending_dir / f"{match['name']}-{match['nonce']}"
        if base.resolve() in active:
            continue
        groups.add(base)
    removed = 0
    for base in groups:
        siblings = [base.parent / f"{base.name}{suffix}" for suffix in (
            ".session", ".session-journal", ".session-wal", ".session-shm",
        )]
        if any(path.is_symlink() or (path.exists() and path.stat().st_mtime > cutoff)
               for path in siblings):
            continue
        cleanup_pending_session(base)
        removed += 1
    return removed


def promote_pending_session(path: Path | None, session_dir: Path, account_name: str) -> None:
    if path is None:
        return
    source = path.parent / f"{path.name}.session"
    if not source.is_file():
        raise ValueError("登录会话文件未生成，旧账户会话已保留")
    source.replace(session_dir / f"{account_name}.session")
    # The account lock still excludes readers here. Old SQLite WAL sidecars
    # must not be applied to the newly authorized database on its next open.
    for suffix in (".session-journal", ".session-wal", ".session-shm"):
        (session_dir / f"{account_name}{suffix}").unlink(missing_ok=True)
    cleanup_pending_session(path)
