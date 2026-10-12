"""Runs the ``git`` binary as a subprocess: no shell, a timeout, and the process killed on it.

Every invocation gets the same protective options. ``safe.directory`` is set to the repository
on the command line (a protected scope, which git honours) because the read-only mount of a
local repository usually has another owner than the worker's user, and git refuses such
repositories by default. Options a hostile repository configuration could use to run commands
while we only read (``core.fsmonitor``, external diff, text conversion) are turned off, and
``GIT_OPTIONAL_LOCKS=0`` keeps read commands from writing to the repository.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from knobridge.connectors.errors import SourceUnavailableError
from knobridge.core.logging import get_logger

# Local reads finish in seconds; clone and fetch of a large repository may take minutes.
DEFAULT_TIMEOUT_SECONDS = 600.0
# Only the start of git's error output reaches the error details (no contents, no secrets).
STDERR_EXCERPT_CHARS = 300

_logger = get_logger(__name__)

_BASE_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_ASKPASS": "",
    "SSH_ASKPASS": "",
    "LC_ALL": "C",
}


class GitCommandError(SourceUnavailableError):
    """``git`` exited with a non-zero status; ``returncode`` lets callers tell cases apart.

    git's error output names worker paths and URLs, so it is logged and kept on the exception
    but never put in ``details``, which reach the API.
    """

    def __init__(self, message: str, *, returncode: int, stderr: str) -> None:
        super().__init__(message, details={"returncode": returncode})
        self.returncode = returncode
        self.stderr = stderr


class GitRunner:
    def __init__(
        self,
        *,
        binary: str = "git",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._binary = binary
        self._timeout = timeout
        self._env = {**os.environ, **_BASE_ENV, **(env or {})}

    async def run(
        self,
        args: Sequence[str],
        *,
        repository: Path | None = None,
        config: Sequence[str] = (),
        stdin: bytes | None = None,
    ) -> bytes:
        """``git [-C repository] <options> args`` and its stdout; raises on failure or timeout.

        ``config`` adds ``-c name=value`` options (e.g. the protocols a clone may use).
        """
        command = [self._binary]
        if repository is not None:
            command += ["-C", str(repository), "-c", f"safe.directory={repository.as_posix()}"]
        command += ["-c", "core.fsmonitor=false", "-c", "log.showSignature=false"]
        for option in config:
            command += ["-c", option]
        command += ["--literal-pathspecs", *args]
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
            )
        except OSError as exc:
            raise SourceUnavailableError("git executable is not available") from exc
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(stdin), self._timeout)
        except TimeoutError:
            process.kill()
            await process.wait()
            raise SourceUnavailableError(
                "git command timed out", details={"timeout_seconds": self._timeout}
            ) from None
        if process.returncode != 0:
            excerpt = stderr.decode("utf-8", errors="replace")[:STDERR_EXCERPT_CHARS]
            # Exit status 1 is an answer ("no such revision", "not an ancestor"), not a failure.
            if process.returncode != 1:
                _logger.warning(
                    "git_command_failed",
                    command=" ".join(args[:1]),
                    returncode=process.returncode,
                    stderr=excerpt,
                )
            raise GitCommandError(
                "git command failed", returncode=process.returncode or 0, stderr=excerpt
            )
        return stdout
