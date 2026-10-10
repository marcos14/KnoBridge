"""``GET /v1/me``: the session's user, memberships with role and the superadmin flag."""

from __future__ import annotations

import pytest
from api_support import ApiEnv

from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration


def test_me_lists_memberships(api: ApiEnv) -> None:
    user, stranger = api.create_user(), api.create_user()
    beta = api.create_workspace({user.id: Role.VIEWER}, name="Beta")
    alpha = api.create_workspace(
        {user.id: Role.OWNER, stranger.id: Role.ADMIN},
        name="Alpha",
        status=WorkspaceStatus.SUSPENDED,
    )
    api.create_workspace({stranger.id: Role.OWNER}, name="Other")
    api.login(user)

    response = api.client.get("/v1/me")

    body = response.json()
    assert response.status_code == 200
    assert body["is_superadmin"] is False
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email
    assert [(w["id"], w["name"], w["status"], w["role"]) for w in body["workspaces"]] == [
        (str(alpha), "Alpha", "suspended", "owner"),
        (str(beta), "Beta", "active", "viewer"),
    ]


def test_me_reports_superadmin(api: ApiEnv) -> None:
    admin = api.create_user(superadmin=True)
    api.login(admin)

    body = api.client.get("/v1/me").json()

    assert body["is_superadmin"] is True
    assert body["workspaces"] == []


def test_me_requires_session(api: ApiEnv) -> None:
    response = api.client.get("/v1/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "unauthenticated", "message": "Authentication required.", "details": None}
    }


def test_me_rejects_unknown_session_token(api: ApiEnv) -> None:
    api.client.cookies.set("knobridge_session", "not-a-real-token")

    response = api.client.get("/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
