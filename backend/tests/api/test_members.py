"""Member routes (list, change role, remove) and renaming the workspace."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    """A workspace whose members have ``roles``, in that order."""
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    return workspace_id, users


def _patch_role(
    api: ApiEnv, workspace_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> httpx.Response:
    return api.client.patch(
        f"/v1/workspaces/{workspace_id}/members/{user_id}",
        json={"role": role},
        headers=api.csrf_headers(),
    )


def _remove(api: ApiEnv, workspace_id: uuid.UUID, user_id: uuid.UUID) -> httpx.Response:
    return api.client.delete(
        f"/v1/workspaces/{workspace_id}/members/{user_id}", headers=api.csrf_headers()
    )


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def test_members_listed_with_roles_for_any_member(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(viewer)

    full = api.client.get(f"/v1/workspaces/{workspace_id}/members")
    page = api.client.get(
        f"/v1/workspaces/{workspace_id}/members", params={"limit": 1, "offset": 1}
    )

    assert full.status_code == 200
    body = full.json()
    assert body["total"] == 2
    assert {(item["user_id"], item["role"]) for item in body["items"]} == {
        (str(owner.id), "owner"),
        (str(viewer.id), "viewer"),
    }
    assert {item["email"] for item in body["items"]} == {owner.email, viewer.email}
    assert all(item["name"] == "Test User" and item["joined_at"] for item in body["items"])
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    assert page.json()["offset"] == 1


def test_admin_changes_member_role(api: ApiEnv) -> None:
    workspace_id, (_, admin, editor) = _team(api, Role.OWNER, Role.ADMIN, Role.EDITOR)
    api.login(admin)

    response = _patch_role(api, workspace_id, editor.id, "viewer")

    assert response.status_code == 200
    assert response.json()["user_id"] == str(editor.id)
    assert response.json()["role"] == "viewer"
    assert api.roles(workspace_id)[editor.id] == Role.VIEWER
    assert (
        "membership.role.changed",
        {"user_id": str(editor.id), "from": "editor", "to": "viewer"},
    ) in api.workspace_audit(workspace_id)


def test_change_to_same_role_is_not_audited(api: ApiEnv) -> None:
    workspace_id, (owner, editor) = _team(api, Role.OWNER, Role.EDITOR)
    api.login(owner)

    response = _patch_role(api, workspace_id, editor.id, "editor")

    assert response.status_code == 200
    assert response.json()["role"] == "editor"
    assert api.workspace_audit(workspace_id) == []


def test_admin_cannot_promote_to_owner_or_touch_owner(api: ApiEnv) -> None:
    workspace_id, (owner, admin, editor) = _team(api, Role.OWNER, Role.ADMIN, Role.EDITOR)
    api.login(admin)

    promote = _patch_role(api, workspace_id, editor.id, "owner")
    demote_owner = _patch_role(api, workspace_id, owner.id, "viewer")
    remove_owner = _remove(api, workspace_id, owner.id)

    assert _error(promote) == (403, "role_not_allowed")
    assert _error(demote_owner) == (403, "role_not_allowed")
    assert _error(remove_owner) == (403, "role_not_allowed")
    assert api.roles(workspace_id) == {
        owner.id: Role.OWNER,
        admin.id: Role.ADMIN,
        editor.id: Role.EDITOR,
    }


def test_last_owner_cannot_be_removed_or_demoted(api: ApiEnv) -> None:
    workspace_id, (owner, admin) = _team(api, Role.OWNER, Role.ADMIN)
    api.login(owner)

    demote = _patch_role(api, workspace_id, owner.id, "admin")
    remove = _remove(api, workspace_id, owner.id)
    _patch_role(api, workspace_id, admin.id, "owner")
    demote_with_other_owner = _patch_role(api, workspace_id, owner.id, "admin")

    assert _error(demote) == (409, "last_owner")
    assert _error(remove) == (409, "last_owner")
    assert demote_with_other_owner.status_code == 200
    assert api.roles(workspace_id) == {owner.id: Role.ADMIN, admin.id: Role.OWNER}


def test_owner_removed_when_another_owner_remains(api: ApiEnv) -> None:
    workspace_id, (first, second) = _team(api, Role.OWNER, Role.OWNER)
    api.login(first)

    response = _remove(api, workspace_id, second.id)

    assert response.status_code == 204
    assert api.roles(workspace_id) == {first.id: Role.OWNER}


def test_admin_removes_member(api: ApiEnv) -> None:
    workspace_id, (_, admin, viewer) = _team(api, Role.OWNER, Role.ADMIN, Role.VIEWER)
    api.login(admin)

    response = _remove(api, workspace_id, viewer.id)

    assert response.status_code == 204
    assert viewer.id not in api.roles(workspace_id)
    assert (
        "membership.removed",
        {"user_id": str(viewer.id), "role": "viewer"},
    ) in api.workspace_audit(workspace_id)
    api.login(viewer)
    assert _error(api.client.get(f"/v1/workspaces/{workspace_id}/members")) == (404, "not_found")


def test_unknown_member_not_found(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)
    stranger = uuid.uuid4()

    assert _error(_patch_role(api, workspace_id, stranger, "viewer")) == (404, "not_found")
    assert _error(_remove(api, workspace_id, stranger)) == (404, "not_found")


def test_viewer_cannot_manage_members(api: ApiEnv) -> None:
    workspace_id, (owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    api.login(viewer)
    base = f"/v1/workspaces/{workspace_id}"

    responses = [
        _patch_role(api, workspace_id, owner.id, "viewer"),
        _remove(api, workspace_id, owner.id),
        api.client.post(
            f"{base}/invites",
            json={"email": "someone@example.test", "role": "viewer"},
            headers=api.csrf_headers(),
        ),
        api.client.get(f"{base}/invites"),
        api.client.patch(base, json={"name": "Taken over"}, headers=api.csrf_headers()),
    ]

    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"] == {
            "code": "forbidden",
            "message": "Your role does not allow this action.",
            "details": {"required_role": "admin"},
        }
    assert api.roles(workspace_id)[owner.id] == Role.OWNER


def test_member_changes_require_csrf(api: ApiEnv) -> None:
    workspace_id, (owner, editor) = _team(api, Role.OWNER, Role.EDITOR)
    api.login(owner)
    path = f"/v1/workspaces/{workspace_id}/members/{editor.id}"

    patch = api.client.patch(path, json={"role": "viewer"})
    delete = api.client.delete(path)

    assert _error(patch) == (403, "csrf_failed")
    assert _error(delete) == (403, "csrf_failed")


def test_members_isolated_by_workspace(api: ApiEnv) -> None:
    workspace_a, (owner_a, member_a) = _team(api, Role.OWNER, Role.EDITOR)
    workspace_b, (owner_b,) = _team(api, Role.OWNER)
    api.login(owner_b)

    listing_b = api.client.get(f"/v1/workspaces/{workspace_b}/members").json()
    listing_a = api.client.get(f"/v1/workspaces/{workspace_a}/members")
    patch_via_b = _patch_role(api, workspace_b, member_a.id, "viewer")
    remove_via_b = _remove(api, workspace_b, member_a.id)
    patch_a = _patch_role(api, workspace_a, member_a.id, "viewer")

    assert [item["user_id"] for item in listing_b["items"]] == [str(owner_b.id)]
    assert _error(listing_a) == (404, "not_found")
    assert _error(patch_via_b) == (404, "not_found")
    assert _error(remove_via_b) == (404, "not_found")
    assert _error(patch_a) == (404, "not_found")
    assert api.roles(workspace_a) == {owner_a.id: Role.OWNER, member_a.id: Role.EDITOR}


def test_admin_renames_workspace(api: ApiEnv) -> None:
    workspace_id, (_, admin) = _team(api, Role.OWNER, Role.ADMIN)
    api.login(admin)
    path = f"/v1/workspaces/{workspace_id}"

    response = api.client.patch(path, json={"name": "  Renamed  "}, headers=api.csrf_headers())
    unchanged = api.client.patch(path, json={"name": "Renamed"}, headers=api.csrf_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(workspace_id)
    assert body["name"] == "Renamed"
    assert body["status"] == "active"
    assert body["slug"].startswith("ws-")
    assert unchanged.status_code == 200
    assert api.workspace_audit(workspace_id) == [("workspace.updated", {"fields": ["name"]})]
    me = api.client.get("/v1/me").json()
    assert [w["name"] for w in me["workspaces"] if w["id"] == str(workspace_id)] == ["Renamed"]


def test_rename_workspace_validates_name(api: ApiEnv) -> None:
    workspace_id, (owner,) = _team(api, Role.OWNER)
    api.login(owner)

    response = api.client.patch(
        f"/v1/workspaces/{workspace_id}", json={"name": "   "}, headers=api.csrf_headers()
    )

    assert _error(response) == (422, "validation_error")
