"""The optional hook a connector uses to settle each item of a run in the engine's transaction.

Most connectors only read their source. The internal ``tickets`` connector also owns state the
engine must update when it is done with an item: the inbox entry leaves ``pending``, and its raw
payload is erased, only once the document is written (docs/specs/chamados.md, "Fim do
processamento e apagamento do bruto"). The engine calls ``settle`` inside the same transaction
that writes the document, removes it or records its error, and marks the run item done, so
either both happen or neither does: a retried batch never loses a ticket nor settles it twice.

This module does not know the tickets: the connector implements ``SettlingConnector`` and the
indexer checks for it, so ``ingestion`` keeps not importing ``tickets``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.connectors.base import DocumentRef


class ItemOutcome(StrEnum):
    # The document is in the index with the fetched content (written now, or already equal).
    INDEXED = "indexed"
    # A removal was applied (the document is gone, or never existed).
    REMOVED = "removed"
    # Fetching or parsing failed; a ``RunError`` was recorded.
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Settlement:
    ref: DocumentRef
    outcome: ItemOutcome
    # ``<code>: <message>`` of a failure, never document content.
    error: str | None = None


@runtime_checkable
class SettlingConnector(Protocol):
    async def settle(self, db: AsyncSession, settlement: Settlement) -> None:
        """Record the outcome of one item in ``db`` (the engine's transaction, scoped to the
        run's workspace). Must be idempotent and must not commit."""
        ...


# What the batch store runs inside a document's transaction.
type Settle = Callable[[AsyncSession], Awaitable[None]]


def settle_with(connector: object, settlement: Settlement) -> Settle | None:
    """The settle step of ``connector`` for one item, or ``None`` when it has none."""
    if not isinstance(connector, SettlingConnector):
        return None
    settling = connector

    async def settle(db: AsyncSession) -> None:
        await settling.settle(db, settlement)

    return settle
