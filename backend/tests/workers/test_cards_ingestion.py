"""Cards of a cards source through the real ingestion steps (production connector factory with
the ``cards`` connector, real Postgres, fake embeddings): cards become ``card`` documents whose
chunks carry the card's citation data and the ``product_dev`` level, the raw payload is erased,
a status outside the source's is filtered and a removal deletes the document."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from ingestion_harness import Harness, credentials, database
from sqlalchemy import select

from knobridge.audit.models import JSONValue
from knobridge.core.db import scoped_session, system_session
from knobridge.core.settings import Settings
from knobridge.ingestion.connectors import SettingsConnectorFactory
from knobridge.ingestion.indexer import Indexer
from knobridge.ingestion.models import Chunk, Document, DocumentKind, Run, RunStatus, RunTrigger
from knobridge.ingestion.models import Source as SourceRow
from knobridge.ingestion.runs import RunLifecycle, RunScope
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import start_sync
from knobridge.levels.level import ResponseLevel
from knobridge.llm.pricing import EmbeddingPriceTable
from knobridge.tickets.connector import TicketsConnectorFactory
from knobridge.tickets.ingest import apply_items, check_items
from knobridge.tickets.models import IngestToken, TicketInboxItem, TicketInboxState
from knobridge.tickets.push import CARDS

pytestmark = pytest.mark.integration


@dataclass
class CardsWorld:
    h: Harness
    source_id: uuid.UUID

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.h.seeded.workspace_id

    def connectors(self) -> SettingsConnectorFactory:
        return SettingsConnectorFactory(
            Settings(env="test"), tickets=TicketsConnectorFactory(self.h.factory, self.h.clock)
        )


def _scenario(database_url: str, body: Callable[[CardsWorld], Awaitable[None]]) -> None:
    async def main() -> None:
        async with database(database_url, {}) as h:
            await body(await _world(h))

    asyncio.run(main())


async def _world(h: Harness) -> CardsWorld:
    async with system_session(h.factory) as db:
        source = SourceRow(
            workspace_id=h.seeded.workspace_id,
            collection_id=h.seeded.collection_id,
            kind=SourceKind.CARDS,
            name="Cards",
            config={"statuses": ["in_progress", "done"]},
        )
        db.add(source)
        await db.flush()
        prefix = secrets.token_hex(4)
        db.add(
            IngestToken(
                workspace_id=h.seeded.workspace_id,
                source_id=source.id,
                token_prefix=prefix,
                token_hash=hashlib.sha256(prefix.encode()).hexdigest(),
                issued_at=h.clock.now(),
            )
        )
        return CardsWorld(h, source.id)


def _card(external_id: str, *, status: str = "done", minute: int = 0) -> dict[str, JSONValue]:
    return {
        "op": "upsert",
        "card": {
            "external_id": external_id,
            "number": f"PROJ-{external_id}",
            "title": f"Exportar nota {external_id}",
            "type": "feature",
            "status": status,
            "sprint": {"name": "Sprint 42"},
            "description": {"body": "Emitir nota fiscal de exportação."},
            "created_at": "2026-10-01T09:00:00Z",
            "updated_at": f"2026-10-01T10:{minute:02d}:00Z",
        },
    }


async def _push(world: CardsWorld, *items: dict[str, JSONValue]) -> None:
    h = world.h
    async with scoped_session(h.factory, workspace_id=world.workspace_id, user_id=None) as db:
        await apply_items(
            db,
            workspace_id=world.workspace_id,
            source_id=world.source_id,
            items=check_items(list(items), CARDS),
            now=h.clock.now(),
        )


async def _steps(world: CardsWorld) -> Run:
    """One run through the steps the activities call, without Temporal."""
    h = world.h
    run = await start_sync(
        h.factory,
        h.starter,
        h.clock,
        workspace_id=world.workspace_id,
        source_id=world.source_id,
        trigger=RunTrigger.INGEST,
    )
    scope = RunScope(world.workspace_id, world.source_id, run.id)
    connectors = world.connectors()
    lifecycle = RunLifecycle(h.factory, h.clock, connectors, EmbeddingPriceTable())
    indexer = Indexer(h.factory, h.clock, connectors, credentials(h.clock).reveal_key, h.embeddings)
    await lifecycle.open(scope)
    total = await lifecycle.list_changes(scope)
    await indexer.process_batch(scope, 0, total)
    await lifecycle.finish(scope, RunStatus.SUCCEEDED)
    return await h.run(run.id)


async def _state(
    world: CardsWorld,
) -> tuple[dict[str, Document], list[Chunk], dict[str, TicketInboxItem]]:
    async with world.h.session() as db:
        documents = await db.scalars(select(Document).where(Document.source_id == world.source_id))
        by_key = {row.natural_key: row for row in documents}
        chunks = list(
            await db.scalars(
                select(Chunk).where(Chunk.document_id.in_(d.id for d in by_key.values()))
            )
        )
    async with system_session(world.h.factory) as db:
        rows = await db.scalars(
            select(TicketInboxItem).where(TicketInboxItem.source_id == world.source_id)
        )
        entries = {row.external_id: row for row in rows}
    return by_key, chunks, entries


def test_cards_are_indexed_as_card_documents_at_the_product_dev_level(
    app_database_url: str,
) -> None:
    async def body(world: CardsWorld) -> None:
        await _push(world, _card("1"), _card("2", status="backlog"))

        run = await _steps(world)

        assert run.status is RunStatus.SUCCEEDED
        documents, chunks, entries = await _state(world)
        assert set(documents) == {"1"}
        document = documents["1"]
        assert (document.kind, document.uri, document.title) == (
            DocumentKind.CARD,
            "card:1",
            "Exportar nota 1",
        )
        assert chunks
        for chunk in chunks:
            assert chunk.meta["kind"] == "card"
            assert chunk.meta["card_number"] == "PROJ-1"
            assert chunk.meta["sprint"] == "Sprint 42"
            assert chunk.min_level is ResponseLevel.PRODUCT_DEV
        assert (entries["1"].state, entries["1"].payload) == (TicketInboxState.INDEXED, None)
        assert (entries["2"].state, entries["2"].payload) == (TicketInboxState.FILTERED, None)

    _scenario(app_database_url, body)


def test_cards_removal_deletes_the_document(app_database_url: str) -> None:
    async def body(world: CardsWorld) -> None:
        await _push(world, _card("1"))
        await _steps(world)
        await _push(
            world,
            {"op": "delete", "external_id": "1", "deleted_at": "2026-10-02T10:00:00Z"},
        )

        await _steps(world)

        documents, _, entries = await _state(world)
        assert documents == {}
        assert entries["1"].state is TicketInboxState.DELETED

    _scenario(app_database_url, body)
