"""HTTP client of /v1/runner/* with the retry rules of docs/specs/runner.md.

Network errors, timeouts and 500/502/503/504 are retried with exponential backoff; every other
answer maps to a domain error (errors.py). TLS is always verified and proxies come from the
standard variables (``HTTPS_PROXY``, ``NO_PROXY``), which httpx honors by default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Self, cast
from uuid import UUID

import httpx

from knobridge_runner import PROTOCOL_VERSION, __version__
from knobridge_runner.backoff import Backoff, Clock, Sleep, monotonic, real_sleep
from knobridge_runner.errors import (
    EXIT_INVALID_TOKEN,
    EXIT_UPGRADE_REQUIRED,
    EXIT_WORKSPACE_SUSPENDED,
    FatalServerError,
    JobGoneError,
    RejectedError,
    ServerError,
    UnavailableError,
)
from knobridge_runner.protocol import (
    RunnerClaimIn,
    RunnerHeartbeatIn,
    RunnerHeartbeatOut,
    RunnerJobDeferIn,
    RunnerJobFailIn,
    RunnerJobHeartbeatIn,
    RunnerJobHeartbeatOut,
    RunnerJobOut,
    RunnerJobStateOut,
    RunnerReportIn,
    RunnerReportOut,
    WireRequest,
)
from knobridge_runner.protocol_result import RunnerJobResultIn, RunnerJobResultOut

logger = logging.getLogger(__name__)

PROTOCOL_HEADER = "KnoBridge-Runner-Protocol"
RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 30.0
# The server may hold a claim for wait_seconds; the read timeout leaves 10 s on top of it.
CLAIM_EXTRA_SECONDS = 10.0
LEASE_SECONDS = 120.0


@dataclass(frozen=True)
class RetryPolicy:
    """How long a call keeps retrying transient failures; None means no limit on that axis."""

    max_attempts: int | None = None
    max_elapsed_seconds: float | None = None


FOREVER = RetryPolicy()
ONCE = RetryPolicy(max_attempts=1)
# While a job runs, retry for as long as the lease may still be alive.
WHILE_LEASED = RetryPolicy(max_elapsed_seconds=LEASE_SECONDS)
# The result is idempotent on the server: up to 10 tries.
RESULT_POLICY = RetryPolicy(max_attempts=10)


def _error_fields(response: httpx.Response) -> tuple[str | None, str]:
    try:
        body: object = response.json()
    except ValueError:
        return None, response.reason_phrase
    error = cast(dict[str, object], body).get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None, response.reason_phrase
    fields = cast(dict[str, object], error)
    code, message = fields.get("code"), fields.get("message")
    return (
        code if isinstance(code, str) else None,
        message if isinstance(message, str) else response.reason_phrase,
    )


def raise_for_status(response: httpx.Response, *, job_route: bool) -> None:
    """Map a non-success answer to the domain error the runner acts on."""
    status = response.status_code
    if status < 300:
        return
    code, message = _error_fields(response)
    if status == 401:
        raise FatalServerError(status, code, message, EXIT_INVALID_TOKEN)
    if status == 403:
        raise FatalServerError(status, code, message, EXIT_WORKSPACE_SUSPENDED)
    if status == 426:
        raise FatalServerError(status, code, message, EXIT_UPGRADE_REQUIRED)
    if job_route and status in (404, 409):
        raise JobGoneError(status, code, message)
    if status in (413, 422):
        raise RejectedError(status, code, message)
    raise ServerError(status, code, message)


class RunnerClient:
    """One instance per process; close it with ``aclose`` or use it as an async context manager."""

    def __init__(
        self,
        server_url: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = real_sleep,
        clock: Clock = monotonic,
        backoff: Backoff | None = None,
    ) -> None:
        self._sleep = sleep
        self._clock = clock
        self._backoff = backoff or Backoff()
        self._http = httpx.AsyncClient(
            base_url=f"{server_url.rstrip('/')}/v1/runner",
            headers={
                "Authorization": f"Bearer {token}",
                PROTOCOL_HEADER: str(PROTOCOL_VERSION),
                "User-Agent": f"knobridge-runner/{__version__}",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
            transport=transport,
            verify=True,
            trust_env=True,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _post(
        self,
        path: str,
        body: WireRequest,
        *,
        policy: RetryPolicy,
        job_route: bool = False,
        read_timeout: float | None = None,
    ) -> httpx.Response:
        started = self._clock()
        failures = 0
        content = body.model_dump_json()
        while True:
            try:
                response = await self._http.post(
                    path,
                    content=content,
                    headers={"Content-Type": "application/json"},
                    timeout=read_timeout or DEFAULT_TIMEOUT_SECONDS,
                )
            except httpx.TransportError as exc:
                reason = type(exc).__name__
            else:
                if response.status_code not in RETRYABLE_STATUS:
                    raise_for_status(response, job_route=job_route)
                    return response
                reason = f"http_{response.status_code}"
            failures += 1
            delay = self._backoff.delay(failures)
            if self._exhausted(policy, failures, self._clock() - started + delay):
                raise UnavailableError(f"{path}: gave up after {failures} tries ({reason})")
            logger.warning(
                "server_request_retry",
                extra={"path": path, "reason": reason, "failures": failures, "delay": delay},
            )
            await self._sleep(delay)

    @staticmethod
    def _exhausted(policy: RetryPolicy, failures: int, elapsed_after_wait: float) -> bool:
        if policy.max_attempts is not None and failures >= policy.max_attempts:
            return True
        return (
            policy.max_elapsed_seconds is not None
            and elapsed_after_wait > policy.max_elapsed_seconds
        )

    async def heartbeat(
        self, body: RunnerHeartbeatIn, *, policy: RetryPolicy = FOREVER
    ) -> RunnerHeartbeatOut:
        response = await self._post("/heartbeat", body, policy=policy)
        return RunnerHeartbeatOut.model_validate_json(response.content)

    async def report(
        self, source_id: UUID, body: RunnerReportIn, *, policy: RetryPolicy = FOREVER
    ) -> RunnerReportOut:
        response = await self._post(f"/sources/{source_id}/report", body, policy=policy)
        return RunnerReportOut.model_validate_json(response.content)

    async def claim(self, body: RunnerClaimIn) -> RunnerJobOut | None:
        """Long-poll for a job; None when the server had none within ``wait_seconds`` (204)."""
        response = await self._post(
            "/jobs/claim",
            body,
            policy=FOREVER,
            read_timeout=body.wait_seconds + CLAIM_EXTRA_SECONDS,
        )
        if response.status_code == 204:
            return None
        return RunnerJobOut.model_validate_json(response.content)

    async def job_heartbeat(
        self, job_id: UUID, body: RunnerJobHeartbeatIn, *, policy: RetryPolicy = WHILE_LEASED
    ) -> RunnerJobHeartbeatOut:
        response = await self._post(
            f"/jobs/{job_id}/heartbeat", body, policy=policy, job_route=True
        )
        return RunnerJobHeartbeatOut.model_validate_json(response.content)

    async def result(
        self, job_id: UUID, body: RunnerJobResultIn, *, policy: RetryPolicy = RESULT_POLICY
    ) -> RunnerJobResultOut:
        response = await self._post(f"/jobs/{job_id}/result", body, policy=policy, job_route=True)
        return RunnerJobResultOut.model_validate_json(response.content)

    async def fail(
        self, job_id: UUID, body: RunnerJobFailIn, *, policy: RetryPolicy = WHILE_LEASED
    ) -> RunnerJobStateOut:
        response = await self._post(f"/jobs/{job_id}/fail", body, policy=policy, job_route=True)
        return RunnerJobStateOut.model_validate_json(response.content)

    async def defer(
        self, job_id: UUID, body: RunnerJobDeferIn, *, policy: RetryPolicy = WHILE_LEASED
    ) -> RunnerJobStateOut:
        response = await self._post(f"/jobs/{job_id}/defer", body, policy=policy, job_route=True)
        return RunnerJobStateOut.model_validate_json(response.content)
