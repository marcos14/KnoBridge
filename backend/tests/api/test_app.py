from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from knobridge import __version__
from knobridge.api import app as app_module
from knobridge.api.app import create_app, serve
from knobridge.core.settings import Settings


def test_create_app_exposes_title_and_version_in_openapi(client: TestClient) -> None:
    response = client.get("/openapi.json")

    info = response.json()["info"]
    assert info == {"title": "KnoBridge API", "version": __version__}


def test_create_app_mounts_routers_under_v1(app: FastAPI) -> None:
    paths = app.openapi()["paths"]

    assert "/v1/health/live" in paths
    assert all(path.startswith("/v1/") for path in paths)


def test_create_app_allows_configured_cors_origin(client: TestClient) -> None:
    response = client.get("/v1/health/live", headers={"Origin": "http://test"})

    assert response.headers["access-control-allow-origin"] == "http://test"


def test_create_app_rejects_unconfigured_cors_origin(client: TestClient) -> None:
    response = client.get("/v1/health/live", headers={"Origin": "http://evil"})

    assert "access-control-allow-origin" not in response.headers


def test_create_app_uses_cached_settings_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_CORS_ORIGINS", '["http://from-env"]')

    with TestClient(create_app()) as client:
        response = client.get("/v1/health/live", headers={"Origin": "http://from-env"})

    assert response.headers["access-control-allow-origin"] == "http://from-env"


def test_serve_runs_uvicorn_on_configured_address(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, str, int]] = []

    def fake_run(app: object, *, host: str, port: int, log_config: object) -> None:
        calls.append((app, host, port))

    monkeypatch.setattr(app_module.uvicorn, "run", fake_run)

    serve(Settings(api_host="0.0.0.0", api_port=8123))  # noqa: S104

    [(served_app, host, port)] = calls
    assert isinstance(served_app, FastAPI)
    assert (host, port) == ("0.0.0.0", 8123)  # noqa: S104


def test_serve_uses_cached_settings_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ports: list[int] = []
    monkeypatch.setenv("KNOBRIDGE_API_PORT", "8999")

    def fake_run(app: object, *, host: str, port: int, log_config: object) -> None:
        ports.append(port)

    monkeypatch.setattr(app_module.uvicorn, "run", fake_run)

    serve()

    assert ports == [8999]
