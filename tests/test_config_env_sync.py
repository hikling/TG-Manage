"""Global settings keep legacy proxy values inert and private."""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.config import ConfigService
from tg_manage.pydantic_compat import model_dump


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


def test_legacy_global_proxy_is_hidden_preserved_and_cannot_be_overridden(isolated_env: Path):
    service = ConfigService()
    path = service._get_global_settings_file()
    legacy = "socks5://legacy-user:legacy-password@proxy.example:1080"
    path.write_text(json.dumps({"global_proxy": legacy, "log_retention_days": 3}))
    assert "global_proxy" not in service.get_global_settings()
    assert "legacy-password" not in service.export_all_configs()
    assert service.save_global_settings({"log_retention_days": 14, "global_proxy": "socks5://new:1080"})
    assert service.get_global_settings()["log_retention_days"] == 14
    assert "global_proxy" not in service.get_global_settings()
    assert json.loads(path.read_text())["global_proxy"] == legacy


def test_old_export_cannot_reintroduce_global_proxy(isolated_env: Path):
    service = ConfigService()
    result = service.import_all_configs(json.dumps({"settings": {"global": {
        "global_proxy": "socks5://old:1080", "log_retention_days": 14,
    }}}))
    assert result["settings_imported"] == 1
    assert "global_proxy" not in service.get_global_settings()
    assert "global_proxy" not in json.loads(service._get_global_settings_file().read_text())


def test_settings_api_omits_retired_proxy_field():
    from backend.api.routes.config import GlobalSettingsRequest, GlobalSettingsResponse

    request = GlobalSettingsRequest(global_proxy="socks5://secret:1080", log_retention_days=14)
    assert model_dump(request, exclude_unset=True) == {"log_retention_days": 14}
    assert "global_proxy" not in model_dump(GlobalSettingsResponse(global_proxy="socks5://secret:1080"))
