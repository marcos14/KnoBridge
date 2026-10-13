"""Maximum level per member and product: the member x product table (defaults by role,
recorded values, filters, statements), recording and removing values with their audit, the
role rule, product and body validation, roles, CSRF and isolation."""

from __future__ import annotations

import uuid
from typing import Any

import httpx2 as httpx
import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv, SeededUser
from product_support import create_product, model_world, products_path

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _world(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser], str, str]:
    """A workspace whose first user (owner or admin) is logged in, with products ERP and
    Portal (Portal inactive)."""
    users = [api.create_user(name=f"User {index}") for index in range(len(roles))]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    api.login(users[0])
    model_world(api, workspace_id)
    erp = create_product(api, workspace_id, name="ERP")
    portal = create_product(api, workspace_id, name="Portal", active=False)
    return workspace_id, users, erp, portal


def _table(api: ApiEnv, workspace_id: uuid.UUID, **params: str | int) -> httpx.Response:
    return api.client.get(f"/v1/workspaces/{workspace_id}/member-levels", params=params)


def _put(
    api: ApiEnv, workspace_id: uuid.UUID, user_id: uuid.UUID, levels: object
) -> httpx.Response:
    return api.client.put(
        f"/v1/workspaces/{workspace_id}/members/{user_id}/product-levels",
        json={"levels": levels},
        headers=api.csrf_headers(),
    )


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _levels(item: dict[str, Any]) -> list[tuple[str, bool]]:
    # ``Any``: a decoded JSON object.
    return [(level["max_level"], level["explicit"]) for level in item["levels"]]


def test_table_has_every_product_and_role_defaults(api: ApiEnv) -> None:
    roles = (Role.OWNER, Role.ADMIN, Role.EDITOR, Role.VIEWER)
    workspace_id, users, erp, portal = _world(api, *roles)

    response = _table(api, workspace_id, sort="role")

    assert response.status_code == 200
    body = response.json()
    assert body["products"] == [
        {"id": erp, "name": "ERP", "active": True},
        {"id": portal, "name": "Portal", "active": False},
    ]
    assert body["total"] == 4
    assert (body["limit"], body["offset"]) == (50, 0)
    items = body["items"]
    assert [item["user_id"] for item in items] == [str(user.id) for user in users]
    assert set(items[0]) == {"user_id", "name", "email", "role", "levels"}
    assert items[0]["levels"][0] == {
        "product_id": erp,
        "max_level": "product_dev",
        "explicit": False,
    }
    assert [_levels(item) for item in items] == [
        [("product_dev", False)] * 2,
        [("product_dev", False)] * 2,
        [("end_user", False)] * 2,
        [("end_user", False)] * 2,
    ]


def test_recorded_levels_override_the_role_both_ways(api: ApiEnv) -> None:
    workspace_id, (_owner, admin, viewer), erp, portal = _world(
        api, Role.OWNER, Role.ADMIN, Role.VIEWER
    )

    raised = _put(api, workspace_id, viewer.id, [{"product_id": erp, "max_level": "support"}])
    lowered = _put(
        api,
        workspace_id,
        admin.id,
        [
            {"product_id": erp, "max_level": "end_user"},
            {"product_id": portal, "max_level": "support"},
        ],
    )

    assert raised.status_code == 200, raised.text
    assert raised.json()["user_id"] == str(viewer.id)
    assert raised.json()["role"] == "viewer"
    assert _levels(raised.json()) == [("support", True), ("end_user", False)]
    assert _levels(lowered.json()) == [("end_user", True), ("support", True)]
    table = {item["user_id"]: item for item in _table(api, workspace_id).json()["items"]}
    assert _levels(table[str(viewer.id)]) == [("support", True), ("end_user", False)]
    events = [d for a, d in api.workspace_audit(workspace_id) if a == "member_level.updated"]
    assert {
        "user_id": str(viewer.id),
        "changes": [{"product_id": erp, "from": None, "to": "support"}],
    } in events
    assert len(events) == 2


def test_recorded_level_does_not_follow_the_role(api: ApiEnv) -> None:
    workspace_id, (_owner, editor, viewer), erp, _portal = _world(
        api, Role.OWNER, Role.EDITOR, Role.VIEWER
    )
    _put(api, workspace_id, editor.id, [{"product_id": erp, "max_level": "support"}])

    for user in (editor, viewer):
        promoted = api.client.patch(
            f"/v1/workspaces/{workspace_id}/members/{user.id}",
            json={"role": "admin"},
            headers=api.csrf_headers(),
        )
        assert promoted.status_code == 200
    table = {item["user_id"]: item for item in _table(api, workspace_id).json()["items"]}

    assert _levels(table[str(editor.id)]) == [("support", True), ("product_dev", False)]
    assert _levels(table[str(viewer.id)]) == [("product_dev", False)] * 2


def test_null_removes_the_recorded_value_and_unchanged_is_not_audited(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer), erp, portal = _world(api, Role.OWNER, Role.VIEWER)
    _put(api, workspace_id, viewer.id, [{"product_id": erp, "max_level": "product_dev"}])

    same = _put(
        api,
        workspace_id,
        viewer.id,
        [
            {"product_id": erp, "max_level": "product_dev"},
            {"product_id": portal, "max_level": None},
        ],
    )
    changed = _put(api, workspace_id, viewer.id, [{"product_id": erp, "max_level": "support"}])
    removed = _put(api, workspace_id, viewer.id, [{"product_id": erp, "max_level": None}])

    assert _levels(same.json()) == [("product_dev", True), ("end_user", False)]
    assert _levels(changed.json()) == [("support", True), ("end_user", False)]
    assert _levels(removed.json()) == [("end_user", False)] * 2
    events = [d for a, d in api.workspace_audit(workspace_id) if a == "member_level.updated"]
    changes = [event["changes"] for event in events]
    assert len(changes) == 3
    assert [{"product_id": erp, "from": "product_dev", "to": "support"}] in changes
    assert [{"product_id": erp, "from": "support", "to": None}] in changes


def test_admin_cannot_edit_an_owner(api: ApiEnv) -> None:
    workspace_id, (owner, admin), erp, _portal = _world(api, Role.OWNER, Role.ADMIN)
    api.login(admin)

    refused = _put(api, workspace_id, owner.id, [{"product_id": erp, "max_level": "end_user"}])
    own = _put(api, workspace_id, admin.id, [{"product_id": erp, "max_level": "support"}])

    assert _error(refused) == (403, "role_not_allowed")
    assert refused.json()["error"]["details"] == {"max_role": "admin"}
    assert own.status_code == 200


def test_unknown_member_and_foreign_products(api: ApiEnv) -> None:
    _other, _, foreign, _ = _world(api, Role.OWNER)
    workspace_id, (_owner, viewer), erp, _portal = _world(api, Role.OWNER, Role.VIEWER)
    stranger = api.create_user()
    missing = str(uuid.uuid4())

    not_member = _put(api, workspace_id, stranger.id, [{"product_id": erp, "max_level": None}])
    invalid = _put(
        api,
        workspace_id,
        viewer.id,
        [
            {"product_id": erp, "max_level": "support"},
            {"product_id": foreign, "max_level": "support"},
            {"product_id": missing, "max_level": None},
        ],
    )

    assert _error(not_member) == (404, "not_found")
    assert _error(invalid) == (422, "member_level_product_invalid")
    assert invalid.json()["error"]["details"] == {"product_ids": sorted([foreign, missing])}
    table = {item["user_id"]: item for item in _table(api, workspace_id).json()["items"]}
    assert _levels(table[str(viewer.id)]) == [("end_user", False)] * 2


@pytest.mark.parametrize("case", ["empty", "repeated", "unknown_level", "too_many", "bad_id"])
def test_put_rejects_invalid_body(api: ApiEnv, case: str) -> None:
    workspace_id, (_owner, viewer), erp, _portal = _world(api, Role.OWNER, Role.VIEWER)
    bodies: dict[str, object] = {
        "empty": [],
        "repeated": [
            {"product_id": erp, "max_level": "support"},
            {"product_id": erp, "max_level": None},
        ],
        "unknown_level": [{"product_id": erp, "max_level": "owner"}],
        "too_many": [{"product_id": str(uuid.uuid4()), "max_level": None} for _ in range(201)],
        "bad_id": [{"product_id": "nope", "max_level": None}],
    }

    response = _put(api, workspace_id, viewer.id, bodies[case])

    assert _error(response) == (422, "validation_error")


def test_table_filters_paginates_and_keeps_statements_constant(api: ApiEnv) -> None:
    workspace_id, users, erp, _portal = _world(
        api, Role.OWNER, Role.VIEWER, Role.VIEWER, Role.VIEWER
    )
    for user in users[1:]:
        _put(api, workspace_id, user.id, [{"product_id": erp, "max_level": "support"}])

    page = _table(api, workspace_id, role="viewer", limit=2, offset=1, sort="-name")
    searched = _table(api, workspace_id, query=users[2].email)
    with count_statements(api) as one:
        assert len(_table(api, workspace_id, limit=1).json()["items"]) == 1
    with count_statements(api) as many:
        assert len(_table(api, workspace_id, limit=50).json()["items"]) == 4

    assert page.json()["total"] == 3
    assert [item["name"] for item in page.json()["items"]] == ["User 2", "User 1"]
    assert [item["user_id"] for item in searched.json()["items"]] == [str(users[2].id)]
    assert len(one) == len(many)


def test_deleting_a_product_or_member_drops_recorded_levels(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer, editor), erp, portal = _world(
        api, Role.OWNER, Role.VIEWER, Role.EDITOR
    )
    _put(
        api,
        workspace_id,
        viewer.id,
        [
            {"product_id": erp, "max_level": "support"},
            {"product_id": portal, "max_level": "support"},
        ],
    )
    _put(api, workspace_id, editor.id, [{"product_id": erp, "max_level": "product_dev"}])

    api.client.delete(products_path(workspace_id, portal), headers=api.csrf_headers())
    api.client.delete(
        f"/v1/workspaces/{workspace_id}/members/{editor.id}", headers=api.csrf_headers()
    )
    api.add_member(workspace_id, editor.id, Role.EDITOR)
    table = {item["user_id"]: item for item in _table(api, workspace_id).json()["items"]}

    assert _levels(table[str(viewer.id)]) == [("support", True)]
    assert _levels(table[str(editor.id)]) == [("end_user", False)]


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
def test_member_levels_require_admin(api: ApiEnv, role: Role) -> None:
    workspace_id, (_owner, member), erp, _portal = _world(api, Role.OWNER, role)
    api.login(member)

    table = _table(api, workspace_id)
    changed = _put(api, workspace_id, member.id, [{"product_id": erp, "max_level": "support"}])

    assert _error(table) == (403, "forbidden")
    assert _error(changed) == (403, "forbidden")


def test_put_requires_csrf(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer), erp, _portal = _world(api, Role.OWNER, Role.VIEWER)

    response = api.client.put(
        f"/v1/workspaces/{workspace_id}/members/{viewer.id}/product-levels",
        json={"levels": [{"product_id": erp, "max_level": "support"}]},
    )

    assert _error(response) == (403, "csrf_failed")


def test_member_levels_isolated_by_workspace(api: ApiEnv) -> None:
    workspace_a, (owner_a, viewer_a), erp_a, _ = _world(api, Role.OWNER, Role.VIEWER)
    workspace_b, (_owner_b, viewer_b), erp_b, _ = _world(api, Role.OWNER, Role.VIEWER)

    across = _put(api, workspace_b, viewer_a.id, [{"product_id": erp_b, "max_level": None}])
    foreign_product = _put(
        api, workspace_b, viewer_b.id, [{"product_id": erp_a, "max_level": "support"}]
    )
    table_b = _table(api, workspace_b).json()
    api.login(owner_a)
    read_b = _table(api, workspace_b)

    assert _error(across) == (404, "not_found")
    assert _error(foreign_product) == (422, "member_level_product_invalid")
    assert table_b["products"][0]["id"] == erp_b
    assert str(viewer_a.id) not in [item["user_id"] for item in table_b["items"]]
    assert _error(read_b) == (404, "not_found")
    assert workspace_a != workspace_b
