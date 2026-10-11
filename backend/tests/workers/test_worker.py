from __future__ import annotations

import asyncio
import io
import json
from typing import Any, cast

import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment

from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings
from knobridge.workers import worker as worker_module
from knobridge.workers.health import HealthWorkflow, ping
from knobridge.workers.ingestion import IngestionWorkflow
from knobridge.workers.worker import build_worker, connect, main, run

# Stand-in for a real client: the fakes below never touch it.
FAKE_CLIENT = cast(Client, object())


class FakeWorker:
    def __init__(self) -> None:
        self.ran = False

    async def run(self) -> None:
        self.ran = True


def _settings() -> Settings:
    return Settings(
        env="test",
        temporal_address="temporal.test:7233",
        temporal_namespace="ns-test",
        temporal_task_queue="queue-test",
    )


@pytest.mark.integration
def test_build_worker_registers_workflows_and_activities() -> None:
    settings = _settings()

    async def build() -> dict[str, Any]:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            return dict(build_worker(env.client, settings).config())

    config = asyncio.run(build())

    assert config["task_queue"] == "queue-test"
    assert list(config["workflows"]) == [HealthWorkflow, IngestionWorkflow]
    activities = list(config["activities"])
    assert activities[0] is ping
    assert [activity.__name__ for activity in activities[1:]] == [
        "open_run",
        "list_changes",
        "process_batch",
        "finish_run",
    ]


def test_connect_uses_address_and_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_connect(target_host: str, *, namespace: str) -> Client:
        calls.append((target_host, namespace))
        return FAKE_CLIENT

    monkeypatch.setattr(Client, "connect", fake_connect)

    client = asyncio.run(connect(_settings()))

    assert (client, calls) == (FAKE_CLIENT, [("temporal.test:7233", "ns-test")])


def test_run_connects_builds_and_runs_worker() -> None:
    settings = _settings()
    fake_worker = FakeWorker()
    built_with: list[tuple[Client, Settings]] = []

    async def fake_connect(received: Settings) -> Client:
        assert received is settings
        return FAKE_CLIENT

    def fake_factory(client: Client, received: Settings) -> FakeWorker:
        built_with.append((client, received))
        return fake_worker

    asyncio.run(run(settings, connect_client=fake_connect, worker_factory=fake_factory))

    assert (fake_worker.ran, built_with) == (True, [(FAKE_CLIENT, settings)])


def test_run_defaults_to_process_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_TEMPORAL_TASK_QUEUE", "from-env")
    seen: list[str] = []

    async def fake_connect(received: Settings) -> Client:
        seen.append(received.temporal_task_queue)
        return FAKE_CLIENT

    asyncio.run(run(connect_client=fake_connect, worker_factory=lambda _c, _s: FakeWorker()))

    assert seen == ["from-env"]


def test_run_logs_worker_started() -> None:
    stream = io.StringIO()
    configure_logging(_settings(), stream=stream)

    async def fake_connect(_: Settings) -> Client:
        return FAKE_CLIENT

    asyncio.run(
        run(_settings(), connect_client=fake_connect, worker_factory=lambda _c, _s: FakeWorker())
    )

    record = json.loads(stream.getvalue().splitlines()[-1])
    assert (record["event"], record["task_queue"]) == ("worker_started", "queue-test")


def test_main_configures_logging_and_runs_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOBRIDGE_LOG_LEVEL", "WARNING")
    received: list[Settings | None] = []
    configured: list[str] = []

    async def fake_run(settings: Settings | None = None) -> None:
        received.append(settings)

    def fake_configure(settings: Settings) -> None:
        configured.append(settings.log_level)

    monkeypatch.setattr(worker_module, "run", fake_run)
    monkeypatch.setattr(worker_module, "configure_logging", fake_configure)

    main([])

    assert configured == ["WARNING"]
    assert len(received) == 1
    assert received[0] is not None
    assert received[0].log_level == "WARNING"


def test_main_help_exits_without_running(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fail_run(settings: Settings | None = None) -> None:
        raise AssertionError("worker must not start on --help")

    monkeypatch.setattr(worker_module, "run", fail_run)

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    assert exc_info.value.code == 0
    assert "knobridge-worker" in capsys.readouterr().out
