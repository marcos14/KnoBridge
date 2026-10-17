"""``retrieval`` of an answer in the panel (``docs/specs/chat.md``, "Desfecho e gravação"):
the summary of its searches, with the queries the model wrote. Only the panel shows it (the
owner's conversation and the administrative view); the public API, MCP and widget do not.
Not a router."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from knobridge.audit.models import JSONValue


class RetrievalSearchOut(BaseModel):
    step: int
    # ``null`` in step 1 (the question itself); the model's query in the others.
    query: str | None
    status: Literal["ok", "empty", "failed"]
    sources: int
    new_sources: int
    duration_ms: int


class RetrievalOut(BaseModel):
    version: int
    tools: Literal["off", "unsupported", "offered", "used"]
    reranked: bool
    searches: list[RetrievalSearchOut]


def retrieval_out(raw: dict[str, JSONValue] | None) -> RetrievalOut | None:
    """The stored summary as the API shows it; ``None`` for questions and older answers."""
    return None if raw is None else RetrievalOut.model_validate(raw)
