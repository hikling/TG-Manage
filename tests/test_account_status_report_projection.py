"""Saved midnight outcomes stay consistent with cached account-list projections."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services import account_status_report as report
from backend.services.telegram import accounts as accounts_mod
from backend.utils import tg_session


class _Service(accounts_mod.TelegramAccountsMixin):
    def __init__(self, session_dir):
        self.session_dir = session_dir
        self._accounts_cache = None
        self._accounts_cache_ts = 0.0


class _ProbeClient:
    def __init__(self, failure):
        self.failure = failure
        self.active = 0
        self.get_chat_history = Mock(side_effect=AssertionError("history is not a status probe"))
        self.download_media = Mock(side_effect=AssertionError("avatars are not a status probe"))

    async def __aenter__(self):
        self.active += 1
        return self

    async def __aexit__(self, *_args):
        self.active -= 1

    async def get_me(self):
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(id=123, username="alpha_user")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status", "code", "report_reason", "needs_relogin"),
    [
        (ConnectionError("network unavailable"), "checking", "CONNECTION_ERROR", "连接失败", False),
        (RuntimeError("SESSION_REVOKED"), "invalid", "ACCOUNT_SESSION_INVALID", "会话失效，请重新登录", True),
    ],
)
async def test_report_failure_then_recovery_updates_saved_account_projection(
    tmp_path, monkeypatch, failure, status, code, report_reason, needs_relogin,
):
    settings = SimpleNamespace(
        resolve_session_dir=lambda: tmp_path,
        secret_key="test-projection-secret-key-0123456789",
    )
    monkeypatch.setattr(tg_session, "get_settings", lambda: settings)
    monkeypatch.setattr(accounts_mod, "is_string_session_mode", lambda: False)
    monkeypatch.setattr(accounts_mod, "get_session_mode", lambda: "file")
    (tmp_path / "alpha.session").write_bytes(b"saved-session")
    tg_session.set_account_api_credentials("alpha", 12345, "a" * 32)

    client = _ProbeClient(failure)
    build_client = Mock(return_value=client)
    monkeypatch.setattr("tg_manage.core.get_client", build_client)
    service = _Service(tmp_path)
    monkeypatch.setattr(report, "get_telegram_service", lambda: service)
    config = SimpleNamespace(get_global_settings=lambda: {
        "telegram_bot_notify_enabled": True,
        "telegram_bot_token": "test-token",
        "telegram_bot_chat_id": "123",
    })
    monkeypatch.setattr(report, "get_config_service", lambda: config)
    monkeypatch.setattr("backend.services.config.get_config_service", lambda: config)
    send = AsyncMock()
    monkeypatch.setattr(report, "send_telegram_bot_message", send)
    monkeypatch.setattr(report, "INTER_DELAY_SECONDS", 0)
    runner = report.AccountStatusReportService()

    assert service.list_accounts()[0]["status"] == "connected"
    assert await runner.run() == {"checked": 1, "ok": 0, "fail": 1, "messages_sent": 1}
    assert f"🔴 alpha — 账户异常（{report_reason}）" in send.await_args.kwargs["text"]
    # The inventory itself was cached before the probe. Reads must overlay the
    # newly persisted outcome, rather than expose its old connected status.
    assert service._accounts_cache[0]["status"] == "connected"
    projected = service.list_accounts()[0]
    saved = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))["accounts"]["alpha"]
    assert projected["status"] == saved["status"] == status
    assert projected["status_code"] == saved["status_code"] == code
    assert projected["status_message"] == saved["status_message"]
    assert projected["status_checked_at"] == saved["status_checked_at"]
    assert projected["status_checked_at"]
    assert projected["needs_relogin"] is needs_relogin
    if not needs_relogin:
        assert projected["status_message"] == report_reason
    for _ in range(5):
        assert service.list_accounts()[0] == projected
    build_client.assert_called_once()

    client.failure = None
    assert await runner.run() == {"checked": 1, "ok": 1, "fail": 0, "messages_sent": 1}
    assert "🟢 @alpha_user — 账户正常" in send.await_args.kwargs["text"]
    recovered = service.list_accounts()[0]
    saved = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))["accounts"]["alpha"]
    assert recovered["status"] == saved["status"] == "connected"
    assert recovered["status_code"] == saved["status_code"] == "OK"
    assert recovered["status_message"] == saved["status_message"] == ""
    assert recovered["needs_relogin"] is False
    assert recovered["status_checked_at"] == saved["status_checked_at"]
    assert build_client.call_count == 2
    assert client.active == 0
    client.get_chat_history.assert_not_called()
    client.download_media.assert_not_called()
