from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.testclient import TestClient
from pydantic import SecretStr

from knobridge.api.app import create_app
from knobridge.core.settings import Settings
from knobridge.security.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    CsrfError,
    check_csrf,
    is_valid_csrf_token,
    issue_csrf_token,
    require_csrf,
    set_csrf_cookie,
)

SECRET = "s" * 40


@pytest.fixture
def csrf_settings() -> Settings:
    return Settings(env="test", secret_key=SecretStr(SECRET), cookie_secure=False)


@pytest.fixture
def csrf_client(csrf_settings: Settings) -> Generator[TestClient]:
    """The real app (so ``app.state.settings`` is the one create_app sets) plus a probe route."""
    app: FastAPI = create_app(csrf_settings)
    router = APIRouter(dependencies=[Depends(require_csrf)])

    @router.api_route("/probe", methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE"])
    def probe() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    with TestClient(app) as client:
        yield client


def test_csrf_allows_safe_methods(csrf_client: TestClient) -> None:
    responses = [csrf_client.request(method, "/probe") for method in ("GET", "HEAD", "OPTIONS")]

    assert [response.status_code for response in responses] == [200, 200, 200]


def test_csrf_rejects_missing_header(csrf_client: TestClient) -> None:
    csrf_client.cookies.set(CSRF_COOKIE_NAME, issue_csrf_token(SECRET))

    response = csrf_client.post("/probe")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_csrf_rejects_missing_cookie(csrf_client: TestClient) -> None:
    response = csrf_client.delete("/probe", headers={CSRF_HEADER_NAME: issue_csrf_token(SECRET)})

    assert response.status_code == 403


def test_csrf_accepts_matching_cookie_and_header(csrf_client: TestClient) -> None:
    token = issue_csrf_token(SECRET)
    csrf_client.cookies.set(CSRF_COOKIE_NAME, token)

    response = csrf_client.put("/probe", headers={CSRF_HEADER_NAME: token})

    assert response.status_code == 200


def test_csrf_rejects_mismatched_header(csrf_client: TestClient) -> None:
    csrf_client.cookies.set(CSRF_COOKIE_NAME, issue_csrf_token(SECRET))

    response = csrf_client.post("/probe", headers={CSRF_HEADER_NAME: issue_csrf_token(SECRET)})

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "Invalid CSRF token."


def test_csrf_rejects_token_signed_with_other_key() -> None:
    forged = issue_csrf_token("x" * 40)

    with pytest.raises(CsrfError):
        check_csrf("POST", forged, forged, SECRET)


@pytest.mark.parametrize("token", ["", "no-separator", ".signature-only", "nonce.bad"])
def test_csrf_token_validation_rejects_malformed(token: str) -> None:
    assert is_valid_csrf_token(SECRET, token) is False


def test_csrf_token_validation_accepts_issued_token() -> None:
    assert is_valid_csrf_token(SECRET, issue_csrf_token(SECRET)) is True


def test_csrf_check_treats_method_case_insensitively() -> None:
    check_csrf("get", None, None, SECRET)


def test_csrf_cookie_is_readable_by_frontend(csrf_settings: Settings) -> None:
    settings = csrf_settings.model_copy(
        update={"cookie_secure": True, "session_ttl": timedelta(hours=2)}
    )
    response = Response()

    set_csrf_cookie(response, "token-value", settings)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{CSRF_COOKIE_NAME}=token-value;")
    assert "HttpOnly" not in cookie
    assert "Max-Age=7200" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
