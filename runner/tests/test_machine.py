"""Local commands, git queries, executor discovery and the machine status."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from knobridge_runner.commands import CommandResult, SubprocessCommandRunner, child_environment
from knobridge_runner.config import ExecutorConfig
from knobridge_runner.executors import (
    CliAuthChecker,
    probe_executor,
    read_version,
    resolve_command,
)
from knobridge_runner.git import is_git_repository, repository_info
from knobridge_runner.status import MachineStatus
from runner_support import FakeAuth, FakeClock, FakeCommandRunner, make_config

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]


def git(cwd: Path, *args: str) -> None:
    subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def local_runner() -> SubprocessCommandRunner:
    return SubprocessCommandRunner(os.environ)


def test_child_environment_drops_runner_variables() -> None:
    parent = {
        "PATH": "/bin",
        "KNOBRIDGE_RUNNER_TOKEN": "secret",
        "CLAUDECODE": "1",
        "ANTHROPIC_API_KEY": "k",
        "RANDOM": "x",
    }

    assert child_environment(parent) == {"PATH": "/bin", "ANTHROPIC_API_KEY": "k"}


def test_subprocess_runner_captures_stdout_and_exit_code() -> None:
    result = local_runner().run([sys.executable, "-c", "print('hi'); raise SystemExit(3)"])

    assert result == CommandResult(returncode=3, stdout="hi\n")


def test_subprocess_runner_reports_missing_executable() -> None:
    assert local_runner().run(["knobridge-no-such-binary-xyz"]).returncode == 127


def test_subprocess_runner_times_out() -> None:
    runner = SubprocessCommandRunner(os.environ, timeout_seconds=0.01)

    # A child that never ends by itself; the runner kills it at the timeout.
    result = runner.run([sys.executable, "-c", "while True: pass"])

    assert result.returncode == -1


def test_git_repository_info_reports_head_branch_and_dirty(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("changed\n", encoding="utf-8")

    info = repository_info(local_runner(), "erp", repo)

    assert info.head_commit is not None
    assert len(info.head_commit) == 40
    assert info.branch == "main"
    assert info.dirty is True


def test_git_repository_info_detached_and_clean(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    git(repo, "checkout", "-q", "--detach")

    info = repository_info(local_runner(), "erp", repo)

    assert info.branch is None
    assert info.dirty is False


def test_git_repository_info_empty_repository_has_no_head(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")

    assert repository_info(local_runner(), "erp", tmp_path).head_commit is None


def test_git_non_repository_reports_nothing(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    runner = FakeCommandRunner({("git",): CommandResult(128, "")})

    info = repository_info(runner, "erp", plain)

    assert (info.head_commit, info.branch, info.dirty) == (None, None, False)
    assert is_git_repository(runner, tmp_path / "missing") is False


def test_resolve_command_prefers_explicit_command() -> None:
    config = ExecutorConfig(command=["python", "fake.py"])

    assert resolve_command("claude_code", config, "linux", lambda _: None) == ["python", "fake.py"]


def test_resolve_command_uses_exe_on_windows() -> None:
    asked: list[str] = []

    def which(name: str) -> str | None:
        asked.append(name)
        return f"C:/bin/{name}"

    assert resolve_command("codex", ExecutorConfig(), "windows", which) == ["C:/bin/codex.exe"]
    assert resolve_command("claude_code", ExecutorConfig(), "linux", which) == ["C:/bin/claude"]
    assert asked == ["codex.exe", "claude"]


def test_resolve_command_missing_returns_none() -> None:
    assert resolve_command("codex", ExecutorConfig(), "linux", lambda _: None) is None


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (CommandResult(0, '{"loggedIn": true, "email": "x"}'), True),
        (CommandResult(0, '{"loggedIn": false}'), False),
        (CommandResult(0, '{"other": 1}'), True),
        (CommandResult(0, "[1]"), True),
        (CommandResult(0, "Logged in"), True),
        (CommandResult(1, ""), False),
        (CommandResult(127, ""), None),
        (CommandResult(-1, ""), None),
    ],
)
def test_cli_auth_checker_reads_claude_status(result: CommandResult, expected: bool | None) -> None:
    runner = FakeCommandRunner({("claude", "auth", "status", "--json"): result})

    assert CliAuthChecker(runner, {}).check("claude_code", ["claude"]) is expected


def test_cli_auth_checker_uses_codex_login_status() -> None:
    runner = FakeCommandRunner({("codex", "login", "status"): CommandResult(1, "Not logged in")})

    assert CliAuthChecker(runner, {}).check("codex", ["codex"]) is False


def test_cli_auth_checker_accepts_api_key_without_running_cli() -> None:
    runner = FakeCommandRunner()

    assert CliAuthChecker(runner, {"OPENAI_API_KEY": "k"}).check("codex", ["codex"]) is True
    assert runner.calls == []


def test_read_version_takes_first_line() -> None:
    runner = FakeCommandRunner(
        {("claude", "--version"): CommandResult(0, "\n2.1.296 (Claude Code)\nx")}
    )

    assert read_version(runner, ["claude"]) == "2.1.296 (Claude Code)"
    assert read_version(FakeCommandRunner(), ["claude"]) is None
    assert read_version(FakeCommandRunner({("c",): CommandResult(0, "  ")}), ["c"]) is None


def test_probe_executor_reports_missing_cli() -> None:
    info = probe_executor(
        "codex",
        ExecutorConfig(),
        platform="linux",
        runner=FakeCommandRunner(),
        auth=FakeAuth(),
        which=lambda _: None,
    )

    assert (info.available, info.version, info.authenticated) == (False, None, None)


def test_machine_status_caches_executors_for_five_minutes(tmp_path: Path) -> None:
    clock = FakeClock()
    runner = FakeCommandRunner({("/bin/claude", "--version"): CommandResult(0, "2.1")})
    status = MachineStatus(
        config=make_config(tmp_path, executors={"codex": {"enabled": False}}),
        platform="linux",
        runner=runner,
        auth=FakeAuth({"claude_code": False}),
        clock=clock,
        which=lambda name: f"/bin/{name}",
    )

    first = asyncio.run(status.executors())
    clock.now += 299
    asyncio.run(status.executors())
    clock.now += 1
    asyncio.run(status.executors())

    assert [(i.name, i.version, i.authenticated) for i in first] == [("claude_code", "2.1", False)]
    assert runner.calls.count(["/bin/claude", "--version"]) == 2
    assert status.claimable_executors() == []
    assert status.executor_version("claude_code") == "2.1"
    assert status.executor_version("codex") is None


def test_machine_status_claimable_and_mark_unauthenticated(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    status = MachineStatus(
        config=make_config(tmp_path, repositories={"erp": str(repo)}),
        platform="linux",
        runner=local_runner(),
        auth=FakeAuth({"codex": None}),
        clock=FakeClock(),
        which=lambda name: sys.executable if name == "claude" else None,
    )

    asyncio.run(status.executors())
    claimable_before = status.claimable_executors()
    status.mark_unauthenticated("claude_code")
    repositories = asyncio.run(status.repositories())

    assert claimable_before == ["claude_code"]
    assert status.claimable_executors() == []
    assert status.repository_names() == ["erp"]
    assert repositories[0].branch == "main"
