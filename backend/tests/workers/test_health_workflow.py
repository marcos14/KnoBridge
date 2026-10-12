from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from knobridge.workers.health import (
    HEALTH_WORKFLOW_NAME,
    PING_ACTIVITY_NAME,
    PING_RESULT,
    HealthWorkflow,
    ping,
)

TASK_QUEUE = "test-health"


async def _execute_health(activities: list[Callable[..., Any]]) -> str:
    # Time skipping fast-forwards retry backoff, so no real time passes in the test.
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[HealthWorkflow],
            activities=activities,
        ),
    ):
        return await env.client.execute_workflow(
            HealthWorkflow.run, id="health-test", task_queue=TASK_QUEUE
        )


def test_ping_activity_returns_ok() -> None:
    result = asyncio.run(ActivityEnvironment().run(ping))

    assert result == PING_RESULT == "ok"


def test_health_names_are_stable_and_versioned() -> None:
    assert (HEALTH_WORKFLOW_NAME, PING_ACTIVITY_NAME) == (
        "knobridge.health.v1",
        "knobridge.health.ping.v1",
    )


@pytest.mark.integration
def test_health_workflow_runs_ping_activity() -> None:
    result = asyncio.run(_execute_health([ping]))

    assert result == "ok"


@pytest.mark.integration
def test_health_workflow_retries_failed_ping() -> None:
    attempts: list[int] = []

    @activity.defn(name=PING_ACTIVITY_NAME)
    async def flaky_ping() -> str:
        attempts.append(activity.info().attempt)
        if len(attempts) == 1:
            raise RuntimeError("transient failure")
        return "recovered"

    result = asyncio.run(_execute_health([flaky_ping]))

    assert (result, attempts) == ("recovered", [1, 2])


@pytest.mark.integration
def test_health_workflow_fails_after_maximum_attempts() -> None:
    attempts: list[int] = []

    @activity.defn(name=PING_ACTIVITY_NAME)
    async def broken_ping() -> str:
        attempts.append(activity.info().attempt)
        raise RuntimeError("permanent failure")

    with pytest.raises(WorkflowFailureError):
        asyncio.run(_execute_health([broken_ping]))

    assert attempts == [1, 2, 3]
