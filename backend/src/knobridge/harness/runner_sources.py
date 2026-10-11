"""Rules of a ``runner`` source that depend on the database (docs/specs/runner.md, "Fonte do
tipo runner"): the config the panel writes, the runner it points at, the unique
``(runner_id, repository)`` pair and the connection test.

Called by ``ingestion.sources.SourceService`` in the route's workspace-scoped session; the
config shape itself is validated by ``ingestion.source_config.RunnerSourceConfig``.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.models import JSONValue
from knobridge.core.errors import ConflictError, ValidationError
from knobridge.harness.models import Runner
from knobridge.harness.runners import is_online, uses_runner
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_check import ConnectionFailure

UNIQUE_REPOSITORY_INDEX = "uq_sources_workspace_id_runner_repository"
HEAD_COMMIT = "head_commit"


class RunnerRepositoryInUseError(ConflictError):
    code = "runner_repository_in_use"


def repository_in_use() -> RunnerRepositoryInUseError:
    return RunnerRepositoryInUseError(
        "Another source of the workspace already uses this runner and repository."
    )


def _binding(config: Mapping[str, object]) -> tuple[object, object]:
    return config.get("runner_id"), config.get("repository")


def runner_config_input(
    data: Mapping[str, object], current: Mapping[str, object] | None
) -> dict[str, object]:
    """The panel's config with ``head_commit`` read only: the panel's value is dropped and the
    stored one kept while the source keeps its runner and repository."""
    payload = {key: value for key, value in data.items() if key != HEAD_COMMIT}
    if current is not None and _binding(current) == _binding(payload):
        head = current.get(HEAD_COMMIT)
        if head is not None:
            payload[HEAD_COMMIT] = head
    return payload


async def check_runner_binding(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    config: Mapping[str, JSONValue],
    current: Source | None,
) -> None:
    """The runner exists in the workspace (and is not revoked when newly chosen) and no other
    source uses the same runner and repository."""
    runner_id = uuid.UUID(str(config["runner_id"]))
    runner = (
        await db.scalars(
            select(Runner).where(Runner.workspace_id == workspace_id, Runner.id == runner_id)
        )
    ).one_or_none()
    kept = current is not None and current.config.get("runner_id") == str(runner_id)
    if runner is None or (runner.revoked_at is not None and not kept):
        raise ValidationError(
            "The source configuration is invalid.",
            code="source_config_invalid",
            details=[
                {
                    "type": "runner_invalid",
                    "loc": ["runner_id"],
                    "msg": "runner not found in the workspace or revoked",
                }
            ],
        )
    conditions = [
        Source.workspace_id == workspace_id,
        uses_runner(runner_id),
        Source.config["repository"].astext == str(config["repository"]),
    ]
    if current is not None:
        conditions.append(Source.id != current.id)
    if await db.scalar(select(exists().where(*conditions))):
        raise repository_in_use()


def _served_repositories(runner: Runner) -> set[str]:
    """Names of the repositories of the last heartbeat (tolerant of an unknown shape)."""
    repositories = runner.capabilities.get("repositories")
    if not isinstance(repositories, list):
        return set()
    return {str(item.get("name")) for item in repositories if isinstance(item, dict)}


async def runner_connection_failure(
    db: AsyncSession, source: Source, *, now: datetime
) -> ConnectionFailure | None:
    """``None`` when the runner is online and served the repository in its last heartbeat."""
    runner = (
        await db.scalars(
            select(Runner).where(
                Runner.workspace_id == source.workspace_id,
                Runner.id == uuid.UUID(str(source.config["runner_id"])),
            )
        )
    ).one_or_none()
    if runner is None or runner.revoked_at is not None:
        reason = "runner_revoked"
    elif not is_online(runner, now):
        reason = "runner_offline"
    elif str(source.config["repository"]) not in _served_repositories(runner):
        reason = "repository_not_served"
    else:
        return None
    return ConnectionFailure(
        "source_unavailable", "The runner cannot serve this source.", {"reason": reason}
    )
