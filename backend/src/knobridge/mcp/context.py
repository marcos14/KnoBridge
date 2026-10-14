"""What an MCP tool call knows about its request: the API key and the app's services.

The ASGI wrapper of ``/v1/mcp`` (``mcp/auth.py``) authenticates the key before any MCP message
and binds a :class:`McpCall` to a ``ContextVar`` around the SDK's handler. In stateless mode the
SDK serves each request in a task spawned from that handler, which copies the context, so the
tools read the call of their own request (never another one served at the same time).
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.conversations.chat import ChatService
from knobridge.core.clock import Clock
from knobridge.retrieval.search import SearchService
from knobridge.tickets.delivery import TicketWebhookStarter
from knobridge.tickets.requests import TicketRequestService


@dataclass(frozen=True)
class McpServices:
    """The app's services the tools use: sessions, clock, the hybrid search, the chat turn
    (``ask``), the ticket requests and the starter of their delivery (``open_ticket``)."""

    factory: async_sessionmaker[AsyncSession]
    clock: Clock
    search: SearchService
    chat: ChatService
    tickets: TicketRequestService
    starter: TicketWebhookStarter


@dataclass(frozen=True)
class McpCall:
    identity: ApiKeyIdentity
    services: McpServices


_CURRENT: ContextVar[McpCall | None] = ContextVar("knobridge_mcp_call", default=None)


class McpContextMissingError(RuntimeError):
    """A tool ran outside an authenticated ``/v1/mcp`` request (a wiring bug)."""


def current_call() -> McpCall:
    call = _CURRENT.get()
    if call is None:
        raise McpContextMissingError("No authenticated MCP request in this context.")
    return call


def current_identity() -> ApiKeyIdentity:
    """The API key of the MCP request being served."""
    return current_call().identity


@contextmanager
def bound(call: McpCall) -> Generator[None]:
    """Bind ``call`` to the current context for the duration of the block."""
    token = _CURRENT.set(call)
    try:
        yield
    finally:
        _CURRENT.reset(token)
