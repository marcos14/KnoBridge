"""The executor subprocess: line reading, timeout with tree kill, tripwire, cancel, stderr tail."""

from __future__ import annotations

import io
import os
import queue
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from harness_support import fake_command
from knobridge_runner.harness import process as process_module
from knobridge_runner.harness.process import (
    STDERR_TAIL_BYTES,
    CancelToken,
    ProcessSpec,
    kill_tree,
    popen_group_options,
    run_process,
)
from knobridge_runner.loop import current_platform

PLATFORM = current_platform()
SLEEPER = [sys.executable, "-c", "import time; time.sleep(3600)"]


def _spec(tmp_path: Path, argv: list[str], timeout: float = 60.0, **env: str) -> ProcessSpec:
    return ProcessSpec(
        argv=argv,
        cwd=tmp_path,
        env={**os.environ, **env},
        stdin_text="prompt\n",
        timeout_seconds=timeout,
        platform=PLATFORM,
    )


def _never(line: str) -> bool:
    del line
    return False


def test_run_process_reads_lines_and_exit_code(tmp_path: Path) -> None:
    code = "import sys; print(sys.stdin.read().strip()); print('b'); sys.exit(4)"
    lines: list[str] = []

    outcome = run_process(
        _spec(tmp_path, [sys.executable, "-c", code]),
        lambda line: lines.append(line) is not None,
        time.monotonic,
        CancelToken(PLATFORM),
    )

    assert lines == ["prompt", "b"]
    assert (outcome.returncode, outcome.killed, outcome.drained) == (4, None, True)


def test_timeout_kills_the_whole_tree(tmp_path: Path) -> None:
    # The fake leaves a grandchild holding stdout: EOF (drained) only arrives if it died too.
    spec = _spec(tmp_path, fake_command("claude_code"), timeout=2.0, FAKE_HARNESS_SCENARIO="hang")

    outcome = run_process(spec, _never, time.monotonic, CancelToken(PLATFORM))

    assert outcome.killed == "timeout"
    assert outcome.drained
    assert outcome.returncode is not None


def test_tripwire_kills_on_handler_request(tmp_path: Path) -> None:
    spec = _spec(tmp_path, fake_command("codex"), FAKE_HARNESS_SCENARIO="hang")

    outcome = run_process(
        spec, lambda line: "item.completed" in line, time.monotonic, CancelToken(PLATFORM)
    )

    assert outcome.killed == "tripwire"
    assert outcome.drained


def test_cancel_during_run_stops_the_process(tmp_path: Path) -> None:
    token = CancelToken(PLATFORM)
    spec = _spec(tmp_path, fake_command("claude_code"), FAKE_HARNESS_SCENARIO="hang")

    def cancel_on_first_line(line: str) -> bool:
        del line
        token.cancel()
        return False

    outcome = run_process(spec, cancel_on_first_line, time.monotonic, token)

    assert outcome.killed == "cancelled"
    assert token.cancelled


def test_stderr_keeps_only_the_tail(tmp_path: Path) -> None:
    code = "import sys; sys.stderr.write('x\\n' * 40000 + 'END')"

    outcome = run_process(
        _spec(tmp_path, [sys.executable, "-c", code]), _never, time.monotonic, CancelToken(PLATFORM)
    )

    assert len(outcome.stderr_tail) <= STDERR_TAIL_BYTES
    assert len(outcome.stderr_tail) > STDERR_TAIL_BYTES - 10
    assert outcome.stderr_tail.endswith("END")


def test_missing_executable_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_process(
            _spec(tmp_path, [str(tmp_path / "missing.exe")]),
            _never,
            time.monotonic,
            CancelToken(PLATFORM),
        )


def test_feed_stdin_ignores_a_closed_pipe() -> None:
    class Broken(io.BytesIO):
        def write(self, data: object) -> int:
            raise BrokenPipeError

    process_module.feed_stdin(Broken(), b"prompt")


def test_drain_and_wait_give_up_after_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(process_module, "DRAIN_SECONDS", 0.05)
    sleeper = subprocess.Popen(SLEEPER)
    try:
        assert process_module.drain_lines(queue.Queue()) is False
        assert process_module.wait_for_exit(sleeper) is None
    finally:
        sleeper.kill()
        sleeper.wait()


def test_popen_group_options_per_platform() -> None:
    assert popen_group_options("linux") == (0, True)
    flags, new_session = popen_group_options("windows")
    assert flags == 0x00000200
    assert new_session is False


def test_kill_tree_on_windows_uses_taskkill() -> None:
    sleeper = subprocess.Popen(SLEEPER)
    calls: list[list[str]] = []
    try:
        kill_tree(sleeper, "windows", run=calls.append)
    finally:
        sleeper.kill()
        sleeper.wait()

    assert calls == [["taskkill", "/F", "/T", "/PID", str(sleeper.pid)]]


def test_kill_tree_on_posix_sends_term_then_kill_to_the_group() -> None:
    sleeper = subprocess.Popen(SLEEPER)
    sent: list[tuple[int, int]] = []

    def killpg(pid: int, sig: int) -> None:
        sent.append((pid, sig))
        sleeper.kill()

    kill_tree(sleeper, "linux", killpg=killpg)
    sleeper.wait()

    sigkill = int(getattr(signal, "SIGKILL", signal.SIGTERM))
    assert sent == [(sleeper.pid, int(signal.SIGTERM)), (sleeper.pid, sigkill)]


def test_kill_tree_on_posix_ignores_a_vanished_group() -> None:
    sleeper = subprocess.Popen(SLEEPER)

    def killpg(pid: int, sig: int) -> None:
        raise ProcessLookupError(pid, sig)

    try:
        kill_tree(sleeper, "linux", killpg=killpg)
    finally:
        sleeper.kill()
        sleeper.wait()


def test_cancel_token_kills_the_attached_process() -> None:
    token = CancelToken(PLATFORM)
    flags, new_session = popen_group_options(PLATFORM)
    sleeper = subprocess.Popen(SLEEPER, creationflags=flags, start_new_session=new_session)
    token.attach(sleeper)

    token.cancel()

    assert sleeper.wait(timeout=30) is not None
    token.attach(None)
