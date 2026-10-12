"""Shared fakes of the runner tests: server (httpx.MockTransport), clock, sleep and commands."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import httpx

from knobridge_runner.backoff import Backoff
from knobridge_runner.client import RunnerClient
from knobridge_runner.commands import CommandResult
from knobridge_runner.config import RunnerConfig
from knobridge_runner.formats import Executor
from knobridge_runner.protocol import RunnerExecutorInfo, RunnerRepositoryInfo

TOKEN = "kbr_abcd1234_" + "A" * 43
SERVER = "https://knobridge.test"
JOB_ID = "11111111-1111-4111-8111-111111111111"
SOURCE_ID = "22222222-2222-4222-8222-222222222222"
COMMIT = "a" * 40

Handler = Callable[[httpx.Request], httpx.Response]


def json_response(status: int, body: object | None = None) -> httpx.Response:
    if body is None:
        return httpx.Response(status)
    return httpx.Response(status, json=body)


def error_response(status: int, code: str) -> httpx.Response:
    return json_response(status, {"error": {"code": code, "message": code, "details": None}})


def heartbeat_out(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "runner_id": "33333333-3333-4333-8333-333333333333",
        "name": "notebook",
        "workspace_id": "44444444-4444-4444-8444-444444444444",
        "protocol": 1,
        "server_time": "2026-10-11T12:00:00Z",
        "heartbeat_interval_seconds": 30,
        "sources": [],
    }
    body.update(overrides)
    return body


def job_out(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "job_id": JOB_ID,
        "attempt": 1,
        "max_attempts": 3,
        "source_id": SOURCE_ID,
        "repository": "erp",
        "module": {
            "key": "src-billing",
            "title": "src/billing",
            "paths": ["src/billing/"],
            "last_commit": None,
        },
        "executor": "claude_code",
        "model": None,
        "budget_usd": 5.0,
        "timeout_seconds": 1200,
        "excerpt_max_lines": 30,
        "include_globs": [],
        "exclude_globs": [],
        "commit_sha": COMMIT,
        "trigger": "manual",
        "schema_version": 1,
        "lease_seconds": 120,
        "heartbeat_interval_seconds": 30,
    }
    body.update(overrides)
    return body


def state_out(status: str = "queued") -> dict[str, object]:
    return {"job_id": JOB_ID, "status": status, "attempts": 1, "not_before": None}


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: httpx.Headers
    body: dict[str, object] | None


@dataclass
class FakeServer:
    """Answers each path from a queue of responses (the last one repeats) or a handler."""

    routes: dict[str, deque[httpx.Response | Handler]] = field(
        default_factory=dict[str, deque[httpx.Response | Handler]]
    )
    requests: list[RecordedRequest] = field(default_factory=list[RecordedRequest])

    def on(self, path: str, *responses: httpx.Response | Handler) -> FakeServer:
        self.routes[path] = deque(responses)
        return self

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1/runner")
        raw = request.content
        body = cast(dict[str, object], json.loads(raw)) if raw else None
        self.requests.append(RecordedRequest(request.method, path, request.headers, body))
        queue = self.routes.get(path)
        if not queue:
            return error_response(404, "no_route")
        answer = queue.popleft() if len(queue) > 1 else queue[0]
        return answer(request) if callable(answer) else answer

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def paths(self) -> list[str]:
        return [request.path for request in self.requests]

    def bodies(self, path: str) -> list[dict[str, object]]:
        return [r.body for r in self.requests if r.path == path and r.body is not None]


@dataclass
class FakeClock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class FakeSleep:
    """Records the delays, advances the clock and yields to the event loop (no real wait)."""

    clock: FakeClock = field(default_factory=FakeClock)
    delays: list[float] = field(default_factory=list[float])
    on_sleep: Callable[[int], None] | None = None

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.clock.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(len(self.delays))
        await asyncio.sleep(0)


def make_client(server: FakeServer, sleep: FakeSleep | None = None) -> RunnerClient:
    fake_sleep = sleep or FakeSleep()
    return RunnerClient(
        SERVER,
        TOKEN,
        transport=server.transport(),
        sleep=fake_sleep,
        clock=fake_sleep.clock,
        backoff=Backoff(jitter=0.0),
    )


@dataclass
class FakeCommandRunner:
    """Maps a command prefix (tuple of arguments) to a result; unknown commands give 127."""

    results: dict[tuple[str, ...], CommandResult] = field(
        default_factory=dict[tuple[str, ...], CommandResult]
    )
    calls: list[list[str]] = field(default_factory=list[list[str]])

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
        self.calls.append(list(argv))
        for prefix, result in sorted(self.results.items(), key=lambda item: -len(item[0])):
            if tuple(argv[: len(prefix)]) == prefix:
                return result
        return CommandResult(returncode=127, stdout="")


@dataclass
class FakeAuth:
    logged_in: dict[Executor, bool | None] = field(default_factory=dict[Executor, bool | None])

    def check(self, name: Executor, command: list[str]) -> bool | None:
        return self.logged_in.get(name, True)


def make_config(tmp_path: Path, **overrides: object) -> RunnerConfig:
    data: dict[str, object] = {
        "server_url": SERVER,
        "token": TOKEN,
        "state_dir": str(tmp_path / "state"),
    }
    data.update(overrides)
    return RunnerConfig.model_validate(data)


@dataclass
class FakeStatus:
    claimable: list[Executor] = field(default_factory=lambda: list[Executor](["claude_code"]))
    names: list[str] = field(default_factory=lambda: ["erp"])
    unauthenticated: list[Executor] = field(default_factory=list[Executor])

    async def executors(self) -> list[RunnerExecutorInfo]:
        return [RunnerExecutorInfo(name="claude_code", available=True, authenticated=True)]

    async def repositories(self) -> list[RunnerRepositoryInfo]:
        return [RunnerRepositoryInfo(name="erp", head_commit=COMMIT, branch="main", dirty=False)]

    def repository_names(self) -> list[str]:
        return self.names

    def claimable_executors(self) -> list[Executor]:
        return self.claimable

    def mark_unauthenticated(self, name: Executor) -> None:
        self.unauthenticated.append(name)
