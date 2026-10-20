"""Session strings are replaced atomically with owner-only permissions."""
from __future__ import annotations

import os

from tg_manage.private_file import write_private_text


def test_private_text_replaces_existing_file_without_leftover_temp(tmp_path):
    path = tmp_path / "account.session_string"
    path.write_text("old", encoding="utf-8")
    write_private_text(path, "new-session")
    assert path.read_text(encoding="utf-8") == "new-session"
    assert list(tmp_path.iterdir()) == [path]
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0
