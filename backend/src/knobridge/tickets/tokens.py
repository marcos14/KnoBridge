"""Ingest tokens: ``kbi_<prefix>_<secret>`` (docs/specs/chamados.md, "Token de envio").

One token per ``tickets`` source. The prefix (8 characters of ``[a-z0-9]``) is public: stored
in clear, unique in the instance, it is how authentication finds the source before the
workspace is known (system mode). The secret is 32 random bytes in URL-safe base64 (43
characters). Only the SHA-256 (hex) of the whole token is stored; the token itself exists once,
in the value returned when it is issued. Rotating replaces prefix and hash in place, so the
previous token stops working at once. Every failure of a token is the same 401, and nothing
about the token reaches a log or the audit trail (only the public prefix).
"""

from __future__ import annotations

import hmac
import re
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ForbiddenError, KnoBridgeError, NotFoundError
from knobridge.core.logging import get_logger
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_check import ConnectionFailure
from knobridge.ingestion.source_config import SourceKind
from knobridge.security.tokens import hash_token
from knobridge.tenancy.models import Workspace, WorkspaceStatus
from knobridge.tickets.models import TOKEN_PREFIX_LENGTH, IngestToken

TOKEN_SCHEME = "kbi"  # noqa: S105 - public marker of the format, not a secret
SECRET_BYTES = 32
_PREFIX_ALPHABET = string.ascii_lowercase + string.digits
_TOKEN_PATTERN = re.compile(r"^kbi_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")
# Compared when no source has the prefix, so an unknown prefix costs the same as a wrong secret.
_DUMMY_HASH = "0" * 64

_log = get_logger(__name__)


class InvalidIngestTokenError(KnoBridgeError):
    """Missing, malformed, unknown, mismatched or rotated token (deliberately one answer)."""

    code = "invalid_ingest_token"
    status_code = HTTPStatus.UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only class default


def invalid_ingest_token() -> InvalidIngestTokenError:
    return InvalidIngestTokenError("Invalid or rotated ingest token.")


@dataclass(frozen=True)
class GeneratedToken:
    """A freshly generated token: hand ``value`` to the user once, store only ``hash``."""

    value: str
    prefix: str
    hash: str


@dataclass(frozen=True)
class IssuedIngestToken:
    token: str  # plain value: shown once to the user, never stored or logged
    prefix: str
    issued_at: datetime


@dataclass(frozen=True)
class IngestIdentity:
    """The ``tickets`` source a valid token opens."""

    workspace_id: uuid.UUID
    source_id: uuid.UUID
    prefix: str


def generate_ingest_token() -> GeneratedToken:
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(TOKEN_PREFIX_LENGTH))
    value = f"{TOKEN_SCHEME}_{prefix}_{secrets.token_urlsafe(SECRET_BYTES)}"
    return GeneratedToken(value=value, prefix=prefix, hash=hash_token(value))


def ingest_token_prefix(token: str) -> str | None:
    """The prefix of a well-formed token; ``None`` for anything else."""
    match = _TOKEN_PATTERN.fullmatch(token)
    return None if match is None else match.group(1)


def token_matches(token: str, stored_hash: str | None) -> bool:
    """Constant-time check of ``token`` against the stored hash (``None``: no such token)."""
    expected = _DUMMY_HASH if stored_hash is None else stored_hash
    return hmac.compare_digest(hash_token(token), expected) and stored_hash is not None


async def authenticate_ingest_token(db: AsyncSession, *, token: str) -> IngestIdentity:
    """The source of ``token``; ``db`` must be in system mode (``apply_system_scope``).

    Raises :class:`InvalidIngestTokenError` (401) or ``workspace_suspended`` (403).
    """
    prefix = ingest_token_prefix(token)
    if prefix is None:
        _log.warning("ingest_auth_failed", reason="malformed")
        raise invalid_ingest_token()
    stored = (
        await db.scalars(select(IngestToken).where(IngestToken.token_prefix == prefix))
    ).one_or_none()
    if not token_matches(token, None if stored is None else stored.token_hash) or stored is None:
        # The prefix is public (shown in the panel); the token and its secret never are.
        reason = "unknown" if stored is None else "mismatch"
        _log.warning("ingest_auth_failed", reason=reason, prefix=prefix)
        raise invalid_ingest_token()
    status = await db.scalar(select(Workspace.status).where(Workspace.id == stored.workspace_id))
    if status != WorkspaceStatus.ACTIVE:
        raise ForbiddenError("Workspace is suspended.", code="workspace_suspended")
    return IngestIdentity(
        workspace_id=stored.workspace_id, source_id=stored.source_id, prefix=prefix
    )


async def ingest_token_failure(db: AsyncSession, source: Source) -> ConnectionFailure | None:
    """Connection test of a ``tickets`` source: fine while it has a token."""
    found = await db.scalar(
        select(IngestToken.id).where(
            IngestToken.workspace_id == source.workspace_id, IngestToken.source_id == source.id
        )
    )
    if found is not None:
        return None
    return ConnectionFailure(
        "source_unavailable",
        "The source has no ingest token yet.",
        {"reason": "ingest_token_missing"},
    )


class IngestTokenService:
    """Issue or rotate the token of a ``tickets`` source (owner or admin, in the route's
    workspace-scoped session; audited in the same transaction)."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._audit = AuditService(clock)

    async def rotate(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        source_id: uuid.UUID,
        ip: str | None,
    ) -> IssuedIngestToken:
        source = (
            await db.scalars(
                select(Source)
                .where(
                    Source.workspace_id == workspace_id,
                    Source.id == source_id,
                    Source.kind == SourceKind.TICKETS,
                )
                .with_for_update()
            )
        ).one_or_none()
        if source is None:
            raise NotFoundError("Source not found.", code="source_not_found")
        generated = generate_ingest_token()
        now = self._clock.now()
        # The source row is locked, so the read and the write below cannot race another rotation.
        stored = (
            await db.scalars(
                select(IngestToken).where(
                    IngestToken.workspace_id == workspace_id, IngestToken.source_id == source_id
                )
            )
        ).one_or_none()
        if stored is None:
            stored = IngestToken(
                workspace_id=workspace_id, source_id=source_id, created_by=actor_id
            )
            db.add(stored)
        stored.token_prefix, stored.token_hash, stored.issued_at = (
            generated.prefix,
            generated.hash,
            now,
        )
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.SOURCE_INGEST_TOKEN_ROTATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("source", str(source_id)),
            metadata={"name": source.name, "prefix": generated.prefix},
            ip=ip,
        )
        return IssuedIngestToken(token=generated.value, prefix=generated.prefix, issued_at=now)
