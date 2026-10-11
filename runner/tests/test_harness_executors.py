"""Executors against the fake claude/codex CLIs of tests/fakes (no model, no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness_support import TASK, FakeRun
from knobridge_runner.config import ModelPrice
from knobridge_runner.formats import Executor as ExecutorName
from knobridge_runner.harness import (
    CancelToken,
    ClaudeCodeExecutor,
    CodexExecutor,
    ExecutorLimits,
    ExecutorSetup,
    build_prompt,
    make_executor,
)
from knobridge_runner.harness.prompt import RESCUE_PROMPT, schema_json
from knobridge_runner.loop import current_platform

BOTH: list[ExecutorName] = ["claude_code", "codex"]


@pytest.fixture
def fake(tmp_path: Path) -> FakeRun:
    return FakeRun(tmp_path)


def test_claude_args_are_read_only(fake: FakeRun) -> None:
    result = fake.run("claude_code", "success", budget_usd=1.0, model="haiku")

    argv = fake.argv()
    assert result.ok
    assert argv[argv.index("--tools") + 1] == "Read,Grep,Glob"
    assert argv[argv.index("--disallowedTools") + 1] == "Edit,Write,Bash"
    assert argv[argv.index("--setting-sources") + 1] == "user"
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "1.00"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert argv[argv.index("--json-schema") + 1] == schema_json()
    assert argv[argv.index("--model") + 1] == "haiku"
    assert "-p" in argv
    assert "--resume" not in argv
    assert not any("dangerous" in arg or "bypass" in arg for arg in argv)


def test_executor_runs_in_checkout_without_runner_variables(fake: FakeRun) -> None:
    fake.run("claude_code", "success")

    call = fake.calls()[0]
    assert Path(str(call["cwd"])).resolve() == fake.checkout.resolve()
    assert call["leaked_env"] == []
    assert call["stdin"] == build_prompt(TASK)
    assert build_prompt(TASK) not in fake.argv()


def test_codex_args_are_read_only_sandbox(fake: FakeRun) -> None:
    result = fake.run("codex", "success", model="gpt-test")

    argv = fake.argv()
    assert result.ok
    assert argv[0:3] == ["exec", "--json", "--output-schema"]
    assert argv[argv.index("--sandbox") + 1] == "read-only"
    assert Path(argv[argv.index("-C") + 1]) == fake.checkout.resolve()
    assert argv[argv.index("-c") + 1] == "mcp_servers={}"
    assert argv[argv.index("-m") + 1] == "gpt-test"
    assert argv[-1] == "-"
    assert not any("dangerous" in arg or "full-access" in arg for arg in argv)
    schema_file = Path(argv[argv.index("--output-schema") + 1])
    assert not schema_file.resolve().is_relative_to(fake.checkout.resolve())


def test_prompt_and_schema_identical_for_both_executors(fake: FakeRun) -> None:
    fake.run("claude_code", "success")
    fake.run("codex", "success")

    claude_call, codex_call = fake.calls()
    assert claude_call["stdin"] == codex_call["stdin"] == build_prompt(TASK)
    assert claude_call["schema"] == codex_call["schema"] == schema_json()


@pytest.mark.parametrize("name", BOTH)
def test_success_returns_output_and_metrics(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "success")

    assert result.ok
    assert result.fail_code is None
    assert result.defer_reason is None
    assert result.output is not None
    assert result.output["schema_version"] == 1
    assert result.tool_calls == 1
    assert result.session_id == ("fake-session-1" if name == "claude_code" else "fake-thread-1")
    assert not result.rescued
    assert len(result.prompt_hash) == 16
    assert result.log_path.is_file()
    assert result.metrics().tool_calls == 1


def test_claude_metrics_follow_the_spec(fake: FakeRun) -> None:
    result = fake.run("claude_code", "success")

    assert (result.cost_usd, result.num_turns, result.model) == (0.02, 3, "fake-claude")
    assert (result.input_tokens, result.cached_input_tokens, result.output_tokens) == (60, 30, 40)


def test_codex_cost_estimated_from_configured_price(fake: FakeRun) -> None:
    price = ModelPrice(input=1.0, cached_input=0.5, output=10.0)

    result = fake.run("codex", "success", model="gpt-test", prices={"gpt-test": price})

    assert (result.input_tokens, result.cached_input_tokens, result.output_tokens) == (100, 40, 20)
    assert result.cost_usd == pytest.approx((60 * 1.0 + 40 * 0.5 + 20 * 10.0) / 1_000_000)
    assert result.model == "gpt-test"


def test_codex_cost_is_null_without_price(fake: FakeRun) -> None:
    result = fake.run("codex", "success")

    assert result.cost_usd is None
    assert result.num_turns == 1


def test_codex_output_falls_back_to_last_agent_message(fake: FakeRun) -> None:
    result = fake.run("codex", "success_stdout_only")

    assert result.ok


@pytest.mark.parametrize("name", BOTH)
def test_missing_json_triggers_resume_once(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "no_json_then_rescue")

    assert result.ok
    assert result.rescued
    calls = fake.calls()
    assert len(calls) == 2
    assert calls[1]["stdin"] == RESCUE_PROMPT
    rescue = fake.argv(1)
    if name == "claude_code":
        assert rescue[rescue.index("--resume") + 1] == "fake-session-1"
        assert rescue[rescue.index("--max-budget-usd") + 1] == "0.98"
        assert rescue[rescue.index("--tools") + 1] == "Read,Grep,Glob"
        assert result.cost_usd == pytest.approx(0.04)
    else:
        assert rescue[0:2] == ["exec", "resume"]
        assert rescue[-2:] == ["fake-thread-1", "-"]
        assert 'sandbox_mode="read-only"' in rescue
        assert "mcp_servers={}" in rescue
        assert "--sandbox" not in rescue
        assert "-C" not in rescue


@pytest.mark.parametrize("name", BOTH)
def test_missing_json_after_rescue_fails(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "no_json")

    assert result.fail_code == "no_structured_output"
    assert result.rescued
    assert len(fake.calls()) == 2


@pytest.mark.parametrize("name", BOTH)
def test_off_schema_json_after_rescue_fails_invalid_output(
    fake: FakeRun, name: ExecutorName
) -> None:
    result = fake.run(name, "invalid_json")

    assert result.fail_code == "invalid_output"
    assert result.output is None
    assert len(fake.calls()) == 2


def test_rescue_skipped_when_budget_left_is_too_small(fake: FakeRun) -> None:
    result = fake.run("claude_code", "no_json_then_rescue", budget_usd=0.06)

    assert result.fail_code == "no_structured_output"
    assert not result.rescued
    assert len(fake.calls()) == 1


def test_rescue_skipped_without_session(fake: FakeRun) -> None:
    result = fake.run("claude_code", "no_json_no_session")

    assert result.fail_code == "no_structured_output"
    assert result.session_id is None
    assert len(fake.calls()) == 1


@pytest.mark.parametrize("name", BOTH)
def test_auth_failure_reported(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "auth")

    assert result.defer_reason == "auth_failed"
    assert result.retry_after_seconds is None
    assert result.fail_code is None
    assert not result.ok
    assert len(fake.calls()) == 1


@pytest.mark.parametrize("name", BOTH)
def test_quota_limit_defers_with_reset_time(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "quota")

    # 20:00 -03 now, reset at 21:20 -03, plus 60 s of slack.
    assert result.defer_reason == "quota_exhausted"
    assert result.retry_after_seconds == 80 * 60 + 60


@pytest.mark.parametrize("name", BOTH)
def test_other_errors_are_executor_error(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "crash")

    assert result.fail_code == "executor_error"
    assert result.defer_reason is None


def test_budget_exceeded_fails_without_rescue(fake: FakeRun) -> None:
    result = fake.run("claude_code", "budget")

    assert result.fail_code == "budget_exceeded"
    assert len(fake.calls()) == 1


@pytest.mark.parametrize("name", BOTH)
def test_unsafe_tool_kills_the_process(fake: FakeRun, name: ExecutorName) -> None:
    result = fake.run(name, "unsafe_tool", timeout_seconds=60.0)

    assert result.fail_code == "unsafe_tool_use"
    assert result.duration_ms < 30_000


def test_timeout_kills_process_tree(fake: FakeRun) -> None:
    # The fake hangs with a grandchild holding stdout: run_process only returns once the whole
    # tree is gone (the tree check itself is in test_harness_process.py).
    result = fake.run("claude_code", "hang", timeout_seconds=2.0)

    assert result.fail_code == "timeout"
    assert not result.rescued
    assert result.duration_ms < 15_000


def test_cancel_interrupts_the_run(fake: FakeRun) -> None:
    token = CancelToken(current_platform())
    token.cancel()

    result = fake.run("claude_code", "hang", cancel=token)

    assert result.fail_code == "interrupted"


def test_missing_executable_reports_not_found(fake: FakeRun, tmp_path: Path) -> None:
    result = fake.run("codex", "success", command=[str(tmp_path / "no-such-codex.exe")])

    assert result.fail_code == "executor_not_found"


def test_work_dir_inside_checkout_is_refused(fake: FakeRun) -> None:
    fake.checkout.mkdir()
    executor = make_executor("claude_code", fake.setup("claude_code", "success"))

    with pytest.raises(ValueError, match="outside the checkout"):
        executor.run(
            TASK,
            fake.checkout,
            ExecutorLimits(budget_usd=1.0, timeout_seconds=60.0),
            work_dir=fake.checkout / "tmp",
            log_label="job-1",
        )


def test_log_keeps_events_and_markers(fake: FakeRun) -> None:
    result = fake.run("claude_code", "no_json_then_rescue")

    lines = result.log_path.read_text(encoding="utf-8").splitlines()
    markers = [json.loads(line) for line in lines if line.startswith('{"knobridge"')]
    assert [m["stage"] for m in markers] == ["initial", "initial", "rescue", "rescue"]
    assert all(m.get("prompt_hash") == result.prompt_hash for m in markers[::2])
    assert result.log_path.name.endswith("-job-1-claude_code.jsonl")


def test_tool_call_hook_is_called(fake: FakeRun) -> None:
    fake.checkout.mkdir()
    seen: list[int] = []
    executor = make_executor("codex", fake.setup("codex", "success"))

    executor.run(
        TASK,
        fake.checkout,
        ExecutorLimits(budget_usd=1.0, timeout_seconds=60.0),
        work_dir=fake.tmp_path / "work",
        log_label="job-1",
        on_tool_call=lambda: seen.append(1),
    )

    assert seen == [1]


def test_make_executor_picks_the_class(fake: FakeRun) -> None:
    assert isinstance(
        make_executor("claude_code", fake.setup("claude_code", "x")), ClaudeCodeExecutor
    )
    assert isinstance(make_executor("codex", fake.setup("codex", "x")), CodexExecutor)


def test_setup_default_clock_is_local_aware_time(fake: FakeRun) -> None:
    setup = ExecutorSetup(
        command=["x"], log_dir=fake.tmp_path, environment={}, platform=current_platform()
    )

    assert setup.now().tzinfo is not None
