"""Long-poll of the claim (docs/specs/runner.md, ``POST /v1/runner/jobs/claim``): try, wait a
short interval, try again, until something comes back, the deadline passes or the client leaves.

The clock and the wait are injected, so tests advance a frozen clock instead of sleeping.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Protocol

from knobridge.core.clock import Clock

CLAIM_MAX_WAIT_SECONDS = 25
CLAIM_POLL_INTERVAL = timedelta(seconds=1)


class Waiter(Protocol):
    async def wait(self, delay: timedelta) -> None:
        """Return after ``delay`` (or earlier; the caller checks its own deadline)."""
        ...


class AsyncioWaiter:
    """The production waiter: ``asyncio.sleep``."""

    async def wait(self, delay: timedelta) -> None:
        await asyncio.sleep(delay.total_seconds())


async def poll[T](
    attempt: Callable[[], Awaitable[T | None]],
    *,
    wait: timedelta,
    clock: Clock,
    waiter: Waiter,
    disconnected: Callable[[], Awaitable[bool]],
    interval: timedelta = CLAIM_POLL_INTERVAL,
) -> T | None:
    """Call ``attempt`` until it returns something or ``wait`` has passed; ``None`` if not."""
    deadline = clock.now() + wait
    while True:
        found = await attempt()
        if found is not None:
            return found
        remaining = deadline - clock.now()
        if remaining <= timedelta(0) or await disconnected():
            return None
        await waiter.wait(min(interval, remaining))
