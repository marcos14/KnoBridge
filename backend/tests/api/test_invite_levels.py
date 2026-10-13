"""Invitations with levels (``docs/specs/produtos-e-niveis.md``, "Convites com nível"): the
levels stored on the invitation, listed and audited, validated against the workspace's
products, and recorded as the member's levels when the invitation is accepted."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser, unique
from product_support import create_product, model_world, products_path

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

NEW_PASSWORD = "a long enough passphrase"  # noqa: S105 - test value


def _owner_world(api: ApiEnv) -> tuple[SeededUser, uuid.UUID, str, str]:
    """An owner logged in, with two products: ERP and Portal."""
    owner = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER})
    api.login(owner)
    model_world(api, workspace_id)
    erp = create_product(api, workspace_id, name="ERP")
    portal = create_product(api, workspace_id, name="Portal")
    return owner, workspace_id, erp, portal


def _invite(
    api: ApiEnv, workspace_id: uuid.UUID, email: str, levels: list[dict[str, object]]
) -> httpx.Response:
    return api.client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        json={"email": email, "role": "viewer", "product_levels": levels},
        headers=api.csrf_headers(),
    )


def _email() -> str:
    return f"{unique('guest')}@example.test"


def _member_levels(api: ApiEnv, workspace_id: uuid.UUID, user_id: str) -> list[object]:
    page = api.client.get(f"/v1/workspaces/{workspace_id}/member-levels").json()
    member = next(item for item in page["items"] if item["user_id"] == user_id)
    levels: list[object] = member["levels"]
    return levels


def test_invite_stores_lists_and_audits_levels(api: ApiEnv) -> None:
    _, workspace_id, erp, _portal = _owner_world(api)
    email = _email()

    created = _invite(api, workspace_id, email, [{"product_id": erp, "max_level": "support"}])
    listed = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["items"]

    assert created.status_code == 201, created.text
    expected = [{"product_id": erp, "max_level": "support"}]
    assert created.json()["product_levels"] == expected
    assert [item["product_levels"] for item in listed] == [expected]
    invited = [d for a, d in api.workspace_audit(workspace_id) if a == "membership.invited"]
    assert invited == [{"role": "viewer", "product_levels": expected}]


def test_invite_without_levels_has_none(api: ApiEnv) -> None:
    _, workspace_id, _erp, _portal = _owner_world(api)

    created = api.client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        json={"email": _email(), "role": "viewer"},
        headers=api.csrf_headers(),
    )

    assert created.status_code == 201
    assert created.json()["product_levels"] == []


def test_invite_refuses_products_of_other_workspaces(api: ApiEnv) -> None:
    _, other_workspace, foreign, _ = _owner_world(api)
    _, workspace_id, erp, _portal = _owner_world(api)
    missing = str(uuid.uuid4())
    assert other_workspace != workspace_id

    response = _invite(
        api,
        workspace_id,
        _email(),
        [
            {"product_id": erp, "max_level": "support"},
            {"product_id": foreign, "max_level": "support"},
            {"product_id": missing, "max_level": "end_user"},
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invite_product_invalid"
    assert response.json()["error"]["details"] == {"product_ids": sorted([foreign, missing])}
    assert api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["total"] == 0


@pytest.mark.parametrize(
    "levels",
    [
        "repeated",
        [{"product_id": "x", "max_level": "support"}],
        "unknown_level",
        "null_level",
        "too_many",
    ],
)
def test_invite_rejects_invalid_levels(api: ApiEnv, levels: object) -> None:
    _, workspace_id, erp, _portal = _owner_world(api)
    bodies: dict[str, object] = {
        "repeated": [
            {"product_id": erp, "max_level": "support"},
            {"product_id": erp, "max_level": "end_user"},
        ],
        "unknown_level": [{"product_id": erp, "max_level": "admin"}],
        "null_level": [{"product_id": erp, "max_level": None}],
        "too_many": [{"product_id": str(uuid.uuid4()), "max_level": "support"} for _ in range(201)],
    }
    body = bodies[levels] if isinstance(levels, str) else levels

    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/invites",
        json={"email": _email(), "role": "viewer", "product_levels": body},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_accept_records_levels_and_skips_deleted_products(api: ApiEnv) -> None:
    owner, workspace_id, erp, portal = _owner_world(api)
    email = _email()
    _invite(
        api,
        workspace_id,
        email,
        [
            {"product_id": erp, "max_level": "product_dev"},
            {"product_id": portal, "max_level": "support"},
        ],
    )
    token = api.emailed_token(email)
    deleted = api.client.delete(products_path(workspace_id, portal), headers=api.csrf_headers())
    api.client.cookies.clear()

    accepted = api.client.post(
        "/v1/invites/accept",
        json={"token": token, "name": "Guest", "password": NEW_PASSWORD},
    )

    assert deleted.status_code == 204
    assert accepted.status_code == 200, accepted.text
    workspace = accepted.json()["workspaces"][0]
    assert [
        (item["product_name"], item["max_level"], item["explicit"])
        for item in workspace["product_levels"]
    ] == [("ERP", "product_dev", True)]
    api.login(owner)
    assert _member_levels(api, workspace_id, accepted.json()["user"]["id"]) == [
        {"product_id": erp, "max_level": "product_dev", "explicit": True}
    ]


def test_reinvite_replaces_levels(api: ApiEnv) -> None:
    _, workspace_id, erp, portal = _owner_world(api)
    email = _email()
    _invite(api, workspace_id, email, [{"product_id": erp, "max_level": "support"}])

    again = _invite(api, workspace_id, email, [{"product_id": portal, "max_level": "end_user"}])
    listed = api.client.get(f"/v1/workspaces/{workspace_id}/invites").json()["items"]

    assert again.status_code == 201
    assert [item["product_levels"] for item in listed] == [
        [{"product_id": portal, "max_level": "end_user"}]
    ]
