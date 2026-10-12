"""Helpers for the schedule tests: an async test runner and a fake Temporal client that keeps
schedules in memory (the SDK's test server does not implement schedules). Not a test module;
imported by its basename."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass, field
from typing import cast

from temporalio.client import (
    Schedule,
    ScheduleAlreadyRunningError,
    ScheduleUpdate,
    ScheduleUpdateInput,
)
from temporalio.service import RPCError, RPCStatusCode


def run_async[**P](test: Callable[P, Coroutine[object, object, None]]) -> Callable[P, None]:
    """Run an async test body in its own event loop (the suite has no asyncio plugin)."""

    @functools.wraps(test)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        asyncio.run(test(*args, **kwargs))

    return wrapper


@dataclass
class _Description:
    schedule: Schedule


@dataclass
class _UpdateInput:
    description: _Description


@dataclass
class _Entry:
    id: str


@dataclass
class FakeScheduleClient:
    """Enough of ``Client`` for ``TemporalScheduleManager``: schedules kept by id."""

    schedules: dict[str, Schedule] = field(default_factory=lambda: dict[str, Schedule]())
    updates: list[str] = field(default_factory=lambda: [])
    delete_error: RPCError | None = None

    async def create_schedule(self, id: str, schedule: Schedule) -> None:
        if id in self.schedules:
            raise ScheduleAlreadyRunningError()
        self.schedules[id] = schedule

    def get_schedule_handle(self, id: str) -> FakeHandle:
        return FakeHandle(self, id)

    async def list_schedules(self) -> AsyncIterator[_Entry]:
        return self._entries()

    async def _entries(self) -> AsyncIterator[_Entry]:
        for key in list(self.schedules):
            yield _Entry(key)


@dataclass
class FakeHandle:
    client: FakeScheduleClient
    id: str

    async def update(self, updater: Callable[[ScheduleUpdateInput], ScheduleUpdate | None]) -> None:
        current = _UpdateInput(_Description(self.client.schedules[self.id]))
        result = updater(cast(ScheduleUpdateInput, current))
        if result is not None:
            self.client.updates.append(self.id)
            self.client.schedules[self.id] = result.schedule

    async def delete(self) -> None:
        if self.client.delete_error is not None:
            raise self.client.delete_error
        if self.id not in self.client.schedules:
            raise RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
        del self.client.schedules[self.id]
