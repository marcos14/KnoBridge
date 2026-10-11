"""Discovery of the harness CLIs: executable, version and login status (never calls the model)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from knobridge_runner.commands import CommandRunner
from knobridge_runner.config import ExecutorConfig
from knobridge_runner.formats import Executor
from knobridge_runner.protocol import RunnerExecutorInfo

Which = Callable[[str], str | None]

BINARIES: dict[Executor, str] = {"claude_code": "claude", "codex": "codex"}
API_KEY_VARIABLES: dict[Executor, tuple[str, ...]] = {
    "claude_code": ("ANTHROPIC_API_KEY",),
    "codex": ("CODEX_API_KEY", "OPENAI_API_KEY"),
}
_NOT_RUN = frozenset({127, -1})


def resolve_command(
    name: Executor, config: ExecutorConfig, platform: str, which: Which = shutil.which
) -> list[str] | None:
    """Explicit command from the config, or the executable found on PATH.

    On Windows only ``.exe`` is resolved: npm ``.cmd``/``.bat`` shims go through cmd.exe, which
    re-parses the quotes of the schema argument (docs/specs/harness.md, "Executável").
    """
    if config.command is not None:
        return list(config.command)
    binary = BINARIES[name]
    found = which(f"{binary}.exe" if platform == "windows" else binary)
    return [found] if found else None


class AuthChecker(Protocol):
    def check(self, name: Executor, command: list[str]) -> bool | None:
        """True if logged in, False if not, None if it could not be verified."""
        ...


class CliAuthChecker:
    """An API key in the environment, else ``claude auth status --json`` / ``codex login status``.

    Neither command calls the model.
    """

    def __init__(self, runner: CommandRunner, environment: Mapping[str, str]) -> None:
        self._runner = runner
        self._env = environment

    def check(self, name: Executor, command: list[str]) -> bool | None:
        if any(self._env.get(variable) for variable in API_KEY_VARIABLES[name]):
            return True
        if name == "claude_code":
            result = self._runner.run([*command, "auth", "status", "--json"])
        else:
            result = self._runner.run([*command, "login", "status"])
        if result.returncode in _NOT_RUN:
            return None
        if result.returncode != 0:
            return False
        return _logged_in_flag(result.stdout)


def _logged_in_flag(stdout: str) -> bool:
    """Claude Code prints ``{"loggedIn": ...}``; Codex prints text and signals by exit code."""
    try:
        data: object = json.loads(stdout)
    except ValueError:
        return True
    if isinstance(data, dict):
        flag = cast(dict[str, object], data).get("loggedIn")
        if isinstance(flag, bool):
            return flag
    return True


def read_version(runner: CommandRunner, command: list[str]) -> str | None:
    result = runner.run([*command, "--version"])
    if result.returncode != 0:
        return None
    first = next((line.strip() for line in result.stdout.splitlines() if line.strip()), "")
    return first[:64] or None


def probe_executor(
    name: Executor,
    config: ExecutorConfig,
    *,
    platform: str,
    runner: CommandRunner,
    auth: AuthChecker,
    which: Which = shutil.which,
) -> RunnerExecutorInfo:
    """What the heartbeat reports about one executor: found, version and login (yes/no only)."""
    command = resolve_command(name, config, platform, which)
    if command is None:
        return RunnerExecutorInfo(name=name, available=False, version=None, authenticated=None)
    return RunnerExecutorInfo(
        name=name,
        available=True,
        version=read_version(runner, command),
        authenticated=auth.check(name, command),
    )
