"""Helpers for the tests that need products and level configuration through the API.

Not a test module. While the chat still reads the model from the product (plan 0009), a
product is created only in a workspace with a configured level, so ``model_world`` and
``configure_level`` set one first.
"""

from __future__ import annotations

import uuid

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from sqlalchemy import update

from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel

API_KEY = "sk-test-product-key-1111"  # synthetic


def products_path(workspace_id: uuid.UUID, product_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/products"
    return base if product_id is None else f"{base}/{product_id}"


def levels_path(workspace_id: uuid.UUID, level: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/levels"
    return base if level is None else f"{base}/{level}"


def create_provider(api: ApiEnv, workspace_id: uuid.UUID, name: str = "Fake") -> str:
    """A ``fake`` provider of the workspace (the logged-in user must be editor+)."""
    response = api.client.post(
        f"/v1/workspaces/{workspace_id}/providers",
        json={"name": name, "kind": "fake", "api_key": API_KEY},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    provider_id: str = response.json()["id"]
    return provider_id


def configure_level(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    provider_id: str,
    *,
    level: str = "product_dev",
    model: str = "fake-model",
    **fields: object,
) -> httpx.Response:
    """Give ``level`` a provider and model (the logged-in user must be admin+)."""
    response = api.client.patch(
        levels_path(workspace_id, level),
        json={"provider_id": provider_id, "model": model, **fields},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text
    return response


def seed_level(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    provider_id: str,
    *,
    level: ResponseLevel = ResponseLevel.PRODUCT_DEV,
    model: str = "fake-model",
    max_steps: int | None = None,
) -> None:
    """Like ``configure_level``, straight in the database, for tests whose user is below admin
    (``max_steps`` omitted keeps the level's)."""
    values: dict[str, object] = {"credential_id": uuid.UUID(provider_id), "model": model}
    if max_steps is not None:
        values["max_steps"] = max_steps

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id, WorkspaceLevel.level == level)
                .values(**values)
            )

    run_db(api.database_url, scenario)


def post_product(
    api: ApiEnv, workspace_id: uuid.UUID, *, name: str = "Support", **fields: object
) -> httpx.Response:
    body: dict[str, object] = {"name": name, **fields}
    return api.client.post(products_path(workspace_id), json=body, headers=api.csrf_headers())


def create_product(
    api: ApiEnv, workspace_id: uuid.UUID, *, name: str = "Support", **fields: object
) -> str:
    response = post_product(api, workspace_id, name=name, **fields)
    assert response.status_code == 201, response.text
    product_id: str = response.json()["id"]
    return product_id


def model_world(api: ApiEnv, workspace_id: uuid.UUID, *, model: str = "fake-model") -> str:
    """A ``fake`` provider set on the ``product_dev`` level (the logged-in user must be admin+);
    returns the provider id."""
    provider_id = create_provider(api, workspace_id)
    configure_level(api, workspace_id, provider_id, model=model)
    return provider_id
