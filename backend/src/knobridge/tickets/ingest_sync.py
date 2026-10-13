"""Around a batch of tickets or cards: the source it goes to and the sync it asks for afterwards
(docs/specs/chamados.md, "Disparo da sincronização").

``open_ingest_source`` runs first in the batch's transaction: a source of the other kind (409
``source_kind_mismatch``) or deactivated (409 ``source_inactive``) refuses the batch with
nothing written, and a source deleted since the token was
checked is the same 401 as a dead token. ``request_ingest_sync`` runs after the commit and never
fails the request: Temporal down (or any refusal to start) leaves the entries ``pending`` for
the next sync and answers ``deferred``.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.ingestion.errors import SourceInactiveError
from knobridge.ingestion.models import RunTrigger, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.ingestion.sync import SyncStarter, request_sync
from knobridge.tickets.tokens import invalid_ingest_token

type SyncOutcome = Literal["started", "pending", "deferred", "none"]

_log = get_logger(__name__)


class SourceKindMismatchError(ConflictError):
    """A token of a source of the other kind (a ``tickets`` token on ``/v1/ingest/cards``, or
    the opposite): nothing is written (docs/specs/cards.md, "Rotas")."""

    code = "source_kind_mismatch"


async def open_ingest_source(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
    kind: SourceKind = SourceKind.TICKETS,
) -> Source:
    """The active source of ``kind``, held (``FOR KEY SHARE``) until the batch commits."""
    source = (
        await db.scalars(
            select(Source)
            .where(Source.workspace_id == workspace_id, Source.id == source_id)
            .with_for_update(key_share=True)
        )
    ).one_or_none()
    if source is None:
        raise invalid_ingest_token()
    if source.kind is not kind:
        raise SourceKindMismatchError(
            f"The token belongs to a {source.kind.value} source.",
            details={"expected": kind.value, "actual": source.kind.value},
        )
    if not source.active:
        raise SourceInactiveError("The source is inactive.")
    return source


async def request_ingest_sync(
    factory: async_sessionmaker[AsyncSession],
    starter: SyncStarter,
    clock: Clock,
    *,
    workspace_id: uuid.UUID,
    source_id: uuid.UUID,
) -> tuple[SyncOutcome, uuid.UUID | None]:
    """Ask for the sync of the source (trigger ``ingest``): ``started`` with the run id,
    ``pending`` when one is already running, ``deferred`` when it could not start."""
    try:
        run = await request_sync(
            factory,
            starter,
            clock,
            workspace_id=workspace_id,
            source_id=source_id,
            trigger=RunTrigger.INGEST,
        )
    except KnoBridgeError as exc:
        _log.warning(
            "tickets_sync_deferred",
            workspace_id=str(workspace_id),
            source_id=str(source_id),
            error_code=exc.code,
        )
        return "deferred", None
    if run is None:
        return "pending", None
    return "started", run.id
