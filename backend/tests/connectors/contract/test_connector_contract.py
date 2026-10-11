"""Behaviour every ``Connector`` must have, run against each source in ``CONTRACT_SOURCES``."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from contract_support import CONTRACT_SOURCES, ContractSource

from knobridge.connectors.base import OPEN_ACL, ChangeSet, Cursor, DocumentRef
from knobridge.connectors.errors import ConnectorError, DocumentNotFoundError, InvalidCursorError
from knobridge.ingestion.models import DocumentKind

INITIAL = {"guide.md": b"# Guide\n\nHow to log in.\n", "src/app.py": b"print('hi')\n"}


@pytest.fixture(params=sorted(CONTRACT_SOURCES))
def source(request: pytest.FixtureRequest, tmp_path: Path) -> ContractSource:
    name: str = request.param
    return CONTRACT_SOURCES[name](tmp_path)


def _seed(source: ContractSource) -> None:
    for key, content in INITIAL.items():
        source.add(key, content)


def _list(source: ContractSource, cursor: Cursor | None) -> ChangeSet:
    changes = asyncio.run(source.connector().list_changes(cursor))
    # The engine stores the cursor as JSONB: whatever comes back must survive a round trip.
    return ChangeSet(
        changes.added, changes.changed, changes.removed, json.loads(json.dumps(changes.cursor))
    )


def _files(refs: tuple[DocumentRef, ...]) -> list[DocumentRef]:
    # Sources may list documents of other kinds too (the Git connector's commits); the
    # contract is about the files every source has.
    return [ref for ref in refs if ref.kind is DocumentKind.FILE]


def _keys(refs: tuple[DocumentRef, ...]) -> list[str]:
    return [ref.key for ref in _files(refs)]


def test_contract_first_listing_adds_every_document(source: ContractSource) -> None:
    _seed(source)

    changes = _list(source, None)

    assert _keys(changes.added) == sorted(INITIAL)
    assert (changes.changed, changes.removed) == ((), ())


def test_contract_listing_with_own_cursor_is_empty(source: ContractSource) -> None:
    _seed(source)
    first = _list(source, None)

    second = _list(source, first.cursor)

    assert second.is_empty
    assert second.cursor == first.cursor


def test_contract_lists_added_changed_and_removed(source: ContractSource) -> None:
    _seed(source)
    first = _list(source, None)
    source.add("notes/new.txt", b"new\n")
    source.change("guide.md", b"# Guide\n\nHow to log in, updated.\n")
    source.remove("src/app.py")

    changes = _list(source, first.cursor)

    assert _keys(changes.added) == ["notes/new.txt"]
    assert _keys(changes.changed) == ["guide.md"]
    assert _keys(changes.removed) == ["src/app.py"]


def test_contract_fetch_returns_content_and_sha256(source: ContractSource) -> None:
    _seed(source)
    ref = _files(_list(source, None).added)[0]

    document = asyncio.run(source.connector().fetch(ref))

    assert document.ref == ref
    assert document.content == INITIAL[ref.key]
    assert document.content_hash == hashlib.sha256(INITIAL[ref.key]).hexdigest()
    assert document.text == INITIAL[ref.key].decode()
    assert document.title
    assert document.uri


def test_contract_fetch_unknown_ref_raises_not_found(source: ContractSource) -> None:
    _seed(source)

    with pytest.raises(DocumentNotFoundError):
        asyncio.run(source.connector().fetch(DocumentRef("missing.md")))


def test_contract_fetch_removed_ref_raises_not_found(source: ContractSource) -> None:
    _seed(source)
    source.remove("guide.md")

    with pytest.raises(DocumentNotFoundError):
        asyncio.run(source.connector().fetch(DocumentRef("guide.md")))


def test_contract_permissions_are_open(source: ContractSource) -> None:
    _seed(source)

    acl = asyncio.run(source.connector().permissions(DocumentRef("guide.md")))

    assert acl == OPEN_ACL
    assert acl.public


def test_contract_test_connection_succeeds_on_readable_source(source: ContractSource) -> None:
    _seed(source)

    asyncio.run(source.connector().test_connection())


def test_contract_test_connection_fails_on_broken_source(source: ContractSource) -> None:
    _seed(source)
    connector = source.connector()
    source.break_source()

    with pytest.raises(ConnectorError):
        asyncio.run(connector.test_connection())


def test_contract_rejects_foreign_cursor(source: ContractSource) -> None:
    _seed(source)

    with pytest.raises(InvalidCursorError):
        asyncio.run(source.connector().list_changes({"unknown": "cursor"}))
