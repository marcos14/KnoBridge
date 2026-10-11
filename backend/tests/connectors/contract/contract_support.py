"""Sources the connector contract suite runs against, one per connector.

A ``ContractSource`` builds a connector over a synthetic source and mutates that source the way
its real counterpart changes (write a file, commit, delete). To put a new connector under the
contract, implement ``ContractSource`` for it and register its factory in ``CONTRACT_SOURCES``.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from fakes.connector import FakeConnector
from knobridge.connectors.base import Connector
from knobridge.connectors.folder import FolderConnector
from knobridge.ingestion.source_config import FolderSourceConfig

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


CONTRACT_SOURCES: dict[str, Callable[[Path], ContractSource]] = {
    "fake": FakeContractSource,
    "folder": FolderContractSource,
}
