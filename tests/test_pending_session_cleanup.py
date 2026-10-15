"""Abandoned login SQLite files are bounded without touching active attempts."""
from __future__ import annotations

import os
import time

from backend.services.telegram.pending_session import cleanup_orphan_pending_files


def test_exact_account_delete_cleans_only_its_pending_files(tmp_path):
    directory = tmp_path / ".pending-logins"
    directory.mkdir()
    deleted = directory / "old-0123456789abcdef.session"
    other = directory / "other-0123456789abcdef.session"
    deleted.write_bytes(b"old")
    other.write_bytes(b"other")

    count = cleanup_orphan_pending_files(tmp_path, account_name="old")

    assert count == 1
    assert not deleted.exists()
    assert other.exists()


def test_manual_prune_keeps_recent_and_active_pending_files(tmp_path):
    directory = tmp_path / ".pending-logins"
    directory.mkdir()
    old = directory / "old-0123456789abcdef.session"
    recent = directory / "recent-0123456789abcdef.session"
    active = directory / "active-0123456789abcdef.session"
    for path in (old, recent, active):
        path.write_bytes(b"pending")
    stale_at = time.time() - 3600
    os.utime(old, (stale_at, stale_at))
    os.utime(active, (stale_at, stale_at))

    count = cleanup_orphan_pending_files(
        tmp_path, active_paths={active.with_suffix("")}, older_than_seconds=1800,
    )

    assert count == 1
    assert not old.exists()
    assert recent.exists()
    assert active.exists()
