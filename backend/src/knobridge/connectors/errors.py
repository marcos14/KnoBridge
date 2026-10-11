"""Domain errors raised by connectors, rendered in the standard API error shape.

Messages never carry file contents; paths are relative to the source root whenever possible,
so the worker's filesystem layout does not leak through the API.
"""

from __future__ import annotations

from http import HTTPStatus

from knobridge.core.errors import KnoBridgeError


class ConnectorError(KnoBridgeError):
    code = "connector_error"
    status_code = HTTPStatus.BAD_GATEWAY


class SourceUnavailableError(ConnectorError):
    """The source cannot be read at all (missing folder, not a folder, no permission)."""

    code = "source_unavailable"


class PathOutsideRootError(ConnectorError):
    """A path escapes the allowed root, directly, through ``..`` or through a symlink."""

    code = "path_outside_root"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class DocumentNotFoundError(ConnectorError):
    """The reference does not name a selectable document (gone, ignored, binary, too large)."""

    code = "document_not_found"
    status_code = HTTPStatus.NOT_FOUND


class InvalidCursorError(ConnectorError):
    """The stored cursor was not produced by this connector or by this version of it."""

    code = "invalid_cursor"
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
