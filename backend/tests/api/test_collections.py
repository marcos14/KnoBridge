"""Collection routes: CRUD with counts, roles, provider rules, the embedding lock, the
in-use rule on delete, audit and isolation."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from api_support import ApiEnv, unique
from index_support import (
    IndexOverrides,
    add_documents,
    base,
    build_world,
    create_provider,
    create_source,
    error_code,
    install,
    post_collection,
    team,
)

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _path(workspace_id: uuid.UUID, collection_id: str | None = None) -> str:
    root = f"{base(workspace_id)}/collections"
    return root if collection_id is None else f"{root}/{collection_id}"


def test_create_collection_returns_counts_and_audits(api: ApiEnv) -> None:
    workspace_id, users = team(api, Role.EDITOR)
    api.login(users[0])
    provider_id = create_provider(api, workspace_id)

    response = post_collection(
        api, workspace_id, provider_id, name="Manuais", description="  Manuais do ERP  "
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Manuais"
    assert body["description"] == "Manuais do ERP"
    assert body["provider_id"] == provider_id
    assert body["embedding_model"] == "fake-embedding"
    assert body["embedding_dimension"] == 1536
    assert (body["source_count"], body["document_count"], body["chunk_count"]) == (0, 0, 0)
    created = (
        "collection.created",
        {
            "name": "Manuais",
            "embedding_model": "fake-embedding",
            "provider_id": provider_id,
        },
    )
    assert created in api.workspace_audit(workspace_id)


def test_list_and_get_collections_with_counts(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER, Role.VIEWER)
    source_id = create_source(api, world)
    add_documents(api, world, source_id, {"docs/a.md": 2, "docs/b.md": 3})
    empty = post_collection(api, world.workspace_id, world.provider_id, name="zz-empty")
    assert empty.status_code == 201

    api.login(world.users[1])  # viewers read
    listing = api.client.get(_path(world.workspace_id), params={"limit": 1})
    single = api.client.get(_path(world.workspace_id, world.collection_id))

    assert listing.status_code == 200
    page = listing.json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (2, 1, 0, 1)
    assert single.status_code == 200
    counts = single.json()
    assert (counts["source_count"], counts["document_count"], counts["chunk_count"]) == (1, 2, 5)
    second = api.client.get(_path(world.workspace_id), params={"offset": 1}).json()["items"]
    assert [item["name"] for item in second] == ["zz-empty"]


def test_create_collection_requires_editor(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN, Role.VIEWER)
    api.login(world.users[1])

    response = post_collection(api, world.workspace_id, world.provider_id)

    assert error_code(response) == (403, "forbidden")


def test_create_collection_without_csrf_is_refused(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)

    response = api.client.post(
        _path(world.workspace_id),
        json={"name": "x", "provider_id": world.provider_id, "embedding_model": "m"},
    )

    assert error_code(response) == (403, "csrf_failed")


def test_create_collection_name_taken_409(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    name = api.client.get(_path(world.workspace_id, world.collection_id)).json()["name"]

    response = post_collection(api, world.workspace_id, world.provider_id, name=name)

    assert error_code(response) == (409, "collection_name_taken")


def test_create_collection_with_provider_of_other_workspace_422(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = build_world(api, Role.OWNER)
    api.login(world.users[0])
    response = post_collection(api, world.workspace_id, other.provider_id)

    assert error_code(response) == (422, "collection_provider_invalid")


def test_create_collection_with_anthropic_provider_422(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    anthropic = create_provider(api, world.workspace_id, kind="anthropic")

    response = post_collection(api, world.workspace_id, anthropic)

    assert error_code(response) == (422, "provider_embeddings_unsupported")


def test_update_collection_fields_and_audit(api: ApiEnv) -> None:
    world = build_world(api, Role.EDITOR)
    other_provider = create_provider(api, world.workspace_id)
    path = _path(world.workspace_id, world.collection_id)

    response = api.client.patch(
        path,
        json={"name": "Renomeada", "provider_id": other_provider, "embedding_model": "m2"},
        headers=api.csrf_headers(),
    )
    unchanged = api.client.patch(path, json={"name": "Renomeada"}, headers=api.csrf_headers())

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["provider_id"], body["embedding_model"]) == (
        "Renomeada",
        other_provider,
        "m2",
    )
    assert unchanged.status_code == 200
    updates = [d for a, d in api.workspace_audit(world.workspace_id) if a == "collection.updated"]
    assert updates == [{"name": "Renomeada", "fields": ["name", "provider_id", "embedding_model"]}]


def test_update_collection_name_taken_409(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    taken = unique("taken")
    assert (
        post_collection(api, world.workspace_id, world.provider_id, name=taken).status_code == 201
    )

    response = api.client.patch(
        _path(world.workspace_id, world.collection_id),
        json={"name": taken},
        headers=api.csrf_headers(),
    )

    assert error_code(response) == (409, "collection_name_taken")


def test_update_collection_model_locked_with_documents(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world)
    add_documents(api, world, source_id, {"docs/a.md": 1})
    path = _path(world.workspace_id, world.collection_id)

    locked = api.client.patch(path, json={"embedding_model": "m2"}, headers=api.csrf_headers())
    renamed = api.client.patch(
        path, json={"description": "still editable"}, headers=api.csrf_headers()
    )

    assert error_code(locked) == (409, "collection_embedding_locked")
    assert renamed.status_code == 200
    assert renamed.json()["description"] == "still editable"


def test_update_collection_with_foreign_provider_422(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = build_world(api, Role.OWNER)
    api.login(world.users[0])

    response = api.client.patch(
        _path(world.workspace_id, world.collection_id),
        json={"provider_id": other.provider_id},
        headers=api.csrf_headers(),
    )

    assert error_code(response) == (422, "collection_provider_invalid")


def test_delete_collection_in_use_409(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    create_source(api, world)

    response = api.client.delete(
        _path(world.workspace_id, world.collection_id), headers=api.csrf_headers()
    )

    assert error_code(response) == (409, "collection_in_use")
    assert api.client.get(_path(world.workspace_id, world.collection_id)).status_code == 200


def test_delete_empty_collection_and_audit(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    path = _path(world.workspace_id, world.collection_id)
    name = api.client.get(path).json()["name"]

    response = api.client.delete(path, headers=api.csrf_headers())

    assert response.status_code == 204
    assert error_code(api.client.get(path)) == (404, "collection_not_found")
    assert ("collection.deleted", {"name": name}) in api.workspace_audit(world.workspace_id)


def test_collections_isolated_by_workspace(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other = build_world(api, Role.OWNER)  # logged in as the other owner now

    listing = api.client.get(_path(other.workspace_id)).json()
    foreign = api.client.get(_path(other.workspace_id, world.collection_id))
    foreign_delete = api.client.delete(
        _path(other.workspace_id, world.collection_id), headers=api.csrf_headers()
    )
    not_member = api.client.get(_path(world.workspace_id))

    assert [item["id"] for item in listing["items"]] == [other.collection_id]
    assert error_code(foreign) == (404, "collection_not_found")
    assert error_code(foreign_delete) == (404, "collection_not_found")
    assert error_code(not_member) == (404, "not_found")
