"""Account reads project route state without triggering a node probe."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.api.routes import accounts as routes
from backend.api.routes.accounts_schemas import AccountStatusCheckRequest


def test_old_manual_proxy_probe_has_no_runtime_callers():
    root = Path(__file__).resolve().parents[1]
    owners = set()
    for path in (root / "backend").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "backend.services.account_proxy_status":
                if any(alias.name == "check_account_proxy" for alias in node.names):
                    owners.add(path.relative_to(root).as_posix())
    assert owners == set()


@pytest.mark.asyncio
async def test_manual_card_check_projects_route_without_probing(monkeypatch):
    service = SimpleNamespace(
        list_accounts=lambda: [{"name": "one"}],
        check_account_status=AsyncMock(return_value={"account_name": "one", "ok": True, "status": "connected"}),
    )
    route = Mock(return_value={
        "route_mode": "fallback", "route_status": "healthy",
        "exit_ip": "198.51.100.42", "exit_country": "US",
    })
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    from backend.services import account_routes
    monkeypatch.setattr(account_routes, "account_route_status", route)
    response = await routes.check_accounts_status(
        AccountStatusCheckRequest(account_names=["one"]), current_user=None,
    )
    assert response.results[0].ok is True
    assert response.results[0].route_mode == "fallback"
    assert response.results[0].exit_ip == "198.51.100.42"
    route.assert_called_once_with("one")


@pytest.mark.asyncio
async def test_manual_check_projects_route_after_account_failure(monkeypatch):
    service = SimpleNamespace(
        list_accounts=lambda: [{"name": "one"}],
        check_account_status=AsyncMock(side_effect=RuntimeError("failed")),
    )
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    from backend.services import account_routes
    monkeypatch.setattr(account_routes, "account_route_status", lambda _: {
        "route_mode": "primary", "route_status": "healthy",
    })
    response = await routes.check_accounts_status(
        AccountStatusCheckRequest(account_names=["one"]), current_user=None,
    )
    assert response.results[0].ok is False
    assert response.results[0].route_mode == "primary"


@pytest.mark.asyncio
async def test_manual_gate_rejects_duplicate_before_route_read(monkeypatch):
    from fastapi import HTTPException

    from backend.services import account_routes
    from backend.services.account_check_gate import account_check_gate

    service = SimpleNamespace(list_accounts=lambda: [{"name": "one"}], check_account_status=AsyncMock())
    route = Mock()
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    monkeypatch.setattr(account_routes, "account_route_status", route)
    held = account_check_gate.reserve(["one"])
    try:
        with pytest.raises(HTTPException) as error:
            await routes.check_accounts_status(
                AccountStatusCheckRequest(account_names=["one"]), current_user=None,
            )
        assert error.value.status_code == 429
        route.assert_not_called()
        service.check_account_status.assert_not_awaited()
    finally:
        held.release()


@pytest.mark.asyncio
async def test_manual_status_error_hides_subscription_credentials(monkeypatch, caplog):
    from fastapi import HTTPException

    secret = "https://user:SECRET@subscription.example/list"
    service = SimpleNamespace(list_accounts=lambda: (_ for _ in ()).throw(RuntimeError(secret)))
    monkeypatch.setattr(routes, "get_telegram_service", lambda: service)
    with pytest.raises(HTTPException) as error:
        await routes.check_accounts_status(AccountStatusCheckRequest(), current_user=None)
    assert error.value.status_code == 500
    assert "SECRET" not in caplog.text + str(error.value.detail)
