"""Helpers for the collection, source, run and document route tests: a workspace with a ``fake``
provider and a collection created through the API, the fake sync starter, schedule manager
and connector factory installed as dependency overrides, and direct writes of runs, errors,
documents and chunks (the ingestion workflow does not run here).

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import httpx2 as httpx
from api_support import ApiEnv, SeededUser, SessionFactory, run_db, unique
from fastapi import FastAPI
from sqlalchemy import func, select

from fakes.connector import FakeConnector
from fakes.schedule_manager import FakeScheduleManager
from fakes.sync_starter import FakeSyncStarter
from knobridge.api.deps import get_connector_factory, get_schedule_manager, get_sync_starter
from knobridge.connectors.base import Connector
from knobridge.core.db import system_session
from knobridge.ingestion.models import (
    Chunk,
    Document,
    DocumentKind,
    Run,
    RunError,
    RunErrorStage,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.llm.fake_embeddings import fake_vector
from knobridge.tenancy.models import Role

API_KEY = "sk-test-index-key-97531"  # synthetic
MODEL = "fake-embedding"
HASH = "0" * 64
# Absolute on the platform running the tests (a drive letter on Windows); never read.
FOLDER = str(Path("/srv/knowledge/docs").resolve())
OTHER_FOLDER = str(Path("/srv/knowledge/other").resolve())


@dataclass
class IndexOverrides:
    """Fake starter, schedule manager and connector factory on the app; ``clear`` removes
    them."""

    app: FastAPI
    starter: FakeSyncStarter = field(default_factory=FakeSyncStarter)
    schedules: FakeScheduleManager = field(default_factory=FakeScheduleManager)
    connector: FakeConnector = field(default_factory=FakeConnector)
    built_for: list[uuid.UUID] = field(default_factory=lambda: [])

    def __post_init__(self) -> None:
        self.app.dependency_overrides[get_sync_starter] = lambda: self.starter
        self.app.dependency_overrides[get_schedule_manager] = lambda: self.schedules
        self.app.dependency_overrides[get_connector_factory] = lambda: self._factory

    def _factory(self, source: Source) -> Connector:
        self.built_for.append(source.id)
        return self.connector

    def clear(self) -> None:
        self.app.dependency_overrides.pop(get_sync_starter, None)
        self.app.dependency_overrides.pop(get_schedule_manager, None)
        self.app.dependency_overrides.pop(get_connector_factory, None)


def install(api: ApiEnv) -> IndexOverrides:
    return IndexOverrides(cast(FastAPI, api.client.app))


@dataclass(frozen=True)
class IndexWorld:
    workspace_id: uuid.UUID
    users: list[SeededUser]
    provider_id: str
    collection_id: str


def base(workspace_id: uuid.UUID) -> str:
    return f"/v1/workspaces/{workspace_id}"


def team(api: ApiEnv, *roles: Role) -> tuple[uuid.UUID, list[SeededUser]]:
    users = [api.create_user() for _ in roles]
    workspace_id = api.create_workspace(
        {user.id: role for user, role in zip(users, roles, strict=True)}
    )
    return workspace_id, users


def create_provider(
    api: ApiEnv, workspace_id: uuid.UUID, *, kind: str = "fake", name: str | None = None
) -> str:
    response = api.client.post(
        f"{base(workspace_id)}/providers",
        json={"name": name or unique("provider"), "kind": kind, "api_key": API_KEY},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    provider_id: str = response.json()["id"]
    return provider_id


def post_collection(
    api: ApiEnv, workspace_id: uuid.UUID, provider_id: str, **fields: object
) -> httpx.Response:
    body: dict[str, object] = {
        "name": unique("collection"),
        "provider_id": provider_id,
        "embedding_model": MODEL,
        **fields,
    }
    return api.client.post(
        f"{base(workspace_id)}/collections", json=body, headers=api.csrf_headers()
    )


def build_world(api: ApiEnv, *roles: Role) -> IndexWorld:
    """A workspace whose first user (owner, admin or editor) creates a ``fake`` provider and a
    collection through the API; the first user stays logged in."""
    workspace_id, users = team(api, *roles)
    api.login(users[0])
    provider_id = create_provider(api, workspace_id)
    response = post_collection(api, workspace_id, provider_id)
    assert response.status_code == 201, response.text
    return IndexWorld(workspace_id, users, provider_id, response.json()["id"])


def post_source(api: ApiEnv, world: IndexWorld, **fields: object) -> httpx.Response:
    body: dict[str, object] = {
        "collection_id": world.collection_id,
        "kind": "folder",
        "name": unique("source"),
        "config": {"path": FOLDER},
        **fields,
    }
    return api.client.post(
        f"{base(world.workspace_id)}/sources", json=body, headers=api.csrf_headers()
    )


def create_source(api: ApiEnv, world: IndexWorld, **fields: object) -> str:
    response = post_source(api, world, **fields)
    assert response.status_code == 201, response.text
    source_id: str = response.json()["id"]
    return source_id


def source_path(world: IndexWorld, source_id: str, action: str = "") -> str:
    suffix = f"/{action}" if action else ""
    return f"{base(world.workspace_id)}/sources/{source_id}{suffix}"


def error_code(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def set_run(
    api: ApiEnv,
    world: IndexWorld,
    run_id: str,
    status: RunStatus,
    *,
    error: str | None = None,
) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            run = await db.get(Run, uuid.UUID(run_id))
            assert run is not None
            run.status, run.error = status, error

    run_db(api.database_url, scenario)


def add_run(
    api: ApiEnv, world: IndexWorld, source_id: str, status: RunStatus, *, errors: int = 0
) -> str:
    """A run written straight to the database, with ``errors`` document errors."""

    async def scenario(factory: SessionFactory) -> str:
        async with system_session(factory) as db:
            run = Run(
                workspace_id=world.workspace_id,
                source_id=uuid.UUID(source_id),
                trigger=RunTrigger.MANUAL,
                status=status,
                documents_failed=errors,
            )
            db.add(run)
            await db.flush()
            db.add_all(
                RunError(
                    workspace_id=world.workspace_id,
                    run_id=run.id,
                    document_key=f"docs/broken-{index:02d}.pdf",
                    stage=RunErrorStage.PARSE,
                    code="parse_failed",
                    message="the document has no extractable text",
                )
                for index in range(errors)
            )
            return str(run.id)

    return run_db(api.database_url, scenario)


def add_documents(
    api: ApiEnv,
    world: IndexWorld,
    source_id: str,
    documents: dict[str, int],
    *,
    kind: DocumentKind = DocumentKind.FILE,
) -> None:
    """Documents (key -> number of chunks) of the source, with fake vectors."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            for key, chunks in documents.items():
                document = Document(
                    workspace_id=world.workspace_id,
                    source_id=uuid.UUID(source_id),
                    natural_key=key,
                    kind=kind,
                    title=key.rsplit("/", 1)[-1],
                    uri=f"file:///srv/knowledge/{key}",
                    content_hash=HASH,
                )
                db.add(document)
                await db.flush()
                db.add_all(
                    Chunk(
                        workspace_id=world.workspace_id,
                        document_id=document.id,
                        collection_id=uuid.UUID(world.collection_id),
                        position=position,
                        content=f"{key} part {position}",
                        content_hash=HASH,
                        embedding_model=MODEL,
                        embedding=fake_vector(f"{key} part {position}"),
                    )
                    for position in range(chunks)
                )

    run_db(api.database_url, scenario)


def index_rows(api: ApiEnv, source_id: str) -> tuple[int, int, int]:
    """(documents, chunks, runs) still stored for the source id."""

    async def scenario(factory: SessionFactory) -> tuple[int, int, int]:
        sid = uuid.UUID(source_id)
        async with system_session(factory) as db:
            documents = await db.scalar(
                select(func.count()).select_from(Document).where(Document.source_id == sid)
            )
            chunks = await db.scalar(
                select(func.count())
                .select_from(Chunk)
                .join(Document, Document.id == Chunk.document_id)
                .where(Document.source_id == sid)
            )
            runs = await db.scalar(
                select(func.count()).select_from(Run).where(Run.source_id == sid)
            )
            return documents or 0, chunks or 0, runs or 0

    return run_db(api.database_url, scenario)
