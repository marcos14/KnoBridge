from __future__ import annotations

from http import HTTPStatus

import pytest

from knobridge.connectors.base import OPEN_ACL, ChangeSet, DocumentRef, RawDocument
from knobridge.connectors.errors import (
    ConnectorError,
    DocumentNotFoundError,
    InvalidCursorError,
    PathOutsideRootError,
    SourceUnavailableError,
)
from knobridge.ingestion.models import DocumentKind


def test_document_ref_defaults_to_file() -> None:
    assert DocumentRef("a.md").kind is DocumentKind.FILE


def test_change_set_is_empty_only_without_refs() -> None:
    ref = DocumentRef("a.md")

    assert ChangeSet((), (), (), {}).is_empty
    assert not ChangeSet((), (), (ref,), {}).is_empty


def test_raw_document_text_replaces_invalid_utf8() -> None:
    document = RawDocument(ref=DocumentRef("a.txt"), title="a.txt", uri="x", content=b"ol\xe1")

    assert document.text == "ol�"
    assert document.metadata == {}


def test_open_acl_is_public_without_principals() -> None:
    assert (OPEN_ACL.public, OPEN_ACL.principals) == (True, ())


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (ConnectorError, "connector_error", HTTPStatus.BAD_GATEWAY),
        (SourceUnavailableError, "source_unavailable", HTTPStatus.BAD_GATEWAY),
        (PathOutsideRootError, "path_outside_root", HTTPStatus.UNPROCESSABLE_ENTITY),
        (DocumentNotFoundError, "document_not_found", HTTPStatus.NOT_FOUND),
        (InvalidCursorError, "invalid_cursor", HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_connector_errors_have_codes_and_statuses(
    error: type[ConnectorError], code: str, status: int
) -> None:
    raised = error("message")

    assert (raised.code, raised.status_code, raised.message) == (code, status, "message")
