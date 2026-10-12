from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from connectors_support import write

from knobridge.connectors.base import ChangeSet, Cursor, DocumentRef
from knobridge.connectors.errors import (
    DocumentNotFoundError,
    InvalidCursorError,
    PathOutsideRootError,
    SourceUnavailableError,
)
from knobridge.connectors.folder import FolderConnector, create_folder_connector
from knobridge.connectors.folder.connector import HASH_PREFIX_CHARS
from knobridge.core.settings import Settings
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import FolderSourceConfig


@pytest.fixture
def allowed(tmp_path: Path) -> Path:
    path = tmp_path / "sources"
    path.mkdir()
    return path


@pytest.fixture
def folder(allowed: Path) -> Path:
    path = allowed / "docs"
    path.mkdir()
    return path


def _connector(
    allowed: Path,
    folder: Path,
    *,
    trust_mtime: bool = True,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
) -> FolderConnector:
    return FolderConnector(
        FolderSourceConfig(path=str(folder)),
        allowed_root=allowed,
        max_file_bytes=1000,
        include_globs=include,
        exclude_globs=exclude,
        trust_mtime=trust_mtime,
    )


def _list(connector: FolderConnector, cursor: Cursor | None = None) -> ChangeSet:
    return asyncio.run(connector.list_changes(cursor))


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in refs]


def test_folder_lists_added_changed_removed(allowed: Path, folder: Path) -> None:
    write(folder, "a.md", "# A\n")
    write(folder, "b/c.txt", "c\n")
    write(folder, "d.txt", "d\n")
    write(folder, "image.dat", b"\x00\x01")
    connector = _connector(allowed, folder)
    first = _list(connector)
    write(folder, "a.md", "# A, longer\n", tick=1)
    (folder / "d.txt").unlink()
    write(folder, "e/f.md", "f\n")

    changes = _list(connector, first.cursor)

    assert _keys(first.added) == ["a.md", "b/c.txt", "d.txt"]
    assert _keys(changes.added) == ["e/f.md"]
    assert _keys(changes.changed) == ["a.md"]
    assert _keys(changes.removed) == ["d.txt"]
    assert all(ref.kind is DocumentKind.FILE for ref in first.added)


def test_folder_cursor_is_compact_json(allowed: Path, folder: Path) -> None:
    write(folder, "a.md", "# A\n", tick=7)

    cursor = _list(_connector(allowed, folder)).cursor

    assert json.loads(json.dumps(cursor)) == cursor
    assert cursor["kind"] == "folder"
    assert cursor["version"] == 1
    entries = cursor["entries"]
    assert isinstance(entries, dict)
    entry = entries["a.md"]
    assert isinstance(entry, list)
    assert (len(str(entry[0])), entry[1]) == (HASH_PREFIX_CHARS, 4)


def test_folder_reuses_hash_when_size_and_mtime_are_unchanged(allowed: Path, folder: Path) -> None:
    write(folder, "a.txt", "one\n")
    connector = _connector(allowed, folder)
    first = _list(connector)
    # Same size and same mtime: the shortcut trusts the stored hash without reading the file.
    write(folder, "a.txt", "two\n")

    assert _list(connector, first.cursor).is_empty
    assert _keys(_list(_connector(allowed, folder, trust_mtime=False), first.cursor).changed) == [
        "a.txt"
    ]


def test_folder_touch_without_content_change_is_not_a_change(allowed: Path, folder: Path) -> None:
    write(folder, "a.txt", "same\n")
    connector = _connector(allowed, folder)
    first = _list(connector)
    write(folder, "a.txt", "same\n", tick=5)

    second = _list(connector, first.cursor)

    assert second.is_empty
    assert second.cursor != first.cursor


def test_folder_applies_source_globs(allowed: Path, folder: Path) -> None:
    write(folder, "docs/a.md")
    write(folder, "docs/draft.md")
    write(folder, "src/app.py")

    changes = _list(_connector(allowed, folder, include=("docs/**",), exclude=("draft.md",)))

    assert _keys(changes.added) == ["docs/a.md"]


def test_folder_fetch_returns_document_with_metadata(allowed: Path, folder: Path) -> None:
    path = write(folder, "guide/Login.MD", "# Login\n")

    document = asyncio.run(_connector(allowed, folder).fetch(DocumentRef("guide/Login.MD")))

    assert (document.title, document.extension, document.language) == ("Login.MD", "md", "markdown")
    assert document.uri == path.as_uri()
    assert document.metadata == {"path": "guide/Login.MD", "size_bytes": 8, "format": "text"}


def test_folder_fetch_returns_parseable_document_as_bytes(allowed: Path, folder: Path) -> None:
    content = b"%PDF-1.7\n\x00\x01binary"
    write(folder, "manual.pdf", content)
    connector = _connector(allowed, folder)

    changes = _list(connector)
    document = asyncio.run(connector.fetch(DocumentRef("manual.pdf")))

    assert _keys(changes.added) == ["manual.pdf"]
    assert (document.content, document.extension, document.language) == (content, "pdf", None)
    assert document.metadata["format"] == "document"


def test_folder_fetch_unknown_extension_has_no_language(allowed: Path, folder: Path) -> None:
    write(folder, "Makefile", "all:\n")

    document = asyncio.run(_connector(allowed, folder).fetch(DocumentRef("Makefile")))

    assert (document.extension, document.language) == ("", None)


def test_folder_fetch_refuses_binary_file(allowed: Path, folder: Path) -> None:
    write(folder, "data.txt", b"\x00binary")

    with pytest.raises(DocumentNotFoundError):
        asyncio.run(_connector(allowed, folder).fetch(DocumentRef("data.txt")))


def test_folder_fetch_refuses_commit_refs(allowed: Path, folder: Path) -> None:
    write(folder, "a.txt")

    with pytest.raises(DocumentNotFoundError):
        asyncio.run(_connector(allowed, folder).fetch(DocumentRef("a.txt", DocumentKind.COMMIT)))


def test_folder_outside_allowed_root_fails(tmp_path: Path, allowed: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    connector = _connector(allowed, outside)

    with pytest.raises(PathOutsideRootError):
        asyncio.run(connector.test_connection())
    with pytest.raises(PathOutsideRootError):
        _list(connector)


def test_folder_missing_folder_is_unavailable(allowed: Path) -> None:
    with pytest.raises(SourceUnavailableError):
        asyncio.run(_connector(allowed, allowed / "missing").test_connection())


@pytest.mark.parametrize(
    "cursor",
    [
        {"kind": "folder", "version": 2, "entries": {}},
        {"kind": "git", "version": 1, "entries": {}},
        {"kind": "folder", "version": 1, "entries": {"a": ["x", 1]}},
    ],
)
def test_folder_rejects_invalid_cursor(allowed: Path, folder: Path, cursor: Cursor) -> None:
    with pytest.raises(InvalidCursorError):
        _list(_connector(allowed, folder), cursor)


def test_create_folder_connector_uses_settings(tmp_path: Path, folder: Path) -> None:
    write(folder, "small.txt", "ok\n")
    write(folder, "large.txt", "x" * 20)
    write(folder, "skip.md", "# skip\n")
    write(folder, "doc.pdf", b"%PDF\x00" + b"x" * 20)
    write(folder, "big.pdf", b"%PDF\x00" + b"x" * 40)
    settings = Settings(
        local_sources_root=tmp_path, max_source_file_bytes=10, max_source_document_bytes=30
    )
    connector = create_folder_connector(
        FolderSourceConfig(path=str(folder)), settings, exclude_globs=["*.md"]
    )

    assert _keys(_list(connector).added) == ["doc.pdf", "small.txt"]
