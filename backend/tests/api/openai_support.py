"""Helpers for the OpenAI-compatible API tests: the official ``openai`` SDK pointed at the app
under test (the ``TestClient`` is its HTTP client, no port opened), extra assistants and readers
of the conversations a key created.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import httpx2 as httpx
from api_key_support import bearer, create_key
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import World, build_world
from openai import OpenAI
from sqlalchemy import select

from knobridge.conversations.models import Conversation, Message
from knobridge.core.db import system_session
from knobridge.tenancy.models import Role

NO_SOURCE = "Não achei nas fontes. Quer abrir um chamado?"
COMPLETIONS = "/v1/chat/completions"


@dataclass(frozen=True)
class KeyWorld:
    world: World
    api_key_id: str
    key: str
    sdk: OpenAI


def sdk(api: ApiEnv, key: str) -> OpenAI:
    """The SDK over the app; no retries, so each failure is one conversation."""
    return OpenAI(
        base_url="http://testserver/v1", api_key=key, http_client=api.client, max_retries=0
    )


def key_world(api: ApiEnv, assistant_ids: list[str] | None = None, **assistant: object) -> KeyWorld:
    world = build_world(api, Role.OWNER, no_source_message=NO_SOURCE, **assistant)
    api_key_id, key = create_key(api, world.workspace_id, assistant_ids)
    return KeyWorld(world, api_key_id, key, sdk(api, key))


def add_assistant(api: ApiEnv, world: World, name: str, *, active: bool = True) -> str:
    created = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/assistants",
        json={
            "name": name,
            "provider_id": world.provider_id,
            "model": "fake-model",
            "description": f"Assistente {name}",
        },
        headers=api.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    assistant_id: str = created.json()["id"]
    if not active:
        response = api.client.patch(
            f"/v1/workspaces/{world.workspace_id}/assistants/{assistant_id}",
            json={"active": False},
            headers=api.csrf_headers(),
        )
        assert response.status_code == 200, response.text
    return assistant_id


def post_raw(api: ApiEnv, key: str, body: object) -> httpx.Response:
    """A completion without the SDK, to read the exact status, headers and stream lines."""
    return api.client.post(COMPLETIONS, json=body, headers=bearer(key))


def stream_lines(response: httpx.Response) -> list[object]:
    """``data:`` payloads of a streamed completion (``"[DONE]"`` kept as text)."""
    lines: list[object] = []
    for frame in response.text.split("\n\n"):
        if not frame.strip():
            continue
        assert frame.startswith("data: ")
        data = frame.removeprefix("data: ")
        lines.append(data if data == "[DONE]" else json.loads(data))
    return lines


def key_conversations(api: ApiEnv, api_key_id: str) -> list[tuple[Conversation, list[Message]]]:
    """Conversations of the key (oldest first) with their messages in order."""

    async def scenario(factory: SessionFactory) -> list[tuple[Conversation, list[Message]]]:
        async with system_session(factory) as db:
            conversations = await db.scalars(
                select(Conversation)
                .where(Conversation.api_key_id == uuid.UUID(api_key_id))
                .order_by(Conversation.created_at, Conversation.id)
            )
            found: list[tuple[Conversation, list[Message]]] = []
            for conversation in conversations.all():
                messages = await db.scalars(
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.position)
                )
                found.append((conversation, list(messages)))
            return found

    return run_db(api.database_url, scenario)
