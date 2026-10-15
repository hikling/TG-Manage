"""Legacy keepalive state remains safe to clean after manual execution is retired."""

from __future__ import annotations

import json

import pytest

from backend.core import config as config_module
from backend.services.device_keepalive import DeviceKeepaliveService


@pytest.fixture()
def keepalive(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", str(tmp_path / "data"))
    config_module.get_settings.cache_clear()
    service = DeviceKeepaliveService()
    yield service
    config_module.get_settings.cache_clear()


def test_deleted_account_state_is_removed_without_touching_other_accounts(keepalive):
    keepalive._save_state_for_cleanup({
        "accounts": {"old": {"last_ok_at": "x"}, "live": {"last_ok_at": "y"}},
    })

    assert keepalive.remove_account_state("old") is True
    assert keepalive.prune_account_state({"live"}, account_exists=lambda _name: False) == 0
    assert keepalive._load_state_for_cleanup()["accounts"] == {"live": {"last_ok_at": "y"}}


def test_orphan_cleanup_preserves_names_that_still_exist(keepalive):
    keepalive._save_state_for_cleanup({
        "accounts": {"removed": {}, "live": {}, "restored": {}},
    })

    assert keepalive.prune_account_state(
        {"live"}, account_exists=lambda name: name == "restored",
    ) == 1
    assert set(keepalive._load_state_for_cleanup()["accounts"]) == {"live", "restored"}


def test_corrupt_keepalive_state_is_not_overwritten_during_cleanup(keepalive):
    keepalive.state_file.parent.mkdir(parents=True, exist_ok=True)
    keepalive.state_file.write_text("{broken", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        keepalive.prune_account_state(set())

    assert keepalive.state_file.read_text(encoding="utf-8") == "{broken"
