"""Short local commands (git, ``--version``, login status) run without a shell, with a timeout.

The child environment is an allowlist (docs/specs/harness.md, "Ambiente do subprocesso"): no
``KNOBRIDGE_*`` variable, so the runner token never reaches another process.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_ALLOWED_ENV = frozenset(
    {
        # system
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "LANG",
        "LC_ALL",
        # network
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "NODE_EXTRA_CA_CERTS",
        # Claude Code
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CONFIG_DIR",
        # Codex
        "CODEX_HOME",
        "CODEX_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    }
)


def child_environment(parent: Mapping[str, str]) -> dict[str, str]:
    """Only the allowlisted variables of PARENT; KNOBRIDGE_* and CLAUDECODE never pass."""
    # os.environ already upper-cases names on Windows, so an exact match is enough.
    return {name: value for name, value in parent.items() if name in _ALLOWED_ENV}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
        """Run ARGV and return its exit code and stdout; a missing executable gives 127."""
        ...


class SubprocessCommandRunner:
    """Runs short commands with a timeout; timeouts and missing executables are failures."""

    def __init__(self, environment: Mapping[str, str], timeout_seconds: float = 15.0) -> None:
        self._env = child_environment(environment)
        self._timeout = timeout_seconds

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandResult:
        try:
            completed = subprocess.run(  # noqa: S603 - argument list, no shell
                list(argv),
                cwd=cwd,
                env=self._env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except FileNotFoundError:
            return CommandResult(returncode=127, stdout="")
        except (subprocess.TimeoutExpired, OSError):
            return CommandResult(returncode=-1, stdout="")
        return CommandResult(returncode=completed.returncode, stdout=completed.stdout)
