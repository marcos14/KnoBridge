"""Tickets of a tickets source through the real ingestion (production connector factory with the
``tickets`` connector, real Postgres, fake embeddings): the workflow on the Temporal test server
indexes, updates, filters and removes tickets and erases the raw payload; the steps alone show
the payload survives a failed batch, a retried batch changes nothing, a ticket that cannot be
read keeps its payload with the error, and another workspace's inbox is never touched."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import pytest
from ingestion_harness import TASK_QUEUE, Harness, credentials, database
from sqlalchemy import select, update
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from knobridge.audit.models import JSONValue
from knobridge.core.db import scoped_session, system_session
from knobridge.core.settings import Settings
from knobridge.ingestion.connectors import SettingsConnectorFactory
from knobridge.ingestion.indexer import Indexer
from knobridge.ingestion.models import (
    Chunk,
    Document,
    DocumentKind,
    Run,
    RunError,
    RunStatus,
    RunTrigger,
    Source,
)
from knobridge.ingestion.runs import RunLifecycle, RunScope
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import SyncStarter, start_sync
from knobridge.llm.errors import ProviderUnavailableError
from knobridge.llm.pricing import EmbeddingPriceTable
from knobridge.tickets.connector import TicketsConnectorFactory
from knobridge.tickets.ingest import apply_items, check_items
from knobridge.tickets.models import IngestToken, TicketInboxItem, TicketInboxState
from knobridge.workers.ingestion import IngestionWorkflow, workflow_id
from knobridge.workers.ingestion_activities import IngestionActivities, TemporalSyncStarter

pytestmark = pytest.mark.integration


@dataclass
class TicketsWorld:
    h: Harness
    source_id: uuid.UUID

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.h.seeded.workspace_id

    def scope_of(self, run_id: uuid.UUID) -> RunScope:
        return RunScope(self.workspace_id, self.source_id, run_id)

    def connectors(self) -> SettingsConnectorFactory:
        return SettingsConnectorFactory(
            Settings(env="test"), tickets=TicketsConnectorFactory(self.h.factory, self.h.clock)
        )

    def lifecycle(self) -> RunLifecycle:
        return RunLifecycle(self.h.factory, self.h.clock, self.connectors(), EmbeddingPriceTable())

    def indexer(self) -> Indexer:
        h = self.h
        return Indexer(
            h.factory, h.clock, self.connectors(), credentials(h.clock).reveal_key, h.embeddings
        )


type Body = Callable[[TicketsWorld], Awaitable[None]]


def _scenario(database_url: str, body: Body) -> None:
    async def main() -> None:
        async with database(database_url, {}) as h:
            await body(await _world(h))

    asyncio.run(main())


async def _tickets_source(
    h: Harness, workspace_id: uuid.UUID, collection_id: uuid.UUID, config: dict[str, JSONValue]
) -> uuid.UUID:
    async with system_session(h.factory) as db:
        source = Source(
            workspace_id=workspace_id,
            collection_id=collection_id,
            kind=SourceKind.TICKETS,
            name="Chamados",
            config=config,
        )
        db.add(source)
        await db.flush()
        prefix = secrets.token_hex(4)
        db.add(
            IngestToken(
                workspace_id=workspace_id,
                source_id=source.id,
                token_prefix=prefix,
                token_hash=hashlib.sha256(prefix.encode()).hexdigest(),
                issued_at=h.clock.now(),
            )
        )
        return source.id


async def _world(h: Harness, config: dict[str, JSONValue] | None = None) -> TicketsWorld:
    statuses: dict[str, JSONValue] = {"statuses": ["open", "pending", "resolved"]}
    source_id = await _tickets_source(
        h, h.seeded.workspace_id, h.seeded.collection_id, config or statuses
    )
    return TicketsWorld(h, source_id)


def _ticket(
    external_id: str, *, status: str = "open", minute: int = 0, body: str = "O caixa não fecha."
) -> dict[str, JSONValue]:
    return {
        "op": "upsert",
        "ticket": {
            "external_id": external_id,
            "number": external_id.removeprefix("T-"),
            "title": f"Erro no caixa {external_id}",
            "status": status,
            "created_at": "2026-10-01T09:00:00Z",
            "updated_at": f"2026-10-01T10:{minute:02d}:00Z",
            "messages": [{"role": "customer", "body": body, "created_at": "2026-10-01T09:00:00Z"}],
        },
    }


def _delete(external_id: str) -> dict[str, JSONValue]:
    return {"op": "delete", "external_id": external_id, "deleted_at": "2026-10-02T10:00:00Z"}


async def _push(world: TicketsWorld, *items: dict[str, JSONValue]) -> None:
    await _push_to(world.h, world.workspace_id, world.source_id, *items)


async def _push_to(
    h: Harness, workspace_id: uuid.UUID, source_id: uuid.UUID, *items: dict[str, JSONValue]
) -> None:
    async with scoped_session(h.factory, workspace_id=workspace_id, user_id=None) as db:
        await apply_items(
            db,
            workspace_id=workspace_id,
            source_id=source_id,
            items=check_items(list(items)),
            now=h.clock.now(),
        )


async def _start(world: TicketsWorld, starter: SyncStarter) -> Run:
    return await start_sync(
        world.h.factory,
        starter,
        world.h.clock,
        workspace_id=world.workspace_id,
        source_id=world.source_id,
        trigger=RunTrigger.INGEST,
    )


async def _steps(world: TicketsWorld) -> Run:
    """One run through the steps the activities call, without Temporal."""
    run = await _start(world, world.h.starter)
    scope = world.scope_of(run.id)
    lifecycle, indexer = world.lifecycle(), world.indexer()
    await lifecycle.open(scope)
    total = await lifecycle.list_changes(scope)
    for start in range(0, total, 50):
        await indexer.process_batch(scope, start, 50)
    await lifecycle.finish(scope, RunStatus.SUCCEEDED)
    return await world.h.run(run.id)


async def _entries(world: TicketsWorld) -> dict[str, TicketInboxItem]:
    async with system_session(world.h.factory) as db:
        rows = await db.scalars(
            select(TicketInboxItem).where(TicketInboxItem.source_id == world.source_id)
        )
        return {row.external_id: row for row in rows}


async def _documents(world: TicketsWorld) -> dict[str, Document]:
    async with world.h.session() as db:
        rows = await db.scalars(select(Document).where(Document.source_id == world.source_id))
        return {row.natural_key: row for row in rows}


async def _chunks(world: TicketsWorld) -> list[Chunk]:
    async with world.h.session() as db:
        rows = await db.scalars(
            select(Chunk)
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.source_id == world.source_id)
            .order_by(Document.natural_key, Chunk.position)
        )
        return list(rows)


def test_tickets_workflow_indexes_updates_filters_and_removes(app_database_url: str) -> None:
    async def body(world: TicketsWorld) -> None:
        h = world.h
        async with await WorkflowEnvironment.start_time_skipping() as env:
            starter = TemporalSyncStarter(env.client, TASK_QUEUE)
            activities = IngestionActivities(
                world.lifecycle(), world.indexer(), heartbeat_interval=0.05
            )
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[IngestionWorkflow],
                activities=activities.all(),
                max_heartbeat_throttle_interval=timedelta(milliseconds=50),
                default_heartbeat_throttle_interval=timedelta(milliseconds=50),
            ):

                async def sync() -> Run:
                    run = await _start(world, starter)
                    handle = env.client.get_workflow_handle_for(
                        IngestionWorkflow.run, workflow_id(str(world.source_id))
                    )
                    with contextlib.suppress(Exception):
                        await handle.result()
                    return await h.run(run.id)

                await _push(world, _ticket("T-1"), _ticket("T-2"), _ticket("T-3"))
                first = await sync()
                indexed = await _entries(world)
                await _push(
                    world,
                    _ticket("T-1", minute=5, body="Agora aparece o erro 4021."),
                    _delete("T-2"),
                    _ticket("T-3", status="closed", minute=5),
                    _ticket("T-4", status="resolved"),
                )
                second = await sync()

        entries = await _entries(world)
        documents = await _documents(world)
        chunks = await _chunks(world)
        assert (first.status, first.trigger, first.documents_new) == (
            RunStatus.SUCCEEDED,
            RunTrigger.INGEST,
            3,
        )
        assert {entry.state for entry in indexed.values()} == {TicketInboxState.INDEXED}
        assert all(entry.payload is None for entry in indexed.values())
        assert (second.status, second.documents_new, second.documents_changed) == (
            RunStatus.SUCCEEDED,
            1,
            1,
        )
        assert second.documents_removed == 2
        assert sorted(documents) == ["T-1", "T-4"]
        assert {document.kind for document in documents.values()} == {DocumentKind.TICKET}
        assert documents["T-1"].uri == "ticket:T-1"
        assert {key: entry.state for key, entry in entries.items()} == {
            "T-1": TicketInboxState.INDEXED,
            "T-2": TicketInboxState.DELETED,
            "T-3": TicketInboxState.FILTERED,
            "T-4": TicketInboxState.INDEXED,
        }
        assert all(entry.payload is None for entry in entries.values())
        assert "erro 4021" in str(chunks[0].meta["display"])
        assert {
            key: chunks[0].meta[key] for key in ("kind", "external_id", "ticket_number", "section")
        } == {"kind": "ticket", "external_id": "T-1", "ticket_number": "1", "section": "problem"}

    _scenario(app_database_url, body)


def test_tickets_payload_survives_a_failed_batch(app_database_url: str) -> None:
    async def body(world: TicketsWorld) -> None:
        h = world.h
        await _push(world, _ticket("T-1"))
        run = await _start(world, h.starter)
        scope = world.scope_of(run.id)
        lifecycle, indexer = world.lifecycle(), world.indexer()
        await lifecycle.open(scope)
        await lifecycle.list_changes(scope)
        h.embeddings.provider.error = ProviderUnavailableError("down", provider="fake")
        with pytest.raises(ProviderUnavailableError):
            await indexer.process_batch(scope, 0, 50)
        failed = (await _entries(world))["T-1"]
        h.embeddings.provider.error = None
        await indexer.process_batch(scope, 0, 50)
        # The retried batch has nothing left to do.
        await indexer.process_batch(scope, 0, 50)
        await lifecycle.finish(scope, RunStatus.SUCCEEDED)
        done = (await _entries(world))["T-1"]

        assert (failed.state, failed.indexed_hash) == (TicketInboxState.PENDING, None)
        assert failed.payload is not None
        assert (done.state, done.payload) == (TicketInboxState.INDEXED, None)
        assert (await h.run(run.id)).documents_new == 1
        assert len(await _documents(world)) == 1

    _scenario(app_database_url, body)


def test_tickets_second_sync_has_nothing_to_do(app_database_url: str) -> None:
    async def body(world: TicketsWorld) -> None:
        await _push(world, _ticket("T-1"))
        await _steps(world)
        # The same ticket again is ``unchanged``: nothing new in the inbox.
        await _push(world, _ticket("T-1"))

        again = await _steps(world)

        assert (again.status, again.documents_new, again.documents_changed) == (
            RunStatus.SUCCEEDED,
            0,
            0,
        )
        assert again.embedding_tokens == 0
        assert (await _entries(world))["T-1"].state is TicketInboxState.INDEXED

    _scenario(app_database_url, body)


def test_tickets_unreadable_ticket_keeps_its_payload_and_error(app_database_url: str) -> None:
    async def body(world: TicketsWorld) -> None:
        await _push(world, _ticket("T-1"), _ticket("T-2"))
        async with system_session(world.h.factory) as db:
            await db.execute(
                update(TicketInboxItem)
                .where(
                    TicketInboxItem.source_id == world.source_id,
                    TicketInboxItem.external_id == "T-2",
                )
                .values(payload={"external_id": "T-2", "status": "open"})
            )

        run = await _steps(world)
        entries = await _entries(world)
        async with world.h.session() as db:
            errors = list(await db.scalars(select(RunError).where(RunError.run_id == run.id)))

        assert (run.status, run.documents_new, run.documents_failed) == (RunStatus.SUCCEEDED, 1, 1)
        assert [(error.document_key, error.code) for error in errors] == [("T-2", "ticket_invalid")]
        assert entries["T-1"].state is TicketInboxState.INDEXED
        assert entries["T-2"].state is TicketInboxState.PENDING
        assert entries["T-2"].payload == {"external_id": "T-2", "status": "open"}
        assert (entries["T-2"].last_error or "").startswith("ticket_invalid: ")

    _scenario(app_database_url, body)


def test_tickets_sync_leaves_other_workspaces_alone(app_database_url: str) -> None:
    async def body(world: TicketsWorld) -> None:
        async with database(app_database_url, {}) as other:
            other_source = await _tickets_source(
                other, other.seeded.workspace_id, other.seeded.collection_id, {}
            )
            await _push_to(other, other.seeded.workspace_id, other_source, _ticket("T-1"))
            await _push(world, _ticket("T-1"))

            await _steps(world)
            async with system_session(other.factory) as db:
                theirs = await db.scalar(
                    select(TicketInboxItem).where(TicketInboxItem.source_id == other_source)
                )

        assert (await _entries(world))["T-1"].state is TicketInboxState.INDEXED
        assert theirs is not None
        assert (theirs.state, theirs.processed_at) == (TicketInboxState.PENDING, None)
        assert theirs.payload is not None

    _scenario(app_database_url, body)
