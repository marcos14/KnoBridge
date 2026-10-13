"""The ``TemporalProbe`` of production and its lazy wrapper of the API.

No Temporal server: a fake client whose ``workflow_service`` answers with the SDK's own
protobuf messages, so the translation to the API of the SDK is checked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

import pytest
from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import PollerInfo
from temporalio.api.workflowservice.v1 import (
    DescribeNamespaceRequest,
    DescribeNamespaceResponse,
    DescribeTaskQueueRequest,
    DescribeTaskQueueResponse,
)
from temporalio.client import Client

from fakes.temporal_probe import FakeTemporalProbe
from knobridge.core.settings import Settings
from knobridge.usage.health import TemporalUnreachableError
from knobridge.workers.sync_client import LazyTemporalHealthProbe
from knobridge.workers.temporal_health import TemporalHealthProbe

SEEN = datetime(2026, 10, 10, 12, 0, 5, tzinfo=UTC)


def _timestamp(moment: datetime) -> Timestamp:
    stamp = Timestamp()
    stamp.FromDatetime(moment)
    return stamp


@dataclass
class FakeWorkflowService:
    pollers: list[PollerInfo] = field(default_factory=lambda: [])
    requests: list[object] = field(default_factory=lambda: [])

    async def describe_namespace(
        self, request: DescribeNamespaceRequest
    ) -> DescribeNamespaceResponse:
        self.requests.append(request)
        return DescribeNamespaceResponse()

    async def describe_task_queue(
        self, request: DescribeTaskQueueRequest
    ) -> DescribeTaskQueueResponse:
        self.requests.append(request)
        return DescribeTaskQueueResponse(pollers=self.pollers)


@dataclass
class FakeClient:
    workflow_service: FakeWorkflowService


def _probe(service: FakeWorkflowService) -> TemporalHealthProbe:
    return TemporalHealthProbe(cast(Client, FakeClient(service)), "knobridge-ns", "kb-queue")


def test_probe_describes_the_namespace() -> None:
    service = FakeWorkflowService()

    asyncio.run(_probe(service).check_namespace())

    assert service.requests == [DescribeNamespaceRequest(namespace="knobridge-ns")]


def test_probe_returns_the_latest_poll_of_the_workflow_queue() -> None:
    service = FakeWorkflowService(
        pollers=[
            PollerInfo(identity="old", last_access_time=_timestamp(SEEN.replace(second=0))),
            PollerInfo(identity="new", last_access_time=_timestamp(SEEN)),
            PollerInfo(identity="never"),
        ]
    )

    seen = asyncio.run(_probe(service).last_poller_seen())

    assert seen == SEEN
    (request,) = service.requests
    assert isinstance(request, DescribeTaskQueueRequest)
    assert (request.namespace, request.task_queue.name, request.task_queue_type) == (
        "knobridge-ns",
        "kb-queue",
        TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
    )


def test_probe_without_pollers_returns_none() -> None:
    assert asyncio.run(_probe(FakeWorkflowService()).last_poller_seen()) is None


def _settings() -> Settings:
    return Settings(env="test", temporal_namespace="knobridge-ns", temporal_task_queue="kb-queue")


def test_lazy_probe_delegates_to_the_probe_of_the_connected_client() -> None:
    fake = FakeTemporalProbe(last_seen=SEEN)
    connected: list[Client] = []

    async def connect(_settings: Settings) -> Client:
        client = cast(Client, object())
        connected.append(client)
        return client

    lazy = LazyTemporalHealthProbe(
        _settings(), connect_client=connect, probe_factory=lambda _c: fake
    )

    async def scenario() -> datetime | None:
        await lazy.check_namespace()
        return await lazy.last_poller_seen()

    assert asyncio.run(scenario()) == SEEN
    assert len(connected) == 1


def test_lazy_probe_builds_the_production_probe() -> None:
    service = FakeWorkflowService()

    async def connect(_settings: Settings) -> Client:
        return cast(Client, FakeClient(service))

    lazy = LazyTemporalHealthProbe(_settings(), connect_client=connect)

    asyncio.run(lazy.check_namespace())

    assert service.requests == [DescribeNamespaceRequest(namespace="knobridge-ns")]


def test_lazy_probe_reports_an_unreachable_server() -> None:
    async def connect(_settings: Settings) -> Client:
        raise RuntimeError("Failed client connect")

    lazy = LazyTemporalHealthProbe(_settings(), connect_client=connect)

    with pytest.raises(TemporalUnreachableError):
        asyncio.run(lazy.last_poller_seen())
