from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from knobridge import __version__
from knobridge.api import health
from knobridge.api.app import create_app
from knobridge.core.settings import Settings


def test_health_live_returns_ok(client: TestClient) -> None:
    response = client.get("/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_health_ready_returns_503_when_database_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing_ping(_engine: AsyncEngine) -> None:
        raise OSError("connection refused by db-secret-host")

    monkeypatch.setattr(health, "ping", failing_ping)

    response = client.get("/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Service is not ready.",
            "details": {"checks": {"database": "error"}},
        }
    }
    assert "db-secret-host" not in response.text


@pytest.mark.integration
def test_health_ready_returns_ok_with_database(settings: Settings, postgres_url: str) -> None:
    app = create_app(settings.model_copy(update={"database_url": SecretStr(postgres_url)}))

    with TestClient(app) as client:
        response = client.get("/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}
