"""``POST /v1/ingest/tickets`` and ``POST /v1/ingest/cards``: an external system pushes up to 100
tickets (or cards) or removals into the inbox of its source (docs/specs/chamados.md, "Envio pela
API"; docs/specs/cards.md).

Only the ingest token (``Authorization: Bearer kbi_…``) opens these routes: no session cookie,
no CSRF, and the token opens nothing else. It is checked in a short system-mode transaction
(``current_ingest_source``); the batch is then written in a transaction scoped to the source's
workspace and, after the commit, the sync of the source is requested (trigger ``ingest``). A
token of a source of the other kind is 409 ``source_kind_mismatch``, with nothing written.

Only errors of the whole body are 422 (``items`` missing, empty, above 100, or an item that is
not an object with ``op`` ``upsert``/``delete``); each item is then validated on its own and an
invalid one comes back ``rejected`` without sinking the batch. To keep that per-item answer,
``items`` is received as raw objects, while the OpenAPI publishes the full item schemas
(``TicketUpsertItemIn``/``TicketDeleteItemIn``, ``CardUpsertItemIn``/``CardDeleteItemIn``). The
5 MiB limit is enforced by the body limit middleware (``body_limit.py``). Logic in ``tickets/``.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from contextlib import contextmanager
from http import HTTPStatus
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, PlainValidator
from pydantic_core import PydanticCustomError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.api.deps import ClockDep, SessionFactoryDep, SyncStarterDep
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session, system_session
from knobridge.core.errors import ServiceUnavailableError
from knobridge.core.logging import get_logger
from knobridge.ingestion.sync import SyncStarter
from knobridge.tickets.card_wire import CardDeleteItemIn, CardUpsertItemIn
from knobridge.tickets.ingest import ItemResult, ItemStatus, apply_items, check_items, count
from knobridge.tickets.ingest_sync import SyncOutcome, open_ingest_source, request_ingest_sync
from knobridge.tickets.push import CARDS, TICKETS, PushKind
from knobridge.tickets.tokens import IngestIdentity, authenticate_ingest_token, invalid_ingest_token
from knobridge.tickets.wire import TicketDeleteItemIn, TicketUpsertItemIn

MAX_ITEMS = 100

_log = get_logger(__name__)


@contextmanager
def database_available() -> Generator[None]:
    """Database unreachable: 503 ``service_unavailable`` (nothing was written; retry)."""
    try:
        yield
    except (OSError, OperationalError, InterfaceError) as exc:
        _log.warning("ingest_database_unavailable", error_type=type(exc).__name__)
        raise ServiceUnavailableError("The database is unavailable; retry later.") from exc


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise invalid_ingest_token()
    return token.strip()


async def current_ingest_source(request: Request, factory: SessionFactoryDep) -> IngestIdentity:
    """The source of the bearer ingest token, found by its prefix in system mode."""
    token = _bearer(request)
    with database_available():
        async with system_session(factory) as db:
            identity = await authenticate_ingest_token(db, token=token)
    return identity


IngestSourceDep = Annotated[IngestIdentity, Depends(current_ingest_source)]


def _raw_item(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("op") not in ("upsert", "delete"):  # pyright: ignore[reportUnknownMemberType]
        raise PydanticCustomError(
            "ingest_item", "Each item must be an object with op 'upsert' or 'delete'."
        )
    item: dict[str, object] = value  # pyright: ignore[reportUnknownVariableType]
    return item


RawItem = Annotated[
    dict[str, object],
    PlainValidator(_raw_item, json_schema_input_type=TicketUpsertItemIn | TicketDeleteItemIn),
]
RawCardItem = Annotated[
    dict[str, object],
    PlainValidator(_raw_item, json_schema_input_type=CardUpsertItemIn | CardDeleteItemIn),
]


class TicketIngestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[RawItem], Field(min_length=1, max_length=MAX_ITEMS)]


class CardIngestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: Annotated[list[RawCardItem], Field(min_length=1, max_length=MAX_ITEMS)]


class TicketIngestItemError(BaseModel):
    code: str
    message: str
    details: object | None


class TicketIngestItemResult(BaseModel):
    index: int
    op: Literal["upsert", "delete"]
    external_id: str | None
    status: Literal["queued", "unchanged", "stale", "rejected"]
    error: TicketIngestItemError | None


class TicketIngestCounts(BaseModel):
    queued: int
    unchanged: int
    stale: int
    rejected: int


class TicketIngestOut(BaseModel):
    results: list[TicketIngestItemResult]
    counts: TicketIngestCounts
    sync: Literal["started", "pending", "deferred", "none"]
    run_id: uuid.UUID | None


INGEST_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "Missing, malformed, unknown or rotated token (`invalid_ingest_token`)."},
    403: {"description": "Workspace of the source suspended (`workspace_suspended`)."},
    409: {
        "description": "Source deactivated (`source_inactive`) or of the other kind "
        "(`source_kind_mismatch`, `details.expected`/`details.actual`): nothing written."
    },
    413: {"description": "Body above 5 MiB (`payload_too_large`, `details.max_bytes`)."},
    422: {"description": "Malformed body (`validation_error`)."},
    503: {"description": "Database unavailable (`service_unavailable`): nothing written."},
}


def _result_out(result: ItemResult) -> TicketIngestItemResult:
    error = result.error
    return TicketIngestItemResult(
        index=result.index,
        op=result.op,
        external_id=result.external_id,
        status=result.status.value,
        error=None
        if error is None
        else TicketIngestItemError(code=error.code, message=error.message, details=error.details),
    )


async def _ingest(
    items: list[dict[str, object]],
    identity: IngestIdentity,
    factory: async_sessionmaker[AsyncSession],
    starter: SyncStarter,
    clock: Clock,
    kind: PushKind,
) -> TicketIngestOut:
    checked = check_items(items, kind)
    with database_available():
        async with scoped_session(factory, workspace_id=identity.workspace_id, user_id=None) as db:
            await open_ingest_source(
                db,
                workspace_id=identity.workspace_id,
                source_id=identity.source_id,
                kind=kind.source_kind,
            )
            results = await apply_items(
                db,
                workspace_id=identity.workspace_id,
                source_id=identity.source_id,
                items=checked,
                now=clock.now(),
            )
    totals = count(results)
    sync: SyncOutcome = "none"
    run_id: uuid.UUID | None = None
    if totals[ItemStatus.QUEUED]:
        sync, run_id = await request_ingest_sync(
            factory,
            starter,
            clock,
            workspace_id=identity.workspace_id,
            source_id=identity.source_id,
        )
    _log.info(
        f"{kind.source_kind.value}_ingested",
        workspace_id=str(identity.workspace_id),
        source_id=str(identity.source_id),
        run_id=None if run_id is None else str(run_id),
        sync=sync,
        **{status.value: total for status, total in totals.items()},
    )
    return TicketIngestOut(
        results=[_result_out(result) for result in results],
        counts=TicketIngestCounts(**{status.value: total for status, total in totals.items()}),
        sync=sync,
        run_id=run_id,
    )


router = APIRouter(tags=["ingest"])


@router.post("/ingest/tickets", status_code=HTTPStatus.ACCEPTED, responses=INGEST_ERRORS)
async def ingest_tickets(
    body: TicketIngestIn,
    identity: IngestSourceDep,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
) -> TicketIngestOut:
    """Validate each item, write the accepted ones to the inbox (the ``updated_at`` rule) and
    request the sync of the source; 202 with the result of every item, in order."""
    return await _ingest(body.items, identity, factory, starter, clock, TICKETS)


@router.post("/ingest/cards", status_code=HTTPStatus.ACCEPTED, responses=INGEST_ERRORS)
async def ingest_cards(
    body: CardIngestIn,
    identity: IngestSourceDep,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
) -> TicketIngestOut:
    """The same as ``/ingest/tickets`` for the cards of a ``cards`` source (``card`` in the
    upsert item); 202 with the result of every item, in order."""
    return await _ingest(body.items, identity, factory, starter, clock, CARDS)
