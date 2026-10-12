"""Connector for a local folder (decision D4): every selected file is a ``file`` document.

Changes are found by content hash. The cursor maps each selected path to a 128-bit prefix of
its SHA-256 plus the size and modification time seen when it was hashed; when size and mtime
are unchanged the stored hash is reused without reading the file (``trust_mtime``). The
connector reads the filesystem only; blocking IO runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from knobridge.connectors.base import OPEN_ACL, Acl, ChangeSet, Cursor, DocumentRef, RawDocument
from knobridge.connectors.errors import DocumentNotFoundError, InvalidCursorError
from knobridge.connectors.selection import (
    LANGUAGES,
    FileSelector,
    SelectionRules,
    file_extension,
    is_document,
    resolve_root,
)
from knobridge.core.settings import Settings
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import FolderSourceConfig

# 32 hex characters (128 bits) per path: collisions are negligible for change detection and
# the cursor of a folder with 10 000 files stays around 1 MB of JSON.
HASH_PREFIX_CHARS = 32

# (content hash prefix, size in bytes, mtime in nanoseconds)
type _Entry = tuple[str, int, int]


class FolderCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["folder"] = "folder"
    version: Literal[1] = 1
    entries: dict[str, tuple[str, int, int]] = Field(default_factory=dict[str, _Entry])


def _parse_cursor(cursor: Cursor | None) -> dict[str, _Entry]:
    if cursor is None:
        return {}
    try:
        return FolderCursor.model_validate(cursor).entries
    except PydanticValidationError as exc:
        raise InvalidCursorError("cursor was not produced by the folder connector") from exc


class FolderConnector:
    def __init__(
        self,
        config: FolderSourceConfig,
        *,
        allowed_root: Path,
        max_file_bytes: int,
        max_document_bytes: int | None = None,
        include_globs: Sequence[str] = (),
        exclude_globs: Sequence[str] = (),
        trust_mtime: bool = True,
    ) -> None:
        self._path = config.path
        self._allowed_root = allowed_root
        self._rules = SelectionRules(
            max_file_bytes=max_file_bytes,
            max_document_bytes=max_document_bytes,
            include_globs=tuple(include_globs),
            exclude_globs=tuple(exclude_globs),
        )
        self._trust_mtime = trust_mtime

    async def list_changes(self, cursor: Cursor | None) -> ChangeSet:
        return await asyncio.to_thread(self._list_changes, cursor)

    async def fetch(self, ref: DocumentRef) -> RawDocument:
        return await asyncio.to_thread(self._fetch, ref)

    async def permissions(self, ref: DocumentRef) -> Acl:
        return OPEN_ACL

    async def test_connection(self) -> None:
        await asyncio.to_thread(self._selector)

    def _selector(self) -> FileSelector:
        # Resolved on every call: the folder may appear, vanish or be relinked between runs.
        return FileSelector(resolve_root(self._path, self._allowed_root), self._rules)

    def _list_changes(self, cursor: Cursor | None) -> ChangeSet:
        previous = _parse_cursor(cursor)
        selector = self._selector()
        current: dict[str, _Entry] = {}
        for file in selector.iter_files():
            known = previous.get(file.key)
            if self._trust_mtime and known is not None and known[1:] == (file.size, file.mtime_ns):
                current[file.key] = known
                continue
            content = selector.read(file)
            if content is not None:
                digest = hashlib.sha256(content).hexdigest()[:HASH_PREFIX_CHARS]
                current[file.key] = (digest, file.size, file.mtime_ns)
        added = sorted(current.keys() - previous.keys())
        removed = sorted(previous.keys() - current.keys())
        changed = sorted(
            key for key in current.keys() & previous.keys() if current[key][0] != previous[key][0]
        )
        return ChangeSet(
            added=tuple(DocumentRef(key) for key in added),
            changed=tuple(DocumentRef(key) for key in changed),
            removed=tuple(DocumentRef(key) for key in removed),
            cursor=FolderCursor(entries=current).model_dump(mode="json"),
        )

    def _fetch(self, ref: DocumentRef) -> RawDocument:
        if ref.kind is not DocumentKind.FILE:
            raise DocumentNotFoundError("folder sources only have files", details={"key": ref.key})
        selector = self._selector()
        file = selector.select(ref.key)
        content = selector.read(file)
        if content is None:
            raise DocumentNotFoundError("document is not selected", details={"key": ref.key})
        name = ref.key.rpartition("/")[2]
        extension = file_extension(name)
        return RawDocument(
            ref=ref,
            title=name,
            uri=file.path.as_uri(),
            content=content,
            extension=extension,
            language=LANGUAGES.get(extension),
            metadata={
                "path": ref.key,
                "size_bytes": len(content),
                # "document": PDF/Office bytes for the parser; "text": UTF-8 text or code.
                "format": "document" if is_document(ref.key) else "text",
            },
        )


def create_folder_connector(
    config: FolderSourceConfig,
    settings: Settings,
    *,
    include_globs: Sequence[str] = (),
    exclude_globs: Sequence[str] = (),
) -> FolderConnector:
    """The folder connector with the root and size limit from settings."""
    return FolderConnector(
        config,
        allowed_root=settings.local_sources_root,
        max_file_bytes=settings.max_source_file_bytes,
        max_document_bytes=settings.max_source_document_bytes,
        include_globs=include_globs,
        exclude_globs=exclude_globs,
    )
