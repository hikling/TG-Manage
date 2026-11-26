from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.user import User

logger = logging.getLogger("backend.users")


def setup_token_path() -> Path:
    return get_settings().resolve_base_dir() / ".admin_setup_token"


def prepare_admin_setup(db: Session) -> None:
    """Prepare a one-time server-side token, without creating a default user.

    Existing installations keep their users; the token never enters API output.
    """
    path = setup_token_path()
    if db.query(User.id).first():
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secrets.token_urlsafe(32))
        handle.flush()
        os.fsync(handle.fileno())
    logger.warning("首次设置管理员：请读取数据目录的 .admin_setup_token 并在网页设置密码")
