"""The ``text/event-stream`` response of a chat turn (contract: ``docs/specs/chat-sse.md``).

Not a router: ``api/conversations.py`` returns a ``ChatEventStream`` from the route that sends
a message. FastAPI's native SSE (generator endpoints) is not used because it would run the
turn's preparation after the response started and after the workspace transaction closed;
here the route prepares (and commits) first and only then streams.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable

import anyio
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from knobridge.conversations.turn import ChatEvent, CitationsEvent, DeltaEvent, DoneEvent

SSE_MEDIA_TYPE = "text/event-stream"
# Turns the events into the body's bytes (default: the SSE frames of chat-sse.md).
type FrameEncoder = Callable[[AsyncIterator[ChatEvent]], AsyncGenerator[bytes]]


def sse_frame(event: ChatEvent) -> bytes:
    """One event in the ``text/event-stream`` wire format (``event:`` + JSON ``data:``)."""
    payload: dict[str, object]
    match event:
        case CitationsEvent():
            name = "citations"
            payload = {
                "message_id": str(event.message_id),
                "user_message_id": str(event.user_message_id),
                "product_id": None if event.product_id is None else str(event.product_id),
                "level": None if event.level is None else event.level.value,
                "citations": event.citations,
            }
        case DeltaEvent():
            name = "delta"
            payload = {"text": event.text}
        case DoneEvent():
            name = "done"
            payload = {
                "message_id": str(event.message_id),
                "status": event.status.value,
                "model": event.model,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cost_usd": None if event.cost_usd is None else float(event.cost_usd),
                "latency_ms": event.latency_ms,
                "ticket_requests_enabled": event.ticket_requests_enabled,
            }
        case _:  # ErrorEvent, the only type left
            name = "error"
            payload = {
                "message_id": str(event.message_id),
                "status": event.status.value,
                "error": {"code": event.code, "message": event.message, "details": event.details},
            }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {name}\ndata: {data}\n\n".encode()


class ChatEventStream(StreamingResponse):
    """SSE response that always closes its event generator and then runs ``on_close``.

    Starlette does not close the body iterator when the client disconnects (the send fails
    or the task is cancelled), so the generator's cleanup could wait for garbage collection.
    Closing it here, shielded from cancellation, runs that cleanup right away; ``on_close``
    then settles an answer whose stream never started. ``frames`` encodes the events (the
    OpenAI-compatible API sends its own chunks, ``openai_wire.py``).
    """

    media_type = SSE_MEDIA_TYPE

    def __init__(
        self,
        events: AsyncGenerator[ChatEvent],
        on_close: Callable[[], Awaitable[None]],
        frames: FrameEncoder | None = None,
    ) -> None:
        self._events = events
        self._on_close = on_close
        self._frames = (frames or _frames)(events)
        super().__init__(
            self._frames, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with anyio.CancelScope(shield=True):
                await self._frames.aclose()
                await self._events.aclose()
                await self._on_close()


async def _frames(events: AsyncIterator[ChatEvent]) -> AsyncGenerator[bytes]:
    async for event in events:
        yield sse_frame(event)
