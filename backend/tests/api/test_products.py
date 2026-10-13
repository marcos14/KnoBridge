"""Product routes: CRUD, roles (viewers see only active ones), validation, the name rule,
the default "no source" message, the reader's level, the transitional model from the level,
deletion with conversations, isolation and the provider-in-use rule."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, SeededUser
from chat_support import build_world, start
from product_support import (
    configure_level,
    create_provider,
    model_world,
    post_product,
    products_path,
)

from knobridge.products.models import DEFAULT_NO_SOURCE_MESSAGE
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    """A workspace whose first user (owner or admin) is logged in, with a configured level."""
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    api.login(users[0])
    model_world(api, workspace_id)
    return workspace_id, users


def _create(
    api: ApiEnv, workspace_id: uuid.UUID, *, name: str = "Support", **fields: object
) -> httpx.Response:
    return post_product(api, workspace_id, name=name, **fields)


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, product_id: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(
        products_path(workspace_id, product_id), json=body, headers=api.csrf_headers()
    )


def _delete(api: ApiEnv, workspace_id: uuid.UUID, product_id: str) -> httpx.Response:
    return api.client.delete(products_path(workspace_id, product_id), headers=api.csrf_headers())


def _error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def _names(response: httpx.Response) -> list[str]:
    return [item["name"] for item in response.json()["items"]]


def _product_events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [event for event in api.workspace_audit(workspace_id) if event[0].startswith("product.")]


def test_create_product_requires_editor(api: ApiEnv) -> None:
    workspace_id, (_owner, editor, viewer) = _team(api, Role.OWNER, Role.EDITOR, Role.VIEWER)
    api.login(viewer)

    refused = _create(api, workspace_id)
    api.login(editor)
    created = _create(api, workspace_id, description="Helps customers")

    assert _error(refused) == (403, "forbidden")
    assert refused.json()["error"]["details"] == {"required_role": "editor"}
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "name",
        "description",
        "instructions",
        "language",
        "tone",
        "no_source_message",
        "active",
        "collection_ids",
        "min_similarity",
        "ticket_webhook_url",
        "ticket_webhook_configured",
        "ticket_webhook_secret_created_at",
        "my_max_level",
        "created_at",
        "updated_at",
    }
    assert body["name"] == "Support"
    assert body["description"] == "Helps customers"
    assert body["instructions"] == ""
    assert body["language"] == "pt-BR"
    assert body["tone"] == "neutral"
    assert body["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE
    assert body["active"] is True
    assert body["collection_ids"] == []
    assert body["min_similarity"] == 0.35
    assert body["my_max_level"] == "end_user"
    assert _product_events(api, workspace_id) == [
        ("product.created", {"name": "Support", "collection_ids": []})
    ]


def test_product_custom_fields_stored(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)

    response = _create(
        api,
        workspace_id,
        instructions="  You answer about the ERP.  ",
        language="en-US",
        tone="formal",
        no_source_message="Não sei; quer abrir um chamado?",
        active=False,
    )

    body = response.json()
    assert response.status_code == 201
    assert body["instructions"] == "You answer about the ERP."
    assert body["language"] == "en-US"
    assert body["tone"] == "formal"
    assert body["no_source_message"] == "Não sei; quer abrir um chamado?"
    assert body["active"] is False
    assert body["my_max_level"] == "product_dev"


@pytest.mark.parametrize("message", ["", "   ", None])
def test_product_empty_no_source_message_uses_default(api: ApiEnv, message: str | None) -> None:
    workspace_id, _ = _team(api, Role.OWNER)

    response = _create(api, workspace_id, no_source_message=message)

    assert response.json()["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE


@pytest.mark.parametrize("name", ["ERP:end_user", "ERP:support", "Portal:product_dev"])
def test_product_name_cannot_end_in_a_level(api: ApiEnv, name: str) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    product_id = _create(api, workspace_id, name="ERP").json()["id"]

    created = _create(api, workspace_id, name=name)
    renamed = _patch(api, workspace_id, product_id, {"name": name})
    allowed = _create(api, workspace_id, name="ERP:end_user v2")

    assert _error(created) == (422, "product_name_invalid")
    assert _error(renamed) == (422, "product_name_invalid")
    assert allowed.status_code == 201


def test_product_needs_a_configured_level(api: ApiEnv) -> None:
    """Transitional (plan 0009): the chat still reads the model from the product."""
    owner = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER})
    api.login(owner)
    provider_id = create_provider(api, workspace_id)

    refused = _create(api, workspace_id)
    configure_level(api, workspace_id, provider_id, level="support", model="gpt-4.1-mini")
    created = _create(api, workspace_id)

    assert _error(refused) == (409, "level_not_configured")
    assert refused.json()["error"]["details"] == {"level": "product_dev"}
    assert created.status_code == 201


def test_viewer_lists_only_active(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    _create(api, workspace_id, name="Active")
    inactive_id = _create(api, workspace_id, name="Draft", active=False).json()["id"]
    owner_list = api.client.get(products_path(workspace_id))
    owner_get = api.client.get(products_path(workspace_id, inactive_id))
    api.login(viewer)

    viewer_list = api.client.get(products_path(workspace_id))
    viewer_get = api.client.get(products_path(workspace_id, inactive_id))

    assert _names(owner_list) == ["Active", "Draft"]
    assert owner_list.json()["total"] == 2
    assert owner_get.status_code == 200
    assert _names(viewer_list) == ["Active"]
    assert viewer_list.json()["total"] == 1
    assert _error(viewer_get) == (404, "not_found")


def test_viewer_reads_active_product_with_own_level(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    created = _create(api, workspace_id).json()
    api.login(viewer)

    response = api.client.get(products_path(workspace_id, created["id"]))

    assert response.status_code == 200
    assert response.json() == {**created, "my_max_level": "end_user"}
    assert created["my_max_level"] == "product_dev"


def test_my_max_level_follows_the_recorded_value(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    raised = _create(api, workspace_id, name="ERP").json()["id"]
    _create(api, workspace_id, name="Portal")
    recorded = api.client.put(
        f"/v1/workspaces/{workspace_id}/members/{viewer.id}/product-levels",
        json={"levels": [{"product_id": raised, "max_level": "support"}]},
        headers=api.csrf_headers(),
    )
    api.login(viewer)

    listed = api.client.get(products_path(workspace_id)).json()["items"]
    single = api.client.get(products_path(workspace_id, raised)).json()

    assert recorded.status_code == 200
    assert [(item["name"], item["my_max_level"]) for item in listed] == [
        ("ERP", "support"),
        ("Portal", "end_user"),
    ]
    assert single["my_max_level"] == "support"


def test_viewer_cannot_change_products(api: ApiEnv) -> None:
    workspace_id, (_owner, viewer) = _team(api, Role.OWNER, Role.VIEWER)
    product_id = _create(api, workspace_id).json()["id"]
    api.login(viewer)

    responses = [
        _patch(api, workspace_id, product_id, {"name": "Mine"}),
        _delete(api, workspace_id, product_id),
    ]

    for response in responses:
        assert _error(response) == (403, "forbidden")


def test_products_listed_by_name_and_paginated(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.ADMIN)
    for name in ("Zeta", "Alpha", "Mid"):
        assert _create(api, workspace_id, name=name).status_code == 201

    full = api.client.get(products_path(workspace_id))
    page = api.client.get(products_path(workspace_id), params={"limit": 1, "offset": 1})

    assert _names(full) == ["Alpha", "Mid", "Zeta"]
    assert page.json() == {
        "items": [full.json()["items"][1]],
        "total": 3,
        "limit": 1,
        "offset": 1,
    }


def test_product_updated_and_audited(api: ApiEnv) -> None:
    workspace_id, (_admin, editor) = _team(api, Role.ADMIN, Role.EDITOR)
    api.login(editor)
    product_id = _create(api, workspace_id, no_source_message="Custom").json()["id"]

    response = _patch(
        api,
        workspace_id,
        product_id,
        {
            "name": "Renamed",
            "instructions": "Secret instructions",
            "tone": "friendly",
            "active": False,
            "no_source_message": None,
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["name"] == "Renamed"
    assert body["instructions"] == "Secret instructions"
    assert body["tone"] == "friendly"
    assert body["active"] is False
    assert body["no_source_message"] == DEFAULT_NO_SOURCE_MESSAGE
    updated = (
        "product.updated",
        {
            "name": "Renamed",
            "fields": ["name", "instructions", "tone", "no_source_message", "active"],
        },
    )
    assert updated in _product_events(api, workspace_id)
    assert "Secret instructions" not in str(api.workspace_audit(workspace_id))


def test_product_update_keeps_omitted_fields(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    created = _create(api, workspace_id, no_source_message="Custom", description="Desc").json()

    response = _patch(api, workspace_id, created["id"], {"language": "es"})

    body = response.json()
    assert body["language"] == "es"
    assert body["no_source_message"] == "Custom"
    assert body["description"] == "Desc"


def test_product_update_without_changes_is_not_audited(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    created = _create(api, workspace_id).json()

    response = _patch(
        api, workspace_id, created["id"], {"name": "Support", "no_source_message": ""}
    )

    assert response.status_code == 200
    assert response.json() == created
    assert [action for action, _ in _product_events(api, workspace_id)] == ["product.created"]


def test_product_name_taken(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    _create(api, workspace_id, name="Taken")
    other_id = _create(api, workspace_id, name="Other").json()["id"]

    duplicate = _create(api, workspace_id, name="Taken")
    renamed = _patch(api, workspace_id, other_id, {"name": "Taken"})

    assert _error(duplicate) == (409, "product_name_taken")
    assert _error(renamed) == (409, "product_name_taken")
    assert len(_product_events(api, workspace_id)) == 2


def test_product_deleted_with_its_conversations_and_audited(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    start(api, world)
    start(api, world)

    response = _delete(api, world.workspace_id, world.assistant_id)
    again = _delete(api, world.workspace_id, world.assistant_id)

    assert response.status_code == 204
    assert _error(again) == (404, "not_found")
    assert api.client.get(products_path(world.workspace_id)).json()["total"] == 0
    conversations = api.client.get(f"/v1/workspaces/{world.workspace_id}/conversations")
    assert conversations.json()["total"] == 0
    assert (
        "product.deleted",
        {"name": "Suporte", "conversation_count": 2},
    ) in _product_events(api, world.workspace_id)


def test_unknown_product_not_found(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    unknown = str(uuid.uuid4())

    responses = [
        api.client.get(products_path(workspace_id, unknown)),
        _patch(api, workspace_id, unknown, {"name": "X"}),
        _delete(api, workspace_id, unknown),
    ]

    for response in responses:
        assert _error(response) == (404, "not_found")


def test_products_isolated_by_workspace(api: ApiEnv) -> None:
    editor = api.create_user()
    outsider = api.create_user()
    workspace_a = api.create_workspace({editor.id: Role.ADMIN})
    workspace_b = api.create_workspace({editor.id: Role.ADMIN, outsider.id: Role.OWNER})
    api.login(editor)
    model_world(api, workspace_a)
    model_world(api, workspace_b)
    product_a = _create(api, workspace_a, name="Only A").json()["id"]
    _create(api, workspace_b, name="Only B")

    listed_b = api.client.get(products_path(workspace_b))
    read_via_b = api.client.get(products_path(workspace_b, product_a))
    patched_via_b = _patch(api, workspace_b, product_a, {"name": "Stolen"})
    deleted_via_b = _delete(api, workspace_b, product_a)
    api.login(outsider)
    outsider_list = api.client.get(products_path(workspace_a))
    outsider_read = api.client.get(products_path(workspace_a, product_a))

    assert _names(listed_b) == ["Only B"]
    assert _error(read_via_b) == (404, "not_found")
    assert _error(patched_via_b) == (404, "not_found")
    assert _error(deleted_via_b) == (404, "not_found")
    assert _error(outsider_list) == (404, "not_found")
    assert _error(outsider_read) == (404, "not_found")
    api.login(editor)
    assert _names(api.client.get(products_path(workspace_a))) == ["Only A"]


def test_product_writes_require_csrf(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    product_id = _create(api, workspace_id).json()["id"]

    responses = [
        api.client.post(products_path(workspace_id), json={"name": "X"}),
        api.client.patch(products_path(workspace_id, product_id), json={"name": "Y"}),
        api.client.delete(products_path(workspace_id, product_id)),
    ]

    for response in responses:
        assert _error(response) == (403, "csrf_failed")


@pytest.mark.parametrize(
    "fields",
    [
        {"name": "   "},
        {"name": "n" * 201},
        {"description": "d" * 1001},
        {"instructions": "p" * 20001},
        {"language": "portuguese brazil"},
        {"language": "p"},
        {"tone": "sarcastic"},
        {"no_source_message": "m" * 2001},
        {"collection_ids": [str(uuid.uuid4()) for _ in range(101)]},
    ],
)
def test_product_create_rejects_invalid_body(api: ApiEnv, fields: dict[str, object]) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    body = {"name": "Valid", **fields}

    response = api.client.post(products_path(workspace_id), json=body, headers=api.csrf_headers())

    assert _error(response) == (422, "validation_error")


@pytest.mark.parametrize("body", [{}, {"tone": "sarcastic"}, {"min_similarity": 2}])
def test_product_update_rejects_invalid_body(api: ApiEnv, body: dict[str, object]) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    product_id = _create(api, workspace_id).json()["id"]

    response = _patch(api, workspace_id, product_id, body)

    assert _error(response) == (422, "validation_error")


def test_old_assistant_routes_are_gone(api: ApiEnv) -> None:
    workspace_id, _ = _team(api, Role.OWNER)
    product_id = _create(api, workspace_id).json()["id"]
    base = f"/v1/workspaces/{workspace_id}/assistants"

    listed = api.client.get(base)
    read = api.client.get(f"{base}/{product_id}")

    assert listed.status_code == 404
    assert read.status_code == 404


def test_provider_in_use_by_product_cannot_be_deleted(api: ApiEnv) -> None:
    owner = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER})
    api.login(owner)
    provider_id = create_provider(api, workspace_id)
    configure_level(api, workspace_id, provider_id)
    product_id = _create(api, workspace_id).json()["id"]
    api.client.patch(
        f"/v1/workspaces/{workspace_id}/levels/product_dev",
        json={"provider_id": None, "model": None},
        headers=api.csrf_headers(),
    )
    provider_path = f"/v1/workspaces/{workspace_id}/providers/{provider_id}"

    refused = api.client.delete(provider_path, headers=api.csrf_headers())
    _delete(api, workspace_id, product_id)
    allowed = api.client.delete(provider_path, headers=api.csrf_headers())

    assert _error(refused) == (409, "provider_in_use")
    assert allowed.status_code == 204
    provider_events = [
        action for action, _ in api.workspace_audit(workspace_id) if action.startswith("provider.")
    ]
    assert provider_events.count("provider.deleted") == 1
