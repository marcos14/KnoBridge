"""First-run setup routes against a brand-new database (no user yet)."""

from __future__ import annotations

import uuid

import pytest
from api_support import PASSWORD, ApiEnv, SessionFactory, run_db
from sqlalchemy import select

from knobridge.audit.models import AuditEvent
from knobridge.core.db import system_session
from knobridge.tenancy.models import Membership, Role, User, Workspace

pytestmark = pytest.mark.integration

SETUP_BODY = {
    "name": "  Ana Admin ",
    "email": "Ana@Example.test",
    "password": PASSWORD,
    "workspace_name": "  Suporte Ágil ",
}


def _users_and_actions(database_url: str) -> tuple[list[User], list[str]]:
    async def scenario(factory: SessionFactory) -> tuple[list[User], list[str]]:
        async with system_session(factory) as db:
            users = list(await db.scalars(select(User)))
            actions = list(await db.scalars(select(AuditEvent.action).order_by(AuditEvent.action)))
            return users, actions

    return run_db(database_url, scenario)


def _workspaces_and_events(
    database_url: str,
) -> tuple[list[tuple[str, str]], list[tuple[uuid.UUID, Role]], list[AuditEvent]]:
    async def scenario(
        factory: SessionFactory,
    ) -> tuple[list[tuple[str, str]], list[tuple[uuid.UUID, Role]], list[AuditEvent]]:
        async with system_session(factory) as db:
            workspaces = [(w.name, w.slug) for w in await db.scalars(select(Workspace))]
            members = [(m.user_id, m.role) for m in await db.scalars(select(Membership))]
            events = list(
                await db.scalars(select(AuditEvent).where(AuditEvent.action == "workspace.created"))
            )
            return workspaces, members, events

    return run_db(database_url, scenario)


def test_setup_status_reports_needs_setup_on_empty_instance(empty_api: ApiEnv) -> None:
    response = empty_api.client.get("/v1/setup/status")

    assert response.status_code == 200
    assert response.json() == {"needs_setup": True}


def test_setup_status_reports_done_when_users_exist(api: ApiEnv) -> None:
    api.create_user()

    response = api.client.get("/v1/setup/status")

    assert response.json() == {"needs_setup": False}


def test_setup_creates_superadmin_once(empty_api: ApiEnv) -> None:
    first = empty_api.client.post("/v1/setup", json=SETUP_BODY)
    second = empty_api.client.post("/v1/setup", json={**SETUP_BODY, "email": "other@example.test"})

    users, actions = _users_and_actions(empty_api.database_url)
    assert first.status_code == 201
    body = first.json()
    assert body["is_superadmin"] is True
    assert body["superadmin_access"] is None
    assert [(w["name"], w["slug"], w["role"], w["access"]) for w in body["workspaces"]] == [
        ("Suporte Ágil", "suporte-agil", "owner", "member")
    ]
    assert body["user"]["email"] == "ana@example.test"
    assert body["user"]["name"] == "Ana Admin"
    assert body["user"]["email_verified_at"] == "2026-10-10T12:00:00Z"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "setup_already_completed"
    assert [(u.email, u.is_superadmin) for u in users] == [("ana@example.test", True)]
    assert actions == ["setup.completed", "user.created", "workspace.created", "workspace.created"]
    assert empty_api.client.get("/v1/setup/status").json() == {"needs_setup": False}


def test_setup_creates_first_workspace_with_owner(empty_api: ApiEnv) -> None:
    response = empty_api.client.post("/v1/setup", json=SETUP_BODY)

    workspaces, members, events = _workspaces_and_events(empty_api.database_url)
    user_id = uuid.UUID(response.json()["user"]["id"])
    workspace_id = uuid.UUID(response.json()["workspaces"][0]["id"])
    assert workspaces == [("Suporte Ágil", "suporte-agil")]
    assert members == [(user_id, Role.OWNER)]
    assert sorted((e.workspace_id is None, e.target_id) for e in events) == [
        (False, str(workspace_id)),
        (True, str(workspace_id)),
    ]
    assert all(
        e.actor_user_id == user_id
        and e.details
        == {"name": "Suporte Ágil", "slug": "suporte-agil", "owner_user_id": str(user_id)}
        for e in events
    )
    assert empty_api.client.get(f"/v1/workspaces/{workspace_id}/members").status_code == 200
    assert empty_api.emails.sent == []


@pytest.mark.parametrize("workspace_name", [None, "", "   ", "x" * 201])
def test_setup_requires_workspace_name(api: ApiEnv, workspace_name: str | None) -> None:
    # The body is validated before the instance state: the shared database already has users.
    body: dict[str, object] = {**SETUP_BODY, "workspace_name": workspace_name}
    if workspace_name is None:
        del body["workspace_name"]

    response = api.client.post("/v1/setup", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_setup_opens_session_with_csrf_cookie(empty_api: ApiEnv) -> None:
    response = empty_api.client.post("/v1/setup", json=SETUP_BODY)

    assert response.status_code == 201
    assert empty_api.client.cookies.get("knobridge_csrf") is not None
    assert empty_api.client.get("/v1/me").json()["user"]["email"] == "ana@example.test"


def test_setup_rejects_weak_password(empty_api: ApiEnv) -> None:
    response = empty_api.client.post("/v1/setup", json={**SETUP_BODY, "password": "short"})

    users, _ = _users_and_actions(empty_api.database_url)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
    assert users == []


def test_setup_rejects_invalid_email(api: ApiEnv) -> None:
    response = api.client.post("/v1/setup", json={**SETUP_BODY, "email": "not-an-email"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
