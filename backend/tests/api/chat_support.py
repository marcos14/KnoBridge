"""Helpers for the conversation API tests: a workspace with a ``fake`` provider and an
assistant, the chat calls, and a parser for the Server-Sent Events of an answer.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import cast

import httpx2 as httpx
from api_support import ApiEnv, SeededUser
from fastapi import FastAPI
from product_support import seed_level

from fakes.embedding_provider import RecordingEmbeddingFactory
from fakes.llm_provider import RecordingFactory
from fakes.retriever import StaticRetriever
from knobridge.api.deps import (
    get_embedding_provider_factory,
    get_provider_factory,
    get_retriever,
)
from knobridge.conversations.retrieval import Source
from knobridge.levels.level import ResponseLevel
from knobridge.llm.provider import LLMProvider
from knobridge.tenancy.models import Role

API_KEY = "sk-test-chat-key-97531"  # synthetic
SOURCES = (
    Source(
        title="Fechamento de caixa",
        content="O fechamento exige o relatório Z antes da sangria.",
        uri="docs/caixa.md",
        document_id="doc-1",
    ),
    Source(title="Sangria", content="A sangria é registrada no menu Caixa."),
)

type SseEvent = tuple[str, dict[str, object]]


@dataclass(frozen=True)
class World:
    workspace_id: uuid.UUID
    users: list[SeededUser]
    provider_id: str
    assistant_id: str


def build_world(api: ApiEnv, *roles: Role, **assistant: object) -> World:
    """A workspace whose first user (an owner or admin) creates a provider and an assistant;
    that user stays logged in."""
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    api.login(users[0])
    provider = api.client.post(
        f"/v1/workspaces/{workspace_id}/providers",
        json={"name": "Fake", "kind": "fake", "api_key": API_KEY},
        headers=api.csrf_headers(),
    )
    assert provider.status_code == 201, provider.text
    provider_id: str = provider.json()["id"]
    # The model belongs to each level of the workspace; written straight in the database
    # because the first user may be an editor. Every level answers, so members of any role
    # can chat at their default level.
    model = str(assistant.pop("model", "fake-model"))
    for level in ResponseLevel:
        seed_level(api, workspace_id, provider_id, level=level, model=model)
    body: dict[str, object] = {
        "name": "Suporte",
        "instructions": "Você ajuda com o ERP.",
        **assistant,
    }
    created = api.client.post(
        f"/v1/workspaces/{workspace_id}/products", json=body, headers=api.csrf_headers()
    )
    assert created.status_code == 201, created.text
    return World(workspace_id, users, provider_id, created.json()["id"])


def conversations_path(workspace_id: uuid.UUID, conversation_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/conversations"
    return base if conversation_id is None else f"{base}/{conversation_id}"


def start(
    api: ApiEnv, world: World, assistant_id: str | None = None, *, level: str | None = None
) -> str:
    """A conversation about the world's product (or ``assistant_id``), at ``level`` (omitted:
    the caller's maximum)."""
    body: dict[str, object] = {"product_id": assistant_id or world.assistant_id}
    if level is not None:
        body["level"] = level
    response = api.client.post(
        conversations_path(world.workspace_id), json=body, headers=api.csrf_headers()
    )
    assert response.status_code == 201, response.text
    conversation_id: str = response.json()["id"]
    return conversation_id


def ask(
    api: ApiEnv, workspace_id: uuid.UUID, conversation_id: str, question: str
) -> httpx.Response:
    return api.client.post(
        f"{conversations_path(workspace_id, conversation_id)}/messages",
        json={"content": question},
        headers=api.csrf_headers(),
    )


def events(response: httpx.Response) -> list[SseEvent]:
    """``(event name, JSON data)`` of each frame of a ``text/event-stream`` body."""
    parsed: list[SseEvent] = []
    for frame in response.text.split("\n\n"):
        if not frame.strip():
            continue
        fields = dict(line.split(": ", 1) for line in frame.split("\n"))
        parsed.append((fields["event"], cast(dict[str, object], json.loads(fields["data"]))))
    return parsed


def messages(api: ApiEnv, workspace_id: uuid.UUID, conversation_id: str) -> list[dict[str, object]]:
    response = api.client.get(conversations_path(workspace_id, conversation_id))
    assert response.status_code == 200, response.text
    items: list[dict[str, object]] = response.json()["messages"]["items"]
    return items


def error(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


@dataclass
class ChatOverrides:
    """Swaps the retriever and the LLM and embedding provider factories of the app under test."""

    app: FastAPI

    def retriever(self, retriever: StaticRetriever) -> StaticRetriever:
        self.app.dependency_overrides[get_retriever] = lambda: retriever
        return retriever

    def provider(self, provider: LLMProvider) -> RecordingFactory:
        factory = RecordingFactory(provider)
        self.app.dependency_overrides[get_provider_factory] = lambda: factory
        return factory

    def embeddings(self, factory: RecordingEmbeddingFactory) -> RecordingEmbeddingFactory:
        self.app.dependency_overrides[get_embedding_provider_factory] = lambda: factory
        return factory

    def clear(self) -> None:
        self.app.dependency_overrides.pop(get_retriever, None)
        self.app.dependency_overrides.pop(get_provider_factory, None)
        self.app.dependency_overrides.pop(get_embedding_provider_factory, None)
