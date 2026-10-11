"""Helpers for the search route tests: a workspace with a ``fake`` provider created through the
API, a collection and chunks written straight to the database (``fake_vector`` embeddings),
without the ingestion workflow.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from api_support import ApiEnv, SeededUser, SessionFactory, run_db, unique

from knobridge.audit.models import JSONValue
from knobridge.core.db import system_session
from knobridge.ingestion.models import Chunk, Collection, Document, DocumentKind, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.fake_embeddings import fake_vector
from knobridge.tenancy.models import Role

API_KEY = "sk-test-search-key-86420"  # synthetic
MODEL = "fake-embedding"
HASH = "0" * 64


@dataclass(frozen=True)
class SearchWorld:
    workspace_id: uuid.UUID
    users: list[SeededUser]
    provider_id: uuid.UUID
    collection_id: uuid.UUID
    source_id: uuid.UUID


@dataclass(frozen=True)
class Passage:
    content: str
    key: str
    position: int = 0
    meta: dict[str, JSONValue] = field(default_factory=lambda: {})


def search_path(workspace_id: uuid.UUID, collection_id: uuid.UUID | str) -> str:
    return f"/v1/workspaces/{workspace_id}/collections/{collection_id}/search"


def build_search_world(api: ApiEnv, *roles: Role) -> SearchWorld:
    """A workspace whose first user (owner, admin or editor) creates a ``fake`` provider;
    a collection with one source on it. The first user stays logged in."""
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
    provider_id = uuid.UUID(provider.json()["id"])

    async def scenario(factory: SessionFactory) -> tuple[uuid.UUID, uuid.UUID]:
        async with system_session(factory) as db:
            collection = Collection(
                workspace_id=workspace_id,
                name=unique("collection"),
                description="",
                credential_id=provider_id,
                embedding_model=MODEL,
            )
            db.add(collection)
            await db.flush()
            source = Source(
                workspace_id=workspace_id,
                collection_id=collection.id,
                kind=SourceKind.FOLDER,
                name=unique("source"),
                config={"path": "/srv/docs"},
            )
            db.add(source)
            await db.flush()
            return collection.id, source.id

    collection_id, source_id = run_db(api.database_url, scenario)
    return SearchWorld(workspace_id, users, provider_id, collection_id, source_id)


def add_passages(api: ApiEnv, world: SearchWorld, *passages: Passage) -> list[uuid.UUID]:
    """Chunk ids in the order given; one document per distinct key."""

    async def scenario(factory: SessionFactory) -> list[uuid.UUID]:
        ids: list[uuid.UUID] = []
        documents: dict[str, uuid.UUID] = {}
        async with system_session(factory) as db:
            for passage in passages:
                if passage.key not in documents:
                    document = Document(
                        workspace_id=world.workspace_id,
                        source_id=world.source_id,
                        natural_key=passage.key,
                        kind=DocumentKind.FILE,
                        title=passage.key.rsplit("/", 1)[-1],
                        uri=f"https://git.example.test/repo/blob/main/{passage.key}",
                        content_hash=HASH,
                    )
                    db.add(document)
                    await db.flush()
                    documents[passage.key] = document.id
                chunk = Chunk(
                    workspace_id=world.workspace_id,
                    document_id=documents[passage.key],
                    collection_id=world.collection_id,
                    position=passage.position,
                    content=passage.content,
                    meta=passage.meta,
                    content_hash=HASH,
                    embedding_model=MODEL,
                    embedding=fake_vector(passage.content),
                )
                db.add(chunk)
                await db.flush()
                ids.append(chunk.id)
        return ids

    return run_db(api.database_url, scenario)
