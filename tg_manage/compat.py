from __future__ import annotations

from types import SimpleNamespace

_PYROGRAM_IMPORT_ERROR: Exception | None = None


def _raise_pyrogram_import_error() -> None:
    raise RuntimeError(
        "Telegram runtime dependencies are unavailable. "
        "Use Python 3.10-3.13 with a compatible pyrogram/kurigram install."
    ) from _PYROGRAM_IMPORT_ERROR


try:
    from pyrogram import Client as BaseClient
    from pyrogram import errors, raw
    from pyrogram.session import Session
    from pyrogram.storage import MemoryStorage
except Exception as exc:  # pragma: no cover - fallback for unsupported runtimes
    _PYROGRAM_IMPORT_ERROR = exc

    class _RPCError(Exception):
        pass

    class _FloodWait(_RPCError):
        def __init__(self, *args, value: int = 0, **kwargs):
            super().__init__(*args)
            self.value = value

    errors = SimpleNamespace(
        RPCError=_RPCError,
        FloodWait=_FloodWait,
        BadRequest=_RPCError,
        Unauthorized=_RPCError,
    )

    raw = SimpleNamespace(
        functions=SimpleNamespace(
            updates=SimpleNamespace(
                GetChannelDifference=type("GetChannelDifference", (), {}),
                GetDifference=type("GetDifference", (), {}),
                GetState=type("GetState", (), {}),
            )
        )
    )

    class Session:
        START_TIMEOUT = 5

    class MemoryStorage:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class BaseClient:
        def __init__(self, *args, **kwargs):
            _raise_pyrogram_import_error()

        async def invoke(self, *args, **kwargs):
            _raise_pyrogram_import_error()
else:
    def _raise_pyrogram_import_error() -> None:
        return None
