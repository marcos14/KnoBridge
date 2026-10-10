"""Domain exceptions and the FastAPI handlers that render every error in one JSON shape.

The shape is ``{"error": {"code": str, "message": str, "details": object | null}}``.
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from knobridge.core.logging import get_logger

_log = get_logger(__name__)

# `details` holds arbitrary JSON-serializable data chosen by each error, hence `object`.
ErrorDetails = object


class KnoBridgeError(Exception):
    """Base class for expected errors; carries everything the API needs to answer."""

    code: str = "error"
    status_code: int = HTTPStatus.BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: ErrorDetails = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(KnoBridgeError):
    code = "not_found"
    status_code = HTTPStatus.NOT_FOUND


class ValidationError(KnoBridgeError):
    code = "validation_error"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


class ConflictError(KnoBridgeError):
    code = "conflict"
    status_code = HTTPStatus.CONFLICT


class UnauthenticatedError(KnoBridgeError):
    code = "unauthenticated"
    status_code = HTTPStatus.UNAUTHORIZED


class ForbiddenError(KnoBridgeError):
    code = "forbidden"
    status_code = HTTPStatus.FORBIDDEN


class TooManyRequestsError(KnoBridgeError):
    code = "too_many_requests"
    status_code = HTTPStatus.TOO_MANY_REQUESTS


class ServiceUnavailableError(KnoBridgeError):
    code = "service_unavailable"
    status_code = HTTPStatus.SERVICE_UNAVAILABLE


def error_body(code: str, message: str, details: ErrorDetails = None) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "details": details}}


def _response(
    status_code: int, code: str, message: str, details: ErrorDetails = None
) -> JSONResponse:
    content = jsonable_encoder(error_body(code, message, details))
    return JSONResponse(status_code=status_code, content=content)


async def _handle_domain_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, KnoBridgeError)  # noqa: S101 - narrowed by handler registration
    return _response(exc.status_code, exc.code, exc.message, exc.details)


async def _handle_request_validation(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - narrowed by registration
    return _response(
        HTTPStatus.UNPROCESSABLE_ENTITY,
        "validation_error",
        "Request validation failed.",
        exc.errors(),
    )


def _http_code(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "http_error"


async def _handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - narrowed by registration
    response = _response(exc.status_code, _http_code(exc.status_code), str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("unhandled_error", path=request.url.path, error_type=type(exc).__name__)
    return _response(
        HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "An unexpected error occurred."
    )


def register_error_handlers(app: FastAPI) -> None:
    """Make every error leaving ``app`` follow the standard error shape."""
    app.add_exception_handler(KnoBridgeError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_unexpected)
