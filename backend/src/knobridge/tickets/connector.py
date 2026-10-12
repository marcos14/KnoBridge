"""The internal ``tickets`` connector: the inbox of a tickets source as ``ticket`` documents
(docs/specs/chamados.md, "Conector interno tickets").

The inbox is the state, so the cursor only names the connector. ``list_changes`` reads the
entries waiting to be processed: a pending ticket whose status the source indexes is added (never
indexed) or changed; a pending ticket outside ``statuses`` and a tombstone are removals. ``fetch``
validates the stored payload again, anonymizes it (when the source asks) and renders its
Markdown; its hash covers the Markdown and the citation metadata.

The connector also settles each item (``ingestion.settle``) in the transaction in which the
engine writes the document, removes it or records its error: the entry leaves ``pending`` and its
raw payload is erased only together with the document write, and only if the entry still holds
the version that was fetched (a newer one, received meanwhile, stays for the next run, which the
upload already asked for). Like the ``knowledge`` connector, it reads the database in a
transaction scoped to the source's workspace, without a user.
"""

from __future__ import annotations

import uuid
from contextlib import AbstractAsyncContextManager
from http import HTTPStatus
from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import ColumnElement, null, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import (
    ConnectorError,
    DocumentNotFoundError,
    InvalidCursorError,
    SourceUnavailableError,
)
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.ingestion.models import DocumentKind, Source
from knobridge.ingestion.settle import ItemOutcome, Settlement
from knobridge.ingestion.source_config import TicketsSourceConfig
from knobridge.tickets.markdown import render_ticket
from knobridge.tickets.models import ERROR_MAX_LENGTH, TicketInboxItem, TicketInboxState
from knobridge.tickets.tokens import ingest_token_failure
from knobridge.tickets.wire import TicketIn

CURSOR_KIND = "tickets"
CURSOR_VERSION = 1


class TicketsCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["tickets"]
    version: Literal[1]


class StoredTicketInvalidError(ConnectorError):
    """A pending payload no longer passes the ticket schema; it stays for a later run."""

    code = "ticket_invalid"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


def _check_cursor(cursor: Cursor | None) -> None:
    if cursor is None:
        return
    try:
        TicketsCursor.model_validate(cursor)
    except PydanticValidationError as exc:
        raise InvalidCursorError("cursor was not produced by the tickets connector") from exc


def _refs(keys: list[str]) -> tuple[DocumentRef, ...]:
    return tuple(DocumentRef(key, DocumentKind.TICKET) for key in sorted(keys))


# Normalized status of the stored ticket (``None`` for a tombstone, which has no payload).
_STATUS = TicketInboxItem.payload["status"].astext


class TicketsConnector:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        clock: Clock,
        *,
        source: Source,
        config: TicketsSourceConfig,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._source = source
        self._workspace_id: uuid.UUID = source.workspace_id
        self._source_id: uuid.UUID = source.id
        self._config = config
        self._statuses = [status.value for status in config.statuses]
        # Content hash of each entry fetched by this instance (one per batch): the version
        # whose document the engine writes, and so the one a settlement may close.
        self._fetched: dict[str, str] = {}

    def _session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return scoped_session(self._sessions, workspace_id=self._workspace_id, user_id=None)

    def _entry(self, key: str) -> list[ColumnElement[bool]]:
        return [
            TicketInboxItem.workspace_id == self._workspace_id,
            TicketInboxItem.source_id == self._source_id,
            TicketInboxItem.external_id == key,
        ]

    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        _check_cursor(cursor)
        async with self._session() as db:
            rows = (
                await db.execute(
                    select(
                        TicketInboxItem.external_id,
                        TicketInboxItem.state,
                        TicketInboxItem.indexed_hash,
                        _STATUS,
                    ).where(
                        TicketInboxItem.workspace_id == self._workspace_id,
                        TicketInboxItem.source_id == self._source_id,
                        TicketInboxItem.state.in_(
                            [TicketInboxState.PENDING, TicketInboxState.PENDING_DELETE]
                        ),
                    )
                )
            ).all()
        added: list[str] = []
        changed: list[str] = []
        removed: list[str] = []
        for key, state, indexed_hash, status in rows:
            if state is TicketInboxState.PENDING_DELETE or status not in self._statuses:
                removed.append(key)
            elif indexed_hash is None:
                added.append(key)
            else:
                changed.append(key)
        return ChangeSet(
            added=_refs(added),
            changed=_refs(changed),
            removed=_refs(removed),
            cursor={"kind": CURSOR_KIND, "version": CURSOR_VERSION},
        )

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        async with self._session() as db:
            row = (
                await db.execute(
                    select(TicketInboxItem.payload, TicketInboxItem.content_hash).where(
                        *self._entry(ref.key), TicketInboxItem.state == TicketInboxState.PENDING
                    )
                )
            ).one_or_none()
        # Gone, processed or turned into a tombstone since it was listed.
        if row is None or row.payload is None or row.content_hash is None:
            raise DocumentNotFoundError("ticket is not pending", details={"key": ref.key})
        try:
            ticket = TicketIn.model_validate(row.payload)
        except PydanticValidationError as exc:
            raise StoredTicketInvalidError(
                "stored ticket does not match the ticket schema", details={"key": ref.key}
            ) from exc
        # A newer version outside ``statuses`` arrived since the listing: not indexed now; the
        # next run lists it as a removal.
        if ticket.status.value not in self._statuses:
            raise DocumentNotFoundError("ticket status is not indexed", details={"key": ref.key})
        document = render_ticket(
            ticket,
            anonymize=self._config.anonymize,
            include_internal_notes=self._config.include_internal_notes,
        )
        self._fetched[ref.key] = row.content_hash
        return RawDocument(
            ref=DocumentRef(ref.key, DocumentKind.TICKET),
            title=document.title,
            uri=document.uri,
            content=document.markdown.encode("utf-8"),
            extension="md",
            metadata=document.metadata,
            digest=document.digest,
        )

    async def permissions(self, ref: DocumentRef) -> Acl:
        # No per-ticket ACL (decision D7): the collection's permission applies.
        return OPEN_ACL

    async def test_connection(self) -> None:
        """Readable while the source has an ingest token (docs/specs/chamados.md)."""
        async with self._session() as db:
            failure = await ingest_token_failure(db, self._source)
        if failure is not None:
            raise SourceUnavailableError(failure.message, details=failure.details)

    async def settle(self, db: AsyncSession, settlement: Settlement) -> None:
        """Close the entry of one processed item, in the engine's transaction."""
        key = settlement.ref.key
        now = self._clock.now()
        entry = update(TicketInboxItem).where(*self._entry(key))
        if settlement.outcome is ItemOutcome.INDEXED:
            digest = self._fetched.get(key)
            if digest is None:
                return
            await db.execute(
                entry.where(
                    TicketInboxItem.state == TicketInboxState.PENDING,
                    TicketInboxItem.content_hash == digest,
                ).values(
                    state=TicketInboxState.INDEXED,
                    payload=null(),
                    indexed_hash=digest,
                    processed_at=now,
                    last_error=None,
                )
            )
        elif settlement.outcome is ItemOutcome.REMOVED:
            closed = {"indexed_hash": None, "processed_at": now, "last_error": None}
            await db.execute(
                entry.where(TicketInboxItem.state == TicketInboxState.PENDING_DELETE).values(
                    state=TicketInboxState.DELETED, **closed
                )
            )
            # Whatever version is pending now, it is filtered too only if its status still is.
            await db.execute(
                entry.where(
                    TicketInboxItem.state == TicketInboxState.PENDING,
                    _STATUS.not_in(self._statuses),
                ).values(state=TicketInboxState.FILTERED, payload=null(), **closed)
            )
        else:
            await db.execute(
                entry.where(TicketInboxItem.state == TicketInboxState.PENDING).values(
                    last_error=(settlement.error or "")[:ERROR_MAX_LENGTH]
                )
            )


class TicketsConnectorFactory:
    """Builds the tickets connector of a tickets source (``ingestion.connectors``)."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    def __call__(self, source: Source) -> TicketsConnector:
        config = source.typed_config()
        if not isinstance(config, TicketsSourceConfig):
            raise SourceUnavailableError("not a tickets source")
        return TicketsConnector(self._sessions, self._clock, source=source, config=config)
