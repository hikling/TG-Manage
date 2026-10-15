"""
backend/services/telegram/sessions.py 单元测试

覆盖范围：
- _release_login_session：连接断开、异常容忍、锁释放、空值容错
- _cleanup_expired_login_sessions：过期清理、新鲜保留、无时间戳保留、
  登录/扫码独立存活期、超量按最旧逐出
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.services.telegram import sessions as sessions_mod


class _FakeClient:
    """模拟 Pyrogram 客户端的最小接口"""

    def __init__(self, connected: bool = True, fail: bool = False):
        self.is_connected = connected
        self.disconnect_calls = 0
        self._fail = fail

    async def disconnect(self):
        self.disconnect_calls += 1
        if self._fail:
            raise RuntimeError("disconnect boom")


@pytest.fixture(autouse=True)
def clean_session_stores():
    """每个用例前后清空全局 session 存储，避免串扰"""
    sessions_mod._login_sessions.clear()
    sessions_mod._qr_login_sessions.clear()
    yield
    sessions_mod._login_sessions.clear()
    sessions_mod._qr_login_sessions.clear()


class TestReleaseLoginSession:
    """_release_login_session() 释放逻辑"""

    @pytest.mark.asyncio
    async def test_disconnects_connected_client(self):
        client = _FakeClient(connected=True)
        await sessions_mod._release_login_session({"client": client})
        assert client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_skips_disconnected_client(self):
        client = _FakeClient(connected=False)
        await sessions_mod._release_login_session({"client": client})
        assert client.disconnect_calls == 0

    @pytest.mark.asyncio
    async def test_tolerates_disconnect_failure(self):
        client = _FakeClient(connected=True, fail=True)
        await sessions_mod._release_login_session({"client": client})
        assert client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_releases_held_lock(self):
        lock = asyncio.Lock()
        await lock.acquire()
        await sessions_mod._release_login_session({"lock": lock})
        assert lock.locked() is False

    @pytest.mark.asyncio
    async def test_empty_value_is_noop(self):
        await sessions_mod._release_login_session({})
        await sessions_mod._release_login_session({"client": None, "lock": None})


class TestCleanupExpiredLoginSessions:
    """_cleanup_expired_login_sessions() 过期与超量清理"""

    @pytest.mark.asyncio
    async def test_expired_login_session_removed_and_released(self):
        client = _FakeClient()
        sessions_mod._login_sessions["old"] = {
            "client": client,
            "_created_at": time.monotonic() - 1900,  # 超过 30 分钟存活期
        }
        await sessions_mod._cleanup_expired_login_sessions()
        assert "old" not in sessions_mod._login_sessions
        assert client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_fresh_and_timeless_sessions_kept(self):
        now = time.monotonic()
        sessions_mod._login_sessions["fresh"] = {"client": _FakeClient(), "_created_at": now}
        sessions_mod._login_sessions["timeless"] = {"client": _FakeClient()}
        await sessions_mod._cleanup_expired_login_sessions()
        assert set(sessions_mod._login_sessions) == {"fresh", "timeless"}

    @pytest.mark.asyncio
    async def test_qr_sessions_use_shorter_max_age(self):
        # 扫码登录存活期 600s：700s 前的应清理；手机号登录 1800s 同时间点应保留
        client_qr = _FakeClient()
        client_login = _FakeClient()
        created = time.monotonic() - 700
        sessions_mod._qr_login_sessions["qr"] = {"client": client_qr, "_created_at": created}
        sessions_mod._login_sessions["login"] = {"client": client_login, "_created_at": created}
        await sessions_mod._cleanup_expired_login_sessions()
        assert "qr" not in sessions_mod._qr_login_sessions
        assert "login" in sessions_mod._login_sessions

    @pytest.mark.asyncio
    async def test_overflow_evicts_oldest(self, monkeypatch):
        monkeypatch.setattr(sessions_mod, "_MAX_LOGIN_SESSIONS", 2)
        now = time.monotonic()
        oldest_client = _FakeClient()
        for key, age, client in (
            ("oldest", 100, oldest_client),
            ("middle", 50, _FakeClient()),
            ("newest", 1, _FakeClient()),
        ):
            sessions_mod._login_sessions[key] = {
                "client": client,
                "_created_at": now - age,
            }
        await sessions_mod._cleanup_expired_login_sessions()
        assert set(sessions_mod._login_sessions) == {"middle", "newest"}
        assert oldest_client.disconnect_calls == 1

    @pytest.mark.asyncio
    async def test_missing_created_at_eviction_uses_inf(self, monkeypatch):
        # 无 _created_at 的条目按 float("inf") 视为最新，不得被优先逐出
        monkeypatch.setattr(sessions_mod, "_MAX_LOGIN_SESSIONS", 1)
        now = time.monotonic()
        old_client = _FakeClient()
        sessions_mod._login_sessions["timed"] = {"client": old_client, "_created_at": now - 50}
        sessions_mod._login_sessions["timeless"] = {"client": _FakeClient()}
        await sessions_mod._cleanup_expired_login_sessions()
        assert set(sessions_mod._login_sessions) == {"timeless"}
        assert old_client.disconnect_calls == 1


class TestPendingLoginLifecycle:
    @pytest.mark.asyncio
    async def test_phone_attempt_expires_without_another_login_request(self, monkeypatch):
        monkeypatch.setattr(sessions_mod, "_LOGIN_SESSION_MAX_AGE", 0.01)
        client = _FakeClient()
        lock = asyncio.Lock()
        await lock.acquire()
        value = {"account_name": "alice", "client": client, "lock": lock}
        sessions_mod._login_sessions["alice_+123"] = value

        sessions_mod._start_phone_login_expiry("alice_+123", value)
        await asyncio.wait_for(value["expire_task"], timeout=1)

        assert "alice_+123" not in sessions_mod._login_sessions
        assert client.disconnect_calls == 1
        assert not lock.locked()

    @pytest.mark.asyncio
    async def test_cancelled_old_watcher_cannot_remove_replacement(self, monkeypatch):
        monkeypatch.setattr(sessions_mod, "_LOGIN_SESSION_MAX_AGE", 0.02)
        old_client = _FakeClient()
        old_value = {"account_name": "alice", "client": old_client}
        sessions_mod._login_sessions["alice_+123"] = old_value
        sessions_mod._start_phone_login_expiry("alice_+123", old_value)

        await sessions_mod._remove_login_session(
            sessions_mod._login_sessions, "alice_+123", expected=old_value,
        )
        replacement = {"account_name": "alice", "client": _FakeClient()}
        sessions_mod._login_sessions["alice_+123"] = replacement
        await asyncio.sleep(0.04)

        assert sessions_mod._login_sessions["alice_+123"] is replacement
        assert old_client.disconnect_calls == 1
        assert old_value["expire_task"].cancelled()

    @pytest.mark.asyncio
    async def test_account_cleanup_cancels_phone_and_qr_but_preserves_other_account(self):
        phone_lock = asyncio.Lock()
        qr_lock = asyncio.Lock()
        await phone_lock.acquire()
        await qr_lock.acquire()
        phone_client = _FakeClient()

        class FakeQrClient:
            is_initialized = True
            is_connected = True

            def __init__(self):
                self.stop_calls = 0
                self.removed = []

            async def stop(self):
                self.stop_calls += 1
                self.is_connected = False

            def remove_handler(self, *handler):
                self.removed.append(handler)

        qr_client = FakeQrClient()
        qr_watcher = asyncio.create_task(asyncio.sleep(60))
        sessions_mod._login_sessions["alice_+123"] = {
            "account_name": "alice", "client": phone_client, "lock": phone_lock,
        }
        sessions_mod._qr_login_sessions["qr-alice"] = {
            "account_name": "alice", "client": qr_client, "lock": qr_lock,
            "handler": ("handler", "group"), "expire_task": qr_watcher,
        }
        other = {"account_name": "bob", "client": _FakeClient()}
        sessions_mod._login_sessions["bob_+456"] = other

        await sessions_mod.cleanup_account_login_sessions("alice")

        assert set(sessions_mod._login_sessions) == {"bob_+456"}
        assert not sessions_mod._qr_login_sessions
        assert sessions_mod._login_sessions["bob_+456"] is other
        assert phone_client.disconnect_calls == 1
        assert qr_client.stop_calls == 1
        assert qr_client.removed == [("handler", "group")]
        assert qr_watcher.cancelled()
        assert not phone_lock.locked() and not qr_lock.locked()

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_releases_every_pending_account(self):
        clients = [_FakeClient(), _FakeClient()]
        locks = [asyncio.Lock(), asyncio.Lock()]
        for lock in locks:
            await lock.acquire()
        sessions_mod._login_sessions["alice_+123"] = {
            "account_name": "alice", "client": clients[0], "lock": locks[0],
        }
        sessions_mod._qr_login_sessions["qr-bob"] = {
            "account_name": "bob", "client": clients[1], "lock": locks[1],
        }

        await sessions_mod.cleanup_all_login_sessions()

        assert not sessions_mod._login_sessions and not sessions_mod._qr_login_sessions
        assert [client.disconnect_calls for client in clients] == [1, 1]
        assert all(not lock.locked() for lock in locks)

    @pytest.mark.asyncio
    async def test_account_cleanup_cancels_in_flight_phone_operation(self):
        entered = asyncio.Event()

        async def pending_operation():
            entered.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(pending_operation())
        await entered.wait()
        lock = asyncio.Lock()
        await lock.acquire()
        client = _FakeClient()
        sessions_mod._login_sessions["alice_+123"] = {
            "account_name": "alice", "client": client, "lock": lock,
            "_active_task": task,
        }

        await sessions_mod.cleanup_account_login_sessions("alice")

        assert task.cancelled()
        assert client.disconnect_calls == 1
        assert not lock.locked()

    @pytest.mark.asyncio
    async def test_qr_expiry_cleans_once_when_cancel_is_called_later(self, tmp_path):
        from backend.services.telegram.login_qr import TelegramQrLoginMixin

        class FakeQrClient:
            is_initialized = True
            is_connected = True

            def __init__(self):
                self.stop_calls = 0

            async def stop(self):
                self.stop_calls += 1
                self.is_connected = False

        service = TelegramQrLoginMixin()
        service.session_dir = tmp_path
        lock = asyncio.Lock()
        await lock.acquire()
        client = FakeQrClient()
        value = {
            "account_name": "alice", "client": client, "lock": lock,
            "expires_ts": int(time.time()) - 1,
        }
        sessions_mod._qr_login_sessions["qr-id"] = value
        watcher = asyncio.create_task(service._expire_qr_login("qr-id", value["expires_ts"]))
        value["expire_task"] = watcher

        await asyncio.wait_for(watcher, timeout=1)
        await service._cleanup_qr_login("qr-id")

        assert "qr-id" not in sessions_mod._qr_login_sessions
        assert client.stop_calls == 1
        assert not lock.locked()

    @pytest.mark.asyncio
    async def test_cancelled_phone_verification_releases_pending_client(self, monkeypatch):
        from backend.services.telegram import login_phone

        entered = asyncio.Event()

        class SlowClient(_FakeClient):
            async def sign_in(self, *_args):
                entered.set()
                await asyncio.Event().wait()

        client = SlowClient()
        lock = asyncio.Lock()
        await lock.acquire()
        sessions_mod._login_sessions["alice_+123"] = {
            "account_name": "alice", "client": client, "lock": lock,
        }
        service = login_phone.TelegramPhoneLoginMixin()
        service._normalize_account_name = lambda name: name
        monkeypatch.setattr(login_phone, "get_global_semaphore", lambda: asyncio.Semaphore(1))

        verifying = asyncio.create_task(service.verify_login("alice", "+123", "12345", "hash"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        verifying.cancel()
        with pytest.raises(asyncio.CancelledError):
            await verifying

        assert not sessions_mod._login_sessions
        assert not lock.locked()
        assert client.disconnect_calls == 1
