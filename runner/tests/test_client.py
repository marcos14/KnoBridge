from __future__ import annotations

import asyncio
from uuid import UUID

import httpx
import pytest

from knobridge_runner import __version__
from knobridge_runner.client import (
    ONCE,
    PROTOCOL_HEADER,
    RetryPolicy,
    RunnerClient,
    raise_for_status,
)
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
    RunnerInventory,
    RunnerJobDeferIn,
    RunnerJobFailIn,
    RunnerJobHeartbeatIn,
    RunnerJobMetrics,
    RunnerJobOut,
    RunnerReportIn,
)
from knobridge_runner.protocol_result import RunnerExecutorRun, RunnerJobResultIn
from runner_support import (
    COMMIT,
    JOB_ID,
    SOURCE_ID,
    TOKEN,
    FakeServer,
    FakeSleep,
    error_response,
    heartbeat_out,
    job_out,
    json_response,
    make_client,
    state_out,
)

JOB = UUID(JOB_ID)


def connect_error(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("down", request=request)


def heartbeat_in() -> RunnerHeartbeatIn:
    return RunnerHeartbeatIn(
        runner_version="0.1.0", platform="linux", executors=[], repositories=[]
    )


def claim_in(wait: int = 25) -> RunnerClaimIn:
    return RunnerClaimIn(wait_seconds=wait, executors=["claude_code"], repositories=["erp"])


def result_in() -> RunnerJobResultIn:
    return RunnerJobResultIn(
        attempt=1,
        commit_sha=COMMIT,
        changed_paths=None,
        executor=RunnerExecutorRun(name="claude_code"),
        metrics=RunnerJobMetrics(duration_ms=10),
        items=[],
        rejections=[],
    )


def test_client_sends_auth_protocol_and_user_agent_headers() -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))

    async def scenario() -> None:
        async with make_client(server) as client:
            await client.heartbeat(heartbeat_in())

    asyncio.run(scenario())

    headers = server.requests[0].headers
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers[PROTOCOL_HEADER] == "1"
    assert headers["User-Agent"] == f"knobridge-runner/{__version__}"
    assert headers["Content-Type"] == "application/json"


def test_client_retries_with_backoff() -> None:
    server = FakeServer().on(
        "/heartbeat",
        error_response(503, "service_unavailable"),
        error_response(500, "internal_error"),
        connect_error,
        json_response(200, heartbeat_out(name="ok")),
    )
    sleep = FakeSleep()

    async def scenario() -> str:
        async with make_client(server, sleep) as client:
            return (await client.heartbeat(heartbeat_in())).name

    name = asyncio.run(scenario())

    assert name == "ok"
    assert sleep.delays == [1.0, 2.0, 4.0]
    assert len(server.requests) == 4


def test_client_backoff_is_capped_at_sixty_seconds() -> None:
    failures = [error_response(502, "bad_gateway")] * 8
    server = FakeServer().on("/heartbeat", *failures, json_response(200, heartbeat_out()))
    sleep = FakeSleep()

    async def scenario() -> None:
        async with make_client(server, sleep) as client:
            await client.heartbeat(heartbeat_in())

    asyncio.run(scenario())

    assert sleep.delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]


def test_client_gives_up_after_max_attempts() -> None:
    server = FakeServer().on("/heartbeat", error_response(504, "timeout"))
    sleep = FakeSleep()

    async def scenario() -> None:
        async with make_client(server, sleep) as client:
            await client.heartbeat(heartbeat_in(), policy=RetryPolicy(max_attempts=3))

    with pytest.raises(UnavailableError, match="3 tries"):
        asyncio.run(scenario())
    assert sleep.delays == [1.0, 2.0]


def test_client_gives_up_when_elapsed_exceeds_budget() -> None:
    server = FakeServer().on("/heartbeat", error_response(503, "service_unavailable"))
    sleep = FakeSleep()

    async def scenario() -> None:
        async with make_client(server, sleep) as client:
            await client.heartbeat(heartbeat_in(), policy=RetryPolicy(max_elapsed_seconds=10))

    with pytest.raises(UnavailableError):
        asyncio.run(scenario())
    # 1 + 2 + 4 = 7 s waited; the next wait (8 s) would pass the 10 s budget.
    assert sleep.delays == [1.0, 2.0, 4.0]


def test_client_once_policy_does_not_retry() -> None:
    server = FakeServer().on("/heartbeat", error_response(503, "service_unavailable"))
    sleep = FakeSleep()

    async def scenario() -> None:
        async with make_client(server, sleep) as client:
            await client.heartbeat(heartbeat_in(), policy=ONCE)

    with pytest.raises(UnavailableError):
        asyncio.run(scenario())
    assert sleep.delays == []


def test_claim_long_poll_handles_empty() -> None:
    server = FakeServer().on("/jobs/claim", json_response(204), json_response(200, job_out()))
    seen_timeouts: list[object] = []
    original = server.handle

    def handle(request: httpx.Request) -> httpx.Response:
        seen_timeouts.append(request.extensions["timeout"]["read"])
        return original(request)

    async def scenario() -> list[RunnerJobOut | None]:
        client = RunnerClient(
            "https://knobridge.test/",
            TOKEN,
            transport=httpx.MockTransport(handle),
            sleep=FakeSleep(),
        )
        async with client:
            return [await client.claim(claim_in(wait=25)), await client.claim(claim_in(wait=25))]

    first, second = asyncio.run(scenario())

    assert first is None
    assert second is not None
    assert str(second.job_id) == JOB_ID
    assert seen_timeouts == [35.0, 35.0]
    assert server.bodies("/jobs/claim")[0] == {
        "wait_seconds": 25,
        "executors": ["claude_code"],
        "repositories": ["erp"],
    }


@pytest.mark.parametrize(
    ("status", "code", "exit_code"),
    [
        (401, "invalid_runner_token", EXIT_INVALID_TOKEN),
        (403, "workspace_suspended", EXIT_WORKSPACE_SUSPENDED),
        (426, "runner_protocol_unsupported", EXIT_UPGRADE_REQUIRED),
    ],
)
def test_client_fatal_answers_carry_exit_code(status: int, code: str, exit_code: int) -> None:
    server = FakeServer().on("/heartbeat", error_response(status, code))

    async def scenario() -> None:
        async with make_client(server) as client:
            await client.heartbeat(heartbeat_in())

    with pytest.raises(FatalServerError) as caught:
        asyncio.run(scenario())
    assert caught.value.exit_code == exit_code
    assert caught.value.code == code


@pytest.mark.parametrize("status", [404, 409])
def test_client_job_route_conflict_means_job_gone(status: int) -> None:
    server = FakeServer().on(f"/jobs/{JOB_ID}/heartbeat", error_response(status, "job_not_leased"))
    body = RunnerJobHeartbeatIn(attempt=1, phase="executing", elapsed_seconds=5, tool_calls=2)

    async def scenario() -> None:
        async with make_client(server) as client:
            await client.job_heartbeat(JOB, body)

    with pytest.raises(JobGoneError):
        asyncio.run(scenario())


def test_client_report_not_found_is_plain_server_error() -> None:
    server = FakeServer().on(
        f"/sources/{SOURCE_ID}/report", error_response(404, "source_not_found")
    )
    body = RunnerReportIn(
        repository="erp",
        head_commit=COMMIT,
        branch="main",
        base_commit=None,
        changed_paths=None,
        inventory=RunnerInventory(files=1, lines=10),
        modules=[],
    )

    async def scenario() -> None:
        async with make_client(server) as client:
            await client.report(UUID(SOURCE_ID), body)

    with pytest.raises(ServerError) as caught:
        asyncio.run(scenario())
    assert not isinstance(caught.value, JobGoneError)
    assert caught.value.code == "source_not_found"


def test_client_report_parses_answer() -> None:
    answer = {
        "source_id": SOURCE_ID,
        "head_commit": COMMIT,
        "modules_total": 2,
        "modules_upserted": 1,
        "jobs_enqueued": [{"job_id": JOB_ID, "module_key": "src-billing"}],
    }
    server = FakeServer().on(f"/sources/{SOURCE_ID}/report", json_response(200, answer))
    body = RunnerReportIn(
        repository="erp",
        head_commit=COMMIT,
        branch=None,
        base_commit=COMMIT,
        changed_paths=["src/a.ts"],
        inventory=RunnerInventory(files=1, lines=10),
        modules=[],
    )

    async def scenario() -> int:
        async with make_client(server) as client:
            return (await client.report(UUID(SOURCE_ID), body)).modules_total

    assert asyncio.run(scenario()) == 2


def test_client_result_rejected_raises_rejected_error() -> None:
    server = FakeServer().on(f"/jobs/{JOB_ID}/result", error_response(422, "result_invalid"))

    async def scenario() -> None:
        async with make_client(server) as client:
            await client.result(JOB, result_in())

    with pytest.raises(RejectedError):
        asyncio.run(scenario())


def test_client_result_fail_and_defer_parse_answers() -> None:
    result = {
        "job_id": JOB_ID,
        "status": "succeeded",
        "items_accepted": 0,
        "items_preserved": 0,
        "items_rejected": 0,
        "sync_run_id": None,
        "duplicate": False,
        "future_field": "ignored",
    }
    server = (
        FakeServer()
        .on(f"/jobs/{JOB_ID}/result", json_response(200, result))
        .on(f"/jobs/{JOB_ID}/fail", json_response(200, state_out("queued")))
        .on(f"/jobs/{JOB_ID}/defer", json_response(200, state_out("deferred")))
    )
    fail = RunnerJobFailIn(attempt=1, code="timeout", retryable=False, message="timeout")
    defer = RunnerJobDeferIn(
        attempt=1, reason="quota_exhausted", retry_after_seconds=600, message="quota"
    )

    async def scenario() -> tuple[str, str, str]:
        async with make_client(server) as client:
            done = await client.result(JOB, result_in())
            failed = await client.fail(JOB, fail)
            deferred = await client.defer(JOB, defer)
            return done.status, failed.status, deferred.status

    assert asyncio.run(scenario()) == ("succeeded", "queued", "deferred")


def test_raise_for_status_uses_reason_without_json_body() -> None:
    response = httpx.Response(400, text="not json")

    with pytest.raises(ServerError) as caught:
        raise_for_status(response, job_route=False)
    assert caught.value.code is None
    assert caught.value.status == 400


@pytest.mark.parametrize(
    "body",
    [{"detail": "x"}, {"error": "flat"}, ["list"], {"error": {"code": 7, "message": None}}],
)
def test_raise_for_status_tolerates_unexpected_error_bodies(body: object) -> None:
    response = httpx.Response(413, json=body)

    with pytest.raises(RejectedError) as caught:
        raise_for_status(response, job_route=True)
    assert caught.value.code is None


def test_raise_for_status_treats_redirect_as_error() -> None:
    with pytest.raises(ServerError):
        raise_for_status(httpx.Response(302), job_route=False)
