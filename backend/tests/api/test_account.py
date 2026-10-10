"""The user's own account: ``PATCH /v1/me``, ``POST /v1/me/password`` and ``/v1/me/sessions``."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from api_support import PASSWORD, START, ApiEnv, SeededUser

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a brand new passphrase"  # noqa: S105 - test value


def _logged_in(api: ApiEnv) -> SeededUser:
    user = api.create_user()
    api.login(user)
    return user


# Response bodies are parsed JSON, so they are typed as Any like `response.json()` itself.
def _patch_me(api: ApiEnv, body: dict[str, object]) -> tuple[int, Any]:
    response = api.client.patch("/v1/me", json=body, headers=api.csrf_headers())
    return response.status_code, response.json()


def test_update_profile_theme_and_locale(api: ApiEnv) -> None:
    user = _logged_in(api)

    status, body = _patch_me(api, {"theme": "dark", "locale": "en"})

    assert status == 200
    me = api.client.get("/v1/me").json()
    assert body == me
    assert (me["user"]["theme"], me["user"]["locale"], me["user"]["name"]) == (
        "dark",
        "en",
        "Test User",
    )
    assert ("user.profile.updated", {"fields": ["locale", "theme"]}) in api.audit_actions(user.id)


def test_update_profile_without_changes_is_not_audited(api: ApiEnv) -> None:
    user = _logged_in(api)
    before = api.audit_actions(user.id)

    status, body = _patch_me(api, {"theme": "system", "name": None})

    assert status == 200
    assert body["user"]["theme"] == "system"
    assert api.audit_actions(user.id) == before


def test_update_profile_strips_name(api: ApiEnv) -> None:
    user = _logged_in(api)

    status, _ = _patch_me(api, {"name": "  Ana Souza  "})

    assert status == 200
    assert api.user(user.id).name == "Ana Souza"


@pytest.mark.parametrize(
    "body",
    [{"theme": "blue"}, {"locale": "pt_BR"}, {"locale": "portuguese"}, {"name": "   "}],
)
def test_update_profile_validates_body(api: ApiEnv, body: dict[str, object]) -> None:
    _logged_in(api)

    status, response = _patch_me(api, body)

    assert status == 422
    assert response["error"]["code"] == "validation_error"


def test_update_profile_requires_csrf(api: ApiEnv) -> None:
    user = _logged_in(api)

    response = api.client.patch("/v1/me", json={"theme": "dark"})

    assert response.status_code == 403
    assert api.user(user.id).theme == "system"


def _change_password(api: ApiEnv, current: str, new: str) -> tuple[int, str]:
    response = api.client.post(
        "/v1/me/password",
        json={"current_password": current, "new_password": new},
        headers=api.csrf_headers(),
    )
    code: str = response.json()["error"]["code"] if response.content else ""
    return response.status_code, code


def test_change_password_requires_current(api: ApiEnv) -> None:
    user = _logged_in(api)

    result = _change_password(api, "not my password", NEW_PASSWORD)

    assert result == (422, "invalid_current_password")
    assert api.hasher.verify(api.user(user.id).password_hash or "", PASSWORD)


def test_change_password_rejects_weak_password(api: ApiEnv) -> None:
    _logged_in(api)

    assert _change_password(api, PASSWORD, "short") == (422, "weak_password")


def test_change_password_keeps_only_current_session(api: ApiEnv) -> None:
    user = _logged_in(api)  # first device
    api.login(user)  # this device

    result = _change_password(api, PASSWORD, NEW_PASSWORD)

    assert result == (204, "")
    assert api.client.get("/v1/me").status_code == 200
    sessions = api.sessions(user.id)
    assert sorted(session.revoked_at is None for session in sessions) == [False, True]
    assert api.hasher.verify(api.user(user.id).password_hash or "", NEW_PASSWORD)
    assert ("auth.password.changed", {"revoked_sessions": 1}) in api.audit_actions(user.id)


def test_change_password_requires_csrf(api: ApiEnv) -> None:
    _logged_in(api)

    response = api.client.post(
        "/v1/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )

    assert response.status_code == 403


def _list_sessions(api: ApiEnv, query: str = "") -> dict[str, Any]:
    response = api.client.get(f"/v1/me/sessions{query}")
    assert response.status_code == 200, response.text
    body = response.json()
    return body


def test_list_and_revoke_own_sessions(api: ApiEnv) -> None:
    user = _logged_in(api)  # another device
    api.clock.advance(timedelta(minutes=1))
    api.client.headers["User-Agent"] = "pytest-browser"
    api.login(user)  # this device

    listed = _list_sessions(api)
    items = listed["items"]
    this, other = items
    revoke = api.client.delete(f"/v1/me/sessions/{other['id']}", headers=api.csrf_headers())
    again = api.client.delete(f"/v1/me/sessions/{other['id']}", headers=api.csrf_headers())

    assert (listed["total"], listed["limit"], listed["offset"]) == (2, 50, 0)
    assert this["current"] is True
    assert other["current"] is False
    assert this["user_agent"] == "pytest-browser"
    assert this["ip_prefix"] is None  # the TestClient peer "testclient" is not an IP
    assert this["last_seen_at"] == (START + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    assert revoke.status_code == 204
    assert again.status_code == 404
    assert again.json()["error"]["code"] == "not_found"
    assert [item["id"] for item in _list_sessions(api)["items"]] == [this["id"]]
    assert api.client.get("/v1/me").status_code == 200


def test_list_sessions_paginates(api: ApiEnv) -> None:
    user = _logged_in(api)
    api.login(user)
    api.login(user)

    page = _list_sessions(api, "?limit=2&offset=1")
    invalid = api.client.get("/v1/me/sessions?limit=0")

    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert invalid.status_code == 422


def test_revoke_current_session_logs_out(api: ApiEnv) -> None:
    _logged_in(api)
    [current] = _list_sessions(api)["items"]

    response = api.client.delete(f"/v1/me/sessions/{current['id']}", headers=api.csrf_headers())

    assert response.status_code == 204
    assert "knobridge_session" not in api.client.cookies
    assert api.client.get("/v1/me").status_code == 401


def test_cannot_revoke_other_user_session(api: ApiEnv) -> None:
    victim = _logged_in(api)
    [victim_session] = api.sessions(victim.id)
    attacker = _logged_in(api)

    response = api.client.delete(f"/v1/me/sessions/{victim_session.id}", headers=api.csrf_headers())
    listed = _list_sessions(api)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    [still_alive] = api.sessions(victim.id)
    assert still_alive.revoked_at is None
    assert [item["id"] for item in listed["items"]] == [str(api.sessions(attacker.id)[0].id)]


def test_revoke_unknown_session_is_not_found(api: ApiEnv) -> None:
    _logged_in(api)

    response = api.client.delete(f"/v1/me/sessions/{uuid.uuid4()}", headers=api.csrf_headers())

    assert response.status_code == 404


def test_session_routes_require_auth_and_csrf(api: ApiEnv) -> None:
    user = _logged_in(api)
    [session] = api.sessions(user.id)

    without_csrf = api.client.delete(f"/v1/me/sessions/{session.id}")
    api.client.cookies.clear()
    anonymous = api.client.get("/v1/me/sessions")

    assert without_csrf.status_code == 403
    assert anonymous.status_code == 401
