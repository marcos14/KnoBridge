"""Body size limits of the runner routes (docs/specs/runner.md, "Limites de payload").

A pure ASGI middleware: for ``POST /v1/runner/*`` it refuses a declared ``Content-Length``
above the route's limit and stops reading the body as soon as it passes the limit (chunked
bodies included), answering 413 ``payload_too_large`` with ``details.max_bytes``. Otherwise it
replays the buffered body to the application, so FastAPI parses and validates it as usual.
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
# Most specific first; the last entry is the fallback of any other runner route.
_LIMITS: tuple[tuple[re.Pattern[str], int], ...] = (
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
    """The body limit of ``path`` in bytes, or ``None`` outside the runner routes."""
    for pattern, limit in _LIMITS:
        if pattern.match(path):
            return limit
    return None


class RunnerBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = body_limit(scope["path"]) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = _content_length(scope)
        body = None if declared is not None and declared > limit else await _read(receive, limit)
        if body is None:
            await _too_large(scope, send, limit)
            return
        await self.app(scope, _replay(body), send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _read(receive: Receive, limit: int) -> bytes | None:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            # Client gone before the body ended: hand over what arrived; nobody reads the answer.
            break
        chunk: bytes = message.get("body", b"")
        size += len(chunk)
        if size > limit:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


async def _too_large(scope: Scope, send: Send, limit: int) -> None:
    error = PayloadTooLargeError("Request body too large.", details={"max_bytes": limit})
    response = JSONResponse(
        status_code=error.status_code, content=error_body(error.code, error.message, error.details)
    )
    # The rest of the body is never read: the response goes out and the connection closes.
    await response(scope, _replay(b""), send)
