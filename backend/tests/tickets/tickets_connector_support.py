"""World of the tickets connector tests: a workspace with a ``tickets`` source (config chosen per
test) and its ingest token, tickets pushed through the real inbox rules (``check_items`` +
``apply_items``) and the connector built by its production factory. Not a test module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from tickets_support import NOW, SessionFactory, new_token

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import DocumentRef
from knobridge.core.clock import FrozenClock
from knobridge.core.db import scoped_session, system_session
from knobridge.ingestion.models import Collection, DocumentKind, Source
from knobridge.ingestion.settle import ItemOutcome, Settlement
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import Workspace
from knobridge.tickets.connector import InboxConnector, TicketsConnectorFactory
from knobridge.tickets.ingest import ItemResult, apply_items, check_items
from knobridge.tickets.models import TicketInboxItem
from knobridge.tickets.push import TICKETS, PushKind

PROCESSED_AT = datetime(2026, 10, 12, 14, 0, tzinfo=UTC)


@dataclass(frozen=True)
class World:
    factory: SessionFactory
    source: Source

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.source.workspace_id

    @property
    def source_id(self) -> uuid.UUID:
        return self.source.id

    def connector(self) -> InboxConnector:
        return TicketsConnectorFactory(self.factory, FrozenClock(PROCESSED_AT))(self.source)


async def world(
    factory: SessionFactory,
    config: dict[str, JSONValue] | None = None,
    *,
    token: bool = True,
    kind: SourceKind = SourceKind.TICKETS,
) -> World:
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(workspace)
        await db.flush()
        credential = ProviderCredential(
            workspace_id=workspace.id,
            name="Fake",
            kind=ProviderKind.FAKE,
            key_ciphertext="v1.x",
            key_last4="1234",
        )
        db.add(credential)
        await db.flush()
        collection = Collection(
            workspace_id=workspace.id,
            name="Chamados",
            description="",
            credential_id=credential.id,
            embedding_model="fake-embedding",
        )
        db.add(collection)
        await db.flush()
        source = Source(
            workspace_id=workspace.id,
            collection_id=collection.id,
            kind=kind,
            name="Chamados",
            config=config or {},
        )
        db.add(source)
        await db.flush()
        if token:
            db.add(new_token(workspace.id, source.id))
        return World(factory, source)


def ticket(
    external_id: str,
    *,
    status: str = "open",
    updated_at: str = "2026-10-01T10:00:00Z",
    body: str = "O caixa não fecha.",
    **fields: JSONValue,
) -> dict[str, JSONValue]:
    payload: dict[str, JSONValue] = {
        "external_id": external_id,
        "title": f"Problema {external_id}",
        "status": status,
        "created_at": "2026-10-01T09:00:00Z",
        "updated_at": updated_at,
        "messages": [{"role": "customer", "body": body, "created_at": "2026-10-01T09:00:00Z"}],
    }
    payload.update(fields)
    return payload


def upsert(payload: dict[str, JSONValue]) -> dict[str, JSONValue]:
    return {"op": "upsert", "ticket": payload}


def delete(external_id: str, deleted_at: str = "2026-10-02T10:00:00Z") -> dict[str, JSONValue]:
    return {"op": "delete", "external_id": external_id, "deleted_at": deleted_at}


async def push(
    world: World, *items: dict[str, JSONValue], kind: PushKind = TICKETS
) -> list[ItemResult]:
    """Items through the same validation and inbox rules as ``POST /v1/ingest/tickets``."""
    async with scoped_session(world.factory, workspace_id=world.workspace_id, user_id=None) as db:
        return await apply_items(
            db,
            workspace_id=world.workspace_id,
            source_id=world.source_id,
            items=check_items(list(items), kind),
            now=NOW,
        )


async def entry(world: World, external_id: str) -> TicketInboxItem:
    async with system_session(world.factory) as db:
        row = await db.scalar(
            select(TicketInboxItem).where(
                TicketInboxItem.source_id == world.source_id,
                TicketInboxItem.external_id == external_id,
            )
        )
        assert row is not None
        return row


async def settle(
    world: World,
    connector: InboxConnector,
    external_id: str,
    outcome: ItemOutcome,
    error: str | None = None,
) -> None:
    """Settle one item in a transaction scoped like the engine's."""
    ref = DocumentRef(external_id, DocumentKind.TICKET)
    async with scoped_session(world.factory, workspace_id=world.workspace_id, user_id=None) as db:
        await connector.settle(db, Settlement(ref, outcome, error))
