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


class SyncAlreadyRunningError(KnoBridgeError):
    """A run of the source is already queued or running; one at a time per source."""

    code = "sync_already_running"
    status_code = HTTPStatus.CONFLICT


class SyncNotRunningError(KnoBridgeError):
    """There is no running synchronization of the source to cancel."""

    code = "sync_not_running"
    status_code = HTTPStatus.CONFLICT


class SourceInactiveError(KnoBridgeError):
    """The source is deactivated, so it is not synchronized."""

    code = "source_inactive"
    status_code = HTTPStatus.CONFLICT


class SyncUnavailableError(KnoBridgeError):
    """The workflow service (Temporal) cannot be reached, so nothing was started or cancelled."""

    code = "sync_unavailable"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
