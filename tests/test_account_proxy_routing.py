"""Proxy edits, route ownership and login use no implicit proxy or probe."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services.telegram import accounts as accounts_mod
from backend.services.telegram import devices as devices_mod
from backend.services.telegram import login_phone, login_qr
from backend.utils import tg_session
from backend.utils.proxy import build_proxy_dict, require_proxy_dict
from tg_manage.core import client as client_mod


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(tg_session, "_account_store_path", lambda: tmp_path / "accounts.json")
    return tmp_path


def test_proxy_status_tracks_edits_and_rejects_stale_or_removed_accounts(store):
    first, second = "socks5://first:1080", "socks5://second:1080"
    tg_session.set_account_profile("one", proxy=first)
    assert tg_session.get_account_proxy_status("one")["proxy_status"] == "pending"
    assert tg_session.set_account_proxy_status(
        "one", expected_proxy=first, status="healthy", code="OK", checked_at="today")
    tg_session.set_account_profile("one", remark="same route")
    assert tg_session.get_account_proxy_status("one")["proxy_status"] == "healthy"
    tg_session.set_account_profile("one", proxy=second)
    assert tg_session.get_account_proxy_status("one") == {
        "proxy_status": "pending", "proxy_status_code": None, "proxy_checked_at": None}
    assert not tg_session.set_account_proxy_status(
        "one", expected_proxy=first, status="healthy", code="OK", checked_at="stale")
    tg_session.set_account_profile("one", proxy=None)
    assert tg_session.get_account_proxy("one") is None
    assert tg_session.get_account_proxy_status("one")["proxy_status"] == "unconfigured"
    tg_session.delete_account_session_string("one")
    assert not tg_session.set_account_proxy_status(
        "one", expected_proxy=second, status="error", code="FAILED", checked_at="today")
    assert "one" not in tg_session.list_account_names()


def test_bad_proxy_rejected_and_percent_encoded_credentials_match(store, monkeypatch):
    monkeypatch.setenv("TG_PROXY", "socks5://global:1080")
    assert client_mod.get_proxy() is None
    assert tg_session.resolve_effective_proxy("one") is None
    with pytest.raises(ValueError, match="INVALID_ACCOUNT_PROXY"):
        tg_session.set_account_profile("one", proxy="socks5://bad:port")
    proxy = require_proxy_dict("socks5://user%40name:p%3Ass%2Fword@host:1080")
    assert proxy["username"] == "user@name"
    assert proxy["password"] == "p:ss/word"
    assert client_mod.get_proxy("socks5://user%40name:p%3Ass%2Fword@host:1080") == proxy


class _LifecycleClient(client_mod.Client):
    def __init__(self, name, *, key, proxy, **kwargs):
        self.name, self.key, self.proxy = name, key, proxy
        self.is_connected = self.is_initialized = False
        self._tg_manage_no_updates = kwargs.get("no_updates")
        self.stop_count = 0

    async def connect(self):
        self.is_connected = True
        return True

    async def get_me(self):
        return SimpleNamespace(id=123, username="sample")

    async def invoke(self, _query):
        pass

    async def initialize(self):
        self.is_initialized = True

    async def stop(self):
        self.stop_count += 1
        self.is_connected = self.is_initialized = False


@pytest.mark.asyncio
async def test_route_edit_preserves_active_refs_and_next_acquisition(store, monkeypatch):
    monkeypatch.setattr(client_mod, "Client", _LifecycleClient)
    monkeypatch.setenv("TG_PROXY", "socks5://global:1080")
    monkeypatch.setattr(accounts_mod, "get_account_profile", tg_session.get_account_profile)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(tg_session, "get_account_api_credentials", lambda _name: (123, "a" * 32))
    service = accounts_mod.TelegramAccountsMixin()
    service.session_dir = store
    tg_session.set_account_profile("one", proxy="socks5://first:1080")
    first, _ = service._build_account_client("one")
    async with first:
        tg_session.set_account_profile("one", proxy="socks5://second:1080")
        second, _ = service._build_account_client("one")
        assert second is not first and first.is_connected and first.stop_count == 0
        async with second:
            assert second.proxy["hostname"] == "second"
            assert first.is_connected
        assert first.is_connected and first.stop_count == 0
        tg_session.set_account_profile("one", proxy="")
        direct, proxy = service._build_account_client("one")
        async with direct:
            assert proxy is None and direct.proxy is None
    assert first.stop_count == second.stop_count == direct.stop_count == 1
    assert not any(str(store) in key for key in client_mod._CLIENT_REFS)
    assert not any(str(store) in key for key in client_mod._CLIENT_INSTANCES)


@pytest.mark.asyncio
async def test_route_client_cancellation_releases_only_its_refs(store, monkeypatch):
    monkeypatch.setattr(client_mod, "Client", _LifecycleClient)
    client = client_mod.get_client("one", workdir=store, api_id=123, api_hash="a" * 32,
                                   proxy=build_proxy_dict("socks5://one:1080"))
    entered = asyncio.Event()

    async def operation():
        async with client:
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(operation())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.stop_count == 1
    assert client.key not in client_mod._CLIENT_REFS


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["list_account_devices", "terminate_account_device", "list_official_messages"])
async def test_waiting_account_operations_build_client_after_proxy_edit(monkeypatch, operation):
    lock = asyncio.Lock()
    await lock.acquire()
    monkeypatch.setattr(devices_mod, "get_account_lock", lambda _name: lock)
    route = {"proxy": "socks5://old:1080"}
    built_routes = []

    class Client:
        is_connected = False

        async def connect(self):
            self.is_connected = True

        async def invoke(self, _request):
            return SimpleNamespace(authorizations=[]) if operation == "list_account_devices" else True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get_chat_history(self, *_args, **_kwargs):
            if False:
                yield None

    class Service(devices_mod.TelegramDevicesMixin):
        _normalize_account_name = staticmethod(lambda name: name)

        def account_exists(self, _name):
            return True

        def _build_account_client(self, _name, no_updates=True):
            built_routes.append(route["proxy"])
            return Client(), {}

    service = Service()
    if operation == "terminate_account_device":
        service.list_account_devices = AsyncMock(return_value=[{"hash": "42", "current": False}])
        task = asyncio.create_task(service.terminate_account_device("one", 42))
    else:
        task = asyncio.create_task(getattr(service, operation)("one"))
    await asyncio.sleep(0.01)
    assert built_routes == []
    route["proxy"] = "socks5://new:1080"
    lock.release()
    await task
    assert built_routes == [route["proxy"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [ConnectionError, RuntimeError])
async def test_account_status_errors_do_not_return_proxy_credentials(store, monkeypatch, error):
    client = _LifecycleClient("one", key="secret-test", proxy=None)
    client.get_me = AsyncMock(side_effect=error("socks5://user:SECRET@host:1080"))
    monkeypatch.setattr("tg_manage.core.get_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    monkeypatch.setattr(accounts_mod, "get_account_profile", lambda _name: {})
    writes = Mock()
    monkeypatch.setattr(accounts_mod, "set_account_status", writes)
    service = accounts_mod.TelegramAccountsMixin()
    service.session_dir = store
    service.account_exists = lambda _name: True
    result = await service.check_account_status("one")
    assert result["ok"] is False
    assert "SECRET" not in str(result) + str(writes.call_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["start_login", "start_qr_login"])
@pytest.mark.parametrize("proxy", [None, "socks5://user:p%40ss@account-proxy:1080"])
@pytest.mark.parametrize("failure", [False, True])
async def test_login_first_connection_uses_only_entered_proxy(store, monkeypatch, caplog, method, proxy, failure):
    captured = []

    class LoginClient:
        def __init__(self, **kwargs):
            self.proxy = kwargs["proxy"]
            self.is_connected = False
            self.is_initialized = False
            self.storage = None

        async def connect(self):
            captured.append(self.proxy)
            if failure:
                raise RuntimeError("socks5://user:SECRET@host:1080")
            self.is_connected = True

        async def disconnect(self):
            self.is_connected = False

        async def send_code(self, _phone):
            return SimpleNamespace(phone_code_hash="code-hash")

        async def sign_in(self, *_args):
            pass

        async def get_me(self):
            return SimpleNamespace(id=123, first_name="sample", username="sample")

        async def export_session_string(self):
            return None

        async def invoke(self, _query):
            return SimpleNamespace(token=b"qr-token", expires=1234567890)

        async def initialize(self):
            self.is_initialized = True

        def add_handler(self, _handler):
            pass

    class Service(login_phone.TelegramPhoneLoginMixin, login_qr.TelegramQrLoginMixin):
        _normalize_account_name = staticmethod(lambda name: name)

    service = Service()
    service.session_dir = store
    monkeypatch.setenv("TG_PROXY", "socks5://global:1080")
    monkeypatch.setattr("pyrogram.Client", LoginClient)
    monkeypatch.setattr("tg_manage.core.close_client_by_name", AsyncMock())
    lock = asyncio.Lock()
    module = login_phone if method == "start_login" else login_qr
    monkeypatch.setattr(module, "get_account_lock", lambda _name: lock)
    monkeypatch.setattr(module, "get_session_mode", lambda: "file")
    monkeypatch.setattr(module, "get_global_semaphore", lambda: asyncio.Semaphore(1))
    monkeypatch.setattr(module, "_cleanup_expired_login_sessions", AsyncMock())
    monkeypatch.setattr(login_phone, "set_account_api_credentials", Mock())
    kwargs = {"account_name": "one", "proxy": proxy, "api_id": 12345, "api_hash": "a" * 32}
    if method == "start_login":
        kwargs["phone_number"] = "+12345678900"
    if failure:
        with pytest.raises(ValueError) as raised:
            await getattr(service, method)(**kwargs)
        assert "SECRET" not in str(raised.value) + caplog.text
        assert not lock.locked()
        return
    await getattr(service, method)(**kwargs)
    assert captured == [build_proxy_dict(proxy) if proxy else None]
    session_store = login_phone._login_sessions if method == "start_login" else login_qr._qr_login_sessions
    assert next(iter(session_store.values()))["proxy"] == proxy
    if method == "start_login":
        await service.verify_login("one", "+12345678900", "12345", "code-hash")
        assert tg_session.get_account_proxy("one") == proxy
    else:
        for session in session_store.values():
            session["expire_task"].cancel()
    session_store.clear()
    if lock.locked():
        lock.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError, ValueError])
async def test_phone_verify_exception_keeps_credentials_out_of_api(store, monkeypatch, error):
    service = login_phone.TelegramPhoneLoginMixin()
    service._normalize_account_name = lambda name: name
    client = SimpleNamespace(is_connected=True,
                             sign_in=AsyncMock(side_effect=error("socks5://user:SECRET@host:1080")),
                             disconnect=AsyncMock())
    lock = asyncio.Lock()
    await lock.acquire()
    monkeypatch.setattr(login_phone, "_login_sessions", {
        "one_+12345678900": {"client": client, "lock": lock}})
    monkeypatch.setattr(login_phone, "get_global_semaphore", lambda: asyncio.Semaphore(1))
    with pytest.raises(ValueError) as raised:
        await service.verify_login("one", "+12345678900", "12345", "hash")
    assert "SECRET" not in str(raised.value)
    assert not lock.locked()
    assert not login_phone._login_sessions


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,expected", [({}, "socks5://first:1080"), ({"proxy": None}, None), ({"proxy": ""}, None)])
async def test_edit_patch_omission_preserves_route_but_empty_clears(store, monkeypatch, payload, expected):
    from backend.api.routes import accounts as routes

    tg_session.set_account_profile("one", proxy="socks5://first:1080")
    service = SimpleNamespace(list_accounts=lambda **kwargs: [{
        "name": "one", "status": "connected", "session_file": "one.session", "exists": True, "size": 1}])
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    refresh = AsyncMock()
    monkeypatch.setattr("backend.services.telebox.get_telebox_service",
                        lambda: SimpleNamespace(refresh_account_proxy=refresh))
    result = await routes.update_account("one", routes.AccountUpdateRequest(**payload), None)
    assert result.success
    assert tg_session.get_account_proxy("one") == expected
    assert refresh.await_count == int("proxy" in payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,alive", [(True, True), (False, True), (True, False)])
async def test_proxy_edit_reconnects_only_enabled_live_telebox(store, monkeypatch, enabled, alive):
    from backend.services import telebox

    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name, account_exists=lambda name: True))
    service = telebox.TeleBoxService(root=store)
    service._marker("one", enabled)
    worker = {"process": SimpleNamespace(returncode=None if alive else 0), "status": "running"}
    service.workers["one"] = worker
    events = []

    async def stop(name, *, disable):
        assert service.locks[name].locked() and disable is False
        events.append("stop")

    async def start(name):
        assert service.locks[name].locked()
        events.append("start")

    monkeypatch.setattr(service, "_stop_locked", stop)
    monkeypatch.setattr(service, "_start_locked", start)
    await service.refresh_account_proxy("one")
    assert events == (["stop", "start"] if enabled and alive else [])
    assert service.status("one")["enabled"] is enabled


@pytest.mark.asyncio
async def test_telebox_proxy_restart_failure_is_visible_and_sanitized(store, monkeypatch):
    from backend.services import telebox

    monkeypatch.setattr(telebox, "get_telegram_service", lambda: SimpleNamespace(
        _normalize_account_name=lambda name: name, account_exists=lambda name: True))
    service = telebox.TeleBoxService(root=store)
    service._marker("one", True)
    service.workers["one"] = {"process": SimpleNamespace(returncode=None), "status": "running"}
    monkeypatch.setattr(service, "_stop_locked", AsyncMock())
    monkeypatch.setattr(service, "_start_locked", AsyncMock(side_effect=ValueError("secret:PROXY_PASSWORD")))
    await service.refresh_account_proxy("one")
    assert service.status("one")["enabled"] is True
    assert service.status("one")["status"] == "failed"
    assert "PROXY_PASSWORD" not in str(service.status("one")) + str(service.log_items("one"))
