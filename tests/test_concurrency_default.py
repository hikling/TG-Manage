"""全局并发默认值测试 — 覆盖 tg_session.py 的 _resolve_concurrency_limit"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestResolveConcurrencyLimit:
    """_resolve_concurrency_limit 应正确处理优先级和默认值"""

    def test_env_var_takes_priority(self):
        """未在面板指定时使用环境变量。"""
        from backend.utils.tg_session import _resolve_concurrency_limit

        service = MagicMock()
        service.get_global_settings.return_value = {"tg_global_concurrency": None}
        with patch.dict(os.environ, {"TG_GLOBAL_CONCURRENCY": "10"}), \
             patch("backend.services.config.get_config_service", return_value=service):
            assert _resolve_concurrency_limit() == 10

    def test_explicit_setting_overrides_compose_default(self):
        from backend.utils.tg_session import _resolve_concurrency_limit

        service = MagicMock()
        service.get_global_settings.return_value = {"tg_global_concurrency": 3}
        with patch.dict(os.environ, {"TG_GLOBAL_CONCURRENCY": "2"}), \
             patch("backend.services.config.get_config_service", return_value=service):
            assert _resolve_concurrency_limit() == 3

    def test_env_var_invalid_falls_through(self):
        """环境变量无效值应降级到下一级"""
        from backend.utils.tg_session import _resolve_concurrency_limit

        with patch.dict(os.environ, {"TG_GLOBAL_CONCURRENCY": "abc"}):
            result = _resolve_concurrency_limit()
            assert isinstance(result, int)
            assert result >= 1

    def test_env_var_zero_clamped_to_one(self):
        """环境变量 0 应被钳制为 1"""
        from backend.utils.tg_session import _resolve_concurrency_limit

        with patch.dict(os.environ, {"TG_GLOBAL_CONCURRENCY": "0"}):
            assert _resolve_concurrency_limit() == 1

    def test_dynamic_default_respects_container_cpu(self):
        """无环境变量或保存配置时按容器 CPU 配额限制默认并发。"""
        from backend.utils.tg_session import _resolve_concurrency_limit

        mock_service = MagicMock()
        mock_service.get_global_settings.return_value = {}
        with patch.dict(os.environ, {}, clear=False), \
             patch("backend.utils.tg_session.os.getenv", side_effect=lambda k, *a: os.environ.get(k, "")), \
             patch("backend.utils.tg_session._effective_cpu_count", return_value=2), \
             patch("backend.services.config.get_config_service", return_value=mock_service):
            result = _resolve_concurrency_limit()
            assert result == 2

    def test_cgroup_v2_quota_caps_host_cpu_count(self):
        from backend.utils.tg_session import _effective_cpu_count

        with patch("backend.utils.tg_session.os.cpu_count", return_value=32), \
             patch("backend.utils.tg_session.os.sched_getaffinity", return_value=set(range(32))), \
             patch("backend.utils.tg_session.Path.read_text", return_value="200000 100000"):
            assert _effective_cpu_count() == 2

    def test_result_is_at_least_one(self):
        """任何情况下返回值应 >= 1"""
        from backend.utils.tg_session import _resolve_concurrency_limit

        result = _resolve_concurrency_limit()
        assert result >= 1


class TestUpdateGlobalSemaphore:
    """update_global_semaphore 应能运行时更新信号量"""

    def test_update_changes_semaphore_limit(self):
        """更新后信号量应使用新值"""
        from backend.utils.tg_session import (
            get_global_semaphore,
            update_global_semaphore,
        )

        original = get_global_semaphore()
        original_limit = original._value

        update_global_semaphore(20)
        updated = get_global_semaphore()
        assert updated._value == 20

        # 恢复
        update_global_semaphore(original_limit)
