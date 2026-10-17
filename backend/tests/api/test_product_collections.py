"""Product routes with collections: ``collection_ids`` of the same workspace, without
repetition, replacing the set, ``min_similarity``, the audit trail and the cascade when a
collection is deleted."""

from __future__ import annotations

import uuid
from typing import cast

import httpx2 as httpx
import pytest
from api_support import ApiEnv, run_db
from fastapi import FastAPI
from product_support import configure_level, post_product, products_path
from search_support import SearchWorld, add_collection, build_search_world, delete_collection
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.products.models import Product
from knobridge.tenancy.auth import SessionFactory
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _world(api: ApiEnv) -> SearchWorld:
    world = build_search_world(api, Role.OWNER)
    configure_level(api, world.workspace_id, str(world.provider_id))
    return world


def _create(api: ApiEnv, workspace_id: uuid.UUID, **fields: object) -> httpx.Response:
    return post_product(api, workspace_id, name=f"Suporte {uuid.uuid4().hex[:6]}", **fields)


def _patch(
    api: ApiEnv, workspace_id: uuid.UUID, product_id: str, body: dict[str, object]
) -> httpx.Response:
    return api.client.patch(
        products_path(workspace_id, product_id), json=body, headers=api.csrf_headers()
    )


def _updates(api: ApiEnv, workspace_id: uuid.UUID) -> list[object]:
    return [
        metadata["fields"]
        for action, metadata in api.workspace_audit(workspace_id)
        if action == "product.updated"
    ]


def test_product_collections_must_belong_to_workspace(api: ApiEnv) -> None:
    other = build_search_world(api, Role.OWNER)
    world = _world(api)
    missing = uuid.uuid4()

    created = _create(
        api,
        world.workspace_id,
        collection_ids=[str(world.collection_id), str(other.collection_id)],
    )
    valid = _create(api, world.workspace_id, collection_ids=[str(world.collection_id)])
    patched = _patch(
        api, world.workspace_id, valid.json()["id"], {"collection_ids": [str(missing)]}
    )

    assert created.status_code == 422
    assert created.json()["error"] == {
        "code": "product_collection_invalid",
        "message": "Some collections do not exist in this workspace.",
        "details": {"collection_ids": [str(other.collection_id)]},
    }
    assert patched.status_code == 422
    assert patched.json()["error"]["details"] == {"collection_ids": [str(missing)]}
    current = api.client.get(products_path(world.workspace_id, valid.json()["id"])).json()
    assert current["collection_ids"] == [str(world.collection_id)]


def test_product_collections_cannot_repeat(api: ApiEnv) -> None:
    world = _world(api)
    first = str(world.collection_id)
    product_id = _create(api, world.workspace_id).json()["id"]

    created = _create(api, world.workspace_id, collection_ids=[first, first])
    patched = _patch(api, world.workspace_id, product_id, {"collection_ids": [first, first]})

    assert created.status_code == 422
    assert created.json()["error"]["code"] == "validation_error"
    assert patched.status_code == 422
    assert patched.json()["error"]["code"] == "validation_error"


def test_product_collections_set_replaced_and_audited(api: ApiEnv) -> None:
    world = _world(api)
    second = add_collection(api, world.workspace_id, world.provider_id)
    first = str(world.collection_id)

    created = _create(api, world.workspace_id, collection_ids=[first], min_similarity=0.45)
    product_id = created.json()["id"]
    same = _patch(api, world.workspace_id, product_id, {"collection_ids": [first]})
    replaced = _patch(
        api,
        world.workspace_id,
        product_id,
        {"collection_ids": [str(second)], "min_similarity": 0.5},
    )
    kept = _patch(api, world.workspace_id, product_id, {"name": "Outro nome"})
    listed = api.client.get(products_path(world.workspace_id)).json()["items"]

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


def test_product_min_similarity_range(api: ApiEnv) -> None:
    world = _world(api)

    too_high = _create(api, world.workspace_id, min_similarity=1.5)
    negative = _create(api, world.workspace_id, min_similarity=-0.1)
    edge = _create(api, world.workspace_id, min_similarity=1)
    nulled = _create(api, world.workspace_id, min_similarity=None)

    assert too_high.status_code == 422
    assert negative.status_code == 422
    assert edge.status_code == 201
    assert edge.json()["min_similarity"] == 1.0
    assert nulled.json()["min_similarity"] is None


def test_deleting_a_collection_unbinds_it(api: ApiEnv) -> None:
    world = _world(api)
    # A collection with sources cannot be deleted; this one has none.
    doomed = add_collection(api, world.workspace_id, world.provider_id)
    created = _create(
        api, world.workspace_id, collection_ids=[str(world.collection_id), str(doomed)]
    )

    delete_collection(api, doomed)

    current = api.client.get(products_path(world.workspace_id, created.json()["id"]))
    assert current.status_code == 200
    assert current.json()["collection_ids"] == [str(world.collection_id)]


def test_product_created_without_min_similarity_stores_null(api: ApiEnv) -> None:
    world = _world(api)

    created = _create(api, world.workspace_id)
    product_id = uuid.UUID(created.json()["id"])

    async def stored(factory: SessionFactory) -> float | None:
        async with system_session(factory) as db:
            query = select(Product.min_similarity).where(Product.id == product_id)
            return await db.scalar(query)

    assert created.status_code == 201
    assert run_db(api.database_url, stored) is None


def test_product_effective_min_similarity_per_model(api: ApiEnv) -> None:
    world = _world(api)
    gemini = add_collection(
        api, world.workspace_id, world.provider_id, model="google/gemini-embedding-001"
    )
    openai = add_collection(
        api, world.workspace_id, world.provider_id, model="openai/text-embedding-3-small"
    )
    ids = [str(world.collection_id), str(gemini), str(openai)]

    default = _create(api, world.workspace_id, collection_ids=ids)
    explicit = _create(api, world.workspace_id, collection_ids=ids[:2], min_similarity=0.5)

    assert default.json()["min_similarity"] is None
    assert default.json()["effective_min_similarity"] == [
        {"embedding_model": "fake-embedding", "value": 0.35, "source": "fallback"},
        {"embedding_model": "google/gemini-embedding-001", "value": 0.6, "source": "model"},
        {"embedding_model": "openai/text-embedding-3-small", "value": 0.35, "source": "model"},
    ]
    assert explicit.json()["effective_min_similarity"] == [
        {"embedding_model": "fake-embedding", "value": 0.5, "source": "product"},
        {"embedding_model": "google/gemini-embedding-001", "value": 0.5, "source": "product"},
    ]


def test_product_patch_null_min_similarity_restores_model_default(api: ApiEnv) -> None:
    world = _world(api)
    gemini = add_collection(api, world.workspace_id, world.provider_id, model="gemini-embedding-2")
    created = _create(api, world.workspace_id, collection_ids=[str(gemini)], min_similarity=0.4)
    product_id = created.json()["id"]

    kept = _patch(api, world.workspace_id, product_id, {"name": "Renomeado"})
    restored = _patch(api, world.workspace_id, product_id, {"min_similarity": None})
    again = _patch(api, world.workspace_id, product_id, {"min_similarity": None})

    assert kept.json()["min_similarity"] == 0.4
    assert restored.status_code == 200
    assert restored.json()["min_similarity"] is None
    assert restored.json()["effective_min_similarity"] == [
        {"embedding_model": "gemini-embedding-2", "value": 0.57, "source": "model"}
    ]
    assert again.status_code == 200
    assert _updates(api, world.workspace_id) == [["name"], ["min_similarity"]]


def test_product_min_similarity_defaults_from_settings(api: ApiEnv) -> None:
    state = cast(FastAPI, api.client.app).state
    state.settings = state.settings.model_copy(
        update={"min_similarity_defaults": {"gemini-embedding-001": 0.62}}
    )
    world = _world(api)
    gemini = add_collection(
        api, world.workspace_id, world.provider_id, model="google/gemini-embedding-001"
    )

    created = _create(api, world.workspace_id, collection_ids=[str(gemini)])

    assert created.json()["effective_min_similarity"] == [
        {"embedding_model": "google/gemini-embedding-001", "value": 0.62, "source": "model"}
    ]
