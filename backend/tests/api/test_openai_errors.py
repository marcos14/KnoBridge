"""Errors of the OpenAI-compatible routes without a database: the classification of KnoBridge
codes, validation errors as 400 and ``OpenAIRoute`` converting everything a route raises."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from knobridge.api.openai_errors import (
    OpenAIError,
    OpenAIRoute,
    classify,
    from_domain_error,
    from_validation_error,
)
from knobridge.apikeys.auth import invalid_api_key
from knobridge.core.errors import ForbiddenError, NotFoundError, ValidationError


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        ("provider_rate_limited", 429, (429, "rate_limit_error")),
        ("provider_unavailable", 503, (503, "api_error")),
        ("chat_failed", 500, (500, "api_error")),
        ("provider_auth_failed", 502, (502, "api_error")),
        ("provider_request_failed", 502, (502, "api_error")),
        ("provider_embeddings_unsupported", 422, (502, "api_error")),
        ("embedding_dimension_mismatch", 502, (502, "api_error")),
        ("workspace_suspended", 403, (403, "permission_error")),
        ("assistant_inactive", 409, (409, "invalid_request_error")),
        ("internal", 500, (500, "api_error")),
    ],
)
def test_classify_status_and_type(code: str, status: int, expected: tuple[int, str]) -> None:
    error = classify(code, status, "Provider said: sk-secret")

    assert (error.status, error.type, error.code) == (*expected, code)


def test_classify_never_repeats_the_provider_text() -> None:
    for code in ("provider_rate_limited", "provider_request_failed", "embedding_x", "chat_failed"):
        assert "sk-secret" not in classify(code, 502, "Provider said: sk-secret").message


def test_model_not_found_points_at_model() -> None:
    error = from_domain_error(
        NotFoundError("The model 'x' does not exist.", code="model_not_found")
    )

    assert error.body() == {
        "error": {
            "message": "The model 'x' does not exist.",
            "type": "invalid_request_error",
            "param": "model",
            "code": "model_not_found",
        }
    }


def test_invalid_api_key_keeps_www_authenticate() -> None:
    error = from_domain_error(invalid_api_key())

    assert (error.status, error.type, error.code) == (
        401,
        "invalid_request_error",
        "invalid_api_key",
    )
    assert error.headers == {"WWW-Authenticate": "Bearer"}
    assert from_domain_error(ForbiddenError("x", code="workspace_suspended")).headers is None


@pytest.mark.parametrize(
    ("errors", "expected"),
    [
        ([{"type": "json_invalid", "loc": ("body", 1)}], (None, "The body is not valid JSON.")),
        ([{"type": "missing", "loc": ("body", "messages", 0, "role")}], ("messages.0.role", None)),
        ([{"type": "missing", "loc": ("body",)}], (None, "The request body is invalid.")),
        ([{"type": "missing", "loc": ("query", "x")}], ("query.x", None)),
        ([], (None, "The request body is invalid.")),
    ],
)
def test_validation_errors_become_400(
    errors: list[dict[str, object]], expected: tuple[str | None, str | None]
) -> None:
    error = from_validation_error(RequestValidationError(errors))

    param, message = expected
    assert (error.status, error.type, error.code, error.param) == (
        400,
        "invalid_request_error",
        "invalid_request",
        param,
    )
    if message is not None:
        assert error.message == message


class _Body(BaseModel):
    count: int


def _client() -> TestClient:
    router = APIRouter(route_class=OpenAIRoute)

    def failing_dependency() -> None:
        raise ValidationError("Bad.", code="something")

    @router.post("/body")
    async def body(payload: _Body) -> dict[str, int]:
        return {"count": payload.count}

    @router.get("/dependency", dependencies=[Depends(failing_dependency)])
    async def dependency() -> None:
        return None

    @router.get("/crash")
    async def crash() -> None:
        raise RuntimeError("boom with sk-secret")

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_openai_route_converts_every_error() -> None:
    client = _client()

    ok = client.post("/body", json={"count": 1})
    invalid = client.post("/body", json={"count": "x"})
    broken = client.post("/body", content=b"{", headers={"content-type": "application/json"})
    domain = client.get("/dependency")
    crashed = client.get("/crash")

    assert ok.json() == {"count": 1}
    assert invalid.status_code == 400
    assert invalid.json()["error"]["param"] == "count"
    assert broken.json()["error"]["code"] == "invalid_request"
    assert (domain.status_code, domain.json()["error"]["code"]) == (422, "something")
    assert crashed.status_code == 500
    assert (
        crashed.json()
        == OpenAIError(500, "The assistant failed to answer.", "api_error", "chat_failed").body()
    )
