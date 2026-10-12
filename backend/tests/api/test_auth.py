"""Authentication routes: CSRF token, login (throttling, suspension, rehash), logout."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from api_support import (
    PASSWORD,
    TEST_LOGIN_MAX_ATTEMPTS,
    ApiEnv,
    SeededUser,
    SessionFactory,
    run_db,
)
from sqlalchemy import select

from knobridge.audit.models import AuditEvent, JSONValue
from knobridge.core.db import system_session
from knobridge.security.csrf import is_valid_csrf_token
from knobridge.security.models import Session
from knobridge.security.passwords import Argon2Params, PasswordHasher
from knobridge.tenancy.models import User, UserStatus

pytestmark = pytest.mark.integration


def _sessions(database_url: str, user_id: uuid.UUID) -> list[Session]:
    async def scenario(factory: SessionFactory) -> list[Session]:
        async with system_session(factory) as db:
            return list(await db.scalars(select(Session).where(Session.user_id == user_id)))

    return run_db(database_url, scenario)


def _login_events(database_url: str, user_id: uuid.UUID) -> list[tuple[str, JSONValue]]:
    async def scenario(factory: SessionFactory) -> list[tuple[str, JSONValue]]:
        async with system_session(factory) as db:
            rows = await db.execute(
                select(AuditEvent.action, AuditEvent.details)
                .where(AuditEvent.target_id == str(user_id))
                .order_by(AuditEvent.occurred_at, AuditEvent.action)
            )
            return [(action, details.get("reason")) for action, details in rows]

    return run_db(database_url, scenario)


def _post_login(api: ApiEnv, email: str, password: str) -> tuple[int, str]:
    response = api.client.post("/v1/auth/login", json={"email": email, "password": password})
    return response.status_code, response.json().get("error", {}).get("code", "")


def test_csrf_endpoint_sets_cookie_and_returns_token(api: ApiEnv) -> None:
    response = api.client.get("/v1/auth/csrf")

    token = response.json()["csrf_token"]
    assert response.status_code == 200
    assert api.client.cookies.get("knobridge_csrf") == token
    assert is_valid_csrf_token("dev-only-insecure-secret-key-change-me", token)


def test_login_sets_httponly_cookie(api: ApiEnv) -> None:
    user = api.create_user()

    response = api.client.post(
        "/v1/auth/login",
        json={"email": user.email.upper(), "password": PASSWORD},
        headers={"User-Agent": "pytest-agent"},
    )

    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith("knobridge_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("knobridge_csrf="))
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)
    assert "HttpOnly" in session_cookie
    assert "samesite=lax" in session_cookie.lower()
    assert "HttpOnly" not in csrf_cookie
    [session] = _sessions(api.database_url, user.id)
    assert session.user_agent == "pytest-agent"
    assert _login_events(api.database_url, user.id) == [("auth.login.succeeded", None)]


def test_login_generic_error_on_wrong_password(api: ApiEnv) -> None:
    user = api.create_user()

    wrong = api.client.post(
        "/v1/auth/login", json={"email": user.email, "password": "wrong password!"}
    )
    unknown = api.client.post(
        "/v1/auth/login", json={"email": "nobody@example.test", "password": "wrong password!"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert "knobridge_session" not in api.client.cookies
    assert _login_events(api.database_url, user.id) == [
        ("auth.login.failed", "invalid_credentials")
    ]


def test_login_rejects_user_without_password(api: ApiEnv) -> None:
    user = api.create_user(password=None)

    assert _post_login(api, user.email, PASSWORD) == (401, "invalid_credentials")


def test_login_rate_limited(api: ApiEnv) -> None:
    user = api.create_user()
    for _ in range(TEST_LOGIN_MAX_ATTEMPTS):
        assert _post_login(api, user.email, "wrong password!") == (401, "invalid_credentials")

    blocked = api.client.post("/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    api.clock.advance(timedelta(minutes=15))
    after_window = _post_login(api, user.email, PASSWORD)

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_attempts"
    assert blocked.json()["error"]["details"] == {"retry_after_seconds": 900}
    assert after_window == (200, "")


def test_login_rate_limit_is_per_email(api: ApiEnv) -> None:
    blocked_user, other_user = api.create_user(), api.create_user()
    for _ in range(TEST_LOGIN_MAX_ATTEMPTS):
        _post_login(api, blocked_user.email, "wrong password!")

    assert _post_login(api, blocked_user.email, PASSWORD) == (429, "too_many_attempts")
    assert _post_login(api, other_user.email, PASSWORD) == (200, "")


def test_login_success_resets_failures(api: ApiEnv) -> None:
    user = api.create_user()
    for _ in range(TEST_LOGIN_MAX_ATTEMPTS - 1):
        _post_login(api, user.email, "wrong password!")
    api.login(user)

    for _ in range(TEST_LOGIN_MAX_ATTEMPTS - 1):
        _post_login(api, user.email, "wrong password!")

    assert _post_login(api, user.email, PASSWORD) == (200, "")


def test_suspended_user_cannot_login(api: ApiEnv) -> None:
    user = api.create_user(status=UserStatus.SUSPENDED)

    result = _post_login(api, user.email, PASSWORD)

    assert result == (401, "invalid_credentials")
    assert _sessions(api.database_url, user.id) == []
    assert _login_events(api.database_url, user.id) == [("auth.login.failed", "suspended")]


def test_login_rehashes_outdated_password_hash(api: ApiEnv) -> None:
    old_hasher = PasswordHasher(Argon2Params(time_cost=2, memory_cost=8, parallelism=1))
    user = api.create_user(hasher=old_hasher)

    api.login(user)

    async def stored_hash(factory: SessionFactory) -> str | None:
        async with system_session(factory) as db:
            row = await db.get(User, user.id)
            return None if row is None else row.password_hash

    new_hash = run_db(api.database_url, stored_hash)
    assert new_hash is not None
    assert not api.hasher.needs_rehash(new_hash)
    assert api.hasher.verify(new_hash, PASSWORD)


def test_login_validates_body(api: ApiEnv) -> None:
    response = api.client.post("/v1/auth/login", json={"email": "", "password": ""})

    assert response.status_code == 422


def _logged_in(api: ApiEnv) -> SeededUser:
    user = api.create_user()
    api.login(user)
    return user


def test_logout_revokes_current_session_and_clears_cookies(api: ApiEnv) -> None:
    user = _logged_in(api)

    response = api.client.post("/v1/auth/logout", headers=api.csrf_headers())

    assert response.status_code == 204
    assert "knobridge_session" not in api.client.cookies
    [session] = _sessions(api.database_url, user.id)
    assert session.revoked_at is not None
    assert api.client.get("/v1/me").status_code == 401


def test_logout_requires_csrf(api: ApiEnv) -> None:
    user = _logged_in(api)

    response = api.client.post("/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    [session] = _sessions(api.database_url, user.id)
    assert session.revoked_at is None


def test_logout_requires_session(api: ApiEnv) -> None:
    api.client.get("/v1/auth/csrf")

    response = api.client.post("/v1/auth/logout", headers=api.csrf_headers())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_logout_all_revokes_sessions(api: ApiEnv) -> None:
    user = _logged_in(api)
    api.login(user)  # a second session (another device); the cookie now holds this one

    response = api.client.post("/v1/auth/logout-all", headers=api.csrf_headers())

    sessions = _sessions(api.database_url, user.id)
    assert response.status_code == 204
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)
    assert api.client.get("/v1/me").status_code == 401

    async def revoked_count(factory: SessionFactory) -> JSONValue:
        async with system_session(factory) as db:
            event = (
                await db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.action == "auth.sessions.revoked",
                        AuditEvent.actor_user_id == user.id,
                    )
                )
            ).one()
            return event.details["revoked"]

    assert run_db(api.database_url, revoked_count) == 2


def test_session_of_suspended_user_is_rejected(api: ApiEnv) -> None:
    user = _logged_in(api)
    api.set_user_status(user.id, UserStatus.SUSPENDED)

    response = api.client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_expired_session_is_rejected(api: ApiEnv) -> None:
    _logged_in(api)
    api.clock.advance(timedelta(days=8))

    response = api.client.get("/v1/me")

    assert response.status_code == 401
