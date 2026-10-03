"""面板全局设置 → 环境变量回灌测试。

覆盖场景：
- 保存时同步到 env（原有行为）
- 进程重启后从持久化设置重新回灌（新增：修复重启后 AI_VISION_* 等静默回退）
- 无效值跳过、空值不清除已有 env
"""

from __future__ import annotations

from pathlib import Path

from backend.services.config import ConfigService
from backend.services.config_mixins import apply_global_settings_to_env


class TestApplyGlobalSettingsToEnv:
    def test_task_settings_sync_without_retired_ai_values(self, isolated_env: Path, monkeypatch):
        import os

        monkeypatch.delenv("SIGN_TASK_EXECUTION_TIMEOUT", raising=False)
        monkeypatch.delenv("AI_VISION_TIMEOUT", raising=False)
        apply_global_settings_to_env({
            "sign_task_execution_timeout": 300,
            "ai_vision_timeout": 30,
        })
        assert os.environ["SIGN_TASK_EXECUTION_TIMEOUT"] == "300"
        assert "AI_VISION_TIMEOUT" not in os.environ

    def test_restart_restores_task_settings_only(self, isolated_env: Path, monkeypatch):
        import os

        service = ConfigService()
        service.save_global_settings({"sign_task_execution_timeout": 300})
        monkeypatch.delenv("SIGN_TASK_EXECUTION_TIMEOUT", raising=False)
        apply_global_settings_to_env(service.get_global_settings())
        assert os.environ["SIGN_TASK_EXECUTION_TIMEOUT"] == "300"


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
