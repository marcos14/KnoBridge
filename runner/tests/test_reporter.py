from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx
import pytest

from knobridge_runner.errors import FatalServerError
from knobridge_runner.layer0 import RepositoryUnavailableError
from knobridge_runner.loop import Runner
from knobridge_runner.processor import JobContext, JobFailed, JobOutcome
from knobridge_runner.protocol import RunnerSourceOut
from knobridge_runner.reporter import GitSourceReporter
from layer0_support import commit_all, local_runner, make_repo, write
from runner_support import (
    JOB_ID,
    SOURCE_ID,
    FakeClock,
    FakeServer,
    FakeSleep,
    FakeStatus,
    error_response,
    heartbeat_out,
    job_out,
    json_response,
    make_client,
    make_config,
    state_out,
)

REPORT = f"/sources/{SOURCE_ID}/report"
REPORT_OUT = {
    "source_id": SOURCE_ID,
    "head_commit": "c" * 40,
    "modules_total": 1,
    "modules_upserted": 1,
    "jobs_enqueued": [{"job_id": "55555555-5555-4555-8555-555555555555", "module_key": "src"}],
}


def source(repository: str = "erp", last: str | None = None) -> RunnerSourceOut:
    return RunnerSourceOut.model_validate(
        {
            "source_id": SOURCE_ID,
            "name": "ERP",
            "repository": repository,
            "last_reported_commit": last,
            "exclude_globs": ["docs/**"],
        }
    )


def sync(server: FakeServer, repo: Path, *rounds: list[RunnerSourceOut], tmp: Path) -> None:
    config = make_config(tmp, repositories={"erp": str(repo)})

    async def scenario() -> None:
        async with make_client(server) as client:
            reporter = GitSourceReporter(client, config, local_runner())
            for sources in rounds:
                await reporter.sync(sources)

    asyncio.run(scenario())


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, {"src/a.py": "x = 1\n", "src/b.py": "y = 2\n", "docs/x.md": "#\n"})


def test_reporter_reports_once_per_head(repo: Path, tmp_path: Path) -> None:
    server = FakeServer().on(REPORT, json_response(200, REPORT_OUT))

    sync(server, repo, [source()], [source()], tmp=tmp_path)

    (body,) = server.bodies(REPORT)
    assert body["repository"] == "erp"
    assert body["base_commit"] is None
    assert body["changed_paths"] is None
    assert body["inventory"] == {
        "files": 2,
        "lines": 2,
        "languages": {"python": {"files": 2, "lines": 2}},
    }


def test_reporter_reports_again_when_head_moves(repo: Path, tmp_path: Path) -> None:
    server = FakeServer().on(REPORT, json_response(200, REPORT_OUT))
    first = commit_all(repo, "noop")
    config = make_config(tmp_path, repositories={"erp": str(repo)})

    async def scenario() -> None:
        async with make_client(server) as client:
            reporter = GitSourceReporter(client, config, local_runner())
            await reporter.sync([source(last=first)])
            write(repo, {"src/a.py": "x = 3\n"})
            commit_all(repo, "change a")
            await reporter.sync([source(last=first)])

    asyncio.run(scenario())

    bodies = server.bodies(REPORT)
    assert [b["changed_paths"] for b in bodies] == [[], ["src/a.py"]]
    assert bodies[0]["head_commit"] != bodies[1]["head_commit"]


def test_reporter_skips_unserved_and_unreadable_repositories(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    server = FakeServer()

    sync(server, plain, [source("other"), source()], tmp=tmp_path)

    assert server.requests == []


def test_reporter_retries_unavailable_server_on_next_sync(
    repo: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeServer().on(
        REPORT,
        error_response(503, "service_unavailable"),
        error_response(503, "service_unavailable"),
        error_response(503, "service_unavailable"),
        json_response(200, REPORT_OUT),
    )

    with caplog.at_level(logging.WARNING):
        sync(server, repo, [source()], [source()], [source()], tmp=tmp_path)

    assert "source_report_unavailable" in caplog.messages
    assert len(server.bodies(REPORT)) == 4


def test_reporter_does_not_repeat_a_refused_report(
    repo: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server = FakeServer().on(REPORT, error_response(409, "repository_mismatch"))

    with caplog.at_level(logging.WARNING):
        sync(server, repo, [source()], [source()], tmp=tmp_path)

    assert "source_report_refused" in caplog.messages
    assert len(server.bodies(REPORT)) == 1


def test_reporter_propagates_fatal_answers(repo: Path, tmp_path: Path) -> None:
    server = FakeServer().on(REPORT, error_response(401, "invalid_runner_token"))

    with pytest.raises(FatalServerError):
        sync(server, repo, [source()], tmp=tmp_path)


def test_reporter_logs_repository_that_breaks_during_report(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise RepositoryUnavailableError("gone")

    monkeypatch.setattr("knobridge_runner.reporter.build_report", broken)
    server = FakeServer()

    with caplog.at_level(logging.WARNING):
        sync(server, repo, [source()], tmp=tmp_path)

    assert "source_report_repository_unavailable" in caplog.messages
    assert server.requests == []


def test_runner_reports_served_sources_at_start(repo: Path, tmp_path: Path) -> None:
    other = source("other").model_dump(mode="json")
    served = source().model_dump(mode="json")
    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out(sources=[other, served])))
        .on(REPORT, json_response(200, REPORT_OUT))
    )
    config = make_config(tmp_path, repositories={"erp": str(repo)})
    sleep = FakeSleep()
    client = make_client(server, sleep)
    runner = Runner(
        client,
        FakeStatus(),
        None,
        concurrency=1,
        sleep=sleep,
        clock=sleep.clock,
        platform="linux",
        reporter=GitSourceReporter(client, config, local_runner()),
    )
    sleep.on_sleep = lambda count: runner.request_stop() if count == 1 else None

    assert asyncio.run(runner.run()) == 0
    assert server.paths() == ["/heartbeat", REPORT, "/heartbeat"]


def test_runner_reports_after_a_job_when_head_moved(repo: Path, tmp_path: Path) -> None:
    stopped = asyncio.Event()

    def report(request: httpx.Request) -> httpx.Response:
        if len(server.bodies(REPORT)) == 2:
            stopped.set()
        return json_response(200, REPORT_OUT)

    served = source().model_dump(mode="json")
    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out(sources=[served])))
        .on(REPORT, report)
        .on("/jobs/claim", json_response(200, job_out()))
        .on(f"/jobs/{JOB_ID}/fail", json_response(200, state_out("failed")))
    )
    config = make_config(tmp_path, repositories={"erp": str(repo)})

    class MovesHead:
        async def process(self, context: JobContext) -> JobOutcome:
            write(repo, {"src/c.py": "z = 1\n"})
            commit_all(repo, "add c")
            runner.request_stop()
            return JobFailed("executor_error", True, "executor finished with an unclassified error")

    async def until_stopped(seconds: float) -> None:
        await stopped.wait()

    client = make_client(server)
    runner = Runner(
        client,
        FakeStatus(),
        MovesHead(),
        concurrency=1,
        sleep=until_stopped,
        clock=FakeClock(),
        platform="linux",
        reporter=GitSourceReporter(client, config, local_runner()),
    )

    assert asyncio.run(runner.run()) == 0
    fail = f"/jobs/{JOB_ID}/fail"
    assert server.paths()[:5] == ["/heartbeat", REPORT, "/jobs/claim", fail, REPORT]
    assert server.bodies(REPORT)[1]["changed_paths"] == ["src/c.py"]
