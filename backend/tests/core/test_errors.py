from __future__ import annotations

import io
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from knobridge.core.errors import (
    ConflictError,
    KnoBridgeError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
    register_error_handlers,
)
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/not-found")
    async def not_found() -> None:
        raise NotFoundError("Source not found.", details={"source_id": "s-1"})

    @app.get("/custom")
    async def custom() -> None:
        raise KnoBridgeError("Quota exceeded.", code="quota_exceeded", status_code=429)

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    @app.get("/http")
    async def http() -> None:
        raise HTTPException(status_code=401, detail="Missing token.", headers={"X-Auth": "1"})

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=599, detail="Odd status.")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
def error_client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_error_handler_returns_standard_shape(error_client: TestClient) -> None:
    response = error_client.get("/not-found")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Source not found.",
            "details": {"source_id": "s-1"},
        }
    }


def test_error_handler_honors_code_and_status_overrides(error_client: TestClient) -> None:
    response = error_client.get("/custom")

    assert response.status_code == 429
    assert response.json()["error"] == {
        "code": "quota_exceeded",
        "message": "Quota exceeded.",
        "details": None,
    }


@pytest.mark.parametrize(
    ("error", "code", "status_code"),
    [
        (KnoBridgeError("x"), "error", 400),
        (NotFoundError("x"), "not_found", 404),
        (ValidationError("x"), "validation_error", 422),
        (ConflictError("x"), "conflict", 409),
        (ServiceUnavailableError("x"), "service_unavailable", 503),
    ],
)
def test_domain_errors_have_default_code_and_status(
    error: KnoBridgeError, code: str, status_code: int
) -> None:
    assert (error.code, error.status_code, error.message) == (code, status_code, "x")


def test_request_validation_returns_422_standard_shape(error_client: TestClient) -> None:
    response = error_client.get("/items/abc")

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["loc"] == ["path", "item_id"]


def test_unknown_route_returns_404_standard_shape(error_client: TestClient) -> None:
    response = error_client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": None}
    }


def test_http_exception_keeps_status_and_headers(error_client: TestClient) -> None:
    response = error_client.get("/http")

    assert response.status_code == 401
    assert response.headers["X-Auth"] == "1"
    assert response.json()["error"] == {
        "code": "unauthorized",
        "message": "Missing token.",
        "details": None,
    }


def test_http_exception_with_unknown_status_uses_generic_code(error_client: TestClient) -> None:
    response = error_client.get("/teapot")

    assert response.status_code == 599
    assert response.json()["error"]["code"] == "http_error"


def test_unhandled_error_returns_500_standard_shape(error_client: TestClient) -> None:
    response = error_client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "An unexpected error occurred.",
            "details": None,
        }
    }


def test_unhandled_error_is_logged_with_stack(error_client: TestClient, settings: Settings) -> None:
    stream = io.StringIO()
    configure_logging(settings, stream=stream)

    error_client.get("/boom")

    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    [record] = [r for r in records if r["event"] == "unhandled_error"]
    assert record["path"] == "/boom"
    assert record["level"] == "error"
    assert "secret internal detail" in record["exception"]
