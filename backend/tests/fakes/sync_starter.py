"""In-memory ``SyncStarter``: what the API tests inject instead of the Temporal one."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from knobridge.ingestion.errors import (
    SyncAlreadyRunningError,
    SyncNotRunningError,
    SyncUnavailableError,
)


@dataclass(frozen=True)
class StartCall:
    workspace_id: uuid.UUID
    source_id: uuid.UUID
    run_id: uuid.UUID


@dataclass
class FakeSyncStarter:
    """Records starts and cancels. A started source stays in ``running`` until cancelled or
    ``finish``ed; ``unavailable = True`` makes every call fail as if Temporal were down."""

    started: list[StartCall] = field(default_factory=lambda: [])
    cancelled: list[uuid.UUID] = field(default_factory=lambda: [])
    running: set[uuid.UUID] = field(default_factory=lambda: set[uuid.UUID]())
    unavailable: bool = False
    # Set: Temporal goes down after this many more successful starts.
    starts_left: int | None = None

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        if self.starts_left is not None:
            self.unavailable = self.starts_left <= 0
            self.starts_left -= 1
        self._check_available()
        if source_id in self.running:
            raise SyncAlreadyRunningError("a sync of this source is already running")
        self.running.add(source_id)
        self.started.append(StartCall(workspace_id, source_id, run_id))

    async def cancel(self, source_id: uuid.UUID) -> None:
        self._check_available()
        if source_id not in self.running:
            raise SyncNotRunningError("no sync of this source is running")
        self.running.discard(source_id)
        self.cancelled.append(source_id)

    def finish(self, source_id: uuid.UUID) -> None:
        """The workflow ended on its own (the run row may still say otherwise)."""
        self.running.discard(source_id)

    def _check_available(self) -> None:
        if self.unavailable:
            raise SyncUnavailableError("temporal is down")
