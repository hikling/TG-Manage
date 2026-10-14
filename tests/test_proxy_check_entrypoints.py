"""The proxy health service has two product triggers, never an idle trigger."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.api.routes import accounts as routes
from backend.api.routes.accounts_schemas import AccountStatusCheckRequest
from backend.services import account_proxy_status


def test_dedicated_probe_is_only_imported_by_explicit_status_owners():
    # Guard this expensive side-effect boundary: adding it to client creation,
    # login, listing or keepalive would turn routine use into forbidden probes.
    root = Path(__file__).resolve().parents[1]
    owners = set()
    for path in (root / "backend").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "backend.services.account_proxy_status":
                if any(alias.name == "check_account_proxy" for alias in node.names):
                    owners.add(path.relative_to(root).as_posix())
    assert owners == {
        "backend/api/routes/accounts.py", "backend/services/account_status_jobs.py",
        "backend/services/account_status_report.py",
    }


@pytest.mark.asyncio
async def test_manual_card_check_projects_independent_proxy_result(monkeypatch):
    service = SimpleNamespace(
        list_accounts=lambda: [{"name": "one"}, {"name": "unselected"}],
        check_account_status=AsyncMock(return_value={"account_name": "one", "ok": True, "status": "connected"}),
    )
    probe = AsyncMock(return_value={"proxy_status": "error", "proxy_status_code": "PROXY_TIMEOUT", "proxy_checked_at": "2026-10-14T00:00:00Z"})
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    monkeypatch.setattr(account_proxy_status, "check_account_proxy", probe)
    response = await routes.check_accounts_status(AccountStatusCheckRequest(account_names=["one"]), current_user=None)
    probe.assert_awaited_once_with("one", timeout_seconds=6.0)
    assert response.results[0].ok is True
    assert response.results[0].proxy_status == "error"
    assert response.results[0].proxy_status_code == "PROXY_TIMEOUT"
    assert response.results[0].proxy_checked_at == "2026-10-14T00:00:00Z"


@pytest.mark.asyncio
async def test_manual_check_still_checks_proxy_when_account_probe_raises(monkeypatch):
    service = SimpleNamespace(list_accounts=lambda: [{"name": "one"}], check_account_status=AsyncMock(side_effect=RuntimeError("failed")))
    probe = AsyncMock(return_value={"proxy_status": "healthy", "proxy_status_code": "PROXY_OK"})
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    monkeypatch.setattr(account_proxy_status, "check_account_proxy", probe)
    response = await routes.check_accounts_status(AccountStatusCheckRequest(account_names=["one"]), current_user=None)
    assert response.results[0].ok is False
    assert response.results[0].proxy_status == "healthy"
    probe.assert_awaited_once()


@pytest.mark.asyncio
async def test_manual_gate_rejects_duplicate_before_proxy_network(monkeypatch):
    from fastapi import HTTPException

    from backend.services.account_check_gate import account_check_gate

    service = SimpleNamespace(list_accounts=lambda: [{"name": "one"}], check_account_status=AsyncMock())
    probe = AsyncMock()
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    monkeypatch.setattr(account_proxy_status, "check_account_proxy", probe)
    held = account_check_gate.reserve(["one"])
    try:
        with pytest.raises(HTTPException) as exc:
            await routes.check_accounts_status(AccountStatusCheckRequest(account_names=["one"]), current_user=None)
        assert exc.value.status_code == 429
        probe.assert_not_awaited()
        service.check_account_status.assert_not_awaited()
    finally:
        held.release()


@pytest.mark.asyncio
async def test_manual_status_unexpected_error_log_hides_proxy_credentials(monkeypatch, caplog):
    from fastapi import HTTPException

    secret = "socks5://user:SECRET@proxy.example:1080"
    service = SimpleNamespace(list_accounts=lambda: (_ for _ in ()).throw(RuntimeError(secret)))
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    with pytest.raises(HTTPException) as exc:
        await routes.check_accounts_status(AccountStatusCheckRequest(), current_user=None)
    assert exc.value.status_code == 500
    assert "SECRET" not in caplog.text + str(exc.value.detail)
