"""The connector contract (section 7.1 of the vision) and the values it exchanges.

A connector reads one source. ``list_changes`` compares the source with the cursor of the
previous run and returns what was added, changed and removed plus the next cursor; ``fetch``
reads one document; ``permissions`` returns who may see it; ``test_connection`` checks the
source is readable. Connectors never touch the database: the ingestion engine stores the
cursor in ``sources.cursor`` and upserts documents by their natural key.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from knobridge.audit.models import JSONValue
from knobridge.ingestion.models import DocumentKind

# Opaque to the engine; must survive a JSON round trip (it is stored as JSONB).
type Cursor = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class DocumentRef:
    """Points at one document of a source by its natural key.

    The key is the POSIX path relative to the source root for files, or the commit SHA for
    commits; it is unique per source and stable across runs.
    """

    key: str
    kind: DocumentKind = DocumentKind.FILE


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """What changed since the given cursor, each tuple sorted by key, plus the next cursor."""

    added: tuple[DocumentRef, ...]
    changed: tuple[DocumentRef, ...]
    removed: tuple[DocumentRef, ...]
    cursor: Cursor

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.changed or self.removed)


@dataclass(frozen=True, slots=True)
class RawDocument:
    """A fetched document, before parsing: raw bytes plus what is needed to cite it."""

    ref: DocumentRef
    title: str
    uri: str
    content: bytes
    # Lower-case extension without the dot ("md", "py"), empty when the name has none.
    extension: str = ""
    # Language name derived from the extension (e.g. "python"), when known.
    language: str | None = None
    metadata: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    @property
    def content_hash(self) -> str:
        """SHA-256 of the content, hex; the ingestion engine skips unchanged documents by it."""
        return hashlib.sha256(self.content).hexdigest()

    @property
    def text(self) -> str:
        # Selection already dropped binaries; invalid bytes in a text file must not abort a run.
        return self.content.decode("utf-8", errors="replace")


@dataclass(frozen=True, slots=True)
class Acl:
    """Who may see a document. ``public`` means every member of the workspace."""

    public: bool = True
    principals: tuple[str, ...] = ()


# Local folders and repositories carry no per-document permission yet.
OPEN_ACL = Acl()


class Connector(Protocol):
    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        """Compare the source with ``cursor`` (``None`` on the first run)."""
        ...

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        """Read one document; raises ``DocumentNotFoundError`` when it is not selectable."""
        ...

    async def permissions(self, ref: DocumentRef) -> Acl: ...

    async def test_connection(self) -> None:
        """Return when the source is readable; raise a ``ConnectorError`` otherwise."""
        ...
