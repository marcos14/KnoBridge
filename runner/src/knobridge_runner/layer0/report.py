"""Layer 0 entry points: the source report and a module's briefing.

``build_report`` builds the body of ``POST /v1/runner/sources/{source_id}/report``: only the
declared repository name, commits, branch, relative paths and counts leave the machine.
``build_briefing`` builds the local briefing of one module for the agent prompt.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from knobridge_runner.commands import CommandRunner
from knobridge_runner.formats import validate_relative_path
from knobridge_runner.layer0.briefing import render_briefing
from knobridge_runner.layer0.extract import extract
from knobridge_runner.layer0.git import GitRepository
from knobridge_runner.layer0.inventory import inventory_of
from knobridge_runner.layer0.modules import module_matcher, suggest_modules
from knobridge_runner.layer0.selection import read_files, scan_repository, selected_paths
from knobridge_runner.protocol import RunnerModuleIn, RunnerReportIn

MAX_CHANGED_PATHS = 20_000
# Keeps the `git log` command line far below the Windows limit (32 767 characters).
MAX_LOG_PATHSPEC_CHARS = 16_000


class RepositoryUnavailableError(Exception):
    """The checkout is missing, not a Git repository or has no commit yet."""


@dataclass(frozen=True)
class ModuleBriefing:
    text: str
    # Relative paths of the module's selected files, sorted.
    files: tuple[str, ...]
    head_commit: str


def _head(repository: GitRepository) -> str:
    head = repository.head()
    if head is None:
        raise RepositoryUnavailableError("checkout is not a git repository with a commit")
    return head


def _valid_path(path: str) -> bool:
    try:
        validate_relative_path(path)
    except ValueError:
        return False
    return True


def _changed_paths(
    repository: GitRepository, previous_head: str | None, head: str
) -> list[str] | None:
    """Changed paths since PREVIOUS_HEAD; ``None`` when unknown (first report, missing base)."""
    if previous_head is None:
        return None
    if previous_head == head:
        return []
    if not repository.commit_exists(previous_head):
        return None
    changed = repository.changed_files(previous_head, head)
    if changed is None or len(changed) > MAX_CHANGED_PATHS:
        return None
    # A path the protocol cannot carry (control characters, too long) is left out.
    return [path for path in changed if _valid_path(path)]


def build_report(
    runner: CommandRunner,
    repository: str,
    checkout: Path,
    previous_head: str | None,
    *,
    include_globs: Sequence[str] = (),
    exclude_globs: Sequence[str] = (),
) -> RunnerReportIn:
    """The report of CHECKOUT for the source declared as REPOSITORY.

    PREVIOUS_HEAD is the source's ``last_reported_commit``; it becomes ``base_commit``.
    """
    git = GitRepository(runner, checkout)
    head = _head(git)
    files = scan_repository(checkout, include_globs, exclude_globs)
    modules = [
        RunnerModuleIn(
            key=module.key,
            title=module.title,
            paths=list(module.paths),
            inventory=inventory_of(module.files),
        )
        for module in suggest_modules(files)
    ]
    return RunnerReportIn(
        repository=repository,
        head_commit=head,
        branch=git.branch(),
        base_commit=previous_head,
        changed_paths=_changed_paths(git, previous_head, head),
        inventory=inventory_of(files),
        modules=modules,
    )


def log_pathspecs(all_paths: Iterable[str], module_paths: Iterable[str]) -> list[str]:
    """Literal pathspecs selecting the module's files for ``git log``.

    Each module file is represented by its shallowest folder whose selected files all belong to
    the module (``.`` for the whole checkout), or by itself.
    """
    members = set(module_paths)
    mixed: set[str] = set()
    for path in all_paths:
        if path not in members:
            parts = path.split("/")
            mixed.update("/".join(parts[:depth]) for depth in range(len(parts)))
    specs: dict[str, None] = {}
    used = 0
    for path in sorted(members):
        parts = path.split("/")
        ancestors = ("/".join(parts[:depth]) for depth in range(len(parts)))
        spec = next((folder or "." for folder in ancestors if folder not in mixed), path)
        if spec in specs:
            continue
        used += len(spec) + 1
        if used > MAX_LOG_PATHSPEC_CHARS:
            # The history then covers part of the module; it is context, not evidence.
            break
        specs[spec] = None
    return list(specs)


def build_briefing(
    runner: CommandRunner,
    checkout: Path,
    module_paths: Sequence[str],
    *,
    include_globs: Sequence[str] = (),
    exclude_globs: Sequence[str] = (),
) -> ModuleBriefing:
    """The briefing of the module whose ``paths`` are MODULE_PATHS (as the server sends them)."""
    git = GitRepository(runner, checkout)
    head = _head(git)
    located = selected_paths(checkout, include_globs, exclude_globs)
    belongs = module_matcher(module_paths)
    pairs = sorted(
        read_files((key, path) for key, path in located if belongs(key)),
        key=lambda pair: pair[0].path,
    )
    files = [file for file, _ in pairs]
    names = [file.path for file in files]
    history = git.log(log_pathspecs((key for key, _ in located), names)) if names else []
    extractions = extract((file.path, text) for file, text in pairs)
    return ModuleBriefing(render_briefing(files, extractions, history), tuple(names), head)
