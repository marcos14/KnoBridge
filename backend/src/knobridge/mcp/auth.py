"""The ASGI wrapper in front of the SDK's Streamable HTTP handler (``docs/specs/mcp.md``,
"Autenticação").

Runs before any MCP message, in this order:

1. ``Origin``: a request that carries one goes on only when the origin is in
   ``KNOBRIDGE_MCP_ALLOWED_ORIGINS`` (case-insensitive); otherwise 403 ``origin_not_allowed``
   (DNS rebinding from a browser). IDE and CLI clients send none.
2. Method: only ``POST`` (stateless JSON transport: no notification stream, no session to
   delete); otherwise 405 with ``Allow: POST``.
3. Key: ``Authorization: Bearer kbk_…`` checked like the public API, in a short system-mode
   transaction that also records ``last_used_at`` (at most once a minute) and commits: 401
   ``invalid_api_key`` with ``WWW-Authenticate: Bearer``, 403 ``workspace_suspended``.

Errors are raised as ``KnoBridgeError`` and rendered by the app's handlers in the standard
shape, in HTTP, never as JSON-RPC. The key's identity and the app's services are then bound to
the context (``mcp/context.py``) for the tools.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from http import HTTPStatus

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from knobridge.apikeys.auth import (
    ApiKeyIdentity,
    authenticate_api_key,
    invalid_api_key,
    touch_last_used,
)
from knobridge.core.db import system_session
from knobridge.core.errors import ForbiddenError, KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.mcp.context import McpCall, McpServices, bound

_log = get_logger(__name__)


class MethodNotAllowedError(KnoBridgeError):
    code = "method_not_allowed"
    status_code = HTTPStatus.METHOD_NOT_ALLOWED
    headers = {"Allow": "POST"}  # noqa: RUF012 - read-only class default


def normalize_origin(origin: str) -> str:
    return origin.strip().lower().rstrip("/")


def bearer_key(headers: Headers) -> str:
    """The key of ``Authorization: Bearer <key>``; 401 when absent or another scheme."""
    scheme, _, key = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not key.strip():
        raise invalid_api_key()
    return key.strip()


def _with_origin(scope: Scope, origin: str) -> list[tuple[bytes, bytes]]:
    headers: list[tuple[bytes, bytes]] = scope["headers"]
    return [
        (name, origin.encode("latin-1") if name == b"origin" else value) for name, value in headers
    ]


class McpEndpoint:
    """Checks origin, method and key, then serves the request with the SDK's ``handler``."""

    def __init__(
        self,
        handler: ASGIApp,
        *,
        allowed_origins: Iterable[str],
        services: Callable[[], McpServices],
    ) -> None:
        self._handler = handler
        self._allowed_origins = frozenset(normalize_origin(item) for item in allowed_origins)
        self._services = services

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        if origin is not None and normalize_origin(origin) not in self._allowed_origins:
            _log.warning("mcp_origin_refused")
            raise ForbiddenError("Origin not allowed.", code="origin_not_allowed")
        if scope["method"] != "POST":
            raise MethodNotAllowedError("Only POST is accepted.")
        services = self._services()
        identity = await self._authenticate(services, headers)
        if origin is not None:
            # The SDK compares origins as written; ours already matched without case.
            scope = {**scope, "headers": _with_origin(scope, normalize_origin(origin))}
        with bound(McpCall(identity=identity, services=services)):
            await self._handler(scope, receive, send)

    @staticmethod
    async def _authenticate(services: McpServices, headers: Headers) -> ApiKeyIdentity:
        key = bearer_key(headers)
        async with system_session(services.factory) as db:
            identity = await authenticate_api_key(db, key=key)
            await touch_last_used(db, identity, services.clock.now())
        return identity
