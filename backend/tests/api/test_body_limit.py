"""Body size limits of the runner routes: declared and streamed bodies, other paths untouched."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from knobridge.api.body_limit import KIB, MIB, RunnerBodyLimitMiddleware, body_limit


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/v1/runner/heartbeat")
    @app.post("/v1/other")
    async def echo(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    app.add_middleware(RunnerBodyLimitMiddleware)
    return TestClient(app)


@pytest.mark.parametrize(
    ("path", "limit"),
    [
        ("/v1/runner/heartbeat", 64 * KIB),
        ("/v1/runner/sources/abc/report", 4 * MIB),
        ("/v1/runner/jobs/claim", 4 * KIB),
        ("/v1/runner/jobs/abc/heartbeat", 4 * KIB),
        ("/v1/runner/jobs/abc/result", 8 * MIB),
        ("/v1/runner/jobs/abc/fail", 8 * KIB),
        ("/v1/runner/jobs/abc/defer", 8 * KIB),
        ("/v1/workspaces/abc/runners", None),
    ],
)
def test_body_limit_per_route(path: str, limit: int | None) -> None:
    assert body_limit(path) == limit


def test_body_limit_passes_body_within_limit() -> None:
    response = _client().post("/v1/runner/heartbeat", content=b"x" * (64 * KIB))

    assert response.status_code == 200
    assert response.json() == {"size": 64 * KIB}


def test_body_limit_refuses_declared_length_above_limit() -> None:
    response = _client().post("/v1/runner/heartbeat", content=b"x" * (64 * KIB + 1))

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": "payload_too_large",
            "message": "Request body too large.",
            "details": {"max_bytes": 64 * KIB},
        }
    }


def test_body_limit_refuses_streamed_body_above_limit() -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(3):
            yield b"x" * (32 * KIB)

    response = _client().post("/v1/runner/heartbeat", content=chunks())

    assert response.status_code == 413


def test_body_limit_ignores_other_paths() -> None:
    response = _client().post("/v1/other", content=b"x" * (128 * KIB))

    assert response.json() == {"size": 128 * KIB}


def _run(scope_headers: list[tuple[bytes, bytes]], messages: list[Message]) -> list[Message]:
    """Drive the middleware by hand; the inner app records the body it receives."""
    received: list[Message] = []
    sent: list[Message] = []

    async def inner(_scope: Scope, receive: Receive, _send: Send) -> None:
        received.append(await receive())
        received.append(await receive())

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {
        "type": "http",
        "path": "/v1/runner/heartbeat",
        "headers": scope_headers,
        "method": "POST",
    }
    asyncio.run(RunnerBodyLimitMiddleware(inner)(scope, receive, send))
    return received or sent


def test_body_limit_tolerates_invalid_content_length() -> None:
    received = _run(
        [(b"content-length", b"abc")],
        [{"type": "http.request", "body": b"{}", "more_body": False}, {"type": "http.disconnect"}],
    )

    assert received[0] == {"type": "http.request", "body": b"{}", "more_body": False}


def test_body_limit_passes_later_client_messages_through() -> None:
    later: Message = {"type": "http.disconnect", "marker": "from-client"}

    received = _run([], [{"type": "http.request", "body": b"{}", "more_body": False}, later])

    assert received[1] is later


def test_body_limit_reports_disconnect_after_partial_body() -> None:
    received = _run(
        [],
        [{"type": "http.request", "body": b"{", "more_body": True}, {"type": "http.disconnect"}],
    )

    assert received[1] == {"type": "http.disconnect"}


def test_body_limit_hands_over_partial_body_on_disconnect() -> None:
    received = _run(
        [],
        [{"type": "http.request", "body": b"{", "more_body": True}, {"type": "http.disconnect"}],
    )

    assert received[0]["body"] == b"{"


def test_body_limit_skips_non_http_scopes() -> None:
    calls: list[str] = []

    async def inner(scope: Scope, _receive: Receive, _send: Send) -> None:
        calls.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(_message: Message) -> None:
        return None

    scope: Scope = {"type": "lifespan"}
    asyncio.run(RunnerBodyLimitMiddleware(inner)(scope, receive, send))

    assert calls == ["lifespan"]
