"""Helpers for the API key tests: the panel routes of keys, the bearer header, the public REST
calls and readers of what got stored.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from sqlalchemy import select

from knobridge.apikeys.models import ApiKey
from knobridge.conversations.models import Conversation, Message
from knobridge.core.db import system_session


def keys_path(workspace_id: uuid.UUID, api_key_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/api-keys"
    return base if api_key_id is None else f"{base}/{api_key_id}"


def post_key(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    name: str | None = None,
    product_ids: list[str] | None = None,
    max_level: str = "product_dev",
) -> httpx.Response:
    return api.client.post(
        keys_path(workspace_id),
        json={
            "name": name or f"Integração {uuid.uuid4().hex[:8]}",
            "product_ids": product_ids,
            "max_level": max_level,
        },
        headers=api.csrf_headers(),
    )


def create_key(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    product_ids: list[str] | None = None,
    max_level: str = "product_dev",
) -> tuple[str, str]:
    """``(api_key id, key)`` of a new key created by the logged-in owner or admin."""
    response = post_key(api, workspace_id, product_ids=product_ids, max_level=max_level)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["api_key"]["id"], body["key"]


def revoke_key(api: ApiEnv, workspace_id: uuid.UUID, api_key_id: str) -> httpx.Response:
    return api.client.post(
        f"{keys_path(workspace_id, api_key_id)}/revoke", headers=api.csrf_headers()
    )


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def start_public(
    api: ApiEnv, key: str, product_id: str, level: str | None = None
) -> httpx.Response:
    body = {"product_id": product_id}
    if level is not None:
        body["level"] = level
    return api.client.post("/v1/conversations", json=body, headers=bearer(key))


def start_public_id(api: ApiEnv, key: str, product_id: str, level: str | None = None) -> str:
    response = start_public(api, key, product_id, level)
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["id"]
    return conversation_id


def ask_public(
    api: ApiEnv, key: str, conversation_id: str, content: str, *, stream: bool = False
) -> httpx.Response:
    return api.client.post(
        f"/v1/conversations/{conversation_id}/messages",
        json={"content": content, "stream": stream},
        headers=bearer(key),
    )


def stored_key(api: ApiEnv, api_key_id: str) -> ApiKey:
    async def scenario(factory: SessionFactory) -> ApiKey:
        async with system_session(factory) as db:
            return (
                await db.scalars(select(ApiKey).where(ApiKey.id == uuid.UUID(api_key_id)))
            ).one()

    return run_db(api.database_url, scenario)


def stored_conversation(api: ApiEnv, conversation_id: str) -> tuple[Conversation, list[Message]]:
    async def scenario(factory: SessionFactory) -> tuple[Conversation, list[Message]]:
        async with system_session(factory) as db:
            conversation = (
                await db.scalars(
                    select(Conversation).where(Conversation.id == uuid.UUID(conversation_id))
                )
            ).one()
            messages = await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.position)
            )
            return conversation, list(messages)

    return run_db(api.database_url, scenario)
