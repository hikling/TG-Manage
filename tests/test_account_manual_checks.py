"""Manual account resource checks stay scoped to the requested account."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.services import account_manual_checks as checks


@pytest.mark.asyncio
async def test_inspection_reads_only_selected_account(monkeypatch):
    exit_check = AsyncMock(return_value={"route_mode": "primary", "exit_ip": "8.8.8.8"})
    telebox_status = Mock(return_value={
        "account": "alice", "status": "running", "enabled": True,
        "authorized": True, "message": "",
    })
    monkeypatch.setattr(checks, "refresh_account_exit", exit_check)
    monkeypatch.setattr(checks, "get_telebox_service", lambda: SimpleNamespace(status=telebox_status))

    result = await checks.inspect_account_resources("alice")

    exit_check.assert_awaited_once_with("alice", fresh_after=None)
    telebox_status.assert_called_once_with("alice")
    assert result["telebox"]["status"] == "running"
    assert result["exit_ip"] == "8.8.8.8"
