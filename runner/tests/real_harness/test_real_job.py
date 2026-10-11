"""Opt-in suite (decision D17): a whole job with the real claude and codex CLIs.

Claim, briefing, executor, verification, excerpts and result against a fake HTTP server
(httpx.MockTransport), on the synthetic repository of test_real_harness.py. Skipped unless
KNOBRIDGE_RUNNER_REAL_HARNESS=1; never on CI.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest
from test_real_harness import BUDGET_USD, TIMEOUT_SECONDS, git, make_repository, tree_digest

from knobridge_runner.commands import SubprocessCommandRunner
from knobridge_runner.config import ExecutorConfig
from knobridge_runner.executors import read_version, resolve_command
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.job import HarnessJobProcessor
from knobridge_runner.layer0 import GIT_TIMEOUT_SECONDS
from knobridge_runner.loop import Runner, current_platform
from knobridge_runner.reporter import GitSourceReporter
from runner_support import (
    JOB_ID,
    SOURCE_ID,
    FakeClock,
    FakeServer,
    FakeStatus,
    heartbeat_out,
    job_out,
    json_response,
    make_client,
    make_config,
)

pytestmark = pytest.mark.real_harness

JOB_BEAT_SECONDS = 10
RUNNING: dict[str, object] = {
    "status": "running",
    "lease_expires_at": None,
    "cancel_requested": False,
}
RESULT_OUT: dict[str, object] = {
    "job_id": JOB_ID,
    "status": "succeeded",
    "items_accepted": 0,
    "items_preserved": 0,
    "items_rejected": 0,
    "sync_run_id": None,
}
REPORT_OUT: dict[str, object] = {
    "source_id": SOURCE_ID,
    "head_commit": "0" * 40,
    "modules_total": 1,
    "modules_upserted": 1,
    "jobs_enqueued": [],
}


def _run_job(
    name: ExecutorName, model: str | None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    platform = current_platform()
    command = resolve_command(name, ExecutorConfig(), platform)
    if command is None:
        pytest.skip(f"{name} not found on PATH")
    repo, head = make_repository(tmp_path)
    before = tree_digest(repo)
    git_runner = SubprocessCommandRunner(os.environ, GIT_TIMEOUT_SECONDS)
    config = make_config(tmp_path, repositories={"store": str(repo)})
    version = read_version(SubprocessCommandRunner(os.environ), command)
    processor = HarnessJobProcessor(
        config=config,
        git=git_runner,
        environment=dict(os.environ),
        platform=platform,
        versions=lambda _name: version,
    )
    job = job_out(
        repository="store",
        module={
            "key": "shipping",
            "title": "shipping",
            "paths": ["shipping/**"],
            "last_commit": None,
        },
        executor=name,
        model=model,
        budget_usd=BUDGET_USD,
        timeout_seconds=int(TIMEOUT_SECONDS),
        heartbeat_interval_seconds=JOB_BEAT_SECONDS,
    )
    source = {
        "source_id": SOURCE_ID,
        "name": "Loja",
        "repository": "store",
        "last_reported_commit": None,
    }
    done = asyncio.Event()

    def finish(answer: dict[str, object]) -> Callable[[httpx.Request], httpx.Response]:
        def handle(request: httpx.Request) -> httpx.Response:
            runner.request_stop()
            done.set()
            return json_response(200, answer)

        return handle

    state = {"job_id": JOB_ID, "attempts": 1, "not_before": None}

    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out(sources=[source])))
        .on(f"/sources/{SOURCE_ID}/report", json_response(200, REPORT_OUT))
        .on("/jobs/claim", json_response(200, job), json_response(204))
        .on(f"/jobs/{JOB_ID}/heartbeat", json_response(200, RUNNING))
        .on(f"/jobs/{JOB_ID}/result", finish(RESULT_OUT))
        .on(f"/jobs/{JOB_ID}/fail", finish({**state, "status": "failed"}))
        .on(f"/jobs/{JOB_ID}/defer", finish({**state, "status": "deferred"}))
    )

    async def sleep(seconds: float) -> None:
        # Job heartbeats really wait (the CLI runs in real time); the runner heartbeat waits
        # until the job is over.
        if seconds == JOB_BEAT_SECONDS:
            try:
                await asyncio.wait_for(done.wait(), seconds)
            except TimeoutError:
                return
        await done.wait()

    client = make_client(server)
    runner = Runner(
        client,
        FakeStatus(claimable=[name], names=["store"]),
        processor,
        concurrency=1,
        sleep=sleep,
        clock=FakeClock(),
        platform=platform,
        reporter=GitSourceReporter(client, config, git_runner),
    )
    started = time.monotonic()
    assert asyncio.run(runner.run()) == 0
    elapsed = time.monotonic() - started

    paths = server.paths()
    assert f"/jobs/{JOB_ID}/result" in paths, (paths, server.bodies(f"/jobs/{JOB_ID}/fail"))
    body = server.bodies(f"/jobs/{JOB_ID}/result")[0]
    metrics = cast(dict[str, object], body["metrics"])
    items = cast(list[dict[str, object]], body["items"])
    rejections = cast(list[dict[str, object]], body["rejections"])
    beats = server.bodies(f"/jobs/{JOB_ID}/heartbeat")
    with capsys.disabled():
        sys.stdout.write(
            f"\n[job {name}] elapsed_s={elapsed:.1f} cost_usd={metrics['cost_usd']} "
            f"input={metrics['input_tokens']} cached={metrics['cached_input_tokens']} "
            f"output={metrics['output_tokens']} turns={metrics['num_turns']} "
            f"tools={metrics['tool_calls']} rescued={metrics['rescued']} "
            f"items={Counter(str(i['kind']) for i in items)} "
            f"rejections={Counter(str(r['code']) for r in rejections)} "
            f"sources_valid={metrics['sources_valid']} "
            f"sources_invalid={metrics['sources_invalid']} redactions={metrics['redactions']} "
            f"heartbeats={[(b['phase'], b['tool_calls']) for b in beats]} "
            f"executor={body['executor']}\n"
        )
    assert body["commit_sha"] == head
    assert items, rejections
    assert cast(int, metrics["sources_valid"]) >= 1
    for item in items:
        for evidence in cast(list[dict[str, object]], item["evidence"]):
            path = repo / str(evidence["path"])
            lines = path.read_text(encoding="utf-8").splitlines()
            assert (
                1
                <= cast(int, evidence["start_line"])
                <= cast(int, evidence["end_line"])
                <= len(lines)
            )
    assert git(repo, "status", "--porcelain") == ""
    assert tree_digest(repo) == before
    return body


def test_real_job_end_to_end_claude(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = os.environ.get("KNOBRIDGE_RUNNER_REAL_CLAUDE_MODEL", "haiku")
    body = _run_job("claude_code", model, tmp_path, capsys)
    cost = cast(dict[str, object], body["metrics"])["cost_usd"]
    assert isinstance(cost, float)
    assert cost <= BUDGET_USD + 0.05


def test_real_job_end_to_end_codex(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = os.environ.get("KNOBRIDGE_RUNNER_REAL_CODEX_MODEL") or None
    _run_job("codex", model, tmp_path, capsys)
