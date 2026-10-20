"""Atomic writes for local files containing reusable credentials."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_private_text(path: Path, value: str) -> None:
    """Replace a credential file without following its old symlink or exposing it."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
