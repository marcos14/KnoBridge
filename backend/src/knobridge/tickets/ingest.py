"""A batch of tickets into the inbox (docs/specs/chamados.md, "POST /v1/ingest/tickets" and
"Idempotência e regra do updated_at").

``check_items`` validates every item on its own (an invalid item never sinks the batch) and is
pure, so the upload of the panel can reuse it. ``apply_items`` writes the accepted ones in the
caller's transaction, scoped to the source's workspace: each item is one atomic
``INSERT … ON CONFLICT … DO UPDATE … WHERE`` on ``(source_id, external_id)``, so two batches
with the same ticket converge to the larger ``updated_at``; when the guarded update does not
happen, the stored entry tells ``unchanged`` from ``stale``.

Cards (docs/specs/cards.md) go through the same functions with ``kind=CARDS``: only the key of
the record in an upsert item, its model and the size error change.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, cast

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.tickets.models import TicketInboxItem, TicketInboxState
from knobridge.tickets.push import TICKETS, PushKind
from knobridge.tickets.wire import (
    MAX_TICKET_BYTES,
    ExternalId,
    Problem,
    TicketDeleteItemIn,
    canonical_payload,
    problems,
    serialized,
)

type Op = Literal["upsert", "delete"]
_EXTERNAL_ID: TypeAdapter[str] = TypeAdapter(ExternalId)


class ItemStatus(StrEnum):
    QUEUED = "queued"
    UNCHANGED = "unchanged"
    STALE = "stale"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ItemError:
    code: str
    message: str
    details: object


@dataclass(frozen=True)
class ItemResult:
    index: int
    op: Op
    external_id: str | None
    status: ItemStatus
    error: ItemError | None = None


@dataclass(frozen=True)
class UpsertItem:
    index: int
    external_id: str
    payload: dict[str, JSONValue]
    content_hash: str
    updated_at: datetime


@dataclass(frozen=True)
class DeleteItem:
    index: int
    external_id: str
    deleted_at: datetime | None


type CheckedItem = UpsertItem | DeleteItem | ItemResult


def _rejected(index: int, op: Op, external_id: str | None, error: ItemError) -> ItemResult:
    return ItemResult(index, op, external_id, ItemStatus.REJECTED, error)


def invalid_item(details: list[Problem], noun: str = TICKETS.item_key) -> ItemError:
    return ItemError("validation_error", f"The item does not match the {noun} format.", details)


def readable_id(value: object) -> str | None:
    """The ``external_id`` of an invalid item, when that field alone is valid."""
    try:
        return _EXTERNAL_ID.validate_python(value, strict=True)
    except PydanticValidationError:
        return None


def _check_upsert(index: int, raw: Mapping[str, object], kind: PushKind) -> UpsertItem | ItemResult:
    key = kind.item_key
    record = raw.get(key)
    item_problems: list[Problem] = [
        {"loc": [name], "problem": "extra_forbidden"} for name in raw if name not in ("op", key)
    ]
    if not isinstance(record, dict):
        item_problems.append(
            {"loc": [key], "problem": "missing" if record is None else "model_type"}
        )
        return _rejected(index, "upsert", None, invalid_item(item_problems, key))
    fields = cast("Mapping[str, object]", record)
    external_id = readable_id(fields.get("external_id"))
    encoded = serialized(fields)
    if len(encoded) > MAX_TICKET_BYTES:
        error = ItemError(
            kind.too_large_code, f"The {key} is above 1 MiB.", {"max_bytes": MAX_TICKET_BYTES}
        )
        return _rejected(index, "upsert", external_id, error)
    try:
        validated = kind.model.model_validate_json(encoded, strict=True)
    except PydanticValidationError as exc:
        # Record problems are located inside the record, as the spec shows them.
        error = invalid_item(item_problems + problems(exc), key)
        return _rejected(index, "upsert", external_id, error)
    if item_problems:
        return _rejected(index, "upsert", validated.external_id, invalid_item(item_problems, key))
    payload, content_hash = canonical_payload(validated)
    return UpsertItem(index, validated.external_id, payload, content_hash, validated.updated_at)


def _check_delete(index: int, raw: Mapping[str, object], kind: PushKind) -> DeleteItem | ItemResult:
    try:
        validated = TicketDeleteItemIn.model_validate_json(serialized(raw), strict=True)
    except PydanticValidationError as exc:
        external_id = readable_id(raw.get("external_id"))
        return _rejected(index, "delete", external_id, invalid_item(problems(exc), kind.item_key))
    return DeleteItem(index, validated.external_id, validated.deleted_at)


def check_items(
    items: Sequence[Mapping[str, object]], kind: PushKind = TICKETS
) -> list[CheckedItem]:
    """Validate each item (``op`` already known to be ``upsert`` or ``delete``), in order.

    A repeated ``external_id`` is rejected as ``duplicate_in_batch`` when an earlier item with
    it was accepted; a rejected item never blocks a later valid one.
    """
    return check_indexed_items(enumerate(items), {}, kind)


def check_indexed_items(
    items: Iterable[tuple[int, Mapping[str, object]]],
    first_index: dict[str, int],
    kind: PushKind = TICKETS,
) -> list[CheckedItem]:
    """``check_items`` over items numbered by the caller (the upload numbers them by line or
    position), with ``first_index`` (``external_id`` → index of the first accepted item) kept
    across calls, so ``duplicate_in_batch`` covers a whole file read in blocks."""
    checked: list[CheckedItem] = []
    for index, raw in items:
        item = (
            _check_upsert(index, raw, kind)
            if raw["op"] == "upsert"
            else _check_delete(index, raw, kind)
        )
        if not isinstance(item, ItemResult):
            if item.external_id in first_index:
                error = ItemError(
                    "duplicate_in_batch",
                    "The external_id already appeared earlier in this batch.",
                    {"first_index": first_index[item.external_id]},
                )
                op: Op = "upsert" if isinstance(item, UpsertItem) else "delete"
                item = _rejected(index, op, item.external_id, error)
            else:
                first_index[item.external_id] = index
        checked.append(item)
    return checked


async def _stored(
    db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID, external_id: str
) -> TicketInboxItem:
    return (
        await db.scalars(
            select(TicketInboxItem).where(
                TicketInboxItem.workspace_id == workspace_id,
                TicketInboxItem.source_id == source_id,
                TicketInboxItem.external_id == external_id,
            )
        )
    ).one()


async def _upsert(
    db: AsyncSession, workspace_id: uuid.UUID, source_id: uuid.UUID, item: UpsertItem, now: datetime
) -> ItemStatus:
    table = TicketInboxItem.__table__
    statement = insert(TicketInboxItem).values(
        workspace_id=workspace_id,
        source_id=source_id,
        external_id=item.external_id,
        state=TicketInboxState.PENDING,
        payload=item.payload,
        content_hash=item.content_hash,
        ticket_updated_at=item.updated_at,
        received_at=now,
    )
    new = statement.excluded
    # Mirrors the table of the spec: a tombstone is revived only by a strictly newer ticket; a
    # ticket is replaced by one at least as new with another hash.
    revives = table.c.content_hash.is_(None) & (new.ticket_updated_at > table.c.ticket_updated_at)
    replaces = (
        table.c.content_hash.is_not(None)
        & (new.ticket_updated_at >= table.c.ticket_updated_at)
        & (new.content_hash != table.c.content_hash)
    )
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.source_id, table.c.external_id],
        set_={
            "state": new.state,
            "payload": new.payload,
            "content_hash": new.content_hash,
            "ticket_updated_at": new.ticket_updated_at,
            "received_at": new.received_at,
            "last_error": None,
            "updated_at": func.now(),
        },
        where=revives | replaces,
    ).returning(table.c.id)
    if (await db.execute(statement)).first() is not None:
        return ItemStatus.QUEUED
    stored = await _stored(db, workspace_id, source_id, item.external_id)
    if stored.content_hash is None or item.updated_at < stored.ticket_updated_at:
        return ItemStatus.STALE
    # Same hash (the hash covers ``updated_at``, so the instant is the same too).
    return ItemStatus.UNCHANGED


async def _delete(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    external_id: str,
    deleted_at: datetime,
    now: datetime,
) -> ItemStatus:
    table = TicketInboxItem.__table__
    statement = insert(TicketInboxItem).values(
        workspace_id=workspace_id,
        source_id=source_id,
        external_id=external_id,
        state=TicketInboxState.PENDING_DELETE,
        payload=None,
        content_hash=None,
        ticket_updated_at=deleted_at,
        received_at=now,
    )
    new = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.source_id, table.c.external_id],
        set_={
            "state": new.state,
            "payload": None,
            "content_hash": None,
            "ticket_updated_at": new.ticket_updated_at,
            "received_at": new.received_at,
            "last_error": None,
            "updated_at": func.now(),
        },
        # Only a ticket not newer than the removal turns into a tombstone.
        where=table.c.content_hash.is_not(None)
        & (table.c.ticket_updated_at <= new.ticket_updated_at),
    ).returning(table.c.id)
    if (await db.execute(statement)).first() is not None:
        return ItemStatus.QUEUED
    stored = await _stored(db, workspace_id, source_id, external_id)
    if stored.content_hash is not None:
        return ItemStatus.STALE
    # A tombstone already: a later removal only moves its date forward.
    await db.execute(
        update(TicketInboxItem)
        .where(
            TicketInboxItem.workspace_id == workspace_id,
            TicketInboxItem.id == stored.id,
            TicketInboxItem.content_hash.is_(None),
            TicketInboxItem.ticket_updated_at < deleted_at,
        )
        .values(ticket_updated_at=deleted_at)
    )
    return ItemStatus.UNCHANGED


async def apply_items(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    items: Sequence[CheckedItem],
    now: datetime,
) -> list[ItemResult]:
    """Write the accepted items in order; rejected ones pass through. A removal without
    ``deleted_at`` is dated ``now`` (the server clock)."""
    results: list[ItemResult] = []
    for item in items:
        if isinstance(item, ItemResult):
            results.append(item)
        elif isinstance(item, UpsertItem):
            status = await _upsert(db, workspace_id, source_id, item, now)
            results.append(ItemResult(item.index, "upsert", item.external_id, status))
        else:
            deleted_at = now if item.deleted_at is None else item.deleted_at
            status = await _delete(db, workspace_id, source_id, item.external_id, deleted_at, now)
            results.append(ItemResult(item.index, "delete", item.external_id, status))
    return results


def count(results: Sequence[ItemResult]) -> dict[ItemStatus, int]:
    totals = dict.fromkeys(ItemStatus, 0)
    for result in results:
        totals[result.status] += 1
    return totals
