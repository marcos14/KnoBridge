from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
import pytest

from job_support import (
    AGENT_OUTPUT,
    MESSAGE,
    SECRET,
    Gate,
    make_processor,
    recorded_calls,
    runner_config,
    synthetic_repo,
)
from knobridge_runner.excerpt import REDACTED
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness import (
    CancelToken,
    ExecutorLimits,
    ExecutorResult,
    HarnessTask,
)
from knobridge_runner.harness.events import ToolCallHook
from knobridge_runner.job import HarnessJobProcessor
from knobridge_runner.loop import Runner
from knobridge_runner.processor import JobContext, JobDeferred, JobFailed, JobOutcome, JobSucceeded
from knobridge_runner.protocol import RunnerJobOut
from knobridge_runner.reporter import GitSourceReporter
from layer0_support import git, local_runner
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
)

HEARTBEAT = f"/jobs/{JOB_ID}/heartbeat"
RESULT = f"/jobs/{JOB_ID}/result"
REPORT = f"/sources/{SOURCE_ID}/report"
JOB_BEAT_SECONDS = 15
RUNNING = {"status": "running", "lease_expires_at": None, "cancel_requested": False}
CANCELLED = {"status": "cancelled", "lease_expires_at": None, "cancel_requested": True}
RESULT_OUT = {
    "job_id": JOB_ID,
    "status": "succeeded",
    "items_accepted": 3,
    "items_preserved": 0,
    "items_rejected": 2,
    "sync_run_id": None,
}
REPORT_OUT: dict[str, object] = {
    "source_id": SOURCE_ID,
    "head_commit": "b" * 40,
    "modules_total": 2,
    "modules_upserted": 2,
    "jobs_enqueued": [],
}
SOURCE = {
    "source_id": SOURCE_ID,
    "name": "ERP",
    "repository": "erp",
    "last_reported_commit": None,
}


def billing_job(last_commit: str | None = None, **overrides: object) -> dict[str, object]:
    module = {
        "key": "src-billing",
        "title": "src/billing",
        "paths": ["src/billing/**"],
        "last_commit": last_commit,
    }
    body = job_out(module=module, heartbeat_interval_seconds=JOB_BEAT_SECONDS)
    body.update(overrides)
    return body


@dataclass
class GatedSleep:
    """The first job heartbeat waits for the agent's first tool call; every other wait (runner
    heartbeat, later job heartbeats) lasts until the test ends. No real time passes."""

    gate: Gate
    done: asyncio.Event
    beats: int = 0

    async def __call__(self, seconds: float) -> None:
        if seconds == JOB_BEAT_SECONDS and self.beats == 0:
            self.beats += 1
            await asyncio.to_thread(self.gate.started.wait, 60)
            return
        await self.done.wait()


def test_job_end_to_end_with_fake_claude(tmp_path: Path) -> None:
    repo = synthetic_repo(tmp_path)
    config = runner_config(tmp_path, repo.path)
    gate = Gate(release=threading.Event())
    processor = make_processor(tmp_path, config, gate=gate)
    job = billing_job(last_commit=repo.first)

    def beat(request: httpx.Request) -> httpx.Response:
        assert gate.release is not None
        gate.release.set()
        return json_response(200, RUNNING)

    def result(request: httpx.Request) -> httpx.Response:
        runner.request_stop()
        done.set()
        return json_response(200, RESULT_OUT)

    server = (
        FakeServer()
        .on("/heartbeat", json_response(200, heartbeat_out(sources=[SOURCE])))
        .on(REPORT, json_response(200, REPORT_OUT))
        .on("/jobs/claim", json_response(200, job), json_response(204))
        .on(HEARTBEAT, beat)
        .on(RESULT, result)
    )
    done = asyncio.Event()
    client = make_client(server)
    runner = Runner(
        client,
        FakeStatus(),
        processor,
        concurrency=1,
        sleep=GatedSleep(gate, done),
        clock=FakeClock(),
        platform="linux",
        reporter=GitSourceReporter(client, config, local_runner()),
    )

    assert asyncio.run(runner.run()) == 0

    # The heartbeat loop wakes up at the end and beats once more before it sees the stop.
    assert server.paths()[:5] == ["/heartbeat", REPORT, "/jobs/claim", HEARTBEAT, RESULT]
    assert set(server.paths()[5:]) <= {"/heartbeat"}
    report = server.bodies(REPORT)[0]
    assert (report["repository"], report["head_commit"], report["changed_paths"]) == (
        "erp",
        repo.head,
        None,
    )
    beat_body = server.bodies(HEARTBEAT)[0]
    assert (beat_body["phase"], beat_body["tool_calls"]) == ("executing", 1)
    body = server.bodies(RESULT)[0]
    assert body["commit_sha"] == repo.head
    assert body["changed_paths"] == ["src/billing/.env", "src/billing/rules.py"]
    assert body["executor"] == {
        "name": "claude_code",
        "version": "claude_code 9.9.9",
        "model": "fake-claude",
        "session_id": "fake-session-1",
    }
    metrics = cast(dict[str, object], body["metrics"])
    assert metrics == {
        "duration_ms": metrics["duration_ms"],
        "cost_usd": 0.02,
        "input_tokens": 60,
        "cached_input_tokens": 30,
        "output_tokens": 40,
        "num_turns": 3,
        "tool_calls": 1,
        "rescued": False,
        "sources_valid": 5,
        "sources_invalid": 2,
        "items_truncated": 0,
        # The rule text, the excerpt of line 6 and the flow excerpt (lines 3-7).
        "redactions": 3,
    }
    items = cast(list[dict[str, object]], body["items"])
    assert [(item["kind"], item["title"]) for item in items] == [
        ("rule", "Total precisa ser positivo"),
        ("rule", "Chave fixa no código"),
        ("module", "src/billing"),
    ]
    first_rule = cast(list[dict[str, object]], items[0]["evidence"])
    assert first_rule == [
        {
            "path": "src/billing/rules.py",
            "start_line": 3,
            "end_line": 5,
            "symbol": "validate_total",
            "excerpt": (
                "def validate_total(total):\n    if total <= 0:\n"
                f'        raise ValueError("{MESSAGE}")'
            ),
            "excerpt_truncated": False,
            "excerpt_omitted": None,
            "redacted": False,
        }
    ]
    secret_rule = items[1]
    assert SECRET not in json.dumps(body)
    assert (
        cast(dict[str, object], secret_rule["content"])["enunciado"] == f"Usa a chave {REDACTED}."
    )
    secret_evidence = cast(list[dict[str, object]], secret_rule["evidence"])[0]
    assert (secret_evidence["excerpt"], secret_evidence["redacted"]) == (
        f'    api_key = "{REDACTED}"',
        True,
    )
    module_evidence = cast(list[dict[str, object]], items[2]["evidence"])
    env = next(e for e in module_evidence if e["path"] == "src/billing/.env")
    assert (env["excerpt"], env["excerpt_omitted"]) == (None, "sensitive_file")
    rejections = cast(list[dict[str, object]], body["rejections"])
    assert [(r["block"], r["code"], r["label"]) for r in rejections] == [
        ("regras", "outside_checkout", "Regra inventada")
    ]

    (call,) = recorded_calls(tmp_path)
    argv = cast(list[str], call["argv"])
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert call["leaked_env"] == []
    assert Path(cast(str, call["cwd"])).resolve() == repo.path.resolve()
    prompt = cast(str, call["stdin"])
    assert "MÓDULO: src/billing (chave src-billing)" in prompt
    assert "src/billing/rules.py (7 linhas)" in prompt
    assert git(repo.path, "status", "--porcelain") == ""
    assert not (config.state_dir / "work" / JOB_ID).exists()


def test_job_cancelled_mid_run(tmp_path: Path) -> None:
    repo = synthetic_repo(tmp_path)
    config = runner_config(tmp_path, repo.path)
    gate = Gate()
    processor = make_processor(tmp_path, config, "hang", gate=gate)
    server = FakeServer().on(HEARTBEAT, json_response(200, CANCELLED))

    async def scenario() -> None:
        done = asyncio.Event()
        client = make_client(server)
        runner = Runner(
            client,
            FakeStatus(),
            processor,
            concurrency=1,
            sleep=GatedSleep(gate, done),
            clock=FakeClock(),
            platform="linux",
        )
        await runner.run_job(processor, RunnerJobOut.model_validate(billing_job()))
        await client.aclose()

    asyncio.run(scenario())

    assert server.paths() == [HEARTBEAT]
    log = next((config.state_dir / "logs" / "harness").glob("*.jsonl"))
    lines = log.read_text(encoding="utf-8").splitlines()
    markers = [json.loads(line) for line in lines if line.startswith('{"knobridge"')]
    end = [m for m in markers if m.get("knobridge") == "end"][-1]
    assert end["killed"] == "cancelled"
    assert not (config.state_dir / "work" / JOB_ID).exists()


def run_process(processor: HarnessJobProcessor, **job: object) -> JobOutcome:
    body = billing_job()
    body.update(job)
    context = JobContext(job=RunnerJobOut.model_validate(body), clock=FakeClock())
    return asyncio.run(processor.process(context))


def test_processor_runs_codex_with_estimated_cost(tmp_path: Path) -> None:
    repo = synthetic_repo(tmp_path)
    price = {"input": 1.0, "cached_input": 0.5, "output": 10.0}
    config = runner_config(tmp_path, repo.path, pricing={"codex": {"gpt-test": price}})
    old_log = config.state_dir / "logs" / "harness" / "20200101-000000-job-old-codex.jsonl"
    old_log.parent.mkdir(parents=True)
    old_log.write_text("{}\n", encoding="utf-8")
    processor = make_processor(tmp_path, config)

    outcome = run_process(processor, executor="codex", model="gpt-test", excerpt_max_lines=0)

    assert isinstance(outcome, JobSucceeded)
    result = outcome.result
    assert result.executor.model == "gpt-test"
    assert result.executor.session_id == "fake-thread-1"
    # (100 - 40) x 1.0 + 40 x 0.5 + 20 x 10.0 per million tokens.
    assert result.metrics.cost_usd == pytest.approx(0.00028)
    assert result.changed_paths is None
    assert all(e.excerpt_omitted == "disabled" for item in result.items for e in item.evidence)
    assert not old_log.exists()


def test_processor_fails_when_repository_is_not_configured(tmp_path: Path) -> None:
    repo = synthetic_repo(tmp_path)
    processor = make_processor(tmp_path, runner_config(tmp_path, repo.path))

    outcome = run_process(processor, repository="other")

    assert outcome == JobFailed(
        "repository_unavailable", True, "repository checkout unavailable or not a git repository"
    )


def test_processor_fails_when_checkout_is_not_a_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    processor = make_processor(tmp_path, runner_config(tmp_path, plain))

    outcome = run_process(processor)

    assert isinstance(outcome, JobFailed)
    assert (outcome.code, outcome.retryable) == ("repository_unavailable", True)


def test_processor_fails_when_executor_is_missing(tmp_path: Path) -> None:
    repo = synthetic_repo(tmp_path)
    config = runner_config(tmp_path, repo.path, executors={})
    processor = make_processor(tmp_path, config)
    processor.which = lambda _name: None

    outcome = run_process(processor)

    assert outcome == JobFailed("executor_not_found", False, "executor executable not found")


@dataclass
class CannedExecutor:
    result: ExecutorResult
    name: ExecutorName = "claude_code"

    def run(
        self,
        task: HarnessTask,
        checkout: Path,
        limits: ExecutorLimits,
        *,
        work_dir: Path,
        log_label: str,
        cancel: CancelToken | None = None,
        on_tool_call: ToolCallHook | None = None,
    ) -> ExecutorResult:
        return self.result


def canned(tmp_path: Path, **fields: object) -> HarnessJobProcessor:
    repo = synthetic_repo(tmp_path)
    processor = make_processor(tmp_path, runner_config(tmp_path, repo.path))
    result = ExecutorResult("claude_code", None, "0" * 16, tmp_path / "log.jsonl", cost_usd=0.3)
    for key, value in fields.items():
        setattr(result, key, value)
    processor.executor_factory = lambda name, setup, prices: CannedExecutor(result)
    return processor


@pytest.mark.parametrize(
    ("fail_code", "retryable", "message"),
    [
        ("timeout", False, "executor timed out after 1200 s"),
        ("budget_exceeded", False, "executor stopped at the budget of US$ 5.00"),
        ("no_structured_output", False, "executor finished without structured output (rescue: no)"),
        ("invalid_output", False, "executor output does not match schema_version 1 (rescue: no)"),
        (
            "unsafe_tool_use",
            False,
            "executor tried a tool outside the read-only set; process tree killed",
        ),
        ("executor_error", True, "executor finished with an unclassified error"),
        ("interrupted", True, "executor cancelled"),
        (None, True, "executor finished with an unclassified error"),
    ],
)
def test_processor_maps_executor_failures(
    tmp_path: Path, fail_code: str | None, retryable: bool, message: str
) -> None:
    outcome = run_process(canned(tmp_path, fail_code=fail_code))

    assert isinstance(outcome, JobFailed)
    assert (outcome.retryable, outcome.message) == (retryable, message)
    assert outcome.code == (fail_code or "executor_error")
    assert outcome.metrics is not None
    assert outcome.metrics.cost_usd == 0.3


def test_processor_reports_rescue_in_failure_message(tmp_path: Path) -> None:
    outcome = run_process(canned(tmp_path, fail_code="invalid_output", rescued=True))

    assert isinstance(outcome, JobFailed)
    assert outcome.message.endswith("(rescue: yes)")


@pytest.mark.parametrize(
    ("reason", "retry_after", "message"),
    [
        ("quota_exhausted", 900, "executor usage limit reached"),
        ("auth_failed", None, "executor not logged in"),
    ],
)
def test_processor_defers_on_quota_and_login(
    tmp_path: Path, reason: str, retry_after: int | None, message: str
) -> None:
    processor = canned(tmp_path, defer_reason=reason, retry_after_seconds=retry_after)

    outcome = run_process(processor)

    assert isinstance(outcome, JobDeferred)
    assert (outcome.reason, outcome.retry_after_seconds, outcome.message) == (
        reason,
        retry_after,
        message,
    )


def test_processor_drops_model_names_the_protocol_refuses(tmp_path: Path) -> None:
    processor = canned(tmp_path, output=AGENT_OUTPUT, model="bad model!", session_id="s" * 150)

    outcome = run_process(processor)

    assert isinstance(outcome, JobSucceeded)
    assert outcome.result.executor.model is None
    assert outcome.result.executor.session_id == "s" * 100


def test_processor_reports_the_model_without_its_context_variant(tmp_path: Path) -> None:
    # Claude Code names the 1M-context variant of its default model "claude-opus-5-5[1m]".
    processor = canned(tmp_path, output=AGENT_OUTPUT, model="claude-opus-5-5[1m]")

    outcome = run_process(processor)

    assert isinstance(outcome, JobSucceeded)
    assert outcome.result.executor.model == "claude-opus-5-5"
