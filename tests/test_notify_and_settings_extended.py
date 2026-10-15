"""扩展设置、Bot 测试与静默时段测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.core.auth import create_access_token
from backend.services.push_notifications import is_in_quiet_hours


def _auth_headers() -> dict:
    token = create_access_token(
        {"sub": "admin"},
        expires_delta=timedelta(hours=1),
    )
    return {"Authorization": f"Bearer {token}"}


class TestAdvancedSettingsApi:
    def test_get_settings_includes_advanced_keys(self, client, authenticated_admin):
        resp = client.get("/api/config/settings", headers=_auth_headers())
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "telegram_bot_quiet_hours_enabled",
            "telegram_bot_quiet_hours_start",
            "telegram_bot_quiet_hours_end",
            "telegram_bot_token_set",
        ):
            assert key in body, f"missing key {key}"
        for key in ("auto_backup_enabled", "webdav_url", "webdav_password"):
            assert key not in body

    def test_legacy_task_settings_are_not_saved(self, client, authenticated_admin):
        resp = client.post(
            "/api/config/settings",
            json={
                "sign_interval": 45,
                "sign_task_execution_timeout": 240,
                "ai_vision_timeout": 20,
            },
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        got = client.get("/api/config/settings", headers=_auth_headers()).json()
        assert "sign_interval" not in got
        assert "sign_task_execution_timeout" not in got
        assert "ai_vision_timeout" not in got
        assert "telegram_bot_task_success_enabled" not in got


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


class TestQuietHours:
    @pytest.mark.parametrize(
        ("start", "end", "current"),
        [
            ("24:00", "07:00", datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))),
            ("23:60", "07:00", datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))),
            ("23:00", "07:60", datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))),
            ("23:00", "24:00", datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))),
            ("-1:00", "07:00", datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))),
            ("23:00:99", "07:00", datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))),
            ("23:00:anything", "07:00", datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))),
            ("23:", "07:00", datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))),
            ("23:00", "07", datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))),
        ],
    )
    def test_invalid_clock_values_fall_back_to_not_quiet(self, start, end, current):
        cfg = {
            "telegram_bot_quiet_hours_enabled": True,
            "telegram_bot_quiet_hours_start": start,
            "telegram_bot_quiet_hours_end": end,
            "timezone": "UTC",
        }
        assert not is_in_quiet_hours(cfg, current)

    def test_quiet_hours_overnight(self):
        cfg = {
            "telegram_bot_quiet_hours_enabled": True,
            "telegram_bot_quiet_hours_start": "23:00",
            "telegram_bot_quiet_hours_end": "07:00",
            "timezone": "UTC",
        }
        assert is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))
        )
        assert is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 6, 0, tzinfo=ZoneInfo("UTC"))
        )
        assert not is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 12, 0, tzinfo=ZoneInfo("UTC"))
        )

    def test_quiet_hours_disabled(self):
        cfg = {"telegram_bot_quiet_hours_enabled": False}
        assert not is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 23, 30, tzinfo=ZoneInfo("UTC"))
        )

    def test_quiet_hours_same_day_window(self):
        cfg = {
            "telegram_bot_quiet_hours_enabled": True,
            "telegram_bot_quiet_hours_start": "12:00",
            "telegram_bot_quiet_hours_end": "14:00",
            "timezone": "UTC",
        }
        assert is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 13, 0, tzinfo=ZoneInfo("UTC"))
        )
        assert not is_in_quiet_hours(
            cfg, datetime(2026, 7, 18, 11, 0, tzinfo=ZoneInfo("UTC"))
        )


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
async def test_keyword_push_respects_quiet_hours():
    """关键词命中推送与其余通知一致：静默时段内跳过，不触发任何通道。"""
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
        m.assert_not_awaited()


@pytest.mark.asyncio
async def test_keyword_push_outside_quiet_hours():
    """静默时段外关键词推送正常发送；窗口内跳过（注入判定结果，避免依赖运行时刻）。"""
    from backend.services.push_notifications import send_keyword_push

    cfg = {
        "keyword_monitor_push_channel": "server_chan",
        "keyword_monitor_server_chan_send_key": "SCT_TEST",
        "telegram_bot_quiet_hours_enabled": True,
        "telegram_bot_quiet_hours_start": "00:00",
        "telegram_bot_quiet_hours_end": "12:00",
        "timezone": "UTC",
    }
    # 窗口外：静默判定返回 False，推送应发送
    with patch(
        "backend.services.push_notifications.is_in_quiet_hours",
        return_value=False,
    ), patch(
        "tg_manage.notification.server_chan.sc_send", new_callable=AsyncMock
    ) as m:
        m.return_value = {"code": 0}
        await send_keyword_push(cfg, {"title": "hit", "body": "body"})
        m.assert_awaited()

    # 窗口内：静默判定返回 True，推送应跳过
    with patch(
        "backend.services.push_notifications.is_in_quiet_hours",
        return_value=True,
    ), patch(
        "tg_manage.notification.server_chan.sc_send", new_callable=AsyncMock
    ) as m:
        await send_keyword_push(cfg, {"title": "hit", "body": "body"})
        m.assert_not_awaited()


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




