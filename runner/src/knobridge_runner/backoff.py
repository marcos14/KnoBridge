"""Exponential backoff with cap and jitter, and the injectable clock and sleep of the runner."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


async def real_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def monotonic() -> float:
    return time.monotonic()


@dataclass
class Backoff:
    """Delays of 1 s, x2 per failure, capped at 60 s, with +/-20% jitter (docs/specs/runner.md)."""

    base: float = 1.0
    factor: float = 2.0
    cap: float = 60.0
    jitter: float = 0.2
    rng: random.Random = field(default_factory=random.Random)

    def delay(self, failures: int) -> float:
        """Delay before the next try after FAILURES consecutive failures (1 or more)."""
        raw = min(self.cap, self.base * self.factor ** (failures - 1))
        # Jitter spreads reconnections of many runners; not a security use of randomness.
        spread = self.rng.uniform(-self.jitter, self.jitter)
        return min(self.cap, raw * (1 + spread))
