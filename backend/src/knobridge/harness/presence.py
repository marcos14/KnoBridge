"""Runner authentication and presence: find the runner of a token, record its heartbeat and
list the sources bound to it (docs/specs/runner.md, "Token de runner" and ``heartbeat``).

``authenticate_runner`` runs in system mode, because the workspace is only known once the
runner is found by its token prefix; the caller then scopes the transaction to the runner's
workspace before anything else. Every failure of the token (malformed, unknown prefix, wrong
secret, revoked) is the same 401, and nothing about the token reaches a log.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.core.errors import ForbiddenError, KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.harness.models import Runner
from knobridge.harness.runners import uses_runner
from knobridge.harness.tokens import token_matches, token_prefix
from knobridge.ingestion.models import Source
from knobridge.tenancy.models import Workspace, WorkspaceStatus

_log = get_logger(__name__)

# Any authenticated request refreshes ``last_seen_at``, at most once per this interval.
LAST_SEEN_RESOLUTION = timedelta(seconds=10)


class InvalidRunnerTokenError(KnoBridgeError):
    """Missing, malformed, unknown, mismatched or revoked token (deliberately one answer)."""

    code = "invalid_runner_token"
    status_code = HTTPStatus.UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only class default


def invalid_runner_token() -> InvalidRunnerTokenError:
    return InvalidRunnerTokenError("Invalid or revoked runner token.")


async def authenticate_runner(db: AsyncSession, *, token: str, now: datetime) -> Runner:
    """The live runner of ``token``; ``db`` must be in system mode (``apply_system_scope``).

    Raises :class:`InvalidRunnerTokenError` (401) or ``workspace_suspended`` (403). Touches
    ``last_seen_at`` when it is older than ``LAST_SEEN_RESOLUTION``.
    """
    prefix = token_prefix(token)
    if prefix is None:
        _log.warning("runner_auth_failed", reason="malformed")
        raise invalid_runner_token()
    runner = (await db.scalars(select(Runner).where(Runner.token_prefix == prefix))).one_or_none()
    stored_hash = None if runner is None else runner.token_hash
    matches = token_matches(token, stored_hash)
    if runner is None or not matches or runner.revoked_at is not None:
        reason = "unknown" if runner is None else ("mismatch" if not matches else "revoked")
        # The prefix is public (shown in the panel); the token and its secret never are.
        _log.warning("runner_auth_failed", reason=reason, prefix=prefix)
        raise invalid_runner_token()
    status = await db.scalar(select(Workspace.status).where(Workspace.id == runner.workspace_id))
    if status != WorkspaceStatus.ACTIVE:
        raise ForbiddenError("Workspace is suspended.", code="workspace_suspended")
    if runner.last_seen_at is None or now - runner.last_seen_at >= LAST_SEEN_RESOLUTION:
        runner.last_seen_at = now
    return runner


async def record_heartbeat(
    db: AsyncSession,
    runner: Runner,
    *,
    now: datetime,
    version: str,
    capabilities: dict[str, JSONValue],
) -> None:
    """Store what the runner reported (``{"platform", "executors", "repositories"}``)."""
    runner.version = version
    runner.capabilities = capabilities
    runner.last_seen_at = now
    await db.flush()
    _log.debug(
        "runner_heartbeat",
        workspace_id=str(runner.workspace_id),
        runner_id=str(runner.id),
        version=version,
    )


async def runner_sources(db: AsyncSession, runner: Runner) -> list[Source]:
    """Active ``runner`` sources of the runner's workspace bound to it, by name."""
    rows = await db.scalars(
        select(Source)
        .where(
            Source.workspace_id == runner.workspace_id,
            Source.active.is_(True),
            uses_runner(runner.id),
        )
        .order_by(Source.name, Source.id)
    )
    return list(rows)
