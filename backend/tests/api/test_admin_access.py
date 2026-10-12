"""Superadmin access to a workspace: enter, act as effective admin, switch and exit."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser, SessionFactory, run_db
from sqlalchemy import select

from knobridge.audit.models import AuditEvent
from knobridge.core.db import system_session
from knobridge.tenancy.models import Role, User, WorkspaceStatus

pytestmark = pytest.mark.integration

EXIT_PATH = "/v1/admin/workspace-access"


def _enter_path(workspace_id: uuid.UUID | str) -> str:
    return f"/v1/admin/workspaces/{workspace_id}/enter"


def _enter(api: ApiEnv, workspace_id: uuid.UUID | str) -> httpx.Response:
    return api.client.post(_enter_path(workspace_id), headers=api.csrf_headers())


def _exit(api: ApiEnv) -> httpx.Response:
    return api.client.delete(EXIT_PATH, headers=api.csrf_headers())


def _members(api: ApiEnv, workspace_id: uuid.UUID) -> httpx.Response:
    return api.client.get(f"/v1/workspaces/{workspace_id}/members")


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _superadmin(api: ApiEnv) -> SeededUser:
    admin = api.create_user(superadmin=True)
    api.login(admin)
    return admin


def _instance_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    """(action, details) of the instance events whose target is the workspace."""

    async def scenario(factory: SessionFactory) -> list[tuple[str, dict[str, object]]]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(AuditEvent).where(
                    AuditEvent.workspace_id.is_(None),
                    AuditEvent.target_type == "workspace",
                    AuditEvent.target_id == str(workspace_id),
                )
            )
            return [(event.action, dict(event.details)) for event in rows]

    return run_db(api.database_url, scenario)


def _set_superadmin(api: ApiEnv, user_id: uuid.UUID, *, value: bool) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            user = await db.get(User, user_id)
            assert user is not None
            user.is_superadmin = value

    run_db(api.database_url, scenario)


def test_enter_gives_admin_access_and_exit_removes_it(api: ApiEnv) -> None:
    owner = api.create_user()
    workspace = api.create_workspace({owner.id: Role.OWNER}, name="Acme")
    admin = _superadmin(api)
    assert _error(_members(api, workspace)) == (404, "not_found")

    entered = _enter(api, workspace)
    members = _members(api, workspace)
    audit = api.client.get(f"/v1/workspaces/{workspace}/audit")
    exited = _exit(api)

    assert entered.status_code == 200
    body = entered.json()
    assert body["superadmin_access"] == {
        "workspace_id": str(workspace),
        "workspace_name": "Acme",
        "entered_at": "2026-10-10T12:00:00Z",
    }
    assert [(w["id"], w["role"], w["access"]) for w in body["workspaces"]] == [
        (str(workspace), "admin", "superadmin")
    ]
    assert members.status_code == 200
    # Not a member: the superadmin does not show up in the member list.
    assert [item["user_id"] for item in members.json()["items"]] == [str(owner.id)]
    assert audit.status_code == 200
    assert exited.status_code == 200
    assert exited.json()["superadmin_access"] is None
    assert exited.json()["workspaces"] == []
    assert _error(_members(api, workspace)) == (404, "not_found")
    session = api.sessions(admin.id)[-1]
    assert (session.superadmin_workspace_id, session.superadmin_entered_at) == (None, None)


def test_enter_and_exit_are_audited_in_both_trails(api: ApiEnv) -> None:
    workspace = api.create_workspace({api.create_user().id: Role.OWNER})
    _superadmin(api)

    _enter(api, workspace)
    _exit(api)

    expected: list[tuple[str, dict[str, object]]] = [
        ("superadmin.workspace_entered", {}),
        ("superadmin.workspace_exited", {"reason": "exit"}),
    ]
    workspace_events = [
        event for event in api.workspace_audit(workspace) if event[0].startswith("superadmin.")
    ]
    assert sorted(workspace_events, key=lambda e: e[0]) == expected
    assert sorted(_instance_events(api, workspace), key=lambda e: e[0]) == expected


def test_enter_same_workspace_again_is_idempotent(api: ApiEnv) -> None:
    workspace = api.create_workspace({api.create_user().id: Role.OWNER})
    _superadmin(api)
    first = _enter(api, workspace)
    api.clock.advance(timedelta(minutes=5))

    second = _enter(api, workspace)

    assert second.status_code == 200
    assert second.json()["superadmin_access"] == first.json()["superadmin_access"]
    assert [a for a, _ in _instance_events(api, workspace)] == ["superadmin.workspace_entered"]


def test_enter_another_workspace_switches(api: ApiEnv) -> None:
    owner = api.create_user()
    alpha = api.create_workspace({owner.id: Role.OWNER}, name="Alpha")
    beta = api.create_workspace({owner.id: Role.OWNER}, name="Beta")
    _superadmin(api)
    _enter(api, alpha)

    switched = _enter(api, beta)

    assert switched.json()["superadmin_access"]["workspace_id"] == str(beta)
    assert _error(_members(api, alpha)) == (404, "not_found")
    assert _members(api, beta).status_code == 200
    assert ("superadmin.workspace_exited", {"reason": "switched"}) in api.workspace_audit(alpha)
    assert ("superadmin.workspace_entered", {}) in api.workspace_audit(beta)
    assert sorted(a for a, _ in _instance_events(api, alpha)) == [
        "superadmin.workspace_entered",
        "superadmin.workspace_exited",
    ]


def test_exit_without_access_records_nothing(api: ApiEnv) -> None:
    admin = _superadmin(api)

    response = _exit(api)

    assert response.status_code == 200
    assert response.json()["superadmin_access"] is None
    assert api.sessions(admin.id)[-1].superadmin_workspace_id is None


def test_effective_admin_cannot_grant_owner(api: ApiEnv) -> None:
    owner, editor = api.create_user(), api.create_user()
    workspace = api.create_workspace({owner.id: Role.OWNER, editor.id: Role.EDITOR})
    _superadmin(api)
    _enter(api, workspace)

    promote_owner = api.client.patch(
        f"/v1/workspaces/{workspace}/members/{editor.id}",
        json={"role": "owner"},
        headers=api.csrf_headers(),
    )
    promote_admin = api.client.patch(
        f"/v1/workspaces/{workspace}/members/{editor.id}",
        json={"role": "admin"},
        headers=api.csrf_headers(),
    )

    assert _error(promote_owner) == (403, "role_not_allowed")
    assert promote_admin.status_code == 200
    assert api.roles(workspace) == {owner.id: Role.OWNER, editor.id: Role.ADMIN}


def test_enter_unknown_workspace_is_not_found(api: ApiEnv) -> None:
    _superadmin(api)

    assert _error(_enter(api, uuid.uuid4())) == (404, "not_found")


def test_enter_suspended_workspace_is_refused(api: ApiEnv) -> None:
    workspace = api.create_workspace({}, status=WorkspaceStatus.SUSPENDED)
    admin = _superadmin(api)

    assert _error(_enter(api, workspace)) == (403, "workspace_suspended")
    assert api.sessions(admin.id)[-1].superadmin_workspace_id is None


def test_workspace_suspended_after_entry_is_refused(api: ApiEnv) -> None:
    workspace = api.create_workspace({})
    _superadmin(api)
    _enter(api, workspace)

    api.set_workspace_status(workspace, WorkspaceStatus.SUSPENDED)

    assert _error(_members(api, workspace)) == (403, "workspace_suspended")
    me = api.client.get("/v1/me").json()
    assert me["workspaces"][0]["status"] == "suspended"


@pytest.mark.parametrize(
    ("method", "path"), [("POST", _enter_path(uuid.uuid4())), ("DELETE", EXIT_PATH)]
)
def test_access_routes_refuse_non_superadmin(api: ApiEnv, method: str, path: str) -> None:
    api.login(api.create_user())

    response = api.client.request(method, path, headers=api.csrf_headers())

    assert _error(response) == (403, "forbidden")


@pytest.mark.parametrize(
    ("method", "path"), [("POST", _enter_path(uuid.uuid4())), ("DELETE", EXIT_PATH)]
)
def test_access_routes_require_csrf(api: ApiEnv, method: str, path: str) -> None:
    _superadmin(api)

    response = api.client.request(method, path)

    assert _error(response) == (403, "csrf_failed")


def test_access_belongs_to_the_session_only(api: ApiEnv) -> None:
    workspace = api.create_workspace({})
    admin = _superadmin(api)
    _enter(api, workspace)
    first_cookie = api.client.cookies.get("knobridge_session")
    assert first_cookie is not None

    api.login(admin)  # a second session of the same user (another browser)
    second = _members(api, workspace)
    second_me = api.client.get("/v1/me").json()
    api.client.cookies.set("knobridge_session", first_cookie)
    first = _members(api, workspace)

    assert _error(second) == (404, "not_found")
    assert second_me["superadmin_access"] is None
    assert first.status_code == 200


def test_access_is_inert_once_superadmin_is_removed(api: ApiEnv) -> None:
    workspace = api.create_workspace({})
    admin = _superadmin(api)
    _enter(api, workspace)

    _set_superadmin(api, admin.id, value=False)

    assert _error(_members(api, workspace)) == (404, "not_found")
    me = api.client.get("/v1/me").json()
    assert (me["superadmin_access"], me["workspaces"]) == (None, [])


def test_me_raises_lower_membership_and_keeps_owner(api: ApiEnv) -> None:
    admin = api.create_user(superadmin=True)
    viewer_of = api.create_workspace({admin.id: Role.VIEWER}, name="Gamma")
    owner_of = api.create_workspace({admin.id: Role.OWNER}, name="Beta")
    other = api.create_workspace({}, name="Alpha")
    api.login(admin)

    as_viewer = _enter(api, viewer_of).json()["workspaces"]
    as_owner = _enter(api, owner_of).json()["workspaces"]
    in_other = _enter(api, other).json()["workspaces"]

    def summary(items: list[dict[str, str]]) -> list[tuple[str, str, str]]:
        return [(item["name"], item["role"], item["access"]) for item in items]

    assert summary(as_viewer) == [("Beta", "owner", "member"), ("Gamma", "admin", "superadmin")]
    assert summary(as_owner) == [("Beta", "owner", "member"), ("Gamma", "viewer", "member")]
    assert summary(in_other) == [
        ("Alpha", "admin", "superadmin"),
        ("Beta", "owner", "member"),
        ("Gamma", "viewer", "member"),
    ]


def test_profile_update_keeps_superadmin_access(api: ApiEnv) -> None:
    workspace = api.create_workspace({})
    _superadmin(api)
    _enter(api, workspace)

    response = api.client.patch("/v1/me", json={"name": "Root"}, headers=api.csrf_headers())

    assert response.json()["superadmin_access"]["workspace_id"] == str(workspace)
