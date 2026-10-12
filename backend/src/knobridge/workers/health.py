"""Health workflow: proves a worker is polling its task queue and can run activities.

This module is loaded inside the Temporal workflow sandbox, so it imports only ``temporalio``
and the standard library.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

# Stable names: Temporal matches history by name, so a behaviour change gets a new version.
HEALTH_WORKFLOW_NAME = "knobridge.health.v1"
PING_ACTIVITY_NAME = "knobridge.health.ping.v1"

PING_RESULT = "ok"
PING_START_TO_CLOSE_TIMEOUT = timedelta(seconds=10)
PING_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)


@activity.defn(name=PING_ACTIVITY_NAME)
async def ping() -> str:
    """Answer ``"ok"``; no side effects, so retries are always safe."""
    return PING_RESULT


@workflow.defn(name=HEALTH_WORKFLOW_NAME)
class HealthWorkflow:
    """Run :func:`ping` once (with explicit timeout and retry) and return its result."""

    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            ping,
            start_to_close_timeout=PING_START_TO_CLOSE_TIMEOUT,
            retry_policy=PING_RETRY_POLICY,
        )
