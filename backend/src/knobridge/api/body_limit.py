"""Body size limits of the bearer-token routes: the runner's (docs/specs/runner.md, "Limites de
payload") and the ingest of tickets (docs/specs/chamados.md, ``POST /v1/ingest/tickets``), plus
the preview of one ticket in the panel (``.../tickets/preview``).

A pure ASGI middleware: for these routes it refuses a
declared ``Content-Length`` above the route's limit and stops reading the body as soon as it
passes the limit (chunked bodies included), answering 413 ``payload_too_large`` with
``details.max_bytes``. Otherwise it replays the buffered body to the application, so FastAPI
parses and validates it as usual.
"""

from __future__ import annotations

import re
from http import HTTPStatus

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from knobridge.core.errors import KnoBridgeError, error_body

KIB = 1024
MIB = 1024 * KIB
RUNNER_PATH_PREFIX = "/v1/runner/"
# Most specific first; ``^/v1/runner/`` is the fallback of any other runner route.
_LIMITS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"^/v1/ingest/tickets$"), 5 * MIB),
    # One ticket (at most 1 MiB) and its envelope. The upload of a file streams instead: its
    # route enforces its own limit while reading (``ticket_uploads.py``).
    (re.compile(r"^/v1/workspaces/[^/]+/sources/[^/]+/tickets/preview$"), 2 * MIB),
    (re.compile(r"^/v1/runner/heartbeat$"), 64 * KIB),
    (re.compile(r"^/v1/runner/sources/[^/]+/report$"), 4 * MIB),
    (re.compile(r"^/v1/runner/jobs/claim$"), 4 * KIB),
    (re.compile(r"^/v1/runner/jobs/[^/]+/heartbeat$"), 4 * KIB),
    (re.compile(r"^/v1/runner/jobs/[^/]+/result$"), 8 * MIB),
    (re.compile(r"^/v1/runner/"), 8 * KIB),
)


class PayloadTooLargeError(KnoBridgeError):
    code = "payload_too_large"
    status_code = HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def body_limit(path: str) -> int | None:
    """The body limit of ``path`` in bytes, or ``None`` outside the limited routes."""
    for pattern, limit in _LIMITS:
        if pattern.match(path):
            return limit
    return None


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = body_limit(scope["path"]) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        read = None if declared is not None and declared > limit else await _read(receive, limit)
        if read is None:
            await _too_large(scope, send, limit)
            return
        body, client_gone = read
        await self.app(scope, _replay(body, None if client_gone else receive), send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _read(receive: Receive, limit: int) -> tuple[bytes, bool] | None:
    """``(body, client_gone)``, or ``None`` as soon as the body passes ``limit``."""
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            # Client gone before the body ended: hand over what arrived; nobody reads the answer.
            return b"".join(chunks), True
        chunk: bytes = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks), False


def _replay(body: bytes, then: Receive | None) -> Receive:
    """The buffered body once; afterwards the client's own messages (``then``), so the
    application still learns of a disconnect (the claim's long-poll stops on it)."""
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"} if then is None else await then()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _too_large(scope: Scope, send: Send, limit: int) -> None:
    error = PayloadTooLargeError("Request body too large.", details={"max_bytes": limit})
    response = JSONResponse(
        status_code=error.status_code, content=error_body(error.code, error.message, error.details)
    )
    # The rest of the body is never read: the response goes out and the connection closes.
    await response(scope, _replay(b"", None), send)
