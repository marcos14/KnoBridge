"""Synthetic HTTP for the LLM adapters: an ``httpx2.MockTransport`` that records requests and
answers with canned JSON or Server-Sent Events, so the official SDKs run without network."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field

import httpx2

from knobridge.llm.provider import ChatEvent

API_KEY = "sk-test-adapter-key-4321"  # synthetic

Handler = Callable[[httpx2.Request], httpx2.Response]


def sse(events: Sequence[tuple[str | None, object]]) -> httpx2.Response:
    """A ``text/event-stream`` response; each item is ``(event name or None, data)``."""
    lines: list[str] = []
    for name, data in events:
        if name is not None:
            lines.append(f"event: {name}")
        payload = data if isinstance(data, str) else json.dumps(data)
        lines.append(f"data: {payload}")
        lines.append("")
    body = "\n".join(lines) + "\n"
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=body.encode()
    )


def json_response(status: int, body: object) -> httpx2.Response:
    return httpx2.Response(status, json=body)


@dataclass
class FakeHttp:
    """Answers every request with ``handler`` and keeps the requests for assertions."""

    handler: Handler
    requests: list[httpx2.Request] = field(default_factory=lambda: [])

    def client(self) -> httpx2.AsyncClient:
        def respond(request: httpx2.Request) -> httpx2.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx2.AsyncClient(transport=httpx2.MockTransport(respond))

    def body(self, index: int = 0) -> dict[str, object]:
        parsed: dict[str, object] = json.loads(self.requests[index].content)
        return parsed


def collect(stream: AsyncIterator[ChatEvent]) -> list[ChatEvent]:
    async def run() -> list[ChatEvent]:
        return [event async for event in stream]

    return asyncio.run(run())


def run[T](awaitable: Callable[[], Awaitable[T]]) -> T:
    async def main() -> T:
        return await awaitable()

    return asyncio.run(main())
