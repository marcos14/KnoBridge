"""In-memory ``Connector``: the reference implementation the contract suite runs against."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from knobridge.audit.models import JSONValue
from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import (
    DocumentNotFoundError,
    InvalidCursorError,
    SourceUnavailableError,
)


class FakeConnector:
    """Documents live in ``files`` (key -> bytes); ``available = False`` breaks the source."""

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(files or {})
        self.available = True

    def put(self, key: str, content: bytes) -> None:
        self.files[key] = content

    def delete(self, key: str) -> None:
        del self.files[key]

    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        self._check_available()
        previous = self._parse(cursor)
        current = {key: hashlib.sha256(data).hexdigest() for key, data in self.files.items()}
        hashes: dict[str, JSONValue] = dict(current)
        return ChangeSet(
            added=self._refs(current.keys() - previous.keys()),
            changed=self._refs(
                k for k in current.keys() & previous.keys() if current[k] != previous[k]
            ),
            removed=self._refs(previous.keys() - current.keys()),
            cursor={"fake": hashes},
        )

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        self._check_available()
        if ref.key not in self.files:
            raise DocumentNotFoundError("document is not selected", details={"key": ref.key})
        return RawDocument(
            ref=ref, title=ref.key, uri=f"fake://{ref.key}", content=self.files[ref.key]
        )

    async def permissions(self, ref: DocumentRef) -> Acl:
        return OPEN_ACL

    async def test_connection(self) -> None:
        self._check_available()

    def _check_available(self) -> None:
        if not self.available:
            raise SourceUnavailableError("fake source is unavailable")

    @staticmethod
    def _parse(cursor: Cursor | None) -> dict[str, str]:
        if cursor is None:
            return {}
        hashes = cursor.get("fake")
        if not isinstance(hashes, dict) or not all(isinstance(v, str) for v in hashes.values()):
            raise InvalidCursorError("cursor was not produced by the fake connector")
        return {key: str(value) for key, value in hashes.items()}

    @staticmethod
    def _refs(keys: Iterable[str]) -> tuple[DocumentRef, ...]:
        return tuple(DocumentRef(key) for key in sorted(keys))
