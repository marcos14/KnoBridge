"""In-memory ``TemporalProbe``: what the health tests inject instead of the Temporal one."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import anyio


@dataclass
class FakeTemporalProbe:
    """``unavailable`` fails both calls (Temporal down); ``queue_error`` fails only the task
    queue; ``last_seen`` is the last poll of a worker (``None``: no poller); ``block`` makes
    every call wait forever, for the timeout path (no sleep: an event never set)."""

    last_seen: datetime | None = None
    unavailable: bool = False
    queue_error: bool = False
    block: bool = False

    async def _wait(self) -> None:
        if self.block:
            await anyio.Event().wait()
        if self.unavailable:
            raise ConnectionError("temporal is down")

    async def check_namespace(self) -> None:
        await self._wait()

    async def last_poller_seen(self) -> datetime | None:
        await self._wait()
        if self.queue_error:
            raise RuntimeError("describe task queue failed")
        return self.last_seen
