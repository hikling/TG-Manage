"""Subscription status counts survive FastAPI response-model serialization."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes.config import router
from backend.core.auth import get_current_user


class _RouteService:
    async def get_subscription_settings(self):
        return {
            "primary": {
                "configured": True,
                "status": "ready",
                "imported_count": 4,
                "usable_count": 2,
                "unsupported_count": 3,
            },
            "fallback": {
                "configured": False,
                "imported_count": 0,
                "usable_count": 0,
                "unsupported_count": 0,
            },
            "latency_threshold_ms": 800,
            "route_mode": "primary",
        }

    async def update_subscription_settings(self, _changes):
        return None

    async def refresh_subscriptions(self):
        return set()


def test_subscription_counts_survive_get_put_and_refresh_response_models():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: object()
    with patch("backend.services.account_routes.get_route_service", return_value=_RouteService()):
        with TestClient(app) as client:
            responses = (
                client.get("/settings/proxy-subscriptions"),
                client.put("/settings/proxy-subscriptions", json={}),
                client.post("/settings/proxy-subscriptions/refresh"),
            )
    for response in responses:
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["primary"]["imported_count"] == 4
        assert body["primary"]["usable_count"] == 2
        assert body["primary"]["unsupported_count"] == 3
        assert body["fallback"]["imported_count"] == 0
