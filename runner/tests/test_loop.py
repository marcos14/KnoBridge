from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass, field

import httpx
import pytest

from knobridge_runner.errors import EXIT_INVALID_TOKEN, EXIT_OK
from knobridge_runner.loop import Runner, current_platform
from knobridge_runner.processor import (
    JobContext,
    JobDeferred,
    JobFailed,
    JobOutcome,
    JobProcessor,
    JobSucceeded,
)
from knobridge_runner.protocol import RunnerJobMetrics, RunnerJobOut
from knobridge_runner.protocol_result import RunnerExecutorRun, RunnerJobResultIn
from runner_support import (
    COMMIT,
    JOB_ID,
    SOURCE_ID,
    FakeServer,
    FakeSleep,
    FakeStatus,
    error_response,
    heartbeat_out,
    job_out,
    json_response,
    make_client,
    state_out,
)

HEARTBEAT = f"/jobs/{JOB_ID}/heartbeat"
RESULT = f"/jobs/{JOB_ID}/result"
FAIL = f"/jobs/{JOB_ID}/fail"
DEFER = f"/jobs/{JOB_ID}/defer"
RESULT_OUT = {
    "job_id": JOB_ID,
    "status": "succeeded",
    "items_accepted": 0,
    "items_preserved": 0,
    "items_rejected": 0,
    "sync_run_id": None,
}


def success_result() -> RunnerJobResultIn:
    return RunnerJobResultIn(
        attempt=1,
        commit_sha=COMMIT,
        changed_paths=None,
        executor=RunnerExecutorRun(name="claude_code"),
        metrics=RunnerJobMetrics(duration_ms=5),
        items=[],
        rejections=[],
    )


@dataclass
class StaticProcessor:
    outcome: JobOutcome | Exception

    async def process(self, context: JobContext) -> JobOutcome:
        await asyncio.sleep(0)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@dataclass
class BlockingProcessor:
    """Never finishes on its own; signals when it started."""

    started: asyncio.Event = field(default_factory=asyncio.Event)

    async def process(self, context: JobContext) -> JobOutcome:
        context.phase = "executing"
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


def make_runner(
    server: FakeServer,
    processor: JobProcessor | None = None,
    status: FakeStatus | None = None,
    sleep: FakeSleep | None = None,
) -> tuple[Runner, FakeSleep]:
    fake_sleep = sleep or FakeSleep()
    runner = Runner(
        make_client(server, fake_sleep),
        status or FakeStatus(),
        processor,
        concurrency=1,
        sleep=fake_sleep,
        clock=fake_sleep.clock,
        platform="linux",
    )
    return runner, fake_sleep


def job() -> RunnerJobOut:
    return RunnerJobOut.model_validate(job_out())


def test_job_heartbeat_runs_until_done() -> None:
    enough = asyncio.Event()

    def beat(request: httpx.Request) -> httpx.Response:
        if len(server.bodies(HEARTBEAT)) >= 3:
            enough.set()
        return json_response(
            200, {"status": "running", "lease_expires_at": None, "cancel_requested": False}
        )

    server = FakeServer().on(HEARTBEAT, beat).on(RESULT, json_response(200, RESULT_OUT))

    @dataclass
    class WaitsForHeartbeats:
        async def process(self, context: JobContext) -> JobOutcome:
            context.phase = "executing"
            context.tool_calls = 4
            await enough.wait()
            return JobSucceeded(success_result())

    runner, sleep = make_runner(server, WaitsForHeartbeats())

    asyncio.run(runner.run_job(WaitsForHeartbeats(), job()))

    beats = server.bodies(HEARTBEAT)
    assert len(beats) >= 3
    assert beats[0] == {"attempt": 1, "phase": "executing", "elapsed_seconds": 30, "tool_calls": 4}
    assert server.paths()[-1] == RESULT
    assert set(sleep.delays) == {30}
    assert [b["elapsed_seconds"] for b in beats[:3]] == [30, 60, 90]


def test_ctrl_c_fails_job_retryably() -> None:
    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out()))
        .on("/jobs/claim", json_response(200, job_out()))
        .on(
            HEARTBEAT,
            json_response(
                200, {"status": "running", "lease_expires_at": None, "cancel_requested": False}
            ),
        )
        .on(FAIL, json_response(200, state_out("queued")))
    )

    async def scenario() -> None:
        processor = BlockingProcessor()
        runner, _ = make_runner(server, processor)
        task = asyncio.ensure_future(runner.run())
        await processor.started.wait()
        task.cancel()  # what asyncio.run does to the main task on Ctrl+C
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert server.bodies(FAIL) == [
        {
            "attempt": 1,
            "code": "interrupted",
            "retryable": True,
            "message": "runner stopped during the job",
            "metrics": None,
        }
    ]
    assert RESULT not in server.paths()


def test_ctrl_c_still_stops_when_interruption_cannot_be_reported() -> None:
    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out()))
        .on("/jobs/claim", json_response(200, job_out()))
        .on(HEARTBEAT, error_response(503, "service_unavailable"))
        .on(FAIL, error_response(409, "job_not_leased"))
    )

    async def scenario() -> None:
        processor = BlockingProcessor()
        runner, _ = make_runner(server, processor)
        task = asyncio.ensure_future(runner.run())
        await processor.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert len(server.bodies(FAIL)) == 1


@pytest.mark.parametrize(
    "answer",
    [
        json_response(
            200, {"status": "cancelled", "lease_expires_at": None, "cancel_requested": True}
        ),
        error_response(409, "job_not_leased"),
    ],
)
def test_job_taken_away_stops_processor_without_report(answer: httpx.Response) -> None:
    server = FakeServer().on(HEARTBEAT, answer)

    asyncio.run(make_runner(server)[0].run_job(BlockingProcessor(), job()))

    assert server.paths() == [HEARTBEAT]


def test_processor_exception_fails_job_retryably() -> None:
    server = FakeServer().on(FAIL, json_response(200, state_out("queued")))

    asyncio.run(make_runner(server)[0].run_job(StaticProcessor(RuntimeError("boom")), job()))

    body = server.bodies(FAIL)[0]
    assert (body["code"], body["retryable"]) == ("internal_error", True)


def test_failed_outcome_is_sent_as_fail() -> None:
    server = FakeServer().on(FAIL, json_response(200, state_out("failed")))
    outcome = JobFailed("timeout", False, "executor timed out after 1200 s")

    asyncio.run(make_runner(server)[0].run_job(StaticProcessor(outcome), job()))

    body = server.bodies(FAIL)[0]
    assert (body["code"], body["retryable"], body["message"]) == (
        "timeout",
        False,
        "executor timed out after 1200 s",
    )


def test_rejected_result_fails_with_result_rejected() -> None:
    server = (
        FakeServer()
        .on(RESULT, error_response(422, "result_invalid"))
        .on(FAIL, json_response(200, state_out("failed")))
    )

    outcome = JobSucceeded(success_result())
    asyncio.run(make_runner(server)[0].run_job(StaticProcessor(outcome), job()))

    body = server.bodies(FAIL)[0]
    assert (body["code"], body["retryable"]) == ("result_rejected", False)


def test_auth_failed_deferral_marks_executor_unauthenticated() -> None:
    server = FakeServer().on(DEFER, json_response(200, state_out("deferred")))
    status = FakeStatus()
    outcome = JobDeferred("auth_failed", None, "executor not logged in")

    asyncio.run(make_runner(server, status=status)[0].run_job(StaticProcessor(outcome), job()))

    assert server.bodies(DEFER)[0]["reason"] == "auth_failed"
    assert status.unauthenticated == ["claude_code"]


def test_quota_deferral_keeps_executor_authenticated() -> None:
    server = FakeServer().on(DEFER, json_response(200, state_out("deferred")))
    status = FakeStatus()
    outcome = JobDeferred("quota_exhausted", 900, "usage limit reached")

    asyncio.run(make_runner(server, status=status)[0].run_job(StaticProcessor(outcome), job()))

    assert server.bodies(DEFER)[0]["retry_after_seconds"] == 900
    assert status.unauthenticated == []


def test_undeliverable_outcome_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    server = FakeServer().on(FAIL, error_response(404, "job_not_found"))
    outcome = JobFailed("executor_error", True, "executor exited with code 1")

    with caplog.at_level(logging.WARNING):
        asyncio.run(make_runner(server)[0].run_job(StaticProcessor(outcome), job()))

    assert "job_outcome_not_delivered" in caplog.messages


def test_run_stops_with_exit_code_on_invalid_token() -> None:
    server = FakeServer().on("/heartbeat", error_response(401, "invalid_runner_token"))

    assert asyncio.run(make_runner(server)[0].run()) == EXIT_INVALID_TOKEN


def test_run_without_processor_only_heartbeats(caplog: pytest.LogCaptureFixture) -> None:
    source = {
        "source_id": SOURCE_ID,
        "name": "ERP",
        "repository": "other",
        "last_reported_commit": None,
    }
    server = FakeServer().on(
        "/heartbeat",
        json_response(200, heartbeat_out(sources=[source, {**source, "repository": "erp"}])),
    )
    runner, sleep = make_runner(server)
    sleep.on_sleep = lambda count: runner.request_stop() if count == 2 else None

    with caplog.at_level(logging.INFO):
        code = asyncio.run(runner.run())

    assert code == EXIT_OK
    assert server.paths() == ["/heartbeat"] * 3
    assert "runner_without_processor" in caplog.messages
    assert "source_repository_not_served" in caplog.messages


def test_worker_waits_while_no_executor_is_claimable() -> None:
    server = FakeServer().on("/heartbeat", json_response(200, heartbeat_out()))
    runner, sleep = make_runner(server, StaticProcessor(RuntimeError()), FakeStatus(claimable=[]))
    sleep.on_sleep = lambda count: runner.request_stop() if count == 3 else None

    assert asyncio.run(runner.run()) == EXIT_OK
    assert "/jobs/claim" not in server.paths()


def test_worker_claims_again_after_empty_poll() -> None:
    claims = 0

    def claim(request: httpx.Request) -> httpx.Response:
        nonlocal claims
        claims += 1
        if claims == 2:
            runner.request_stop()
        return json_response(204)

    server = (
        FakeServer().on("/heartbeat", json_response(200, heartbeat_out())).on("/jobs/claim", claim)
    )
    runner, _ = make_runner(server, StaticProcessor(RuntimeError()))

    assert asyncio.run(runner.run()) == EXIT_OK
    assert claims >= 2


def test_worker_reports_active_job_in_runner_heartbeat() -> None:
    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out()))
        .on(RESULT, json_response(200, RESULT_OUT))
    )

    @dataclass
    class BeatsDuringJob:
        async def process(self, context: JobContext) -> JobOutcome:
            await runner.heartbeat_once()
            return JobSucceeded(success_result())

    runner, _ = make_runner(server)
    asyncio.run(runner.run_job(BeatsDuringJob(), job()))

    assert server.bodies("/heartbeat")[0]["active_job_ids"] == [JOB_ID]


@pytest.mark.parametrize(
    ("value", "expected"), [("win32", "windows"), ("darwin", "darwin"), ("linux", "linux")]
)
def test_current_platform_maps_sys_platform(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: str
) -> None:
    monkeypatch.setattr(sys, "platform", value)

    assert current_platform() == expected
