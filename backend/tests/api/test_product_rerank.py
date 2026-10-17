"""The products' ``rerank`` option (plan 0011 F2.1): off by default (ADR 0011), stored as
given, changed and audited by name, copied by "duplicate", and ``rerank_available`` telling
whether the instance has a reranker (``api.deps.get_reranker``; the tests' settings have none)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import cast

import pytest
from api_support import ApiEnv
from fastapi import FastAPI
from product_support import create_product, model_world, post_product, products_path

from fakes.reranker import FakeReranker, fake_instance
from knobridge.api.deps import get_reranker
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def with_reranker(api: ApiEnv) -> Generator[None]:
    app = cast(FastAPI, api.client.app)
    app.dependency_overrides[get_reranker] = lambda: fake_instance(FakeReranker())
    yield
    app.dependency_overrides.pop(get_reranker, None)


def _workspace(api: ApiEnv) -> uuid.UUID:
    owner = api.create_user()
    workspace_id = api.create_workspace({owner.id: Role.OWNER})
    api.login(owner)
    model_world(api, workspace_id)
    return workspace_id


def _get(api: ApiEnv, workspace_id: uuid.UUID, product_id: str) -> dict[str, object]:
    response = api.client.get(products_path(workspace_id, product_id))
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_product_rerank_is_off_by_default_without_a_reranker(api: ApiEnv) -> None:
    workspace_id = _workspace(api)

    created = post_product(api, workspace_id).json()
    listed = api.client.get(products_path(workspace_id)).json()["items"]

    assert (created["rerank"], created["rerank_available"]) == (False, False)
    assert [(item["rerank"], item["rerank_available"]) for item in listed] == [(False, False)]


def test_product_rerank_available_with_the_instance_reranker(
    api: ApiEnv, with_reranker: None
) -> None:
    workspace_id = _workspace(api)

    product_id = create_product(api, workspace_id, rerank=True)

    body = _get(api, workspace_id, product_id)
    assert (body["rerank"], body["rerank_available"]) == (True, True)


def test_product_rerank_changed_and_audited(api: ApiEnv) -> None:
    workspace_id = _workspace(api)
    product_id = create_product(api, workspace_id)

    response = api.client.patch(
        products_path(workspace_id, product_id),
        json={"rerank": True},
        headers=api.csrf_headers(),
    )
    kept = api.client.patch(
        products_path(workspace_id, product_id),
        json={"description": "ERP"},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200, response.text
    assert response.json()["rerank"] is True
    assert kept.json()["rerank"] is True
    events = [event for event in api.workspace_audit(workspace_id) if event[0] == "product.updated"]
    assert ("product.updated", {"name": "Support", "fields": ["rerank"]}) in events


def test_product_duplicate_copies_the_rerank_option(api: ApiEnv) -> None:
    workspace_id = _workspace(api)
    product_id = create_product(api, workspace_id, rerank=True)

    response = api.client.post(
        f"{products_path(workspace_id, product_id)}/duplicate", headers=api.csrf_headers()
    )

    assert response.status_code == 201, response.text
    assert response.json()["rerank"] is True


def test_product_rerank_must_be_a_boolean(api: ApiEnv) -> None:
    workspace_id = _workspace(api)

    response = post_product(api, workspace_id, rerank="sometimes")

    assert response.status_code == 422
