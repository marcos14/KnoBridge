"""What the runner reports about the machine: executors (cached) and repositories."""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field

from knobridge_runner.backoff import Clock
from knobridge_runner.commands import CommandRunner
from knobridge_runner.config import ExecutorConfig, RunnerConfig
from knobridge_runner.executors import AuthChecker, Which, probe_executor
from knobridge_runner.formats import Executor
from knobridge_runner.git import repository_info
from knobridge_runner.protocol import RunnerExecutorInfo, RunnerRepositoryInfo

# Login status is re-checked every 5 minutes, without calling the model (docs/specs/runner.md).
EXECUTOR_REFRESH_SECONDS = 300.0


@dataclass
class MachineStatus:
    config: RunnerConfig
    platform: str
    runner: CommandRunner
    auth: AuthChecker
    clock: Clock
    which: Which = shutil.which
    _executors: list[RunnerExecutorInfo] = field(default_factory=list[RunnerExecutorInfo])
    _probed_at: float | None = None

    def repository_names(self) -> list[str]:
        return list(self.config.repositories)

    def _probe(self) -> list[RunnerExecutorInfo]:
        return [
            probe_executor(
                name,
                self.config.executors.get(name, ExecutorConfig()),
                platform=self.platform,
                runner=self.runner,
                auth=self.auth,
                which=self.which,
            )
            for name in self.config.enabled_executors()
        ]

    async def executors(self) -> list[RunnerExecutorInfo]:
        now = self.clock()
        if self._probed_at is None or now - self._probed_at >= EXECUTOR_REFRESH_SECONDS:
            self._executors = await asyncio.to_thread(self._probe)
            self._probed_at = now
        return list(self._executors)

    async def repositories(self) -> list[RunnerRepositoryInfo]:
        def read() -> list[RunnerRepositoryInfo]:
            return [
                repository_info(self.runner, name, path)
                for name, path in self.config.repositories.items()
            ]

        return await asyncio.to_thread(read)

    def claimable_executors(self) -> list[Executor]:
        """Executors found on PATH whose login is not known to be missing."""
        return [
            info.name
            for info in self._executors
            if info.available and info.authenticated is not False
        ]

    def mark_unauthenticated(self, name: Executor) -> None:
        """After an auth_failed deferral: stop claiming for NAME until the next check."""
        self._executors = [
            info.model_copy(update={"authenticated": False}) if info.name == name else info
            for info in self._executors
        ]
