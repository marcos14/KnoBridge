"""Harness for the ingestion tests: real Postgres with a seeded workspace, collection and
source, an in-memory connector, a recording fake embedding provider and, for the workflow
tests, the Temporal test server with a worker. Not a test module; imported by its basename."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from fakes.connector import FakeConnector
from fakes.embedding_provider import RecordingEmbeddingFactory
from knobridge.connectors.base import Connector, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, SourceUnavailableError
from knobridge.core.clock import FrozenClock
from knobridge.core.crypto import SecretBox
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.ingestion.indexer import Indexer
from knobridge.ingestion.models import (
    Chunk,
    Collection,
    Document,
    Run,
    RunError,
    RunItem,
    RunTrigger,
    Source,
)
from knobridge.ingestion.runs import RunLifecycle, RunScope
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import SyncStarter, start_sync
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.models import ProviderKind
from knobridge.llm.pricing import EmbeddingPriceTable
from knobridge.tenancy.models import Membership, Role, User, Workspace
from knobridge.workers.ingestion import BATCH_SIZE, IngestionWorkflow, workflow_id
from knobridge.workers.ingestion_activities import IngestionActivities, TemporalSyncStarter

SessionFactory = async_sessionmaker[AsyncSession]
TASK_QUEUE = "test-ingestion"
START = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
API_KEY = "sk-test-ingestion-2468"  # synthetic
SECRET = "test-secret-key-for-ingestion-0123456789"  # noqa: S105 - test value
MODEL = "text-embedding-3-small"


class ScriptedConnector(FakeConnector):
    """``FakeConnector`` whose ``fetch`` can fail (some keys, or the whole source) or wait on
    a gate."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        super().__init__(files)
        self.missing: set[str] = set()
        self.fetch_unavailable = False
        self.gate: asyncio.Event | None = None
        self.fetch_started = asyncio.Event()
        self.fetched: list[str] = []

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        self.fetched.append(ref.key)
        self.fetch_started.set()
        if self.gate is not None:
            await self.gate.wait()
        if self.fetch_unavailable:
            raise SourceUnavailableError("fake source is unavailable")
        if ref.key in self.missing:
            raise DocumentNotFoundError("document is not selected", details={"key": ref.key})
        return await super().fetch(ref)


class RecordingStarter:
    """``SyncStarter`` without Temporal: records the runs it was asked to start."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.started: list[uuid.UUID] = []

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        if self.error is not None:
            raise self.error
        self.started.append(run_id)

    async def cancel(self, source_id: uuid.UUID) -> None:
        raise AssertionError("not used by these tests")


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    collection_id: uuid.UUID
    source_id: uuid.UUID


@dataclass
class Harness:
    factory: SessionFactory
    seeded: Seeded
    connector: ScriptedConnector
    embeddings: RecordingEmbeddingFactory
    clock: FrozenClock
    starter: SyncStarter
    env: WorkflowEnvironment | None = None
    sources_seen: list[uuid.UUID] = field(default_factory=list[uuid.UUID])

    def connector_for(self, source: Source) -> Connector:
        self.sources_seen.append(source.id)
        return self.connector

    @property
    def lifecycle(self) -> RunLifecycle:
        return RunLifecycle(self.factory, self.clock, self.connector_for, EmbeddingPriceTable())

    @property
    def indexer(self) -> Indexer:
        return Indexer(
            self.factory,
            self.clock,
            self.connector_for,
            credentials(self.clock).reveal_key,
            self.embeddings,
        )

    def scope(self, run_id: uuid.UUID) -> RunScope:
        return RunScope(self.seeded.workspace_id, self.seeded.source_id, run_id)

    async def start(self) -> Run:
        return await start_sync(
            self.factory,
            self.starter,
            self.clock,
            workspace_id=self.seeded.workspace_id,
            source_id=self.seeded.source_id,
            trigger=RunTrigger.MANUAL,
        )

    def handle(self) -> WorkflowHandle[IngestionWorkflow, str]:
        assert self.env is not None
        return self.env.client.get_workflow_handle_for(
            IngestionWorkflow.run, workflow_id(str(self.seeded.source_id))
        )

    async def sync(self) -> Run:
        """Start a sync, wait for the workflow to end (whatever the outcome), reload the run."""
        run = await self.start()
        # A failed or cancelled workflow raises here; the outcome is asserted on the run row.
        with contextlib.suppress(Exception):
            await self.handle().result()
        return await self.run(run.id)

    def session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return scoped_session(self.factory, workspace_id=self.seeded.workspace_id, user_id=None)

    async def run(self, run_id: uuid.UUID) -> Run:
        async with self.session() as db:
            row = await db.get(Run, run_id)
            assert row is not None
            return row

    async def documents(self) -> dict[str, Document]:
        async with self.session() as db:
            rows = await db.scalars(
                select(Document).where(Document.source_id == self.seeded.source_id)
            )
            return {row.natural_key: row for row in rows}

    async def chunks(self) -> list[Chunk]:
        async with self.session() as db:
            rows = await db.scalars(
                select(Chunk)
                .where(Chunk.collection_id == self.seeded.collection_id)
                .order_by(Chunk.document_id, Chunk.position)
            )
            return list(rows)

    async def errors(self, run_id: uuid.UUID) -> list[RunError]:
        async with self.session() as db:
            rows = await db.scalars(select(RunError).where(RunError.run_id == run_id))
            return list(rows)

    async def items(self, run_id: uuid.UUID) -> list[RunItem]:
        async with self.session() as db:
            rows = await db.scalars(
                select(RunItem).where(RunItem.run_id == run_id).order_by(RunItem.ordinal)
            )
            return list(rows)

    async def source(self) -> Source:
        async with self.session() as db:
            row = await db.get(Source, self.seeded.source_id)
            assert row is not None
            return row


def credentials(clock: FrozenClock) -> ProviderCredentialService:
    return ProviderCredentialService(
        clock, SecretBox.derive(SECRET, info=CREDENTIALS_KEY_INFO), allow_fake=True
    )


async def seed(factory: SessionFactory, clock: FrozenClock, *, model: str = MODEL) -> Seeded:
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        user = User(email=f"{uuid.uuid4().hex[:12]}@example.test", name="Ingest")
        db.add_all([workspace, user])
        await db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role=Role.OWNER))
        workspace_id, user_id = workspace.id, user.id
    async with scoped_session(factory, workspace_id=workspace_id, user_id=user_id) as db:
        credential = await credentials(clock).create(
            db,
            workspace_id=workspace_id,
            actor_id=user_id,
            name="Fake",
            kind=ProviderKind.FAKE,
            base_url=None,
            api_key=API_KEY,
            ip=None,
        )
        collection = Collection(
            workspace_id=workspace_id,
            name="Docs",
            description="",
            credential_id=credential.id,
            embedding_model=model,
        )
        db.add(collection)
        await db.flush()
        source = Source(
            workspace_id=workspace_id,
            collection_id=collection.id,
            kind=SourceKind.FOLDER,
            name="Pasta",
            config={"path": "/sources/docs"},
        )
        db.add(source)
        await db.flush()
        return Seeded(workspace_id, collection.id, source.id)


@asynccontextmanager
async def database(
    database_url: str, files: dict[str, bytes], *, model: str = MODEL
) -> AsyncGenerator[Harness]:
    """A seeded database and the fakes, with a ``RecordingStarter`` (no Temporal)."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    factory = create_session_factory(engine)
    clock = FrozenClock(START)
    try:
        yield Harness(
            factory=factory,
            seeded=await seed(factory, clock, model=model),
            connector=ScriptedConnector(files),
            embeddings=RecordingEmbeddingFactory(),
            clock=clock,
            starter=RecordingStarter(),
        )
    finally:
        await engine.dispose()


@asynccontextmanager
async def harness(
    database_url: str,
    files: dict[str, bytes],
    *,
    batch_size: int = BATCH_SIZE,
    model: str = MODEL,
) -> AsyncGenerator[Harness]:
    """``database`` plus the Temporal test server and a worker running the ingestion."""
    async with (
        database(database_url, files, model=model) as h,
        await WorkflowEnvironment.start_time_skipping() as env,
    ):
        h.env = env
        h.starter = TemporalSyncStarter(env.client, TASK_QUEUE, batch_size=batch_size)
        activities = IngestionActivities(h.lifecycle, h.indexer, heartbeat_interval=0.05)
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[IngestionWorkflow],
            activities=activities.all(),
            # Cancellation reaches an activity on its next heartbeat; keep that quick.
            max_heartbeat_throttle_interval=timedelta(milliseconds=50),
            default_heartbeat_throttle_interval=timedelta(milliseconds=50),
        ):
            yield h
