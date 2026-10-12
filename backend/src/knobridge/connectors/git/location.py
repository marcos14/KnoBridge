"""Where a Git source lives: a local repository read in place, or an https remote cloned.

A local repository (``path``) sits under ``KNOBRIDGE_LOCAL_SOURCES_ROOT``, usually on a
read-only mount: it is only queried through ``git -C <path>`` read commands, never fetched,
checked out or otherwise written. A remote (``url``) is cloned once into
``KNOBRIDGE_GIT_WORKDIR/<hash of the url>`` as a partial clone (``--filter=blob:none``: full
history of commits and trees, file contents on demand) and fetched before each listing.
"""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from knobridge.connectors.errors import (
    BranchNotFoundError,
    PathOutsideRootError,
    SourceUnavailableError,
)
from knobridge.connectors.git.repository import Repository
from knobridge.connectors.git.runner import GitCommandError, GitRunner
from knobridge.connectors.selection import resolve_root

# Enough to make collisions between the URLs of one instance irrelevant, short enough for paths.
CLONE_DIR_HASH_CHARS = 24
# ``git ls-remote --exit-code`` exits with 2 when no ref matches.
_NO_MATCHING_REF = 2


class Location(Protocol):
    async def open(self, *, update: bool) -> Repository:
        """The repository, fetched from its remote first when ``update`` and it has one."""
        ...

    async def head(self, repository: Repository) -> str:
        """The SHA of the configured branch; ``BranchNotFoundError`` when it does not exist."""
        ...

    async def prefetch(self, repository: Repository, commit: str) -> None:
        """Make the file contents of ``commit`` available locally, in one go."""
        ...

    async def check(self) -> None:
        """Cheap reachability check for ``test_connection``, without cloning."""
        ...


def _missing_branch(branch: str | None) -> BranchNotFoundError:
    if branch is None:
        return BranchNotFoundError("repository has no commits on its default branch")
    return BranchNotFoundError("branch does not exist", details={"branch": branch})


def _check_layout(root: Path, top: str, common_dir: str, allowed_root: Path) -> None:
    # A plain folder inside a repository would make git use the enclosing repository.
    if Path(top).resolve() != root:
        raise SourceUnavailableError("source path is not the root of a Git repository")
    # A linked worktree keeps its objects in the main repository, which must be allowed too.
    if not Path(common_dir).resolve().is_relative_to(allowed_root.resolve()):
        raise PathOutsideRootError(
            "repository objects are outside the allowed sources root",
            details={"allowed_root": str(allowed_root.resolve())},
        )


def _is_same_dir(reported: str, directory: Path) -> bool:
    return Path(reported).resolve() == directory.resolve()


def _reset_dir(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
    directory.parent.mkdir(parents=True, exist_ok=True)


class LocalLocation:
    def __init__(
        self, runner: GitRunner, path: str, branch: str | None, *, allowed_root: Path
    ) -> None:
        self._runner = runner
        self._path = path
        self._branch = branch
        self._allowed_root = allowed_root

    async def open(self, *, update: bool) -> Repository:
        root = await asyncio.to_thread(resolve_root, self._path, self._allowed_root)
        repository = Repository(self._runner, root)
        try:
            output = await repository.git(
                "rev-parse", "--is-bare-repository", "--path-format=absolute",
                "--git-dir", "--git-common-dir",
            )  # fmt: skip
            bare, git_dir, common_dir = output.decode("utf-8").split("\n")[:3]
            if bare == "true":
                top = git_dir
            else:
                top = (await repository.git("rev-parse", "--show-toplevel")).decode("utf-8")
        except GitCommandError as exc:
            raise SourceUnavailableError("source path is not a Git repository") from exc
        await asyncio.to_thread(_check_layout, root, top.strip(), common_dir, self._allowed_root)
        return repository

    async def head(self, repository: Repository) -> str:
        if self._branch is None:
            candidates = ["HEAD"]
        else:
            # A mounted clone often has only the default branch locally; others are remote refs.
            candidates = [f"refs/heads/{self._branch}", f"refs/remotes/origin/{self._branch}"]
        for revision in candidates:
            sha = await repository.resolve(revision)
            if sha is not None:
                return sha
        raise _missing_branch(self._branch)

    async def prefetch(self, repository: Repository, commit: str) -> None:
        """Every object of a local repository is already there."""

    async def check(self) -> None:
        await self.head(await self.open(update=False))


class RemoteLocation:
    def __init__(
        self,
        runner: GitRunner,
        url: str,
        branch: str | None,
        *,
        workdir: Path,
        allowed_protocols: Collection[str],
        url_rewriter: Callable[[str], str] | None = None,
    ) -> None:
        self._runner = runner
        self._branch = branch
        clone_url = url_rewriter(url) if url_rewriter is not None else url
        if urlsplit(clone_url).scheme not in allowed_protocols:
            raise SourceUnavailableError("repository url uses a protocol that is not allowed")
        self._url = clone_url
        self._directory = workdir / hashlib.sha256(url.encode()).hexdigest()[:CLONE_DIR_HASH_CHARS]
        # Redirects and submodule-like indirections cannot switch to another transport.
        self._protocols = [
            "protocol.allow=never",
            *(f"protocol.{name}.allow=always" for name in sorted(allowed_protocols)),
        ]

    async def open(self, *, update: bool) -> Repository:
        repository = Repository(self._runner, self._directory)
        if await self._is_clone(repository):
            if update:
                await self._runner.run(
                    ["fetch", "--quiet", "--prune", "--force", "--no-tags", "origin"],
                    repository=self._directory,
                    config=self._protocols,
                )
            return repository
        # A half-written clone (worker killed mid-clone) is discarded and cloned again.
        await asyncio.to_thread(_reset_dir, self._directory)
        try:
            await self._runner.run(
                ["clone", "--quiet", "--filter=blob:none", "--no-checkout", "--no-tags",
                 "--", self._url, str(self._directory)],
                config=self._protocols,
            )  # fmt: skip
        except SourceUnavailableError:
            await asyncio.to_thread(_reset_dir, self._directory)
            raise
        return repository

    async def head(self, repository: Repository) -> str:
        ref = "HEAD" if self._branch is None else self._branch
        sha = await repository.resolve(f"refs/remotes/origin/{ref}")
        if sha is None:
            raise _missing_branch(self._branch)
        return sha

    async def prefetch(self, repository: Repository, commit: str) -> None:
        # Checking the commit out downloads the missing file contents of a partial clone in
        # one batch; reading them one by one would cost a round trip per file.
        await self._runner.run(
            ["checkout", "--quiet", "--force", "--detach", commit],
            repository=self._directory,
            config=self._protocols,
        )

    async def check(self) -> None:
        pattern = "HEAD" if self._branch is None else f"refs/heads/{self._branch}"
        try:
            await self._runner.run(
                ["ls-remote", "--exit-code", "--", self._url, pattern], config=self._protocols
            )
        except GitCommandError as exc:
            if exc.returncode == _NO_MATCHING_REF:
                raise _missing_branch(self._branch) from exc
            raise

    async def _is_clone(self, repository: Repository) -> bool:
        try:
            top = await repository.git("rev-parse", "--show-toplevel")
        except GitCommandError:
            return False
        # git walks up from a folder that is not a repository: that parent is not our clone.
        return await asyncio.to_thread(_is_same_dir, top.decode("utf-8").strip(), self._directory)
