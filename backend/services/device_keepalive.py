from __future__ import annotations

import json
from typing import Any, Dict

from backend.core.config import get_settings
from backend.utils.atomic_io import write_json_atomic


class DeviceKeepaliveService:
    """Clean up legacy keepalive state when accounts are deleted or reconciled."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.workdir = self.settings.resolve_workdir()
        self.state_file = self.workdir / ".device_keepalive_state.json"

    def _load_state_for_cleanup(self) -> Dict[str, Any]:
        """Never overwrite an unreadable state file while pruning accounts."""
        if self.state_file.is_symlink():
            raise ValueError("设备保活状态文件不能是链接")
        if not self.state_file.exists():
            return {"accounts": {}}
        if self.state_file.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("设备保活状态文件过大")
        data = json.loads(self.state_file.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), dict):
            raise ValueError("设备保活状态文件格式错误")
        return data

    def _save_state_for_cleanup(self, state: Dict[str, Any]) -> None:
        write_json_atomic(self.state_file, state)

    def remove_account_state(self, account_name: str) -> bool:
        """Remove only the deleted account's keepalive history."""
        state = self._load_state_for_cleanup()
        removed = state["accounts"].pop(account_name, None) is not None
        if removed:
            self._save_state_for_cleanup(state)
        return removed

    def prune_account_state(
        self, live_names: set[str], *, account_exists=None,
    ) -> int:
        """Prune stale history using a verified durable account inventory."""
        state = self._load_state_for_cleanup()
        accounts = state["accounts"]
        stale = []
        for name in accounts:
            if name in live_names:
                continue
            try:
                if account_exists and account_exists(name):
                    continue
            except (TypeError, ValueError):
                pass  # Malformed historical keys are never live account names.
            stale.append(name)
        for name in stale:
            accounts.pop(name, None)
        if stale:
            self._save_state_for_cleanup(state)
        return len(stale)

_device_keepalive_service: DeviceKeepaliveService | None = None


def get_device_keepalive_service() -> DeviceKeepaliveService:
    """获取设备保活服务单例。"""
    global _device_keepalive_service
    if _device_keepalive_service is None:
        _device_keepalive_service = DeviceKeepaliveService()
    return _device_keepalive_service
