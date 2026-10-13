"""``product_levels`` in ``GET /v1/me`` (``docs/specs/autenticacao.md``, "Nível por produto no
``/v1/me``"): the user's level in each active product of each workspace, by name, recorded or
by role, empty for a suspended workspace, the superadmin's effective admin, workspaces the
user is not in, and a constant number of statements."""

from __future__ import annotations

import uuid

import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv, SeededUser
from product_support import create_product, model_world

from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration


def _workspace(
    api: ApiEnv, owner: SeededUser, members: dict[uuid.UUID, Role], *names: str, name: str = "W"
) -> tuple[uuid.UUID, list[str]]:
    """A workspace with ``owner`` and ``members`` and the named products, created by the owner."""
    workspace_id = api.create_workspace({owner.id: Role.OWNER, **members}, name=name)
    api.login(owner)
    model_world(api, workspace_id)
    return workspace_id, [create_product(api, workspace_id, name=item) for item in names]


def _levels(api: ApiEnv) -> dict[str, list[tuple[str, str, bool]]]:
    body = api.client.get("/v1/me").json()
    return {
        workspace["name"]: [
            (level["product_name"], level["max_level"], level["explicit"])
            for level in workspace["product_levels"]
        ]
        for workspace in body["workspaces"]
    }


def test_me_lists_levels_by_role_and_recorded_value(api: ApiEnv) -> None:
    owner, user = api.create_user(), api.create_user()
    alpha, (portal, _erp) = _workspace(
        api, owner, {user.id: Role.VIEWER}, "Portal", "ERP", name="Alpha"
    )
    inactive = create_product(api, alpha, name="Antigo", active=False)
    api.client.put(
        f"/v1/workspaces/{alpha}/members/{user.id}/product-levels",
        json={
            "levels": [
                {"product_id": portal, "max_level": "support"},
                {"product_id": inactive, "max_level": "support"},
            ]
        },
        headers=api.csrf_headers(),
    )
    _workspace(api, owner, {user.id: Role.ADMIN}, "Fiscal", name="Beta")
    api.login(user)

    body = api.client.get("/v1/me").json()

    alpha_item = body["workspaces"][0]
    assert alpha_item["product_levels"][1] == {
        "product_id": portal,
        "product_name": "Portal",
        "max_level": "support",
        "explicit": True,
    }
    assert _levels(api) == {
        "Alpha": [("ERP", "end_user", False), ("Portal", "support", True)],
        "Beta": [("Fiscal", "product_dev", False)],
    }


def test_me_suspended_workspace_has_no_levels(api: ApiEnv) -> None:
    owner = api.create_user()
    workspace_id, _ = _workspace(api, owner, {}, "ERP", name="Suspenso")
    api.set_workspace_status(workspace_id, WorkspaceStatus.SUSPENDED)

    assert _levels(api) == {"Suspenso": []}


def test_me_never_shows_other_workspaces(api: ApiEnv) -> None:
    owner, stranger = api.create_user(), api.create_user()
    _workspace(api, stranger, {}, "Segredo", name="Alheio")
    _workspace(api, owner, {}, "ERP", name="Meu")

    assert _levels(api) == {"Meu": [("ERP", "product_dev", False)]}


def test_me_superadmin_access_has_admin_levels(api: ApiEnv) -> None:
    owner = api.create_user()
    superadmin = api.create_user(superadmin=True)
    workspace_id, _ = _workspace(api, owner, {superadmin.id: Role.VIEWER}, "ERP", name="Cliente")
    api.login(superadmin)
    before = _levels(api)

    entered = api.client.post(
        f"/v1/admin/workspaces/{workspace_id}/enter", headers=api.csrf_headers()
    )

    assert before == {"Cliente": [("ERP", "end_user", False)]}
    assert entered.status_code == 200, entered.text
    entered_item = entered.json()["workspaces"][0]
    assert entered_item["access"] == "superadmin"
    assert [level["max_level"] for level in entered_item["product_levels"]] == ["product_dev"]
    assert _levels(api) == {"Cliente": [("ERP", "product_dev", False)]}


def test_me_statements_do_not_grow_with_workspaces(api: ApiEnv) -> None:
    owner = api.create_user()
    _workspace(api, owner, {}, "A", name="Um")
    with count_statements(api) as one:
        api.client.get("/v1/me")
    _workspace(api, owner, {}, "B", "C", name="Dois")
    _workspace(api, owner, {}, "D", name="Três")
    with count_statements(api) as many:
        api.client.get("/v1/me")

    assert len(one) == len(many)
