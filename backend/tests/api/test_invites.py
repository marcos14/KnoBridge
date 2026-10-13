"""Invitation routes: create, list, revoke and resend (workspace) and preview/accept (public)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx2 as httpx
import pytest
from api_support import PASSWORD, ApiEnv, SeededUser, unique
from sqlalchemy import false

from knobridge.tenancy import invitations as invitations_module
from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a long enough passphrase"  # noqa: S105 - test value
INVITATION_TTL = timedelta(days=7)  # settings default


def _guest_email() -> str:
    return f"{unique('guest')}@example.test"


def _owner_workspace(api: ApiEnv, *, name: str = "Acme") -> tuple[SeededUser, uuid.UUID]:
    owner = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER}, name=name)
    api.login(owner)
    return owner, workspace_id


def _invite(
    api: ApiEnv, workspace_id: uuid.UUID, email: str, role: str = "viewer"
) -> httpx.Response:
    return api.client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        json={"email": email, "role": role},
        headers=api.csrf_headers(),
    )


def _invited_token(api: ApiEnv, workspace_id: uuid.UUID, email: str, role: str = "viewer") -> str:
    response = _invite(api, workspace_id, email, role)
    assert response.status_code == 201, response.text
    return api.emailed_token(email)


def _accept(api: ApiEnv, token: str, body: dict[str, str] | None = None) -> httpx.Response:
    headers = api.csrf_headers() if api.client.cookies.get("knobridge_csrf") else {}
    return api.client.post(
        "/v1/invites/accept", json={"token": token, **(body or {})}, headers=headers
    )


def _preview(api: ApiEnv, token: str) -> httpx.Response:
    return api.client.post("/v1/invites/preview", json={"token": token})


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def test_invite_concurrent_duplicate_answers_conflict(
    api: ApiEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    first_token = _invited_token(api, workspace_id, email)
    # Simulate the race: the second request's lookup ran before the first one committed, so
    # it does not see the pending invitation and only the unique index stops the insert.
    unseen = invitations_module.pending_invitations().where(false())
    monkeypatch.setattr(invitations_module, "pending_invitations", lambda: unseen)

    response = _invite(api, workspace_id, email, "editor")

    assert _error(response) == (409, "invitation_pending")
    assert len(api.emails.sent_to(email)) == 1
    monkeypatch.undo()
    assert _preview(api, first_token).json()["role"] == "viewer"  # the first one stands


def test_invite_public_routes_require_token_in_body(api: ApiEnv) -> None:
    preview = api.client.post("/v1/invites/preview", json={})
    accept = api.client.post("/v1/invites/accept", json={"token": ""})

    assert _error(preview) == (422, "validation_error")
    assert _error(accept) == (422, "validation_error")


def test_invite_sends_email_with_token(api: ApiEnv) -> None:
    owner, workspace_id = _owner_workspace(api, name="Acme Support")
    email = _guest_email()

    response = _invite(api, workspace_id, email.upper(), "editor")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["role"] == "editor"
    assert body["invited_by_user_id"] == str(owner.id)
    assert body["expired"] is False
    [sent] = api.emails.sent_to(email)
    assert "/accept-invitation?token=" in sent.text
    assert "Acme Support" in sent.text
    assert api.emailed_token(email)
    assert ("membership.invited", {"role": "editor", "product_levels": []}) in (
        api.workspace_audit(workspace_id)
    )


def test_invite_lists_pending_invitations(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    first, second = _guest_email(), _guest_email()
    _invited_token(api, workspace_id, first)
    _invited_token(api, workspace_id, second)

    response = api.client.get(f"/v1/workspaces/{workspace_id}/invites", params={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["email"] in {first, second}


def test_admin_cannot_invite_owner(api: ApiEnv) -> None:
    owner = api.create_user()
    admin = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER, admin.id: Role.ADMIN})
    api.login(admin)

    response = _invite(api, workspace_id, _guest_email(), "owner")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_not_allowed"
    assert response.json()["error"]["details"] == {"max_role": "admin"}
    assert api.emails.sent == []


def test_invite_existing_member_conflicts(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    member = api.create_user()
    api.add_member(workspace_id, member.id, Role.VIEWER)

    response = _invite(api, workspace_id, member.email)

    assert _error(response) == (409, "already_member")


def test_invite_requires_csrf(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)

    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/invites", json={"email": _guest_email(), "role": "viewer"}
    )

    assert _error(response) == (403, "csrf_failed")


def test_invite_validates_email(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)

    response = _invite(api, workspace_id, "not-an-email")

    assert _error(response) == (422, "validation_error")


def test_reinvite_replaces_previous_invitation(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    old_token = _invited_token(api, workspace_id, email, "viewer")

    new_token = _invited_token(api, workspace_id, email, "editor")

    assert _error(_preview(api, old_token)) == (400, "invalid_token")
    assert _preview(api, new_token).json()["role"] == "editor"
    listing = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()
    assert [item["email"] for item in listing["items"]] == [email]
    assert ("membership.invitation.revoked", {"replaced": True}) in api.workspace_audit(
        workspace_id
    )


def test_revoke_invite_kills_link(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    token = _invited_token(api, workspace_id, email)
    invitation_id = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["items"][0][
        "id"
    ]
    path = f"/v1/workspaces/{workspace_id}/invites/{invitation_id}"

    revoked = api.client.delete(path, headers=api.csrf_headers())
    again = api.client.delete(path, headers=api.csrf_headers())

    assert revoked.status_code == 204
    assert _error(again) == (404, "not_found")
    assert _error(_preview(api, token)) == (400, "invalid_token")
    assert api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["total"] == 0
    assert ("membership.invitation.revoked", {"replaced": False}) in api.workspace_audit(
        workspace_id
    )


def test_resend_invite_issues_new_link(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    old_token = _invited_token(api, workspace_id, email)
    first = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["items"][0]
    api.clock.advance(timedelta(days=1))

    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/invites/{first['id']}/resend", headers=api.csrf_headers()
    )

    assert response.status_code == 200
    assert response.json()["expires_at"] > first["expires_at"]
    new_token = api.emailed_token(email)
    assert new_token != old_token
    assert len(api.emails.sent_to(email)) == 2
    assert _error(_preview(api, old_token)) == (400, "invalid_token")
    assert _preview(api, new_token).status_code == 200
    assert ("membership.invitation.resent", {}) in api.workspace_audit(workspace_id)


def test_admin_cannot_revoke_owner_invitation(api: ApiEnv) -> None:
    owner, workspace_id = _owner_workspace(api)
    admin = api.create_user()
    api.add_member(workspace_id, admin.id, Role.ADMIN)
    _invited_token(api, workspace_id, _guest_email(), "owner")
    invitation_id = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["items"][0][
        "id"
    ]
    api.login(admin)

    response = api.client.delete(
        f"/v1/workspaces/{workspace_id}/invites/{invitation_id}", headers=api.csrf_headers()
    )

    assert _error(response) == (403, "role_not_allowed")
    assert owner.id in api.roles(workspace_id)


def test_invite_token_expired(api: ApiEnv) -> None:
    owner, workspace_id = _owner_workspace(api)
    email = _guest_email()
    token = _invited_token(api, workspace_id, email)
    api.clock.advance(INVITATION_TTL)
    api.login(owner)  # the idle session expired too

    preview = _preview(api, token)
    listing = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()
    api.client.cookies.clear()
    accepted = _accept(api, token, {"name": "Guest", "password": NEW_PASSWORD})

    assert _error(preview) == (400, "invalid_token")
    assert _error(accepted) == (400, "invalid_token")
    assert listing["items"][0]["expired"] is True


def test_preview_invite_shows_workspace_and_account_state(api: ApiEnv) -> None:
    owner, workspace_id = _owner_workspace(api, name="Preview Co")
    existing = api.create_user()
    new_token = _invited_token(api, workspace_id, _guest_email(), "editor")
    existing_token = _invited_token(api, workspace_id, existing.email)
    api.client.cookies.clear()

    new = _preview(api, new_token).json()
    known = _preview(api, existing_token).json()

    assert new["workspace_id"] == str(workspace_id)
    assert new["workspace_name"] == "Preview Co"
    assert new["role"] == "editor"
    assert new["inviter_name"] == "Test User"
    assert new["user_exists"] is False
    assert known["user_exists"] is True
    assert known["email"] == existing.email
    assert owner.id in api.roles(workspace_id)


def test_preview_invite_of_suspended_workspace_is_invalid(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    token = _invited_token(api, workspace_id, _guest_email())
    api.set_workspace_status(workspace_id, WorkspaceStatus.SUSPENDED)

    assert _error(_preview(api, token)) == (400, "invalid_token")


def test_accept_invite_creates_user(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    token = _invited_token(api, workspace_id, email, "editor")
    api.client.cookies.clear()

    response = _accept(api, token, {"name": "  New Person ", "password": NEW_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == email
    assert body["user"]["name"] == "New Person"
    assert body["user"]["email_verified_at"] is not None
    assert [(w["id"], w["role"]) for w in body["workspaces"]] == [(str(workspace_id), "editor")]
    assert api.client.get("/v1/me").json()["user"]["email"] == email  # logged in by cookies
    user_id = uuid.UUID(body["user"]["id"])
    assert api.roles(workspace_id)[user_id] == Role.EDITOR
    assert ("user.created", {"via": "invitation"}) in api.audit_actions(user_id)
    accepted = [e for e in api.workspace_audit(workspace_id) if e[0].endswith(".accepted")]
    assert accepted[0][1]["new_account"] is True
    api.client.cookies.clear()
    assert _error(_accept(api, token, {"name": "X", "password": NEW_PASSWORD})) == (
        400,
        "invalid_token",
    )


def test_accept_invite_new_user_requires_name_and_password(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    token = _invited_token(api, workspace_id, _guest_email())
    api.client.cookies.clear()

    missing = _accept(api, token, {"name": "Only Name"})
    weak = _accept(api, token, {"name": "Guest", "password": "short"})

    assert _error(missing) == (422, "account_details_required")
    assert _error(weak) == (422, "weak_password")
    assert _preview(api, token).status_code == 200  # the link survives


def test_accept_invite_existing_user_joins(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    guest = api.create_user()
    token = _invited_token(api, workspace_id, guest.email, "viewer")
    api.login(guest)

    response = _accept(api, token)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(guest.id)
    assert body["user"]["email_verified_at"] is not None
    assert str(workspace_id) in [w["id"] for w in body["workspaces"]]
    assert api.roles(workspace_id)[guest.id] == Role.VIEWER
    assert api.user(guest.id).password_hash is not None
    assert api.hasher.verify(api.user(guest.id).password_hash or "", PASSWORD)


def test_accept_invite_existing_user_requires_login(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    guest = api.create_user()
    token = _invited_token(api, workspace_id, guest.email)
    api.client.cookies.clear()

    response = _accept(api, token)

    assert _error(response) == (401, "login_required")
    assert _preview(api, token).status_code == 200


def test_accept_invite_with_other_account_is_forbidden(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    guest, intruder = api.create_user(), api.create_user()
    token = _invited_token(api, workspace_id, guest.email)
    api.login(intruder)

    response = _accept(api, token)

    assert _error(response) == (403, "invitation_email_mismatch")
    assert intruder.id not in api.roles(workspace_id)


def test_accept_invite_logged_in_requires_csrf(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    guest = api.create_user()
    token = _invited_token(api, workspace_id, guest.email)
    api.login(guest)

    response = api.client.post("/v1/invites/accept", json={"token": token})

    assert _error(response) == (403, "csrf_failed")


def test_accept_invite_when_already_member_conflicts(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    guest = api.create_user()
    token = _invited_token(api, workspace_id, guest.email)
    api.add_member(workspace_id, guest.id, Role.EDITOR)
    api.login(guest)

    response = _accept(api, token)

    assert _error(response) == (409, "already_member")
    assert api.roles(workspace_id)[guest.id] == Role.EDITOR


def test_accept_invite_ignores_dead_session_cookie(api: ApiEnv) -> None:
    _, workspace_id = _owner_workspace(api)
    email = _guest_email()
    token = _invited_token(api, workspace_id, email)
    api.client.cookies.clear()
    api.client.cookies.set("knobridge_session", "not-a-live-session")

    response = _accept(api, token, {"name": "Guest", "password": NEW_PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


def test_invites_isolated_by_workspace(api: ApiEnv) -> None:
    _, workspace_a = _owner_workspace(api)
    _invited_token(api, workspace_a, _guest_email())
    invitation_a = api.client.get(f"/v1/workspaces/{workspace_a}/invites").json()["items"][0]
    other_owner = api.create_user()
    workspace_b = api.create_workspace({other_owner.id: Role.OWNER})
    api.login(other_owner)

    listing_b = api.client.get(f"/v1/workspaces/{workspace_b}/invites").json()
    revoke = api.client.delete(
        f"/v1/workspaces/{workspace_b}/invites/{invitation_a['id']}", headers=api.csrf_headers()
    )
    resend = api.client.post(
        f"/v1/workspaces/{workspace_b}/invites/{invitation_a['id']}/resend",
        headers=api.csrf_headers(),
    )
    list_a = api.client.get(f"/v1/workspaces/{workspace_a}/invites")

    assert listing_b["total"] == 0
    assert _error(revoke) == (404, "not_found")
    assert _error(resend) == (404, "not_found")
    assert _error(list_a) == (404, "not_found")
