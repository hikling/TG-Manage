"""扩展设置与 Bot 测试。"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.auth import create_access_token
from backend.services.config_mixins import normalize_global_settings


def _auth_headers() -> dict:
    token = create_access_token(
        {"sub": "admin"},
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdvancedSettingsApi:
    def test_retired_quiet_settings_are_removed_from_saved_data(self):
        assert normalize_global_settings({
            "telegram_bot_notify_enabled": True,
            "telegram_bot_quiet_hours_enabled": True,
            "telegram_bot_quiet_hours_start": "23:00",
            "telegram_bot_quiet_hours_end": "07:00",
        }) == {"telegram_bot_notify_enabled": True}

    def test_get_settings_includes_advanced_keys(self, client, authenticated_admin):
        resp = client.get("/api/config/settings", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert "telegram_bot_token_set" in body
        for key in ("auto_backup_enabled", "webdav_url", "webdav_password", "telegram_bot_quiet_hours_enabled"):
            assert key not in body

    def test_legacy_task_settings_are_not_saved(self, client, authenticated_admin):
        resp = client.post(
            "/api/config/settings",
            json={
                "sign_interval": 45,
                "sign_task_execution_timeout": 240,
                "ai_vision_timeout": 20,
                "telegram_bot_quiet_hours_enabled": True,
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        got = client.get("/api/config/settings", headers=_auth_headers()).json()
        assert "sign_interval" not in got
        assert "sign_task_execution_timeout" not in got
        assert "ai_vision_timeout" not in got
        assert "telegram_bot_task_success_enabled" not in got
        assert "telegram_bot_quiet_hours_enabled" not in got


class TestBotTestApi:
    def test_bot_test_requires_config(self, client, authenticated_admin):
        # 清空 token/chat
        client.post(
            "/api/config/settings",
            json={"telegram_bot_token": "", "telegram_bot_chat_id": ""},
            headers=_auth_headers(),
        )
        resp = client.post("/api/config/bot/test", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert "配置" in body["message"] or "Token" in body["message"] or "token" in body["message"].lower()

    def test_bot_test_starts_background_check_without_midnight_snapshot(self, client, authenticated_admin):
        client.post(
            "/api/config/settings",
            json={
                "telegram_bot_notify_enabled": True,
                "telegram_bot_token": "123:ABC",
                "telegram_bot_chat_id": "999",
            },
            headers=_auth_headers(),
        )
        with patch(
            "backend.services.bot_test_report_jobs.start_bot_test_report_job",
            return_value={"job_id": "abc123"},
        ) as start:
            resp = client.post("/api/config/bot/test", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["job_id"] == "abc123"
        start.assert_called_once_with()

    def test_bot_test_busy_returns_failure(self, client, authenticated_admin):
        with patch(
            "backend.services.bot_test_report_jobs.start_bot_test_report_job",
            side_effect=ValueError("账户日报检测正在运行，请等待完成"),
        ):
            resp = client.post("/api/config/bot/test", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert "正在运行" in resp.json()["message"]

    def test_bot_test_job_can_be_polled(self, client, authenticated_admin):
        with patch(
            "backend.services.bot_test_report_jobs.get_bot_test_report_job",
            return_value={"status": "completed", "summary": {"checked": 2}, "error": None},
        ):
            resp = client.get("/api/config/bot/test-jobs/abc123", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["summary"]["checked"] == 2

    def test_connection_uses_saved_bot_without_account_checks(self, client, authenticated_admin):
        client.post(
            "/api/config/settings",
            json={
                "telegram_bot_notify_enabled": False,
                "telegram_bot_token": "123:ABC",
                "telegram_bot_chat_id": "999",
                "telegram_bot_message_thread_id": 7,
            },
            headers=_auth_headers(),
        )
        with patch(
            "backend.services.push_notifications.send_telegram_bot_message",
            new_callable=AsyncMock,
        ) as send, patch(
            "backend.services.bot_test_report_jobs.start_bot_test_report_job"
        ) as full_report:
            resp = client.post("/api/config/bot/test-connection", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["job_id"] is None
        send.assert_awaited_once_with(
            bot_token="123:ABC",
            chat_id="999",
            message_thread_id=7,
            text="✅ TG Manage 机器人连接测试成功",
            verify_response=True,
        )
        full_report.assert_not_called()

    def test_connection_requires_saved_credentials(self, client, authenticated_admin):
        resp = client.post("/api/config/bot/test-connection", headers=_auth_headers())
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_connection_does_not_expose_transport_errors(self, client, authenticated_admin):
        client.post(
            "/api/config/settings",
            json={"telegram_bot_token": "123:ABC", "telegram_bot_chat_id": "999"},
            headers=_auth_headers(),
        )
        with patch(
            "backend.services.push_notifications.send_telegram_bot_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("123:ABC"),
        ):
            resp = client.post("/api/config/bot/test-connection", headers=_auth_headers())
        assert resp.json()["success"] is False
        assert "123:ABC" not in resp.json()["message"]


@pytest.mark.asyncio
async def test_server_chan_channel():
    from backend.services.push_notifications import send_keyword_push

    with patch(
        "tg_manage.notification.server_chan.sc_send", new_callable=AsyncMock
    ) as m:
        m.return_value = {"code": 0}
        await send_keyword_push(
            {
                "keyword_monitor_push_channel": "server_chan",
                "keyword_monitor_server_chan_send_key": "SCT_TEST",
            },
            {"title": "hit", "body": "body"},
        )
        m.assert_awaited()


@pytest.mark.asyncio
async def test_legacy_quiet_settings_do_not_suppress_keyword_push():
    """Existing installations may still have the retired keys on disk."""
    from backend.services.push_notifications import send_keyword_push

    cfg = {
        "keyword_monitor_push_channel": "server_chan",
        "keyword_monitor_server_chan_send_key": "SCT_TEST",
        "telegram_bot_quiet_hours_enabled": True,
        "telegram_bot_quiet_hours_start": "00:00",
        "telegram_bot_quiet_hours_end": "23:59",
        "timezone": "UTC",
    }
    with patch(
        "tg_manage.notification.server_chan.sc_send", new_callable=AsyncMock
    ) as m:
        await send_keyword_push(cfg, {"title": "hit", "body": "body"})
        m.assert_awaited_once()


def test_global_settings_includes_timezone(client, authenticated_admin):
    resp = client.get("/api/config/settings", headers=_auth_headers())
    assert resp.status_code == 200
    assert resp.json().get("timezone")


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/config/export/all"),
    ("POST", "/api/config/import/all"),
    ("POST", "/api/config/import-preview"),
    ("GET", "/api/ops/backup/status"),
    ("POST", "/api/ops/backup/export"),
    ("POST", "/api/ops/backup/webdav/test"),
    ("GET", "/api/ops/backup/webdav/files"),
    ("GET", "/api/ops/backup/webdav/download"),
])
def test_retired_data_management_routes_are_gone(client, authenticated_admin, method, path):
    response = client.request(method, path, headers=_auth_headers())
    assert response.status_code in (404, 405)




