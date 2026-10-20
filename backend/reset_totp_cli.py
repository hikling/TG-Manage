"""Local-only recovery for an administrator who lost their authenticator."""
from __future__ import annotations

import argparse

from backend.core.database import get_session_local, init_engine
from backend.models.user import User


def reset_totp_for_user(username: str) -> bool:
    init_engine()
    with get_session_local()() as db:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            return False
        user.totp_secret = None
        user.auth_version = (user.auth_version or 0) + 1
        db.commit()
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset TOTP from the application host")
    parser.add_argument("--username", required=True, help="Exact administrator username")
    args = parser.parse_args()
    if not reset_totp_for_user(args.username):
        parser.exit(1, "User not found; no changes made.\n")
    print("TOTP disabled and all existing login tokens revoked. Sign in with your password.")


if __name__ == "__main__":
    main()
