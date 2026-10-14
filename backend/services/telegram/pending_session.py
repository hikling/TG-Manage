"""Keep an in-progress login separate from an already authorized account session."""
from __future__ import annotations

import secrets
from pathlib import Path


def new_pending_session_path(session_dir: Path, account_name: str) -> Path:
    pending_dir = session_dir / ".pending-logins"
    pending_dir.mkdir(parents=True, exist_ok=True)
    return pending_dir / f"{account_name}-{secrets.token_hex(8)}"


def cleanup_pending_session(path: Path | None) -> None:
    if path is None:
        return
    for suffix in (".session", ".session-journal", ".session-wal", ".session-shm"):
        (path.parent / f"{path.name}{suffix}").unlink(missing_ok=True)


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
