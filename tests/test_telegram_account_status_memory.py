"""Repeated account probes must release their reference-counted clients."""
from __future__ import annotations

import asyncio
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.services.telegram import accounts as accounts_mod


@pytest.fixture(autouse=True)
def _configured_route(monkeypatch):
    """These client-lifecycle tests run after route selection has completed."""
    monkeypatch.setattr(accounts_mod, "resolve_account_route", lambda _name: None)


class _Service(accounts_mod.TelegramAccountsMixin):
    def __init__(self, session_dir):
        self.session_dir = session_dir

    def account_exists(self, _name):
        return True


class _Client:
    def __init__(self, behavior="ok"):
        self.behavior = behavior
        self.active = 0
        self.enters = 0
        self.exits = 0

    async def __aenter__(self):
        self.enters += 1
        self.active += 1
        return self

    async def __aexit__(self, *_args):
        self.exits += 1
        self.active -= 1

    async def get_me(self):
        if self.behavior == "error":
            raise ConnectionError("network unavailable")
        if self.behavior == "timeout":
            await asyncio.sleep(60)
        return SimpleNamespace(id=123, username="sample_user")


@pytest.fixture
def chat_resources(monkeypatch):
    gate = asyncio.Semaphore(1)
    lock = asyncio.Lock()
    monkeypatch.setattr(accounts_mod, 'get_global_semaphore', lambda: gate)
    monkeypatch.setattr(accounts_mod, 'get_account_lock', lambda _name: lock)
    monkeypatch.setattr(accounts_mod, 'get_session_mode', lambda: 'file')
    monkeypatch.setattr(accounts_mod, 'get_account_profile', lambda _name: {'proxy': 'socks5://127.0.0.1:1080'})
    return gate, lock


@pytest.mark.asyncio
@pytest.mark.parametrize("behavior", ["ok", "error", "timeout"])
async def test_status_probe_releases_client_on_all_outcomes(tmp_path, monkeypatch, behavior):
    client = _Client(behavior)
    monkeypatch.setattr("tg_manage.core.get_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    status_write = Mock()
    monkeypatch.setattr(accounts_mod, "set_account_status", status_write)

    iterations = 20 if behavior != "timeout" else 1
    for _ in range(iterations):
        result = await _Service(tmp_path).check_account_status("sample", timeout_seconds=1)
        assert result["ok"] is (behavior == "ok")
        if behavior == "ok":
            assert result["username"] == "sample_user"
        assert client.active == 0
    assert client.enters == client.exits == iterations
    assert status_write.call_count == iterations
    last = status_write.call_args.kwargs
    assert last["status"] == ("connected" if behavior == "ok" else "checking")
    assert last["code"] == {"ok": "OK", "error": "CONNECTION_ERROR", "timeout": "TIMEOUT"}[behavior]


@pytest.mark.asyncio
async def test_removed_account_is_not_recreated_by_status_result(tmp_path, monkeypatch):
    class RemovedDuringProbe(_Service):
        calls = 0

        def account_exists(self, _name):
            self.calls += 1
            return self.calls == 1

    monkeypatch.setattr("tg_manage.core.get_client", lambda *_args, **_kwargs: _Client())
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    status_write = Mock()
    monkeypatch.setattr(accounts_mod, "set_account_status", status_write)
    result = await RemovedDuringProbe(tmp_path).check_account_status("sample")
    assert result["ok"] is True
    status_write.assert_not_called()


@pytest.mark.asyncio
async def test_probe_reuses_identity_from_client_enter(tmp_path, monkeypatch):
    class AuthenticatedClient(_Client):
        async def __aenter__(self):
            await super().__aenter__()
            self.me = SimpleNamespace(id=456, username="already_verified")
            return self

        async def get_me(self):
            raise AssertionError("status probe must not repeat get_me")

    monkeypatch.setattr("tg_manage.core.get_client", lambda *_args, **_kwargs: AuthenticatedClient())
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    monkeypatch.setattr(accounts_mod, "set_account_status", Mock())

    result = await _Service(tmp_path).check_account_status("sample")
    assert result["ok"] is True
    assert result["username"] == "already_verified"


@pytest.mark.asyncio
async def test_avatar_download_closes_in_memory_media_buffer(tmp_path, monkeypatch):
    data = io.BytesIO(b"\xff\xd8\xffavatar")

    class PhotoClient(_Client):
        async def get_me(self):
            return SimpleNamespace(photo=SimpleNamespace(small_file_id="small"))

        async def download_media(self, _file_id, *, in_memory):
            assert in_memory is True
            return data

    client = PhotoClient()
    monkeypatch.setattr("tg_manage.core.get_client", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    assert await _Service(tmp_path).download_account_avatar("sample") == b"\xff\xd8\xffavatar"
    assert data.closed
    assert client.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('read_error', [False, True])
async def test_chat_avatar_download_closes_buffer_even_if_read_fails(tmp_path, monkeypatch, read_error):
    class PhotoBuffer(io.BytesIO):
        def read(self, *args):
            if read_error:
                raise OSError('buffer read failed')
            return super().read(*args)

    data = PhotoBuffer(b'\xff\xd8\xffchat-avatar')

    class PhotoClient(_Client):
        async def get_chat(self, chat_id):
            assert chat_id == 12345
            return SimpleNamespace(photo=SimpleNamespace(small_file_id='small'))

        async def download_media(self, _file_id, *, in_memory):
            assert in_memory is True
            return data

    client = PhotoClient()
    monkeypatch.setattr('tg_manage.core.get_client', lambda *_args, **_kwargs: client)
    monkeypatch.setattr(accounts_mod, 'get_session_mode', lambda: 'file')
    monkeypatch.setattr(accounts_mod, 'get_account_profile', lambda _name: {})
    if read_error:
        with pytest.raises(OSError):
            await _Service(tmp_path).download_chat_avatar('sample', 12345)
    else:
        assert await _Service(tmp_path).download_chat_avatar('sample', 12345) == b'\xff\xd8\xffchat-avatar'
    assert data.closed
    assert client.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('extra_bytes', [0, 1])
async def test_chat_avatar_read_limit_and_cleanup(tmp_path, monkeypatch, chat_resources, extra_bytes):
    from backend.services.avatar_cache import CHAT_AVATAR_MAX_BYTES

    read_sizes = []

    class PhotoBuffer(io.BytesIO):
        def read(self, size=-1):
            read_sizes.append(size)
            return super().read(size)

    data = PhotoBuffer(b'x' * (CHAT_AVATAR_MAX_BYTES + extra_bytes))

    class PhotoClient(_Client):
        async def get_chat(self, _chat_id):
            return SimpleNamespace(photo=SimpleNamespace(small_file_id='small'))

        async def download_media(self, _file_id, *, in_memory):
            return data

    gate, lock = chat_resources
    client = PhotoClient()

    def build(*_args, **_kwargs):
        assert lock.locked() and gate.locked()
        return client

    monkeypatch.setattr('tg_manage.core.get_client', build)
    if extra_bytes:
        with pytest.raises(ValueError, match='头像超过大小限制'):
            await _Service(tmp_path).download_chat_avatar('sample', 12345)
    else:
        assert len(await _Service(tmp_path).download_chat_avatar('sample', 12345)) == CHAT_AVATAR_MAX_BYTES
    assert read_sizes == [CHAT_AVATAR_MAX_BYTES + 1]
    assert data.closed
    assert client.enters == client.exits == 1
    assert client.active == 0
    assert not lock.locked() and not gate.locked()


@pytest.mark.asyncio
@pytest.mark.parametrize('wait_at', ['account_lock', 'global_permit'])
async def test_cancelled_chat_avatar_waiter_does_not_construct_client(tmp_path, monkeypatch, chat_resources, wait_at):
    gate, lock = chat_resources
    held = lock if wait_at == 'account_lock' else gate
    await held.acquire()
    build = Mock()
    monkeypatch.setattr('tg_manage.core.get_client', build)
    task = asyncio.create_task(_Service(tmp_path).download_chat_avatar('sample', 12345))
    try:
        await asyncio.sleep(0)
        build.assert_not_called()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        build.assert_not_called()
        assert held.locked()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        held.release()
    assert not lock.locked() and not gate.locked()
    assert await asyncio.wait_for(gate.acquire(), 1) is True
    gate.release()


@pytest.mark.asyncio
@pytest.mark.parametrize('wait_at', ['get_chat', 'download_media'])
async def test_active_chat_avatar_cancellation_releases_client_lock_and_permit(tmp_path, monkeypatch, chat_resources, wait_at):
    gate, lock = chat_resources
    started = asyncio.Event()

    class PhotoClient(_Client):
        async def get_chat(self, _chat_id):
            if wait_at == 'get_chat':
                started.set()
                await asyncio.Future()
            return SimpleNamespace(photo=SimpleNamespace(small_file_id='small'))

        async def download_media(self, _file_id, *, in_memory):
            started.set()
            await asyncio.Future()

    client = PhotoClient()
    monkeypatch.setattr('tg_manage.core.get_client', lambda *_args, **_kwargs: client)
    task = asyncio.create_task(_Service(tmp_path).download_chat_avatar('sample', 12345))
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert gate.locked() and lock.locked() and client.active == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert client.enters == client.exits == 1
        assert client.active == 0
        assert not gate.locked() and not lock.locked()
        assert await asyncio.wait_for(gate.acquire(), 1) is True
        gate.release()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
