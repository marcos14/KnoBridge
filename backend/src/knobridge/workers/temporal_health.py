"""The ``TemporalProbe`` of production: describes the namespace and the worker's task queue.

Used by the instance health checks (``usage/health.py``) through the lazy client of
``sync_client.py``. The worker is seen by its pollers: each one carries the last time it
asked the task queue for work.
"""

from __future__ import annotations

from datetime import UTC, datetime

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest
from temporalio.client import Client


class TemporalHealthProbe:
    def __init__(self, client: Client, namespace: str, task_queue: str) -> None:
        self._client = client
        self._namespace = namespace
        self._task_queue = task_queue

    async def check_namespace(self) -> None:
        await self._client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=self._namespace)
        )

    async def last_poller_seen(self) -> datetime | None:
        response = await self._client.workflow_service.describe_task_queue(
            DescribeTaskQueueRequest(
                namespace=self._namespace,
                task_queue=TaskQueue(name=self._task_queue),
                task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
            )
        )
        seen = [
            poller.last_access_time.ToDatetime(tzinfo=UTC)
            for poller in response.pollers
            if poller.HasField("last_access_time")
        ]
        return max(seen, default=None)
