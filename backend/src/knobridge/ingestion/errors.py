"""Domain errors of the ingestion steps.

A document that cannot be processed raises one of these; the ingestion engine records it as a
``RunError`` (stage, code, message) and moves on to the next document, so one bad file never
aborts a run. Messages are short and never carry document content.
"""

from __future__ import annotations

from http import HTTPStatus

from knobridge.core.errors import KnoBridgeError


class IngestionError(KnoBridgeError):
    code = "ingestion_error"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class UnsupportedFormatError(IngestionError):
    """The document's format is not one the parser reads (legacy Office, binary text)."""

    code = "unsupported_format"


class ParseFailedError(IngestionError):
    """The format is supported but the content could not be converted (corrupt, no text)."""

    code = "parse_failed"
