"""Assistant routes with collections: ``collection_ids`` of the same workspace, replacing the
set, ``min_similarity``, the audit trail and the cascade when a collection is deleted."""

from __future__ import annotations

import uuid

import httpx2 as httpx
import pytest
from api_support import ApiEnv, run_db
from search_support import add_collection, build_search_world, delete_collection
from sqlalchemy import select

from knobridge.assistants.models import Assistant
from knobridge.core.db import system_session
from knobridge.tenancy.auth import SessionFactory
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _path(workspace_id: uuid.UUID, assistant_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/assistants"
    return base if assistant_id is None else f"{base}/{assistant_id}"


def _create(
    api: ApiEnv, workspace_id: uuid.UUID, provider_id: uuid.UUID, **fields: object
) -> httpx.Response:
    body: dict[str, object] = {
        "name": f"Suporte {uuid.uuid4().hex[:6]}",
        "provider_id": str(provider_id),
        "model": "fake-model",
        **fields,
    }
    return api.client.post(_path(workspace_id), json=body, headers=api.csrf_headers())


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, assistant_id: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(
        _path(workspace_id, assistant_id), json=body, headers=api.csrf_headers()
    )


def _updates(api: ApiEnv, workspace_id: uuid.UUID) -> list[object]:
    return [
        metadata["fields"]
        for action, metadata in api.workspace_audit(workspace_id)
        if action == "assistant.updated"
    ]


def test_assistant_collections_must_belong_to_workspace(api: ApiEnv) -> None:
    other = build_search_world(api, Role.OWNER)
    world = build_search_world(api, Role.OWNER)
    missing = uuid.uuid4()

    created = _create(
        api,
        world.workspace_id,
        world.provider_id,
        collection_ids=[str(world.collection_id), str(other.collection_id)],
    )
    valid = _create(
        api, world.workspace_id, world.provider_id, collection_ids=[str(world.collection_id)]
    )
    patched = _patch(
        api, world.workspace_id, valid.json()["id"], {"collection_ids": [str(missing)]}
    )

    assert created.status_code == 422
    assert created.json()["error"] == {
        "code": "assistant_collection_invalid",
        "message": "Some collections do not exist in this workspace.",
        "details": {"collection_ids": [str(other.collection_id)]},
    }
    assert patched.status_code == 422
    assert patched.json()["error"]["details"] == {"collection_ids": [str(missing)]}
    current = api.client.get(_path(world.workspace_id, valid.json()["id"])).json()
    assert current["collection_ids"] == [str(world.collection_id)]


def test_assistant_collections_set_replaced_and_audited(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    second = add_collection(api, world.workspace_id, world.provider_id)
    first = str(world.collection_id)

    created = _create(
        api,
        world.workspace_id,
        world.provider_id,
        collection_ids=[first, first],
        min_similarity=0.45,
    )
    assistant_id = created.json()["id"]
    same = _patch(api, world.workspace_id, assistant_id, {"collection_ids": [first]})
    replaced = _patch(
        api,
        world.workspace_id,
        assistant_id,
        {"collection_ids": [str(second)], "min_similarity": 0.5},
    )
    kept = _patch(api, world.workspace_id, assistant_id, {"name": "Outro nome"})
    listed = api.client.get(_path(world.workspace_id)).json()["items"]

    assert created.status_code == 201
    assert created.json()["collection_ids"] == [first]
    assert created.json()["min_similarity"] == 0.45
    assert same.json()["collection_ids"] == [first]
    assert replaced.json()["collection_ids"] == [str(second)]
    assert replaced.json()["min_similarity"] == 0.5
    assert replaced.json()["updated_at"] >= created.json()["updated_at"]
    assert kept.json()["collection_ids"] == [str(second)]
    assert [item["collection_ids"] for item in listed] == [[str(second)]]
    updates = _updates(api, world.workspace_id)
    assert ["min_similarity", "collection_ids"] in updates
    assert ["name"] in updates
    assert len(updates) == 2


def test_assistant_min_similarity_range(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)

    too_high = _create(api, world.workspace_id, world.provider_id, min_similarity=1.5)
    negative = _create(api, world.workspace_id, world.provider_id, min_similarity=-0.1)
    edge = _create(api, world.workspace_id, world.provider_id, min_similarity=1)
    nulled = _create(api, world.workspace_id, world.provider_id, min_similarity=None)

    assert too_high.status_code == 422
    assert negative.status_code == 422
    assert edge.status_code == 201
    assert edge.json()["min_similarity"] == 1.0
    assert nulled.json()["min_similarity"] == 0.35


def test_deleting_a_collection_unbinds_it(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    # A collection with sources cannot be deleted; this one has none.
    doomed = add_collection(api, world.workspace_id, world.provider_id)
    created = _create(
        api,
        world.workspace_id,
        world.provider_id,
        collection_ids=[str(world.collection_id), str(doomed)],
    )

    delete_collection(api, doomed)

    current = api.client.get(_path(world.workspace_id, created.json()["id"]))
    assert current.status_code == 200
    assert current.json()["collection_ids"] == [str(world.collection_id)]


def test_assistant_created_without_min_similarity_stores_035(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)

    created = _create(api, world.workspace_id, world.provider_id)
    assistant_id = uuid.UUID(created.json()["id"])

    async def stored(factory: SessionFactory) -> float | None:
        async with system_session(factory) as db:
            query = select(Assistant.min_similarity).where(Assistant.id == assistant_id)
            return await db.scalar(query)

    assert created.status_code == 201
    assert run_db(api.database_url, stored) == 0.35
