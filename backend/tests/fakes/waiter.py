"""``Waiter`` that moves a ``FrozenClock`` instead of sleeping: the claim's long-poll in tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta

from knobridge.core.clock import FrozenClock


@dataclass
class ClockWaiter:
    """Advances ``clock`` by each delay and records it in ``waits``; ``on_wait`` (if set) runs
    after each wait, e.g. to queue a job while the claim is waiting."""

    clock: FrozenClock
    on_wait: Callable[[int], Awaitable[None]] | None = None
    waits: list[timedelta] = field(default_factory=lambda: list[timedelta]())

    async def wait(self, delay: timedelta) -> None:
        self.clock.advance(delay)
        self.waits.append(delay)
        if self.on_wait is not None:
            await self.on_wait(len(self.waits))
