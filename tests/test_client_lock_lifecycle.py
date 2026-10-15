"""Shared Telegram client locks follow active lifecycle users, not route history."""

import asyncio
import gc
import weakref
from collections import defaultdict
from types import SimpleNamespace

import pytest

from tg_manage.core import client as client_mod


class _LifecycleClient(client_mod.Client):
    def __init__(self, name, *, key, proxy=None, **_kwargs):
        self.name, self.key, self.proxy = name, key, proxy
        self.is_connected = self.is_initialized = False
        self.connect_count = self.stop_count = 0
        self.stop_started = None
        self.stop_allowed = None

    async def connect(self):
        self.connect_count += 1
        self.is_connected = True
        return True

    async def get_me(self):
        return SimpleNamespace(id=123)

    async def invoke(self, _query):
        return None

    async def initialize(self):
        self.is_initialized = True

    async def stop(self):
        self.stop_count += 1
        if self.stop_started is not None:
            self.stop_started.set()
            await self.stop_allowed.wait()
        self.is_connected = self.is_initialized = False


@pytest.fixture
def lifecycle(monkeypatch, tmp_path):
    monkeypatch.setattr(client_mod, "Client", _LifecycleClient)
    monkeypatch.setattr(client_mod, "_CLIENT_INSTANCES", weakref.WeakValueDictionary())
    monkeypatch.setattr(client_mod, "_CLIENT_REFS", defaultdict(int))
    monkeypatch.setattr(client_mod, "_CLIENT_ASYNC_LOCKS", {})
    monkeypatch.setattr(client_mod, "_CLIENT_LOCK_USERS", {})

    def make(proxy=None):
        return client_mod.get_client(
            "one", workdir=tmp_path, api_id=123, api_hash="a" * 32, proxy=proxy
        )

    return make, tmp_path


async def _wait_for_users(key, count):
    for _ in range(100):
        if client_mod._CLIENT_LOCK_USERS.get(key) == count:
            return
        await asyncio.sleep(0)
    pytest.fail(f"client lock did not reach {count} users")


def test_unentered_client_cache_uses_external_ownership(lifecycle):
    make, _workdir = lifecycle
    proxy = {"scheme": "socks5", "hostname": "proxy", "port": 1080}
    client = make(proxy)
    key = client.key
    owned = weakref.ref(client)
    assert make(proxy) is client
    assert client_mod._CLIENT_INSTANCES[key] is client

    del client
    gc.collect()
    assert owned() is None
    assert key not in client_mod._CLIENT_INSTANCES

    for index in range(100):
        unused = make({**proxy, "password": str(index)})
        del unused
    gc.collect()
    assert not client_mod._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_proxy_rotation_reclaims_completed_lifecycle_locks(lifecycle):
    make, _workdir = lifecycle
    for index in range(100):
        client = make(
            {"scheme": "socks5", "hostname": "proxy", "port": 1080, "password": str(index)}
        )
        async with client:
            assert client.is_connected
        assert client.stop_count == 1
        assert not client_mod._CLIENT_ASYNC_LOCKS
        assert not client_mod._CLIENT_LOCK_USERS
        assert not client_mod._CLIENT_INSTANCES
        assert not client_mod._CLIENT_REFS


@pytest.mark.asyncio
async def test_old_instance_cannot_enter_after_new_instance_claims_same_key(lifecycle):
    make, _workdir = lifecycle
    old = make()
    async with old:
        pass
    new = make()
    assert new is not old
    with pytest.raises(ConnectionError, match="superseded"):
        await old.__aenter__()
    async with new:
        assert new.is_connected
    assert not client_mod._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_waiting_enter_retains_same_lock_until_stop_finishes(lifecycle):
    make, _workdir = lifecycle
    client = make()
    await client.__aenter__()
    client.stop_started = asyncio.Event()
    client.stop_allowed = asyncio.Event()

    exiting = asyncio.create_task(client.__aexit__(None, None, None))
    await client.stop_started.wait()
    lock = client_mod._CLIENT_ASYNC_LOCKS[client.key]
    entering = asyncio.create_task(client.__aenter__())
    await _wait_for_users(client.key, 2)
    assert client_mod._CLIENT_ASYNC_LOCKS[client.key] is lock
    assert client.connect_count == 1
    assert make() is client

    client.stop_allowed.set()
    await exiting
    assert await entering is client
    assert client.connect_count == 2
    await client.__aexit__(None, None, None)
    assert client.stop_count == 2
    assert not client_mod._CLIENT_ASYNC_LOCKS
    assert not client_mod._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_canceled_waiter_does_not_remove_held_lock(lifecycle):
    make, _workdir = lifecycle
    client = make()
    await client.__aenter__()
    client.stop_started = asyncio.Event()
    client.stop_allowed = asyncio.Event()
    exiting = asyncio.create_task(client.__aexit__(None, None, None))
    await client.stop_started.wait()
    lock = client_mod._CLIENT_ASYNC_LOCKS[client.key]
    entering = asyncio.create_task(client.__aenter__())
    await _wait_for_users(client.key, 2)

    entering.cancel()
    with pytest.raises(asyncio.CancelledError):
        await entering
    assert client_mod._CLIENT_LOCK_USERS[client.key] == 1
    assert client_mod._CLIENT_ASYNC_LOCKS[client.key] is lock
    client.stop_allowed.set()
    await exiting
    assert not client_mod._CLIENT_ASYNC_LOCKS
    assert not client_mod._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_close_waiter_retires_old_client_without_lock_split(lifecycle):
    make, workdir = lifecycle
    client = make()
    await client.__aenter__()
    client.stop_started = asyncio.Event()
    client.stop_allowed = asyncio.Event()
    exiting = asyncio.create_task(client.__aexit__(None, None, None))
    await client.stop_started.wait()
    lock = client_mod._CLIENT_ASYNC_LOCKS[client.key]
    closing = asyncio.create_task(client_mod.close_client_by_name("one", workdir=workdir))
    await _wait_for_users(client.key, 2)
    entering = asyncio.create_task(client.__aenter__())
    await _wait_for_users(client.key, 3)
    assert client_mod._CLIENT_ASYNC_LOCKS[client.key] is lock

    client.stop_allowed.set()
    await exiting
    await closing
    with pytest.raises(ConnectionError, match="closed"):
        await entering
    assert not client_mod._CLIENT_ASYNC_LOCKS
    assert not client_mod._CLIENT_LOCK_USERS
    assert not client_mod._CLIENT_INSTANCES
    assert not client_mod._CLIENT_REFS


@pytest.mark.asyncio
async def test_canceled_close_waiter_releases_only_its_reservation(lifecycle):
    make, workdir = lifecycle
    client = make()
    await client.__aenter__()
    client.stop_started = asyncio.Event()
    client.stop_allowed = asyncio.Event()
    exiting = asyncio.create_task(client.__aexit__(None, None, None))
    await client.stop_started.wait()
    lock = client_mod._CLIENT_ASYNC_LOCKS[client.key]
    closing = asyncio.create_task(client_mod.close_client_by_name("one", workdir=workdir))
    await _wait_for_users(client.key, 2)

    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    assert client_mod._CLIENT_ASYNC_LOCKS[client.key] is lock
    assert client_mod._CLIENT_LOCK_USERS[client.key] == 1
    client.stop_allowed.set()
    await exiting
    assert not client_mod._CLIENT_ASYNC_LOCKS
    assert not client_mod._CLIENT_INSTANCES


@pytest.mark.asyncio
async def test_close_keeps_fresh_replacement_and_old_exit_cannot_change_its_refs(lifecycle):
    make, workdir = lifecycle
    old = make()
    await old.__aenter__()
    old.stop_started = asyncio.Event()
    old.stop_allowed = asyncio.Event()
    closing = asyncio.create_task(client_mod.close_client_by_name("one", workdir=workdir))
    await old.stop_started.wait()

    replacement = make()
    assert replacement is not old
    assert client_mod._CLIENT_INSTANCES[old.key] is replacement
    entering = asyncio.create_task(replacement.__aenter__())
    await _wait_for_users(old.key, 2)
    old.stop_allowed.set()
    await closing
    assert await entering is replacement
    assert client_mod._CLIENT_INSTANCES[old.key] is replacement
    assert client_mod._CLIENT_REFS[old.key] == 1

    await old.__aexit__(None, None, None)
    assert client_mod._CLIENT_REFS[old.key] == 1
    await replacement.__aexit__(None, None, None)
    assert not client_mod._CLIENT_INSTANCES
    assert not client_mod._CLIENT_REFS
    assert not client_mod._CLIENT_ASYNC_LOCKS
