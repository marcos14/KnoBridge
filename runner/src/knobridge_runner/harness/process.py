"""One executor subprocess: prompt on stdin, stdout read line by line, timeout and tree kill.

docs/specs/harness.md, "Timeout, cancelamento e kill": own process group (POSIX new session,
Windows ``CREATE_NEW_PROCESS_GROUP``); on timeout, cancellation or tool tripwire the whole tree is
killed (Windows ``taskkill /F /T``; POSIX ``killpg`` SIGTERM, 10 s, SIGKILL); only the last
64 KiB of stderr are kept.
"""

from __future__ import annotations

import contextlib
import os
import queue
import signal
import subprocess
import threading
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Literal, cast

from knobridge_runner.backoff import Clock

STDERR_TAIL_BYTES = 64 * 1024
POSIX_GRACE_SECONDS = 10.0
# After the tree is killed the pipes close at once; this bound only matters if a kill failed.
DRAIN_SECONDS = 15.0
_WINDOWS_NEW_PROCESS_GROUP = 0x00000200

KillReason = Literal["timeout", "tripwire", "cancelled"]
LineHandler = Callable[[str], bool]
"""Called with each stdout line; returning True kills the tree (tool tripwire)."""
Run = Callable[[list[str]], object]
KillPg = Callable[[int, int], None]


def popen_group_options(platform: str) -> tuple[int, bool]:
    """``(creationflags, start_new_session)`` that put the child in a process group of its own."""
    if platform == "windows":
        flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", _WINDOWS_NEW_PROCESS_GROUP)
        return int(flag), False
    return 0, True


def _run_quiet(argv: list[str]) -> object:
    return subprocess.run(argv, capture_output=True, check=False)  # noqa: S603 - fixed argv


def kill_tree(
    process: subprocess.Popen[bytes],
    platform: str,
    *,
    run: Run = _run_quiet,
    killpg: KillPg | None = None,
) -> None:
    """Kill PROCESS and every descendant, even if the leader already exited; idempotent."""
    if platform == "windows":
        run(["taskkill", "/F", "/T", "/PID", str(process.pid)])
        return
    send: KillPg = killpg or getattr(os, "killpg")  # noqa: B009 - os.killpg is POSIX only
    sigkill = int(getattr(signal, "SIGKILL", signal.SIGTERM))
    try:
        send(process.pid, int(signal.SIGTERM))
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=POSIX_GRACE_SECONDS)
        # Children that ignored SIGTERM (or outlived the leader) still get SIGKILL.
        send(process.pid, sigkill)
    except ProcessLookupError:
        return


@dataclass
class CancelToken:
    """Cancels the running subprocess from another thread (job cancelled, Ctrl+C)."""

    platform: str
    _cancelled: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _process: subprocess.Popen[bytes] | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            process = self._process
        if process is not None:
            kill_tree(process, self.platform)

    def attach(self, process: subprocess.Popen[bytes] | None) -> None:
        with self._lock:
            self._process = process
        if process is not None and self.cancelled:
            kill_tree(process, self.platform)


@dataclass(frozen=True)
class ProcessOutcome:
    returncode: int | None
    stderr_tail: str
    killed: KillReason | None
    # True when stdout reached EOF, i.e. no process of the tree still holds the pipe.
    drained: bool


@dataclass(frozen=True)
class ProcessSpec:
    argv: Sequence[str]
    cwd: Path
    env: Mapping[str, str]
    stdin_text: str
    timeout_seconds: float
    platform: str


def feed_stdin(stream: IO[bytes], data: bytes) -> None:
    try:
        stream.write(data)
        stream.close()
    except OSError:  # the child exited before reading the whole prompt
        return


def _pump_lines(stream: IO[bytes], lines: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            lines.put(line.decode("utf-8", errors="replace").rstrip("\r\n"))
    finally:
        lines.put(None)


def _keep_tail(stream: IO[bytes], tail: deque[bytes]) -> None:
    size = 0
    for chunk in stream:
        tail.append(chunk)
        size += len(chunk)
        while size > STDERR_TAIL_BYTES and len(tail) > 1:
            size -= len(tail.popleft())


def _start(spec: ProcessSpec) -> subprocess.Popen[bytes]:
    creationflags, new_session = popen_group_options(spec.platform)
    return subprocess.Popen(  # noqa: S603 - argument list, no shell
        list(spec.argv),
        cwd=spec.cwd,
        env=dict(spec.env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=creationflags,
        start_new_session=new_session,
    )


def drain_lines(lines: queue.Queue[str | None]) -> bool:
    """Discard the rest of stdout until EOF; False if the pipe stayed open (tree survived)."""
    while True:
        try:
            if lines.get(timeout=DRAIN_SECONDS) is None:
                return True
        except queue.Empty:
            return False


def wait_for_exit(process: subprocess.Popen[bytes]) -> int | None:
    try:
        return process.wait(timeout=DRAIN_SECONDS)
    except subprocess.TimeoutExpired:
        return None


def run_process(
    spec: ProcessSpec, on_line: LineHandler, clock: Clock, cancel: CancelToken
) -> ProcessOutcome:
    """Run SPEC to the end, to the timeout, to the tripwire or to a cancellation.

    Raises OSError (FileNotFoundError, PermissionError) when the executable cannot be started.
    """
    process = _start(spec)
    cancel.attach(process)
    # The three streams are binary pipes (subprocess.PIPE above), never None. Binary on purpose:
    # text mode would turn the prompt's "\n" into "\r\n" on Windows.
    stdin = cast(IO[bytes], process.stdin)
    stdout = cast(IO[bytes], process.stdout)
    stderr = cast(IO[bytes], process.stderr)
    lines: queue.Queue[str | None] = queue.Queue()
    tail: deque[bytes] = deque()
    tail_reader = threading.Thread(target=_keep_tail, args=(stderr, tail), daemon=True)
    for thread in (
        threading.Thread(
            target=feed_stdin, args=(stdin, spec.stdin_text.encode("utf-8")), daemon=True
        ),
        threading.Thread(target=_pump_lines, args=(stdout, lines), daemon=True),
        tail_reader,
    ):
        thread.start()
    deadline = clock() + spec.timeout_seconds
    killed: KillReason | None = None
    drained = False
    while True:
        try:
            line = lines.get(timeout=max(0.0, deadline - clock()))
        except queue.Empty:
            killed = "timeout"
            break
        if line is None:
            drained = True
            break
        if on_line(line):
            killed = "tripwire"
            break
    if killed is not None:
        kill_tree(process, spec.platform)
        drained = drain_lines(lines)
    elif cancel.cancelled:
        killed = "cancelled"
    returncode = wait_for_exit(process)
    cancel.attach(None)
    tail_reader.join(timeout=DRAIN_SECONDS)
    stderr_tail = b"".join(tail)[-STDERR_TAIL_BYTES:].decode("utf-8", errors="replace")
    return ProcessOutcome(returncode, stderr_tail, killed, drained)
