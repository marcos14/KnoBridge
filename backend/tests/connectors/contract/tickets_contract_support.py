"""The ``tickets`` connector under the contract: a tickets source in real Postgres whose
documents are tickets pushed through the inbox rules (``check_items`` + ``apply_items``).

Unlike a tree, the inbox is the state: what was listed stays pending until the engine processes
it, so ``processed`` fetches and settles a listing the way the indexer does. Each document is a
ticket whose first customer message is the contract content; what ``fetch`` returns is that
ticket's Markdown and hash (``render_ticket``). The ``cards`` connector runs the same contract
(``CardsContractSource``), each document a card whose description is the content. Not a test
module.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import ChangeSet
from knobridge.core.clock import FrozenClock
from knobridge.core.db import create_session_factory, scoped_session, system_session
from knobridge.ingestion.models import Collection, DocumentKind, Source
from knobridge.ingestion.settle import ItemOutcome, Settlement
from knobridge.ingestion.source_config import SourceKind
from knobridge.llm.models import ProviderCredential, ProviderKind
from knobridge.tenancy.models import Workspace
from knobridge.tickets.card_markdown import render_card
from knobridge.tickets.card_wire import CardIn
from knobridge.tickets.connector import InboxConnector, TicketsConnectorFactory
from knobridge.tickets.ingest import apply_items, check_items
from knobridge.tickets.markdown import RenderedDocument, render_ticket
from knobridge.tickets.models import IngestToken
from knobridge.tickets.push import CARDS, TICKETS
from knobridge.tickets.wire import TicketIn

START = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)


def _instant(minutes: int) -> str:
    return (START + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


class TicketsContractSource:
    kind = DocumentKind.TICKET
    source_kind = SourceKind.TICKETS
    push_kind = TICKETS

    def record(self, key: str, content: bytes) -> dict[str, JSONValue]:
        """The pushed record whose indexed text is ``content``."""
        return {
            "external_id": key,
            "title": f"Chamado {key}",
            "status": "open",
            "created_at": _instant(0),
            "updated_at": _instant(self._version),
            "messages": [{"role": "customer", "body": content.decode(), "created_at": _instant(0)}],
        }

    def rendered(self, record: dict[str, JSONValue]) -> RenderedDocument:
        ticket = TicketIn.model_validate(record)
        return render_ticket(ticket, anonymize=True, include_internal_notes=False)

    def __init__(self, database_url: str, tmp_path: Path) -> None:
        # NullPool: every call runs in its own event loop and keeps no connection.
        self._factory = create_session_factory(
            create_async_engine(database_url, poolclass=NullPool)
        )
        self._clock = FrozenClock(START)
        self._version = 0
        self._records: dict[str, dict[str, JSONValue]] = {}
        self._source = asyncio.run(self._seed())

    async def _seed(self) -> Source:
        async with system_session(self._factory) as db:
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
                kind=self.source_kind,
                name="Caixa de entrada",
                config={},
            )
            db.add(source)
            await db.flush()
            prefix = secrets.token_hex(4)
            token = f"kbi_{prefix}_{secrets.token_urlsafe(32)}"
            db.add(
                IngestToken(
                    workspace_id=workspace.id,
                    source_id=source.id,
                    token_prefix=prefix,
                    token_hash=hashlib.sha256(token.encode()).hexdigest(),
                    issued_at=START,
                )
            )
            return source

    def connector(self) -> InboxConnector:
        return TicketsConnectorFactory(self._factory, self._clock)(self._source)

    def _push(self, item: dict[str, JSONValue]) -> None:
        async def push() -> None:
            async with scoped_session(
                self._factory, workspace_id=self._source.workspace_id, user_id=None
            ) as db:
                await apply_items(
                    db,
                    workspace_id=self._source.workspace_id,
                    source_id=self._source.id,
                    items=check_items([item], self.push_kind),
                    now=START,
                )

        asyncio.run(push())

    def add(self, key: str, content: bytes) -> None:
        self._version += 1
        record = self.record(key, content)
        self._records[key] = record
        self._push({"op": "upsert", self.push_kind.item_key: record})

    def change(self, key: str, content: bytes) -> None:
        self.add(key, content)

    def remove(self, key: str) -> None:
        self._version += 1
        self._push({"op": "delete", "external_id": key, "deleted_at": _instant(self._version)})

    def break_source(self) -> None:
        async def drop_token() -> None:
            async with system_session(self._factory) as db:
                source_id = self._source.id
                await db.execute(delete(IngestToken).where(IngestToken.source_id == source_id))

        asyncio.run(drop_token())

    def expected(self, key: str, content: bytes) -> tuple[bytes, str]:
        document = self.rendered(self._records[key])
        return document.markdown.encode("utf-8"), document.digest

    def processed(self, changes: ChangeSet) -> None:
        async def process(connector: InboxConnector) -> None:
            settlements = [Settlement(ref, ItemOutcome.REMOVED) for ref in changes.removed]
            for ref in changes.added + changes.changed:
                await connector.fetch(ref)
                settlements.append(Settlement(ref, ItemOutcome.INDEXED))
            for settlement in settlements:
                async with scoped_session(
                    self._factory, workspace_id=self._source.workspace_id, user_id=None
                ) as db:
                    await connector.settle(db, settlement)

        asyncio.run(process(self.connector()))


class CardsContractSource(TicketsContractSource):
    """The ``cards`` connector under the same contract: each document is a card whose
    description is the contract content."""

    kind = DocumentKind.CARD
    source_kind = SourceKind.CARDS
    push_kind = CARDS

    def record(self, key: str, content: bytes) -> dict[str, JSONValue]:
        return {
            "external_id": key,
            "title": f"Card {key}",
            "type": "task",
            "status": "backlog",
            "description": {"body": content.decode()},
            "created_at": _instant(0),
            "updated_at": _instant(self._version),
        }

    def rendered(self, record: dict[str, JSONValue]) -> RenderedDocument:
        return render_card(CardIn.model_validate(record), anonymize=True, include_comments=True)
