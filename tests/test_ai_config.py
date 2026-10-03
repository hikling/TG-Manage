"""Retired global AI configuration remains inert during portable import/export."""

from __future__ import annotations

import json
from pathlib import Path

from backend.services.config import ConfigService


def test_export_omits_retired_ai_config(isolated_env: Path):
    service = ConfigService()
    old_config = service.workdir / ".openai_config.json"
    old_config.write_text(json.dumps({"api_key": "old-secret", "model": "old-model"}))

    exported = json.loads(service.export_all_configs())
    assert "ai" not in exported["settings"]
    assert "old-secret" not in json.dumps(exported)
    assert "sessions" in exported["_meta"]["excludes"]


def test_import_skips_retired_ai_config_without_changing_old_file(isolated_env: Path):
    service = ConfigService()
    old_config = service.workdir / ".openai_config.json"
    original = '{"model": "previous", "api_key": "old-secret"}'
    old_config.write_text(original)
    payload = {"settings": {"ai": {"model": "new", "api_key": "new-secret"}}}

    result = service.import_all_configs(json.dumps(payload), overwrite=True)
    assert result["settings_skipped"] >= 1
    assert any("retired ai" in warning.lower() for warning in result["warnings"])
    assert old_config.read_text() == original


def test_import_rejects_non_object_root(isolated_env: Path):
    result = ConfigService().import_all_configs(json.dumps([1, 2, 3]), overwrite=True)
    assert any("根节点" in error for error in result["errors"])


def test_import_records_invalid_signs_type(isolated_env: Path):
    result = ConfigService().import_all_configs(
        json.dumps({"signs": "not-a-dict", "monitors": {}}), overwrite=True
    )
    assert any("signs" in error for error in result["errors"])


def test_portable_import_never_recreates_retired_tasks(isolated_env: Path):
    service = ConfigService()
    payload = {"signs": {"old": {"name": "old", "actions": [{"action": 1}]}},
               "monitors": {"watch": {"keyword": "old"}}, "settings": {}}
    result = service.import_all_configs(json.dumps(payload), overwrite=True)
    assert result["signs_imported"] == result["monitors_imported"] == 0
    assert result["signs_skipped"] == result["monitors_skipped"] == 1
    assert not (service.workdir / "signs").exists()
    assert not (service.workdir / "monitors").exists()
    assert "signs" not in json.loads(service.export_all_configs())


def test_preview_rejects_non_object(isolated_env: Path):
    preview = ConfigService().preview_import_all(json.dumps("x"))
    assert preview["errors"]
