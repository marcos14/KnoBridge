"""Product list (search, filters, sort, viewers, statements, isolation) and the duplicate
action (``docs/specs/produtos-e-niveis.md``)."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import httpx2 as httpx
import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv
from index_support import IndexWorld, build_world, error_code, post_collection
from product_support import seed_level
from ticket_request_support import HOOK_URL, RequestOverrides, configured_world, install

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def hooks(api: ApiEnv) -> Generator[RequestOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _path(workspace_id: uuid.UUID, suffix: str = "") -> str:
    return f"/v1/workspaces/{workspace_id}/products{suffix}"


def _world(api: ApiEnv, *roles: Role) -> IndexWorld:
    world = build_world(api, *roles)
    seed_level(api, world.workspace_id, world.provider_id)
    return world


def _create(api: ApiEnv, world: IndexWorld, name: str, **fields: object) -> str:
    body: dict[str, object] = {"name": name, **fields}
    response = api.client.post(_path(world.workspace_id), json=body, headers=api.csrf_headers())
    assert response.status_code == 201, response.text
    product_id: str = response.json()["id"]
    return product_id


def _names(api: ApiEnv, workspace_id: uuid.UUID, **params: str | int) -> list[str]:
    response = api.client.get(_path(workspace_id), params=params)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def _duplicate(
    api: ApiEnv, workspace_id: uuid.UUID, product_id: str, body: object = None
) -> httpx.Response:
    return api.client.post(
        _path(workspace_id, f"/{product_id}/duplicate"), json=body, headers=api.csrf_headers()
    )


def test_product_list_search_filters_and_sort(api: ApiEnv) -> None:
    other = _world(api, Role.OWNER)
    _create(api, other, "Suporte fiscal")  # same name, another workspace
    world = _world(api, Role.EDITOR, Role.VIEWER)
    _create(api, world, "Suporte fiscal", collection_ids=[world.collection_id])
    _create(api, world, "Vendas", description="Pedidos e 100%_descontos", active=False)
    _create(api, world, "Estoque", description="Inventário")
    workspace_id = world.workspace_id

    assert _names(api, workspace_id, query="FISCAL") == ["Suporte fiscal"]
    assert _names(api, workspace_id, query="%_desc") == ["Vendas"]
    assert _names(api, workspace_id, query="INVENT") == ["Estoque"]
    assert _names(api, workspace_id, active="false") == ["Vendas"]
    assert _names(api, workspace_id, collection_id=world.collection_id) == ["Suporte fiscal"]
    ascending = _names(api, workspace_id)
    assert _names(api, workspace_id, sort="-name") == list(reversed(ascending))
    created = _names(api, workspace_id, sort="created_at")
    assert created == ["Suporte fiscal", "Vendas", "Estoque"]
    assert _names(api, workspace_id, sort="-updated_at") == list(reversed(created))
    assert _names(api, workspace_id, sort="-created_at") == list(reversed(created))
    api.login(world.users[1])  # viewers only see active ones, whatever the filter
    assert _names(api, workspace_id, active="false") == []
    assert _names(api, workspace_id, query="vendas") == []


def test_product_list_rejects_unknown_values(api: ApiEnv) -> None:
    world = _world(api, Role.OWNER)

    bad_sort = api.client.get(_path(world.workspace_id), params={"sort": "model"})
    long_query = api.client.get(_path(world.workspace_id), params={"query": "x" * 201})

    assert error_code(bad_sort) == (422, "validation_error")
    assert error_code(long_query) == (422, "validation_error")


def test_product_list_statements_do_not_grow_with_the_page(api: ApiEnv) -> None:
    world = _world(api, Role.OWNER)
    for number in range(3):
        _create(api, world, f"a{number}", collection_ids=[world.collection_id])
    params = {"query": "a", "collection_id": world.collection_id, "sort": "-created_at"}

    with count_statements(api) as one:
        assert len(_names(api, world.workspace_id, limit=1, **params)) == 1
    with count_statements(api) as many:
        assert len(_names(api, world.workspace_id, limit=50, **params)) == 3

    assert len(one) == len(many)


def test_duplicate_copies_configuration_and_audits(api: ApiEnv) -> None:
    world = _world(api, Role.EDITOR)
    second = post_collection(api, world.workspace_id, world.provider_id).json()["id"]
    original_id = _create(
        api,
        world,
        "Suporte",
        description="ERP",
        instructions="Responda curto.",
        language="en",
        tone="formal",
        no_source_message="Não sei.",
        active=False,
        min_similarity=0.5,
        collection_ids=[world.collection_id, second],
    )
    original = api.client.get(_path(world.workspace_id, f"/{original_id}")).json()

    response = _duplicate(api, world.workspace_id, original_id)

    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != original_id
    assert copy["name"] == "Suporte (cópia)"
    kept = set(original) - {"id", "name", "created_at", "updated_at", "collection_ids"}
    assert {key: copy[key] for key in kept} == {key: original[key] for key in kept}
    assert sorted(copy["collection_ids"]) == sorted(original["collection_ids"])
    created = (
        "product.created",
        {
            "name": "Suporte (cópia)",
            "collection_ids": copy["collection_ids"],
            "duplicated_from": original_id,
        },
    )
    # Both lists come ordered by collection id.
    assert created in api.workspace_audit(world.workspace_id)


def test_duplicate_numbers_copies_and_takes_a_given_name(api: ApiEnv) -> None:
    world = _world(api, Role.OWNER)
    original_id = _create(api, world, "Suporte")
    _create(api, world, "Suporte (cópia 2)")
    workspace_id = world.workspace_id

    first = _duplicate(api, workspace_id, original_id).json()["name"]
    third = _duplicate(api, workspace_id, original_id, {}).json()["name"]
    named = _duplicate(api, workspace_id, original_id, {"name": "  Atendimento  "})
    taken = _duplicate(api, workspace_id, original_id, {"name": "Suporte"})
    invalid = _duplicate(api, workspace_id, original_id, {"name": "ERP:support"})

    assert (first, third) == ("Suporte (cópia)", "Suporte (cópia 3)")
    assert named.status_code == 201
    assert named.json()["name"] == "Atendimento"
    assert error_code(taken) == (409, "product_name_taken")
    assert error_code(invalid) == (422, "product_name_invalid")


def test_duplicate_works_without_a_configured_level(api: ApiEnv) -> None:
    """The copy takes the original's model, not the level's (plan 0009, transitional)."""
    world = _world(api, Role.OWNER)
    original_id = _create(api, world, "Suporte")
    api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/levels/product_dev",
        json={"provider_id": None, "model": None},
        headers=api.csrf_headers(),
    )

    response = _duplicate(api, world.workspace_id, original_id)
    fresh = api.client.post(
        _path(world.workspace_id), json={"name": "Novo"}, headers=api.csrf_headers()
    )

    assert response.status_code == 201, response.text
    assert error_code(fresh) == (409, "level_not_configured")


def test_duplicate_cuts_a_long_name(api: ApiEnv) -> None:
    world = _world(api, Role.OWNER)
    original_id = _create(api, world, "x" * 200)

    response = _duplicate(api, world.workspace_id, original_id)

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "x" * 192 + " (cópia)"


def test_duplicate_keeps_webhook_url_but_not_secret(api: ApiEnv, hooks: RequestOverrides) -> None:
    world = configured_world(api, Role.OWNER)
    original = api.client.get(_path(world.workspace_id, f"/{world.assistant_id}")).json()

    response = _duplicate(api, world.workspace_id, world.assistant_id)

    assert original["ticket_webhook_configured"] is True
    copy = response.json()
    assert copy["ticket_webhook_url"] == HOOK_URL
    assert copy["ticket_webhook_configured"] is False
    assert copy["ticket_webhook_secret_created_at"] is None


def test_duplicate_roles_csrf_and_isolation(api: ApiEnv) -> None:
    other = _world(api, Role.OWNER)
    foreign_id = _create(api, other, "Externo")
    world = _world(api, Role.OWNER, Role.VIEWER)
    original_id = _create(api, world, "Suporte")
    path = _path(world.workspace_id, f"/{original_id}/duplicate")

    foreign = _duplicate(api, world.workspace_id, foreign_id)
    missing = _duplicate(api, world.workspace_id, str(uuid.uuid4()))
    no_csrf = api.client.post(path)
    api.login(world.users[1])
    viewer = api.client.post(path, headers=api.csrf_headers())

    assert error_code(foreign) == (404, "not_found")
    assert error_code(missing) == (404, "not_found")
    assert error_code(no_csrf) == (403, "csrf_failed")
    assert error_code(viewer) == (403, "forbidden")
    api.login(world.users[0])
    assert _names(api, world.workspace_id) == ["Suporte"]
