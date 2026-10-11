"""Sources the connector contract suite runs against, one per connector.

A ``ContractSource`` builds a connector over a synthetic source and mutates that source the way
its real counterpart changes (write a file, commit, delete). To put a new connector under the
contract, implement ``ContractSource`` for it and register its factory in ``CONTRACT_SOURCES``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import AnyUrl

from fakes.connector import FakeConnector
from knobridge.connectors.base import Connector
from knobridge.connectors.folder import FolderConnector
from knobridge.connectors.git import GitConnector
from knobridge.ingestion.source_config import FolderSourceConfig, GitSourceConfig

# Fixed, increasing mtimes: a rewrite never depends on the real clock's resolution.
BASE_MTIME_NS = 1_700_000_000_000_000_000
MTIME_STEP_NS = 1_000_000_000


class ContractSource(Protocol):
    def connector(self) -> Connector: ...

    def add(self, key: str, content: bytes) -> None: ...

    def change(self, key: str, content: bytes) -> None: ...

    def remove(self, key: str) -> None: ...

    def break_source(self) -> None:
        """Make the source unreadable, so ``test_connection`` must fail."""
        ...


class FakeContractSource:
    def __init__(self, tmp_path: Path) -> None:
        self._connector = FakeConnector()

    def connector(self) -> Connector:
        return self._connector

    def add(self, key: str, content: bytes) -> None:
        self._connector.put(key, content)

    def change(self, key: str, content: bytes) -> None:
        self._connector.put(key, content)

    def remove(self, key: str) -> None:
        self._connector.delete(key)

    def break_source(self) -> None:
        self._connector.available = False


class FolderContractSource:
    def __init__(self, tmp_path: Path) -> None:
        self._allowed_root = tmp_path / "sources"
        self._folder = self._allowed_root / "docs"
        self._folder.mkdir(parents=True)
        self._writes = 0

    def connector(self) -> Connector:
        return FolderConnector(
            FolderSourceConfig(path=str(self._folder)),
            allowed_root=self._allowed_root,
            max_file_bytes=1024 * 1024,
        )

    def add(self, key: str, content: bytes) -> None:
        path = self._folder / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self._writes += 1
        mtime = BASE_MTIME_NS + self._writes * MTIME_STEP_NS
        os.utime(path, ns=(mtime, mtime))

    def change(self, key: str, content: bytes) -> None:
        self.add(key, content)

    def remove(self, key: str) -> None:
        (self._folder / key).unlink()

    def break_source(self) -> None:
        shutil.rmtree(self._folder)


def _git(repo: Path, *args: str, commits: int = 0) -> None:
    # No system or global config (autocrlf, signing, hooks) and fixed dates: same SHAs anywhere.
    date = f"{1_700_000_000 + commits * 60} +0000"
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
    }
    # Fixed git commands on a tmp_path repository; "git" from PATH like the connector itself.
    command = ["git", "-C", str(repo), *args]
    subprocess.run(command, check=True, capture_output=True, env=env)  # noqa: S603


class GitContractSource:
    """A repository under the allowed root; every mutation is one commit."""

    def __init__(self, tmp_path: Path) -> None:
        self._allowed_root = tmp_path / "sources"
        self._repo = self._allowed_root / "repo"
        self._workdir = tmp_path / "work"
        self._repo.mkdir(parents=True)
        self._commits = 0
        _git(self._repo, "init", "--quiet", "--initial-branch=main")
        _git(self._repo, "config", "user.name", "Contract Author")
        _git(self._repo, "config", "user.email", "author@example.test")

    def connector(self) -> Connector:
        return GitConnector(
            GitSourceConfig(path=str(self._repo)),
            allowed_root=self._allowed_root,
            workdir=self._workdir,
            max_file_bytes=1024 * 1024,
        )

    def add(self, key: str, content: bytes) -> None:
        path = self._repo / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self._commit(f"write {key}")

    def change(self, key: str, content: bytes) -> None:
        self.add(key, content)

    def remove(self, key: str) -> None:
        (self._repo / key).unlink()
        self._commit(f"remove {key}")

    def break_source(self) -> None:
        self._repo.rename(self._repo.with_name("moved"))

    def _commit(self, message: str) -> None:
        self._commits += 1
        _git(self._repo, "add", "--all")
        _git(self._repo, "commit", "--quiet", "--message", message, commits=self._commits)


class GitUrlContractSource(GitContractSource):
    """A remote served as ``file://`` (tests only) behind an https URL, cloned by the connector."""

    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self._remote = self._repo.as_uri()

    def connector(self) -> Connector:
        return GitConnector(
            GitSourceConfig(url=AnyUrl("https://example.test/repo.git")),
            allowed_root=self._allowed_root,
            workdir=self._workdir,
            max_file_bytes=1024 * 1024,
            allowed_protocols={"file"},
            url_rewriter=lambda _url: self._remote,
        )


CONTRACT_SOURCES: dict[str, Callable[[Path], ContractSource]] = {
    "fake": FakeContractSource,
    "folder": FolderContractSource,
    "git": GitContractSource,
    "git_url": GitUrlContractSource,
}
