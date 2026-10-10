from __future__ import annotations

from fastapi.testclient import TestClient

from knobridge import __version__


def test_health_live_returns_ok(client: TestClient) -> None:
    response = client.get("/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
