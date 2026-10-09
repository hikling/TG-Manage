"""accounts 路由缺口补测：登录/QR 流程、批量状态 Job、日志、设备、官方消息与头像缓存。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.routes import accounts as accounts_mod
from backend.services.telegram import credentials
from tests.test_api import _auth, _login, api_client, db  # noqa: F401


def _svc() -> MagicMock:
    """构造带异步方法的 TelegramService Mock；各用例再按需配置返回值。"""
    svc = MagicMock()
    svc.start_login = AsyncMock(
        return_value={
            "phone_code_hash": "hash-1",
            "phone_number": "+8613800000000",
            "account_name": "acc",
        }
    )
    svc.verify_login = AsyncMock(
        return_value={"user_id": 7, "first_name": "F", "username": "u"}
    )
    svc.start_qr_login = AsyncMock(
        return_value={
            "login_id": "login-1",
            "qr_uri": "tg://login?token=abc",
            "expires_at": "2030-01-01T00:00:00",
        }
    )
    svc.get_qr_login_status = AsyncMock(
        return_value={"status": "pending", "expires_at": None, "message": None}
    )
    svc.submit_qr_password = AsyncMock(return_value={"message": "登录成功"})
    svc.cancel_qr_login = AsyncMock(return_value=True)
    svc.list_accounts.return_value = []
    svc.account_exists.return_value = True
    svc.check_account_status = AsyncMock(
        return_value={
            "account_name": "a1",
            "ok": True,
            "status": "connected",
            "message": "OK",
        }
    )
    svc.list_account_devices = AsyncMock(return_value=[{"hash": "42", "current": True}])
    svc.terminate_account_device = AsyncMock(return_value=True)
    svc.list_official_messages = AsyncMock(
        return_value=[{"id": 1, "date": "2026-07-31", "text": "验证码", "outgoing": False}]
    )
    svc.download_account_avatar = AsyncMock(return_value=b"\xff\xd8\xffavatar")
    return svc


def _patch_svc(svc: MagicMock):
    return patch(
        "backend.api.routes.accounts.get_telegram_service", return_value=svc
    )


class TestLoginFlow:
    @pytest.mark.parametrize(
        ("endpoint", "payload", "method"),
        [
            ("/api/accounts/login/start", {"account_name": "plain_login", "phone_number": "+8613800000000"}, "start_login"),
            ("/api/accounts/qr/start", {"account_name": "plain_qr"}, "start_qr_login"),
        ],
    )
    def test_plain_login_without_telebox_or_api_credentials(self, api_client, db, monkeypatch, tmp_path, endpoint, payload, method):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        monkeypatch.setattr(credentials, "get_settings", lambda: SimpleNamespace(resolve_workdir=lambda: tmp_path))
        for name in ("TG_MANAGE_TG_API_ID", "TG_MANAGE_TG_API_HASH", "SIGNPULSE_TG_API_ID", "SIGNPULSE_TG_API_HASH", "TG_API_ID", "TG_API_HASH"):
            monkeypatch.delenv(name, raising=False)
        with _patch_svc(svc):
            response = api_client.post(endpoint, json=payload, headers=_auth(token))
        assert response.status_code == 200
        assert getattr(svc, method).await_args.kwargs["api_id"] == credentials.LEGACY_DEFAULT_API_ID
        assert getattr(svc, method).await_args.kwargs["api_hash"] == credentials.LEGACY_DEFAULT_API_HASH

    def test_start_success(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_start_ok", "phone_number": "+8613800000000"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["phone_code_hash"] == "hash-1"
        svc.start_login.assert_awaited_once()

    def test_start_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.start_login.side_effect = ValueError("手机号格式不正确")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_start_v", "phone_number": "bad"},
                headers=_auth(token),
            )
        assert resp.status_code == 400
        assert "手机号格式不正确" in resp.json()["detail"]

    def test_start_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.start_login.side_effect = RuntimeError("network down")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_start_e", "phone_number": "+8613800000000"},
                headers=_auth(token),
            )
        assert resp.status_code == 500
        assert "发送验证码失败" in resp.json()["detail"]

    def test_verify_success(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/verify",
                json={
                    "account_name": "acc_verify_ok",
                    "phone_number": "+8613800000000",
                    "phone_code": "12345",
                    "phone_code_hash": "hash-1",
                },
                headers=_auth(token),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True and body["user_id"] == 7

    def test_verify_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.verify_login.side_effect = ValueError("验证码错误")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/verify",
                json={
                    "account_name": "acc_verify_v",
                    "phone_number": "+8613800000000",
                    "phone_code": "00000",
                    "phone_code_hash": "hash-1",
                },
                headers=_auth(token),
            )
        assert resp.status_code == 400
        assert "验证码错误" in resp.json()["detail"]

    def test_verify_session_password_needed_returns_code(self, api_client, db):  # noqa: F811
        """需要 2FA 密码时返回稳定错误码，前端按码分支而非按文案匹配。"""
        token = _login(api_client)
        svc = _svc()
        svc.verify_login.side_effect = ValueError("此账号启用了两步验证，请输入 2FA 密码")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/verify",
                json={
                    "account_name": "acc_verify_2fa",
                    "phone_number": "+8613800000000",
                    "phone_code": "12345",
                    "phone_code_hash": "hash-1",
                },
                headers=_auth(token),
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "SESSION_PASSWORD_NEEDED"

    def test_verify_password_hash_invalid_returns_code(self, api_client, db):  # noqa: F811
        """2FA 密码错误返回稳定错误码。"""
        token = _login(api_client)
        svc = _svc()
        svc.verify_login.side_effect = ValueError("2FA 密码错误")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/verify",
                json={
                    "account_name": "acc_verify_2fa_bad",
                    "phone_number": "+8613800000000",
                    "phone_code": "12345",
                    "phone_code_hash": "hash-1",
                },
                headers=_auth(token),
            )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "PASSWORD_HASH_INVALID"


class TestQrLoginFlow:
    def test_qr_start_success(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_qr_ok"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["login_id"] == "login-1"
        assert body["expires_at"] == "2030-01-01T00:00:00"

    def test_qr_start_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.start_qr_login.side_effect = RuntimeError("boom")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_qr_e"},
                headers=_auth(token),
            )
        assert resp.status_code == 500
        assert "开始扫码登录失败" in resp.json()["detail"]

    def test_qr_status_without_account(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.get(
                "/api/accounts/qr/status",
                params={"login_id": "login-1"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pending" and body["account"] is None

    def test_qr_status_with_account(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.get_qr_login_status.return_value = {
            "status": "success",
            "account": {"name": "acc", "session_file": "f", "exists": True, "size": 1},
            "user_id": 9,
        }
        with _patch_svc(svc):
            resp = api_client.get(
                "/api/accounts/qr/status",
                params={"login_id": "login-1"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["account"]["name"] == "acc"

    def test_qr_password_success(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/password",
                json={"login_id": "login-1", "password": "2fa"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_qr_password_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.submit_qr_password.side_effect = ValueError("密码错误")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/password",
                json={"login_id": "login-1", "password": "wrong"},
                headers=_auth(token),
            )
        assert resp.status_code == 400

    def test_qr_cancel_result_variants(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            ok = api_client.post(
                "/api/accounts/qr/cancel",
                json={"login_id": "login-1"},
                headers=_auth(token),
            )
            assert ok.json() == {"success": True, "message": "已取消"}
        svc.cancel_qr_login.return_value = False
        with _patch_svc(svc):
            gone = api_client.post(
                "/api/accounts/qr/cancel",
                json={"login_id": "login-1"},
                headers=_auth(token),
            )
            assert gone.json() == {"success": False, "message": "登录已失效"}


class TestStatusCheckJobs:
    def test_start_job_created(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)
        monkeypatch.setattr(
            "backend.services.account_status_jobs.start_account_status_check_job",
            lambda **kwargs: {"job_id": "job_1", "status": "running"},
        )
        resp = api_client.post(
            "/api/accounts/status/check-jobs",
            json={"account_names": ["a1"]},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["job_id"] == "job_1"

    def test_start_job_value_error_400(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)

        def _raise(**kwargs):
            raise ValueError("已有任务进行中")

        monkeypatch.setattr(
            "backend.services.account_status_jobs.start_account_status_check_job", _raise
        )
        resp = api_client.post(
            "/api/accounts/status/check-jobs",
            json={"account_names": ["a1"]},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    def test_list_jobs_clamps_limit(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)
        seen: list[int] = []
        monkeypatch.setattr(
            "backend.services.account_status_jobs.list_account_status_jobs",
            lambda limit: seen.append(limit) or [],
        )
        api_client.get(
            "/api/accounts/status/check-jobs", params={"limit": 999}, headers=_auth(token)
        )
        api_client.get(
            "/api/accounts/status/check-jobs", params={"limit": 0}, headers=_auth(token)
        )
        assert seen == [50, 1]

    def test_get_job_404(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)
        monkeypatch.setattr(
            "backend.services.account_status_jobs.get_account_status_job",
            lambda job_id: None,
        )
        resp = api_client.get(
            "/api/accounts/status/check-jobs/nope", headers=_auth(token)
        )
        assert resp.status_code == 404

    def test_cancel_job_variants(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)
        monkeypatch.setattr(
            "backend.services.account_status_jobs.cancel_account_status_job",
            lambda job_id: False,
        )
        bad = api_client.post(
            "/api/accounts/status/check-jobs/j1/cancel", headers=_auth(token)
        )
        assert bad.status_code == 400
        monkeypatch.setattr(
            "backend.services.account_status_jobs.cancel_account_status_job",
            lambda job_id: True,
        )
        ok = api_client.post(
            "/api/accounts/status/check-jobs/j1/cancel", headers=_auth(token)
        )
        assert ok.status_code == 200 and ok.json() == {"ok": True, "job_id": "j1"}










class TestDevicesAndOfficialMessages:
    def test_list_devices(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        with _patch_svc(_svc()):
            resp = api_client.get("/api/accounts/a1/devices", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1 and body["devices"][0]["hash"] == "42"

    def test_list_devices_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_account_devices.side_effect = ValueError("账号离线")
        with _patch_svc(svc):
            resp = api_client.get("/api/accounts/a1/devices", headers=_auth(token))
        assert resp.status_code == 400

    def test_list_devices_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_account_devices.side_effect = RuntimeError("tg down")
        with _patch_svc(svc):
            resp = api_client.get("/api/accounts/a1/devices", headers=_auth(token))
        assert resp.status_code == 500

    def test_terminate_device(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.delete(
                "/api/accounts/a1/devices/42", headers=_auth(token)
            )
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "message": "设备已下线"}
        svc.terminate_account_device.assert_awaited_with("a1", 42)

    def test_terminate_device_bad_hash_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.delete(
                "/api/accounts/a1/devices/abc", headers=_auth(token)
            )
        assert resp.status_code == 400
        svc.terminate_account_device.assert_not_awaited()

    def test_terminate_device_failure_message(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.terminate_account_device.return_value = False
        with _patch_svc(svc):
            resp = api_client.delete(
                "/api/accounts/a1/devices/42", headers=_auth(token)
            )
        assert resp.json() == {"success": False, "message": "设备下线失败"}

    def test_official_messages(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        with _patch_svc(_svc()):
            resp = api_client.get(
                "/api/accounts/a1/official-messages", headers=_auth(token)
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1 and body["messages"][0]["text"] == "验证码"

    def test_official_messages_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_official_messages.side_effect = ValueError("账号失效")
        with _patch_svc(svc):
            resp = api_client.get(
                "/api/accounts/a1/official-messages", headers=_auth(token)
            )
        assert resp.status_code == 400


class TestAvatarCache:
    def test_status_check_defaults_to_no_avatar_download(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_default"]}, headers=_auth(token))
        assert checked.status_code == 200
        assert checked.json()["results"][0].get("avatar_refreshed") is not True
        svc.download_account_avatar.assert_not_awaited()

    def test_multi_account_avatar_refresh_is_rejected(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["a", "b"], "refresh_avatar": True}, headers=_auth(token))
        assert checked.status_code == 400
        svc.download_account_avatar.assert_not_awaited()

    def test_check_refreshes_avatar_then_cache_only_get(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            missing = api_client.get("/api/accounts/ava_a/avatar", headers=_auth(token))
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_a"], "refresh_avatar": True}, headers=_auth(token))
            first = api_client.get("/api/accounts/ava_a/avatar", headers=_auth(token))
            second = api_client.get("/api/accounts/ava_a/avatar", headers=_auth(token))
        assert missing.status_code == 404
        assert checked.json()["results"][0]["avatar_refreshed"] is True
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/jpeg"
        assert first.content == b"\xff\xd8\xffavatar"
        assert second.status_code == 200
        # 两次 GET 只读磁盘，下载只发生在明确检测动作中。
        assert svc.download_account_avatar.await_count == 1

    def test_no_avatar_marked_then_404_fast(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.download_account_avatar.return_value = None
        with _patch_svc(svc):
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_b"], "refresh_avatar": True}, headers=_auth(token))
            first = api_client.get("/api/accounts/ava_b/avatar", headers=_auth(token))
            second = api_client.get("/api/accounts/ava_b/avatar", headers=_auth(token))
        assert checked.status_code == 200
        assert first.status_code == 404
        assert second.status_code == 404
        # 无头像标记由检测写入，GET 不会下载。
        assert svc.download_account_avatar.await_count == 1

    def test_download_error_falls_back_404(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.download_account_avatar.side_effect = RuntimeError("flood wait")
        with _patch_svc(svc):
            resp = api_client.get("/api/accounts/ava_c/avatar", headers=_auth(token))
        assert resp.status_code == 404
        svc.download_account_avatar.assert_not_awaited()
        # 普通 GET 不会把瞬时错误误标记为无头像。
        from backend.core.config import get_settings

        marker = get_settings().resolve_workdir() / "avatars" / "ava_c.no_avatar"
        assert not marker.exists()

    def test_avatar_requires_auth(self, api_client, db):  # noqa: F811
        resp = api_client.get("/api/accounts/ava_d/avatar")
        assert resp.status_code == 401


class TestStatusCheckExtended:
    @pytest.mark.asyncio
    async def test_canceled_card_probe_releases_reservation(self):
        from backend.services.account_check_gate import account_check_gate

        svc = _svc()
        svc.check_account_status.side_effect = asyncio.CancelledError()
        with _patch_svc(svc), pytest.raises(asyncio.CancelledError):
            await accounts_mod.check_accounts_status(
                accounts_mod.AccountStatusCheckRequest(account_names=["cancel-card"]),
                current_user=None,
            )
        account_check_gate.reserve(["cancel-card"]).release()
        svc.download_account_avatar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_probe_keeps_cooldown_when_avatar_refresh_fails(self):
        from backend.services.account_check_gate import (
            AccountCheckBusy,
            account_check_gate,
        )

        svc = _svc()
        with _patch_svc(svc), patch(
            "backend.services.avatar_cache.refresh_account_avatar", side_effect=RuntimeError("download failed")
        ):
            response = await accounts_mod.check_accounts_status(
                accounts_mod.AccountStatusCheckRequest(account_names=["avatar-failed"], refresh_avatar=True),
                current_user=None,
            )
        assert response.results[0].ok
        assert response.results[0].avatar_refresh_error
        with pytest.raises(AccountCheckBusy) as error:
            account_check_gate.reserve(["avatar-failed"])
        assert error.value.remaining_seconds == 45

    @pytest.mark.asyncio
    async def test_card_cooldown_starts_after_avatar_refresh_finishes(self):
        from backend.services.account_check_gate import (
            AccountCheckBusy,
            account_check_gate,
        )

        svc = _svc()
        started = asyncio.Event()
        release = asyncio.Event()

        async def refresh(_name, _download):
            started.set()
            await release.wait()
            return True

        with _patch_svc(svc), patch("backend.services.avatar_cache.refresh_account_avatar", side_effect=refresh):
            task = asyncio.create_task(accounts_mod.check_accounts_status(
                accounts_mod.AccountStatusCheckRequest(account_names=["timing"], refresh_avatar=True),
                current_user=None,
            ))
            await started.wait()
            with pytest.raises(AccountCheckBusy):
                account_check_gate.reserve(["timing"])
            release.set()
            response = await task
        assert response.results[0].avatar_refreshed is True
        with pytest.raises(AccountCheckBusy) as error:
            account_check_gate.reserve(["timing"])
        assert error.value.remaining_seconds == 45

    def test_successful_card_check_blocks_same_account_batch_for_45_seconds(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            first = api_client.post(
                "/api/accounts/status/check",
                json={"account_names": ["cooldown_a"], "refresh_avatar": True},
                headers=_auth(token),
            )
            repeated = api_client.post(
                "/api/accounts/status/check",
                json={"account_names": ["cooldown_b", "cooldown_a"]},
                headers=_auth(token),
            )
        assert first.status_code == 200
        assert repeated.status_code == 429
        assert repeated.headers["retry-after"] == "45"
        assert svc.check_account_status.await_count == 1
        assert svc.download_account_avatar.await_count == 1

    def test_failed_check_can_retry_without_cooldown(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.check_account_status = AsyncMock(side_effect=[
            {"account_name": "retry_a", "ok": False, "status": "error", "message": "failed"},
            {"account_name": "retry_a", "ok": True, "status": "connected", "message": "ok"},
        ])
        with _patch_svc(svc):
            first = api_client.post(
                "/api/accounts/status/check", json={"account_names": ["retry_a"]}, headers=_auth(token)
            )
            second = api_client.post(
                "/api/accounts/status/check", json={"account_names": ["retry_a"]}, headers=_auth(token)
            )
        assert first.status_code == second.status_code == 200
        assert svc.check_account_status.await_count == 2

    def test_per_account_failure_and_timeout_clamp(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()

        async def _check(name, timeout_seconds=6.0, no_updates=None):
            if name == "bad":
                raise RuntimeError("flood wait")
            return {
                "account_name": name,
                "ok": True,
                "status": "connected",
                "message": "OK",
            }

        svc.check_account_status = AsyncMock(side_effect=_check)
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/status/check",
                json={"account_names": ["good", "bad"], "timeout_seconds": 999},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert results[0]["ok"] is True
        assert results[1]["ok"] is False
        # 超时参数被钳制到上限 20s
        assert svc.check_account_status.await_args_list[0].kwargs["timeout_seconds"] == 20.0

    def test_default_names_from_list_accounts(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_accounts.return_value = [
            {"name": "from_list", "session_file": "f", "exists": True, "size": 1}
        ]

        async def _check(name, timeout_seconds=6.0, no_updates=None):
            return {
                "account_name": name,
                "ok": True,
                "status": "connected",
                "message": "OK",
            }

        svc.check_account_status = AsyncMock(side_effect=_check)
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/status/check", json={}, headers=_auth(token)
            )
        assert resp.status_code == 200
        names = [r["account_name"] for r in resp.json()["results"]]
        assert names == ["from_list"]
        assert svc.check_account_status.await_args_list[0].args[0] == "from_list"

    def test_status_check_service_crash_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_accounts.side_effect = RuntimeError("fs error")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/status/check", json={}, headers=_auth(token)
            )
        assert resp.status_code == 500


class TestAccountsModuleHelper:
    def test_apply_rate_limit_composes_key(self, api_client, db):  # noqa: F811
        # 直接校验 _apply_rate_limit 返回合成键（限流器为真实内存实例）
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/x",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
        key = accounts_mod._apply_rate_limit(
            "test.scope",
            Request(scope),
            "detail",
            "part1",
            max_attempts=10,
            window_seconds=60,
            block_seconds=60,
        )
        assert key
        accounts_mod.rate_limiter.reset("test.scope", key)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """每个用例后清空限流器，避免同键累计触发 429。"""
    yield
    accounts_mod.rate_limiter.reset_all()


class TestErrorBranchesRound2:
    """各端点剩余错误分支：400/404/500 的映射完整性。"""

    def test_verify_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.verify_login.side_effect = RuntimeError("tg 崩溃")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/login/verify",
                json={
                    "account_name": "acc_verify_e",
                    "phone_number": "+8613800000000",
                    "phone_code": "12345",
                    "phone_code_hash": "hash-1",
                },
                headers=_auth(token),
            )
        assert resp.status_code == 500
        assert "登录验证失败" in resp.json()["detail"]

    def test_qr_start_value_error_400(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.start_qr_login.side_effect = ValueError("账号名已存在")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/start",
                json={"api_id": 12345, "api_hash": "0" * 32, "account_name": "acc_qr_v"},
                headers=_auth(token),
            )
        assert resp.status_code == 400

    def test_qr_status_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.get_qr_login_status.side_effect = RuntimeError("状态丢失")
        with _patch_svc(svc):
            resp = api_client.get(
                "/api/accounts/qr/status",
                params={"login_id": "login-x"},
                headers=_auth(token),
            )
        assert resp.status_code == 500
        assert "获取扫码状态失败" in resp.json()["detail"]

    def test_qr_password_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.submit_qr_password.side_effect = RuntimeError("boom")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/password",
                json={"login_id": "login-x", "password": "p"},
                headers=_auth(token),
            )
        assert resp.status_code == 500

    def test_qr_cancel_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.cancel_qr_login.side_effect = RuntimeError("boom")
        with _patch_svc(svc):
            resp = api_client.post(
                "/api/accounts/qr/cancel",
                json={"login_id": "login-x"},
                headers=_auth(token),
            )
        assert resp.status_code == 500
        assert "取消扫码登录失败" in resp.json()["detail"]

    def test_start_job_generic_error_500(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)

        def _raise(**kwargs):
            raise RuntimeError("db locked")

        monkeypatch.setattr(
            "backend.services.account_status_jobs.start_account_status_check_job", _raise
        )
        resp = api_client.post(
            "/api/accounts/status/check-jobs",
            json={"account_names": ["a1"]},
            headers=_auth(token),
        )
        assert resp.status_code == 500

    def test_get_job_found(self, api_client, db, monkeypatch):  # noqa: F811
        token = _login(api_client)
        monkeypatch.setattr(
            "backend.services.account_status_jobs.get_account_status_job",
            lambda job_id: {"job_id": job_id, "status": "done"},
        )
        resp = api_client.get(
            "/api/accounts/status/check-jobs/job_9", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json()["job_id"] == "job_9"

    def test_list_accounts_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_accounts.side_effect = RuntimeError("扫描失败")
        with _patch_svc(svc):
            resp = api_client.get("/api/accounts", headers=_auth(token))
        assert resp.status_code == 500

    def test_terminate_device_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.terminate_account_device.side_effect = RuntimeError("tg down")
        with _patch_svc(svc):
            resp = api_client.delete(
                "/api/accounts/a1/devices/42", headers=_auth(token)
            )
        assert resp.status_code == 500

    def test_official_messages_generic_error_500(self, api_client, db):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        svc.list_official_messages.side_effect = RuntimeError("tg down")
        with _patch_svc(svc):
            resp = api_client.get(
                "/api/accounts/a1/official-messages", headers=_auth(token)
            )
        assert resp.status_code == 500




class TestAvatarStaleCache:
    def test_expired_cache_still_served_without_download(self, api_client, db):  # noqa: F811
        import os

        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_e"], "refresh_avatar": True}, headers=_auth(token))
        assert checked.status_code == 200
        # 把缓存文件 mtime 拨到 8 天前，使新鲜期失效
        from backend.core.config import get_settings

        cache_file = (
            get_settings().resolve_workdir() / "avatars" / "ava_e.jpg"
        )
        stale = cache_file.stat().st_mtime - 8 * 86400
        os.utime(cache_file, (stale, stale))
        svc.download_account_avatar.side_effect = RuntimeError("flood wait")
        with _patch_svc(svc):
            resp = api_client.get("/api/accounts/ava_e/avatar", headers=_auth(token))
        # 普通 GET 永远只读磁盘，即使缓存较旧。
        assert resp.status_code == 200
        assert resp.content == b"\xff\xd8\xffavatar"
        assert svc.download_account_avatar.await_count == 1

    def test_expired_no_avatar_marker_ignored(self, api_client, db):  # noqa: F811
        import os

        token = _login(api_client)
        svc = _svc()
        svc.download_account_avatar.return_value = None
        with _patch_svc(svc):
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_f"], "refresh_avatar": True}, headers=_auth(token))
            first = api_client.get("/api/accounts/ava_f/avatar", headers=_auth(token))
        assert checked.status_code == 200
        assert first.status_code == 404
        # 把无头像标记拨到 8 天前：普通 GET 仍不应重新下载。
        from backend.core.config import get_settings

        marker = (
            get_settings().resolve_workdir() / "avatars" / "ava_f.no_avatar"
        )
        stale = marker.stat().st_mtime - 8 * 86400
        os.utime(marker, (stale, stale))
        # This test exercises expired avatar metadata, not the new check cooldown.
        from backend.services.account_check_gate import account_check_gate

        account_check_gate._deadlines.pop("ava_f", None)
        svc.download_account_avatar.return_value = b"\xff\xd8\xffnew"
        svc.download_account_avatar.side_effect = None
        with _patch_svc(svc):
            missing = api_client.get("/api/accounts/ava_f/avatar", headers=_auth(token))
            checked = api_client.post("/api/accounts/status/check", json={"account_names": ["ava_f"], "refresh_avatar": True}, headers=_auth(token))
            resp = api_client.get("/api/accounts/ava_f/avatar", headers=_auth(token))
        assert missing.status_code == 404
        assert checked.status_code == 200
        assert resp.status_code == 200
        assert resp.content == b"\xff\xd8\xffnew"




class TestUpdateAccountRename:
    def test_rename_flow(self, api_client, db, monkeypatch, tmp_path):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        old = {"name": "old_acc", "session_file": "f", "exists": True, "size": 1}
        new = {"name": "new_acc", "session_file": "f2", "exists": True, "size": 2}
        svc.list_accounts.side_effect = [[old], [new]]
        svc.rename_account = AsyncMock(return_value="new_acc")
        # 改名会同步新的每日任务。
        monkeypatch.setattr("backend.scheduler.sync_jobs", AsyncMock())
        telebox = MagicMock()
        telebox.directory.return_value = tmp_path / "unused-telebox-target"
        telebox.stop = AsyncMock()
        with _patch_svc(svc), patch(
            "backend.services.telebox.get_telebox_service", return_value=telebox
        ):
            resp = api_client.patch(
                "/api/accounts/old_acc",
                json={"new_account_name": "new_acc", "remark": "备注"},
                headers=_auth(token),
            )
        assert resp.status_code == 200, resp.json()
        body = resp.json()
        assert body["success"] is True
        assert body["account"]["name"] == "new_acc"
        svc.rename_account.assert_awaited_once_with("old_acc", "new_acc")
        telebox.stop.assert_awaited_once_with("old_acc")
        telebox.rename_account_data.assert_called_once_with("old_acc", "new_acc")



class TestAccountNameValidation:
    """路径参数输入校验：穿越名/路径分隔符统一 400，且不触达服务层。

    说明：Starlette 路由在匹配前解码路径，%2F 编码斜杠（..%2F..）会被路由层
    以 404 拦截、到不了 {account_name} 参数；能到达 handler 的穿越向量是
    ``..``、反斜杠、空串与 null 字节，均由 validate_storage_name 拦为 400。
    """

    @pytest.mark.parametrize(
        "account_name",
        ["a%5Cb", "%2e", "%2e%2e", "%00", "%20%20"],
    )
    def test_exists_rejects_invalid_names(self, api_client, db, account_name):  # noqa: F811
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.get(
                f"/api/accounts/{account_name}/exists", headers=_auth(token)
            )
        assert resp.status_code == 400
        svc.account_exists.assert_not_called()

    @pytest.mark.parametrize("account_name", ["..%2F..", "%2Fetc%2Fpasswd"])
    def test_encoded_slash_rejected_by_router(self, api_client, db, account_name):  # noqa: F811
        """编码斜杠在路由匹配前解码为路径分隔符，请求不匹配任何路由（404）。"""
        token = _login(api_client)
        svc = _svc()
        with _patch_svc(svc):
            resp = api_client.get(
                f"/api/accounts/{account_name}/exists", headers=_auth(token)
            )
        assert resp.status_code == 404
        svc.account_exists.assert_not_called()

    def test_all_account_endpoints_reject_traversal(self, api_client, db):  # noqa: F811
        """现有账号路由对 ``..`` 穿越名返回 400 且不调用服务。"""
        token = _login(api_client)
        svc = _svc()
        name = "%2e%2e"
        with _patch_svc(svc):
            # 删除账号
            resp = api_client.delete(f"/api/accounts/{name}", headers=_auth(token))
            assert resp.status_code == 400
            svc.delete_account.assert_not_called()

            # 存在性检查
            resp = api_client.get(f"/api/accounts/{name}/exists", headers=_auth(token))
            assert resp.status_code == 400
            svc.account_exists.assert_not_called()

            # 设备列表 / 踢下线
            resp = api_client.get(f"/api/accounts/{name}/devices", headers=_auth(token))
            assert resp.status_code == 400
            svc.list_account_devices.assert_not_called()
            resp = api_client.delete(
                f"/api/accounts/{name}/devices/42", headers=_auth(token)
            )
            assert resp.status_code == 400
            svc.terminate_account_device.assert_not_called()

            # 官方消息
            resp = api_client.get(
                f"/api/accounts/{name}/official-messages", headers=_auth(token)
            )
            assert resp.status_code == 400
            svc.list_official_messages.assert_not_called()

            # 头像
            resp = api_client.get(f"/api/accounts/{name}/avatar", headers=_auth(token))
            assert resp.status_code == 400
            svc.download_account_avatar.assert_not_called()

            # 账户编辑
            resp = api_client.patch(
                f"/api/accounts/{name}", json={}, headers=_auth(token)
            )
            assert resp.status_code == 400
            svc.list_accounts.assert_not_called()
