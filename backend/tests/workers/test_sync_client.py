"""The API's lazy Temporal ``SyncStarter``: connects on first use, keeps the client, and turns
an unreachable server into ``sync_unavailable``. No Temporal server: fake clients."""

from __future__ import annotations

import asyncio
import functools
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import timedelta
from typing import cast

import pytest
from fastapi.testclient import TestClient
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from fakes.sync_starter import FakeSyncStarter
from fakes.ticket_webhook_starter import FakeTicketWebhookStarter
from knobridge.api.app import create_app
from knobridge.core.settings import Settings
from knobridge.ingestion.errors import SyncNotRunningError, SyncUnavailableError
from knobridge.ingestion.sync import SyncStarter
from knobridge.tickets.delivery import TicketDeliveryUnavailableError
from knobridge.workers.sync_client import (
    LazyTemporalSyncStarter,
    LazyTemporalTicketWebhookStarter,
)

IDS = {"workspace_id": uuid.uuid4(), "source_id": uuid.uuid4(), "run_id": uuid.uuid4()}


def run_async[**P](test: Callable[P, Coroutine[object, object, None]]) -> Callable[P, None]:
    """Run an async test body in its own event loop (the suite has no asyncio plugin)."""

    @functools.wraps(test)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        asyncio.run(test(*args, **kwargs))

    return wrapper


def _settings() -> Settings:
    return Settings(env="test", temporal_task_queue="test-queue")


@dataclass
class Connector:
    """``connect_client`` fake: fails ``failures`` times, then returns a fake client."""

    failures: int = 0
    error: Exception = field(default_factory=lambda: RuntimeError("Failed client connect"))
    calls: int = 0

    async def __call__(self, settings: Settings) -> Client:
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error
        return cast(Client, object())


@dataclass
class RaisingStarter:
    error: Exception

    async def start(
        self, *, workspace_id: uuid.UUID, source_id: uuid.UUID, run_id: uuid.UUID
    ) -> None:
        raise self.error

    async def cancel(self, source_id: uuid.UUID) -> None:
        raise self.error


def _lazy(connect: Connector, starter: SyncStarter) -> LazyTemporalSyncStarter:
    return LazyTemporalSyncStarter(
        _settings(), connect_client=connect, starter_factory=lambda _client: starter
    )


@run_async
async def test_lazy_starter_connects_once_and_delegates() -> None:
    connect, fake = Connector(), FakeSyncStarter()
    lazy = _lazy(connect, fake)

    await lazy.start(**IDS)
    await lazy.cancel(IDS["source_id"])

    assert connect.calls == 1
    assert [call.run_id for call in fake.started] == [IDS["run_id"]]
    assert fake.cancelled == [IDS["source_id"]]


@run_async
async def test_lazy_starter_concurrent_first_calls_connect_once() -> None:
    connect, fake = Connector(), FakeSyncStarter()
    lazy = _lazy(connect, fake)

    await asyncio.gather(
        lazy.start(workspace_id=uuid.uuid4(), source_id=uuid.uuid4(), run_id=uuid.uuid4()),
        lazy.start(workspace_id=uuid.uuid4(), source_id=uuid.uuid4(), run_id=uuid.uuid4()),
    )

    assert (connect.calls, len(fake.started)) == (1, 2)


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Failed client connect"),
        OSError("connection refused"),
        RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b""),
    ],
)
@run_async
async def test_lazy_starter_connect_failure_is_unavailable_and_retried(error: Exception) -> None:
    connect, fake = Connector(failures=1, error=error), FakeSyncStarter()
    lazy = _lazy(connect, fake)

    with pytest.raises(SyncUnavailableError) as raised:
        await lazy.start(**IDS)
    await lazy.start(**IDS)

    assert raised.value.code == "sync_unavailable"
    assert raised.value.status_code == 503
    assert (connect.calls, len(fake.started)) == (2, 1)


@pytest.mark.parametrize("status", [RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED])
@run_async
async def test_lazy_starter_unreachable_on_call_is_unavailable(status: RPCStatusCode) -> None:
    lazy = _lazy(Connector(), RaisingStarter(RPCError("down", status, b"")))

    with pytest.raises(SyncUnavailableError):
        await lazy.start(**IDS)
    with pytest.raises(SyncUnavailableError):
        await lazy.cancel(IDS["source_id"])


@run_async
async def test_lazy_starter_other_errors_propagate() -> None:
    rpc = RPCError("bad", RPCStatusCode.INVALID_ARGUMENT, b"")
    lazy = _lazy(Connector(), RaisingStarter(rpc))
    domain = _lazy(Connector(), RaisingStarter(SyncNotRunningError("not running")))

    with pytest.raises(RPCError) as start_error:
        await lazy.start(**IDS)
    with pytest.raises(RPCError):
        await lazy.cancel(IDS["source_id"])
    with pytest.raises(SyncNotRunningError):
        await domain.cancel(IDS["source_id"])

    assert start_error.value is rpc


@dataclass
class RecordingClient:
    """Enough of ``Client`` for ``TemporalSyncStarter.start``."""

    task_queues: list[str] = field(default_factory=lambda: [])

    async def start_workflow(self, *_args: object, task_queue: str, **_kwargs: object) -> None:
        self.task_queues.append(task_queue)


@run_async
async def test_lazy_starter_default_factory_uses_settings_task_queue() -> None:
    client = RecordingClient()

    async def connect(_settings: Settings) -> Client:
        return cast(Client, client)

    lazy = LazyTemporalSyncStarter(_settings(), connect_client=connect)

    await lazy.start(**IDS)

    assert client.task_queues == ["test-queue"]


def test_app_lifespan_creates_lazy_starter_without_connecting() -> None:
    app = create_app(Settings(env="test", temporal_address="127.0.0.1:1"))

    with TestClient(app):
        assert isinstance(app.state.sync_starter, LazyTemporalSyncStarter)
        assert isinstance(app.state.ticket_webhook_starter, LazyTemporalTicketWebhookStarter)


REQUEST_ID = uuid.uuid4()


async def _start_ticket(lazy: LazyTemporalTicketWebhookStarter) -> None:
    await lazy.start(workspace_id=uuid.uuid4(), request_id=REQUEST_ID, remaining=timedelta(hours=1))


@dataclass
class RaisingTicketStarter:
    error: Exception

    async def start(
        self, *, workspace_id: uuid.UUID, request_id: uuid.UUID, remaining: timedelta
    ) -> None:
        raise self.error


@run_async
async def test_lazy_ticket_starter_connects_once_and_delegates() -> None:
    connect, fake = Connector(), FakeTicketWebhookStarter()
    lazy = LazyTemporalTicketWebhookStarter(
        _settings(), connect_client=connect, starter_factory=lambda _client: fake
    )

    await _start_ticket(lazy)
    await _start_ticket(lazy)

    assert connect.calls == 1
    assert [call.request_id for call in fake.started] == [REQUEST_ID] * 2


@run_async
async def test_lazy_ticket_starter_down_is_unavailable() -> None:
    down = LazyTemporalTicketWebhookStarter(_settings(), connect_client=Connector(failures=1))
    unreachable = LazyTemporalTicketWebhookStarter(
        _settings(),
        connect_client=Connector(),
        starter_factory=lambda _client: RaisingTicketStarter(
            RPCError("down", RPCStatusCode.UNAVAILABLE, b"")
        ),
    )

    with pytest.raises(TicketDeliveryUnavailableError) as raised:
        await _start_ticket(down)
    with pytest.raises(TicketDeliveryUnavailableError):
        await _start_ticket(unreachable)

    assert (raised.value.code, raised.value.status_code) == ("ticket_delivery_unavailable", 503)


@run_async
async def test_lazy_ticket_starter_default_factory_uses_settings_task_queue() -> None:
    client = RecordingClient()

    async def connect(_settings: Settings) -> Client:
        return cast(Client, client)

    lazy = LazyTemporalTicketWebhookStarter(_settings(), connect_client=connect)

    await _start_ticket(lazy)

    assert client.task_queues == ["test-queue"]
