"""Git queries of layer 0 (docs/specs/harness.md, "Git"): HEAD, branch, changed files, log.

Every command is ``git -c safe.directory=<checkout> -C <checkout> ...`` without a shell, through
the injected ``CommandRunner`` (allowlisted environment; build it with ``GIT_TIMEOUT_SECONDS``).
``safe.directory`` on the command line lets git read a checkout owned by another user;
``--no-optional-locks`` keeps reads from writing to the repository; ``core.fsmonitor`` and
signature checks are off so a hostile repository config cannot run commands while we only read;
``core.quotepath=false`` and ``-z`` give raw UTF-8 paths.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from knobridge_runner.commands import CommandRunner
from knobridge_runner.formats import COMMIT_PATTERN

GIT_TIMEOUT_SECONDS = 60.0
MAX_LOG_ENTRIES = 20
MAX_SUBJECT_CHARS = 120
MAX_BRANCH_CHARS = 255

_COMMIT = re.compile(COMMIT_PATTERN)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class LogEntry:
    """Short hash, ISO date and subject; never the author or e-mail."""

    short_hash: str
    date: str
    subject: str


class GitRepository:
    def __init__(self, runner: CommandRunner, checkout: Path) -> None:
        self._runner = runner
        self._checkout = checkout

    def _run(self, *args: str) -> tuple[bool, str]:
        argv = [
            "git",
            "-c",
            f"safe.directory={self._checkout.as_posix()}",
            "-C",
            str(self._checkout),
            "--no-optional-locks",
            "-c",
            "core.quotepath=false",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "log.showSignature=false",
            "--literal-pathspecs",
            *args,
        ]
        result = self._runner.run(argv)
        return result.returncode == 0, result.stdout

    def head(self) -> str | None:
        """The HEAD commit, or ``None`` outside a repository or before the first commit."""
        ok, out = self._run("rev-parse", "--verify", "-q", "HEAD")
        sha = out.strip()
        return sha if ok and _COMMIT.match(sha) else None

    def branch(self) -> str | None:
        """The current branch; ``None`` on a detached HEAD."""
        ok, out = self._run("rev-parse", "--abbrev-ref", "HEAD")
        name = out.strip()
        if not ok or not name or name == "HEAD" or _CONTROL.search(name):
            return None
        return name[:MAX_BRANCH_CHARS]

    def commit_exists(self, sha: str) -> bool:
        ok, _ = self._run("cat-file", "-e", f"{sha}^{{commit}}")
        return ok

    def changed_files(self, base: str, head: str) -> list[str] | None:
        """Paths changed between two commits (a rename lists both names); ``None`` on error."""
        ok, out = self._run("diff", "--name-only", "--no-renames", "-z", base, head)
        if not ok:
            return None
        return sorted({path for path in out.split("\0") if path})

    def log(self, pathspecs: Sequence[str]) -> list[LogEntry]:
        """The last 20 commits touching PATHSPECS (literal paths); empty on error."""
        ok, out = self._run(
            "log",
            "-n",
            str(MAX_LOG_ENTRIES),
            "--date=short",
            "--format=%h%x09%ad%x09%s",
            "--",
            *pathspecs,
        )
        if not ok:
            return []
        entries: list[LogEntry] = []
        for line in out.splitlines():
            short_hash, _, rest = line.partition("\t")
            date, _, subject = rest.partition("\t")
            if short_hash and date:
                entries.append(LogEntry(short_hash, date, subject[:MAX_SUBJECT_CHARS]))
        return entries
