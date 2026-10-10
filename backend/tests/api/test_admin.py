"""Superadmin routes under ``/v1/admin``: workspaces, users and the instance audit trail."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser, unique

from knobridge.tenancy import admin_workspaces
from knobridge.tenancy.models import Role, UserStatus

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a long enough passphrase"  # noqa: S105 - test value
SESSION_COOKIE = "knobridge_session"


def _superadmin(api: ApiEnv) -> SeededUser:
    user = api.create_user(superadmin=True)
    api.login(user)
    return user


def _email() -> str:
    return f"{unique('owner')}@example.test"


def _create_workspace(api: ApiEnv, **body: str) -> httpx.Response:
    return api.client.post("/v1/admin/workspaces", json=body, headers=api.csrf_headers())


def _patch_workspace(api: ApiEnv, workspace_id: uuid.UUID | str, **body: object) -> httpx.Response:
    return api.client.patch(
        f"/v1/admin/workspaces/{workspace_id}", json=body, headers=api.csrf_headers()
    )


def _patch_user(api: ApiEnv, user_id: uuid.UUID, **body: object) -> httpx.Response:
    return api.client.patch(f"/v1/admin/users/{user_id}", json=body, headers=api.csrf_headers())


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


ROUTES = [
    ("GET", "/v1/admin/workspaces"),
    ("POST", "/v1/admin/workspaces"),
    ("PATCH", f"/v1/admin/workspaces/{uuid.uuid4()}"),
    ("GET", "/v1/admin/users"),
    ("PATCH", f"/v1/admin/users/{uuid.uuid4()}"),
    ("GET", "/v1/admin/audit"),
]


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_non_superadmin_forbidden(api: ApiEnv, method: str, path: str) -> None:
    user = api.create_user()
    api.create_workspace({user.id: Role.OWNER})  # an owner is still not a superadmin
    api.login(user)

    response = api.client.request(method, path, json={}, headers=api.csrf_headers())

    assert _error(response) == (403, "forbidden")


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_admin_routes_require_session(api: ApiEnv, method: str, path: str) -> None:
    api.client.get("/v1/auth/csrf")  # a valid CSRF pair, so only the missing session counts

    response = api.client.request(method, path, json={}, headers=api.csrf_headers())

    assert _error(response) == (401, "unauthenticated")


def test_admin_unsafe_routes_require_csrf(api: ApiEnv) -> None:
    _superadmin(api)

    response = api.client.post(
        "/v1/admin/workspaces", json={"name": "Acme", "owner_email": _email()}
    )

    assert _error(response) == (403, "csrf_failed")


def test_create_workspace_invites_owner(api: ApiEnv) -> None:
    admin = _superadmin(api)
    owner_email = _email()
    name = f"Ação Rápida {unique('x')}"

    response = _create_workspace(api, name=name, owner_email=owner_email.upper())

    assert response.status_code == 201, response.text
    body = response.json()
    workspace = body["workspace"]
    assert workspace["name"] == name
    assert workspace["slug"] == admin_workspaces.slugify(name)
    assert workspace["slug"].startswith("acao-rapida-x-")
    assert workspace["status"] == "active"
    assert workspace["member_count"] == 0
    invitation = body["owner_invitation"]
    assert (invitation["email"], invitation["role"]) == (owner_email, "owner")
    assert invitation["invited_by_user_id"] == str(admin.id)
    assert invitation["expired"] is False
    workspace_id = uuid.UUID(workspace["id"])
    events = api.workspace_audit(workspace_id)
    assert ("workspace.created", {"slug": workspace["slug"]}) in events
    assert ("membership.invited", {"role": "owner"}) in events
    instance = api.client.get(
        "/v1/admin/audit", params={"action": "workspace.created", "actor_user_id": str(admin.id)}
    ).json()
    assert [(item["target_type"], item["target_id"]) for item in instance["items"]] == [
        ("workspace", str(workspace_id))
    ]
    # The invitee accepts with a new account and becomes the owner.
    api.client.cookies.clear()
    token = api.emailed_token(owner_email)
    accepted = api.client.post(
        "/v1/invites/accept", json={"token": token, "name": "Owner", "password": NEW_PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    assert list(api.roles(workspace_id).values()) == [Role.OWNER]


def test_create_workspace_generates_unique_slug(api: ApiEnv) -> None:
    _superadmin(api)
    name = unique("Twin")

    first = _create_workspace(api, name=name, owner_email=_email())
    second = _create_workspace(api, name=name, owner_email=_email())

    assert first.json()["workspace"]["slug"] == name.lower()
    assert second.json()["workspace"]["slug"] == f"{name.lower()}-2"


def test_create_workspace_with_given_slug(api: ApiEnv) -> None:
    _superadmin(api)
    slug = unique("custom")

    response = _create_workspace(api, name="Anything", slug=slug, owner_email=_email())

    assert response.status_code == 201
    assert response.json()["workspace"]["slug"] == slug


def test_create_workspace_with_taken_slug_conflicts(api: ApiEnv) -> None:
    _superadmin(api)
    slug = unique("taken")
    assert _create_workspace(api, name="One", slug=slug, owner_email=_email()).status_code == 201
    owner_email = _email()

    response = _create_workspace(api, name="Two", slug=slug, owner_email=owner_email)

    assert _error(response) == (409, "slug_taken")
    assert response.json()["error"]["details"] == {"slug": slug}
    assert api.emails.sent_to(owner_email) == []


def test_create_workspace_slug_race_conflicts(api: ApiEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    _superadmin(api)
    slug = unique("race")
    assert _create_workspace(api, name="One", slug=slug, owner_email=_email()).status_code == 201

    # The lookup misses a slug a concurrent request just took; only the unique index stops it.
    async def never_taken(*_: object) -> bool:
        return False

    monkeypatch.setattr(admin_workspaces, "slug_taken", never_taken)

    response = _create_workspace(api, name="Two", slug=slug, owner_email=_email())

    assert _error(response) == (409, "slug_taken")


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Acme", "slug": "Not A Slug", "owner_email": "owner@example.test"},
        {"name": "Acme", "owner_email": "not-an-email"},
        {"name": "  ", "owner_email": "owner@example.test"},
    ],
)
def test_create_workspace_rejects_invalid_body(api: ApiEnv, body: dict[str, str]) -> None:
    _superadmin(api)

    response = _create_workspace(api, **body)

    assert _error(response) == (422, "validation_error")


def test_admin_workspaces_search_paginates(api: ApiEnv) -> None:
    _superadmin(api)
    token = unique("find")
    member = api.create_user()
    ids = [
        api.create_workspace({member.id: Role.OWNER}, name=f"{token} {letter}") for letter in "abc"
    ]
    api.create_workspace({}, name=f"{token}_x")  # the "_" in a query is literal, no wildcard

    first = api.client.get("/v1/admin/workspaces", params={"q": token.upper(), "limit": 2})
    last = api.client.get(
        "/v1/admin/workspaces", params={"q": f"{token} ", "limit": 2, "offset": 2}
    )
    literal = api.client.get("/v1/admin/workspaces", params={"q": f"{token}_"})

    assert first.status_code == 200
    assert first.json()["total"] == 4
    assert [item["id"] for item in first.json()["items"]] == [str(ids[0]), str(ids[1])]
    assert first.json()["items"][0]["member_count"] == 1
    assert last.json()["total"] == 3
    assert [item["id"] for item in last.json()["items"]] == [str(ids[2])]
    assert (last.json()["limit"], last.json()["offset"]) == (2, 2)
    assert literal.json()["total"] == 1


def test_admin_workspaces_search_matches_slug(api: ApiEnv) -> None:
    _superadmin(api)
    slug = unique("slugonly")
    _create_workspace(api, name="Unrelated name", slug=slug, owner_email=_email())

    response = api.client.get("/v1/admin/workspaces", params={"q": slug})

    assert [item["slug"] for item in response.json()["items"]] == [slug]


def test_suspend_workspace_blocks_members(api: ApiEnv) -> None:
    admin = _superadmin(api)
    member = api.create_user()
    workspace_id = api.create_workspace({member.id: Role.OWNER})

    suspended = _patch_workspace(api, workspace_id, status="suspended")
    api.login(member)
    blocked = api.client.get(f"/v1/workspaces/{workspace_id}/members")
    api.login(admin)
    reactivated = _patch_workspace(api, workspace_id, status="active")
    api.login(member)
    restored = api.client.get(f"/v1/workspaces/{workspace_id}/members")

    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["member_count"] == 1
    assert _error(blocked) == (403, "workspace_suspended")
    assert reactivated.json()["status"] == "active"
    assert restored.status_code == 200
    actions = [action for action, _ in api.workspace_audit(workspace_id)]
    assert {"workspace.suspended", "workspace.reactivated"} <= set(actions)


def test_rename_workspace_audits_only_real_changes(api: ApiEnv) -> None:
    admin = _superadmin(api)
    workspace_id = api.create_workspace({}, name="Old")

    renamed = _patch_workspace(api, workspace_id, name=" New ")
    unchanged = _patch_workspace(api, workspace_id, name="New", status="active")

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "New"
    assert unchanged.json()["name"] == "New"
    assert api.workspace_audit(workspace_id) == [("workspace.updated", {"fields": ["name"]})]
    instance = api.client.get(
        "/v1/admin/audit", params={"action": "workspace.updated", "actor_user_id": str(admin.id)}
    )
    assert instance.json()["total"] == 1


def test_update_workspace_not_found(api: ApiEnv) -> None:
    _superadmin(api)

    response = _patch_workspace(api, uuid.uuid4(), name="Ghost")

    assert _error(response) == (404, "not_found")


def test_update_workspace_requires_a_field(api: ApiEnv) -> None:
    _superadmin(api)
    workspace_id = api.create_workspace({})

    response = _patch_workspace(api, workspace_id)

    assert _error(response) == (422, "validation_error")


def test_admin_users_search_paginates(api: ApiEnv) -> None:
    _superadmin(api)
    token = unique("people")
    users = [api.create_user(name=f"{token} {letter}") for letter in "abc"]
    percent = api.create_user(name=f"{token} 100%")

    first = api.client.get("/v1/admin/users", params={"q": token, "limit": 2})
    rest = api.client.get("/v1/admin/users", params={"q": token, "limit": 2, "offset": 2})
    by_email = api.client.get("/v1/admin/users", params={"q": users[1].email.upper()})
    literal = api.client.get("/v1/admin/users", params={"q": f"{token} 100%"})
    no_wildcard = api.client.get("/v1/admin/users", params={"q": f"{token} %"})

    assert first.status_code == 200
    assert first.json()["total"] == 4
    assert [item["id"] for item in first.json()["items"]] == [str(percent.id), str(users[0].id)]
    assert [item["id"] for item in rest.json()["items"]] == [str(users[1].id), str(users[2].id)]
    item = by_email.json()["items"][0]
    assert by_email.json()["total"] == 1
    assert item == {
        "id": str(users[1].id),
        "email": users[1].email,
        "name": f"{token} b",
        "status": "active",
        "is_superadmin": False,
        "email_verified_at": None,
        "created_at": item["created_at"],
    }
    assert [item["id"] for item in literal.json()["items"]] == [str(percent.id)]
    assert no_wildcard.json()["total"] == 0


def test_suspend_user_revokes_sessions(api: ApiEnv) -> None:
    user = api.create_user()
    api.login(user)
    user_cookie = api.client.cookies.get(SESSION_COOKIE)
    _superadmin(api)

    suspended = _patch_user(api, user.id, status="suspended")
    admin_cookie = api.client.cookies.get(SESSION_COOKIE)
    api.client.cookies.set(SESSION_COOKIE, str(user_cookie))
    rejected = api.client.get("/v1/me")
    api.client.cookies.set(SESSION_COOKIE, str(admin_cookie))
    reactivated = _patch_user(api, user.id, status="active")

    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"
    assert all(session.revoked_at is not None for session in api.sessions(user.id))
    assert _error(rejected) == (401, "unauthenticated")
    assert reactivated.json()["status"] == "active"
    # Same frozen instant: no order between the events, so check membership.
    events = api.audit_actions(user.id)
    assert ("user.suspended", {"sessions_revoked": 1}) in events
    assert ("user.reactivated", {}) in events
    assert api.user(user.id).status == UserStatus.ACTIVE


def test_cannot_suspend_self(api: ApiEnv) -> None:
    admin = _superadmin(api)

    response = _patch_user(api, admin.id, status="suspended")

    assert _error(response) == (409, "cannot_suspend_self")


def test_grant_and_remove_superadmin(api: ApiEnv) -> None:
    _superadmin(api)
    user = api.create_user()

    granted = _patch_user(api, user.id, is_superadmin=True)
    repeated = _patch_user(api, user.id, is_superadmin=True)
    removed = _patch_user(api, user.id, is_superadmin=False)

    assert granted.json()["is_superadmin"] is True
    assert repeated.json()["is_superadmin"] is True
    assert removed.json()["is_superadmin"] is False
    assert sorted(api.audit_actions(user.id)) == [
        ("user.superadmin.granted", {}),
        ("user.superadmin.revoked", {}),
    ]


def test_update_user_not_found(api: ApiEnv) -> None:
    _superadmin(api)

    response = _patch_user(api, uuid.uuid4(), status="suspended")

    assert _error(response) == (404, "not_found")


def test_update_user_requires_a_field(api: ApiEnv) -> None:
    admin = _superadmin(api)

    response = _patch_user(api, admin.id)

    assert _error(response) == (422, "validation_error")


def test_cannot_remove_last_superadmin(empty_api: ApiEnv) -> None:
    api = empty_api
    first = _superadmin(api)
    suspended_admin = api.create_user(superadmin=True, status=UserStatus.SUSPENDED)

    alone = _patch_user(api, first.id, is_superadmin=False)
    second = api.create_user(superadmin=True)
    shared = _patch_user(api, first.id, is_superadmin=False)
    api.login(second)
    last = _patch_user(api, second.id, is_superadmin=False)

    # A suspended superadmin does not count: the instance needs one who can log in.
    assert _error(alone) == (409, "last_superadmin")
    assert shared.status_code == 200
    assert shared.json()["is_superadmin"] is False
    assert _error(last) == (409, "last_superadmin")
    assert api.user(second.id).is_superadmin is True
    assert api.user(suspended_admin.id).is_superadmin is True


def test_suspend_superadmin_keeps_another_active(api: ApiEnv) -> None:
    _superadmin(api)
    other = api.create_user(superadmin=True)

    response = _patch_user(api, other.id, status="suspended")

    assert response.json()["status"] == "suspended"
    assert response.json()["is_superadmin"] is True


def test_admin_audit_lists_instance_events_only(api: ApiEnv) -> None:
    admin = _superadmin(api)
    _create_workspace(api, name=unique("Audited"), owner_email=_email())

    invited = api.client.get(
        "/v1/admin/audit", params={"action": "membership.invited", "actor_user_id": str(admin.id)}
    )
    logins = api.client.get(
        "/v1/admin/audit",
        params={"action": "auth.login.succeeded", "actor_user_id": str(admin.id), "limit": 1},
    )

    # The invitation is a workspace event: it lives in that workspace's trail, not here.
    assert invited.status_code == 200
    assert invited.json()["total"] == 0
    assert logins.json()["total"] == 1
    assert logins.json()["items"][0]["action"] == "auth.login.succeeded"


@pytest.mark.parametrize("resource", ["workspaces", "users"])
def test_admin_listing_without_query_returns_everything(api: ApiEnv, resource: str) -> None:
    _superadmin(api)
    api.create_workspace({})

    response = api.client.get(f"/v1/admin/{resource}", params={"limit": 1})

    # Shared database: only lower bounds are stable.
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert len(response.json()["items"]) == 1
