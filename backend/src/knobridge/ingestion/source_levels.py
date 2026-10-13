"""The minimum level of a source (``docs/specs/produtos-e-niveis.md``, "Nível mínimo de fonte,
de documento e de trecho").

Only owners and admins create a source with a level other than its kind's default or change
the level of a source (403 ``forbidden`` with ``details.required_role = admin`` for an editor,
who still edits the other fields): the level is an access rule. A change applies at once,
without reindexing: in the same transaction, one statement recomputes ``chunks.min_level`` of
every chunk of the source as the highest of the new level, ``documents.min_level`` and
``chunks.meta.min_level``. No embedding is computed (tickets and cards already dropped their
raw content, so reindexing would not even be possible).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.errors import ForbiddenError
from knobridge.ingestion.models import DEFAULT_SOURCE_MIN_LEVELS, Source
from knobridge.ingestion.source_config import SourceKind
from knobridge.levels.level import ResponseLevel

_LEVELS = "ARRAY['end_user', 'support', 'product_dev']::text[]"
_RANK = "array_position(" + _LEVELS + ", {})"
# The highest of the three; ``array_position`` of ``NULL`` (no refinement) or of an unknown
# value is ``NULL``, which ``GREATEST`` ignores.
_RECOMPUTE = text(
    f"UPDATE chunks c SET min_level = ({_LEVELS})[GREATEST("  # noqa: S608 - constant fragments
    f"{_RANK.format('CAST(:level AS text)')}, {_RANK.format('d.min_level')}, "
    f"{_RANK.format("c.meta ->> 'min_level'")})] "
    "FROM documents d "
    "WHERE c.workspace_id = :workspace_id AND d.workspace_id = c.workspace_id "
    "AND d.id = c.document_id AND d.source_id = :source_id"
)


def default_min_level(kind: SourceKind) -> ResponseLevel:
    """The minimum level of a new source of ``kind`` when none is given."""
    return DEFAULT_SOURCE_MIN_LEVELS[kind]


def require_level_admin(allowed: bool) -> None:
    """403 for a caller below admin who sets or changes a source's minimum level."""
    if not allowed:
        raise ForbiddenError(
            "Only owners and admins set the minimum level of a source.",
            details={"required_role": "admin"},
        )


async def change_source_level(
    db: AsyncSession,
    audit: AuditService,
    *,
    source: Source,
    level: ResponseLevel,
    actor_id: uuid.UUID | None,
    ip: str | None,
) -> None:
    """Store the new level (locking the source, so a batch storing a document waits for the
    commit) and recompute the chunks; audited ``source.min_level_changed``."""
    previous = source.min_level
    source.min_level = level
    await db.flush()
    await recompute_chunk_levels(
        db, workspace_id=source.workspace_id, source_id=source.id, level=level
    )
    await audit.record(
        db,
        action=AuditAction.SOURCE_MIN_LEVEL_CHANGED,
        workspace_id=source.workspace_id,
        actor_user_id=actor_id,
        target=AuditTarget("source", str(source.id)),
        metadata={"name": source.name, "from": previous.value, "to": level.value},
        ip=ip,
    )


async def recompute_chunk_levels(
    db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID, level: ResponseLevel
) -> None:
    """Set the effective minimum level of every chunk of the source (one statement)."""
    await db.execute(
        _RECOMPUTE,
        {"level": level.value, "workspace_id": workspace_id, "source_id": source_id},
    )
