"""Global settings: retired fields and proxy lookup."""

from __future__ import annotations

from pathlib import Path

from backend.services.config import ConfigService


def test_retired_settings_are_dropped_on_save_and_load(isolated_env: Path):
    service = ConfigService()
    path = service._get_global_settings_file()
    path.write_text('{"sign_interval": 45, "ai_vision_timeout": 30, "log_retention_days": 3}')
    assert service.get_global_settings()["log_retention_days"] == 3
    assert "sign_interval" not in service.get_global_settings()
    assert "ai_vision_timeout" not in service.get_global_settings()
    assert service.save_global_settings({"sign_task_execution_timeout": 300,
                                         "telegram_bot_task_success_enabled": True})
    assert "sign_task_execution_timeout" not in service.get_global_settings()
    assert "telegram_bot_task_success_enabled" not in service.get_global_settings()


class TestGetGlobalProxy:
    """ConfigService.get_global_proxy() 统一入口测试。"""

    def test_returns_none_when_unset(self, isolated_env: Path):
        service = ConfigService()
        assert service.get_global_proxy() is None

    def test_returns_saved_proxy(self, isolated_env: Path):
        service = ConfigService()
        service.save_global_settings({"global_proxy": "socks5://127.0.0.1:1080"})
        assert service.get_global_proxy() == "socks5://127.0.0.1:1080"

    def test_matches_global_settings_value(self, isolated_env: Path):
        service = ConfigService()
        service.save_global_settings({"global_proxy": "http://u:p@h:8080"})
        assert service.get_global_proxy() == service.get_global_settings()["global_proxy"]
