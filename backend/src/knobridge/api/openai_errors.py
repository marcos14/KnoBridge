"""Errors of the OpenAI-compatible routes in OpenAI's shape (``docs/specs/api-publica.md``,
"Erros no formato OpenAI").

These routes answer ``{"error": {"message", "type", "param", "code"}}`` instead of the standard
KnoBridge shape. ``OpenAIRoute`` (the router's ``route_class``) converts every error raised while
handling a request, dependencies included: domain errors by their code, FastAPI's validation
errors (422) as 400 ``invalid_request`` and anything unexpected as 500 ``chat_failed``. The
message is always ours: a provider's text is never repeated.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, cast

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger

INVALID_REQUEST = "invalid_request_error"
API_ERROR = "api_error"
_log = get_logger(__name__)

# Codes whose message is fixed here, so a provider's text never reaches the client.
_PROVIDER_MESSAGES = {
    "provider_rate_limited": "The model provider is rate limiting requests. Try again later.",
    "provider_unavailable": "The model provider is unavailable. Try again later.",
    "provider_auth_failed": "The model provider rejected the assistant's credential.",
    "chat_failed": "The assistant failed to answer.",
}
_PROVIDER_FAILED = "The model provider failed to answer."
_PARAMS = {"model_not_found": "model"}


@dataclass(frozen=True)
class OpenAIError:
    status: int
    message: str
    type: str
    code: str
    param: str | None = None
    headers: dict[str, str] | None = None

    def body(self) -> dict[str, object]:
        return openai_error_body(self.message, self.type, self.code, self.param)

    def response(self) -> JSONResponse:
        return JSONResponse(status_code=self.status, content=self.body(), headers=self.headers)


class OpenAIRequestError(KnoBridgeError):
    """A request the OpenAI-compatible routes refuse (400), with the offending ``param``."""

    status_code = HTTPStatus.BAD_REQUEST

    def __init__(self, message: str, *, code: str, param: str | None) -> None:
        super().__init__(message, code=code)
        self.param = param


def openai_error_body(
    message: str, type_: str, code: str, param: str | None = None
) -> dict[str, object]:
    return {"error": {"message": message, "type": type_, "param": param, "code": code}}


def classify(code: str, status: int, message: str) -> OpenAIError:
    """The OpenAI error of a KnoBridge error code (status and message used when generic)."""
    if code == "provider_rate_limited":
        return OpenAIError(429, _PROVIDER_MESSAGES[code], "rate_limit_error", code)
    if code == "provider_unavailable":
        return OpenAIError(503, _PROVIDER_MESSAGES[code], API_ERROR, code)
    if code == "chat_failed":
        return OpenAIError(500, _PROVIDER_MESSAGES[code], API_ERROR, code)
    if code.startswith(("provider_", "embedding_")):
        return OpenAIError(502, _PROVIDER_MESSAGES.get(code, _PROVIDER_FAILED), API_ERROR, code)
    if status == HTTPStatus.FORBIDDEN:
        return OpenAIError(status, message, "permission_error", code)
    type_ = INVALID_REQUEST if status < HTTPStatus.INTERNAL_SERVER_ERROR else API_ERROR
    return OpenAIError(status, message, type_, code, _PARAMS.get(code))


def from_domain_error(exc: KnoBridgeError) -> OpenAIError:
    error = classify(exc.code, exc.status_code, exc.message)
    if isinstance(exc, OpenAIRequestError):
        error = OpenAIError(error.status, error.message, error.type, error.code, exc.param)
    if exc.headers:
        error = OpenAIError(
            error.status, error.message, error.type, error.code, error.param, dict(exc.headers)
        )
    return error


def _param(location: tuple[int | str, ...]) -> str | None:
    path = location[1:] if location[:1] == ("body",) else location
    return ".".join(str(part) for part in path) or None


def from_validation_error(exc: RequestValidationError) -> OpenAIError:
    errors = exc.errors()
    first = cast(dict[str, object], errors[0]) if errors else {}
    if first.get("type") == "json_invalid":
        return OpenAIError(400, "The body is not valid JSON.", INVALID_REQUEST, "invalid_request")
    # Pydantic's error location: a sequence of field names and list indexes.
    location = cast(Sequence[int | str], first.get("loc", ()))
    param = _param(tuple(location))
    message = f"Invalid value for '{param}'." if param else "The request body is invalid."
    return OpenAIError(400, message, INVALID_REQUEST, "invalid_request", param)


class OpenAIRoute(APIRoute):
    """An ``APIRoute`` whose errors leave in OpenAI's shape."""

    # ``Any`` mirrors FastAPI's own signature of this hook.
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return from_validation_error(exc).response()
            except KnoBridgeError as exc:
                return from_domain_error(exc).response()
            except Exception as exc:
                _log.exception(
                    "openai_route_failed", path=request.url.path, error_type=type(exc).__name__
                )
                return classify("chat_failed", 500, "").response()

        return route_handler
