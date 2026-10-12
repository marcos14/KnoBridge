"""When the runner sends ``POST /v1/runner/sources/{source_id}/report`` (docs/specs/runner.md).

For each source served by this runner: once at start and whenever the repository HEAD changes,
checked at every runner heartbeat and after every job (a HEAD that moved during a job). Only the
declared repository name, commits, branch, relative paths and counts leave the machine.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from knobridge_runner.client import RetryPolicy, RunnerClient
from knobridge_runner.commands import CommandRunner
from knobridge_runner.config import RunnerConfig
from knobridge_runner.errors import FatalServerError, ServerError, UnavailableError
from knobridge_runner.layer0 import RepositoryUnavailableError, build_report
from knobridge_runner.layer0.git import GitRepository
from knobridge_runner.protocol import RunnerSourceOut

logger = logging.getLogger(__name__)

# A report must not hold the heartbeat loop for long; a failed one is retried at the next check.
REPORT_POLICY = RetryPolicy(max_attempts=3)


class SourceReporter(Protocol):
    async def sync(self, sources: Sequence[RunnerSourceOut]) -> None:
        """Report every source of SOURCES whose HEAD this process has not reported yet."""
        ...


class GitSourceReporter:
    def __init__(self, client: RunnerClient, config: RunnerConfig, git: CommandRunner) -> None:
        self._client = client
        self._config = config
        self._git = git
        # Last HEAD sent per source (accepted or refused), and last HEAD the server accepted.
        self._reported: dict[UUID, str] = {}
        self._accepted: dict[UUID, str] = {}
        self._lock = asyncio.Lock()

    async def sync(self, sources: Sequence[RunnerSourceOut]) -> None:
        async with self._lock:
            for source in sources:
                await self._sync_one(source)

    async def _sync_one(self, source: RunnerSourceOut) -> None:
        checkout = self._config.repositories.get(source.repository)
        if checkout is None:
            return
        log = {"source_id": str(source.source_id), "repository": source.repository}
        head = await asyncio.to_thread(GitRepository(self._git, checkout).head)
        if head is None or self._reported.get(source.source_id) == head:
            return
        try:
            body = await asyncio.to_thread(
                build_report,
                self._git,
                source.repository,
                checkout,
                # Until the next heartbeat refreshes the source, our last accepted report is the
                # server's head_commit: using it as base keeps changed_paths (and auto_on_commit).
                self._accepted.get(source.source_id, source.last_reported_commit),
                include_globs=source.include_globs,
                exclude_globs=source.exclude_globs,
            )
            answer = await self._client.report(source.source_id, body, policy=REPORT_POLICY)
        except RepositoryUnavailableError:
            logger.warning("source_report_repository_unavailable", extra=log)
            return
        except UnavailableError:
            logger.warning("source_report_unavailable", extra=log)
            return
        except FatalServerError:
            raise
        except ServerError as exc:
            # 404, 409, 413 or 422: the same report cannot pass; try again when HEAD moves.
            logger.warning(
                "source_report_refused", extra={**log, "status": exc.status, "code": exc.code}
            )
            self._reported[source.source_id] = head
            return
        self._reported[source.source_id] = head
        self._accepted[source.source_id] = head
        logger.info(
            "source_reported",
            extra={
                **log,
                "modules_total": answer.modules_total,
                "jobs_enqueued": len(answer.jobs_enqueued),
            },
        )
