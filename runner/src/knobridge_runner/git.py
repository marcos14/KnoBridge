"""Read-only git queries about a configured checkout (HEAD, branch, local changes)."""

from __future__ import annotations

import re
from pathlib import Path

from knobridge_runner.commands import CommandRunner
from knobridge_runner.formats import COMMIT_PATTERN
from knobridge_runner.protocol import RunnerRepositoryInfo

_COMMIT = re.compile(COMMIT_PATTERN)


def _git(runner: CommandRunner, path: Path, *args: str) -> tuple[bool, str]:
    result = runner.run(["git", "-C", str(path), *args])
    return result.returncode == 0, result.stdout.strip()


def is_git_repository(runner: CommandRunner, path: Path) -> bool:
    if not path.is_dir():
        return False
    ok, out = _git(runner, path, "rev-parse", "--is-inside-work-tree")
    return ok and out == "true"


def repository_info(runner: CommandRunner, name: str, path: Path) -> RunnerRepositoryInfo:
    """What the heartbeat reports about a checkout; only the declared name leaves the machine."""
    if not is_git_repository(runner, path):
        return RunnerRepositoryInfo(name=name, head_commit=None, branch=None, dirty=False)
    ok, head = _git(runner, path, "rev-parse", "HEAD")
    head_commit = head if ok and _COMMIT.match(head) else None
    ok, branch = _git(runner, path, "symbolic-ref", "--short", "-q", "HEAD")
    ok_status, status = _git(runner, path, "status", "--porcelain")
    return RunnerRepositoryInfo(
        name=name,
        head_commit=head_commit,
        branch=branch[:255] if ok and branch else None,
        dirty=ok_status and bool(status),
    )
