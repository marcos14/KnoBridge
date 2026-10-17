"""The OpenAI-compatible API (``GET /v1/models``, ``POST /v1/chat/completions``), opened by an
API key (``docs/specs/api-publica.md``, "API compatível com OpenAI").

A model is a product of the key's scope, optionally with a level (``<product>[:<level>]``;
without a level, the key's maximum). Every completion creates a new ``channel = api``
conversation of the key that saves only the question (the last user message) and the answer;
the client's earlier messages are context for the LLM, never sources. The turn is the panel's
(``ChatService`` with an ``ApiKeyReader``): retrieval, rule 8 and the two phases. Errors leave
in OpenAI's shape (``openai_errors.OpenAIRoute``); the wire format is in ``openai_wire.py``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import anyio
from fastapi import APIRouter, Response

from knobridge.api.api_key_deps import ApiKeyContextDep, ApiKeyIdentityDep
from knobridge.api.chat_stream import SSE_MEDIA_TYPE, ChatEventStream
from knobridge.api.conversations import CitationOut
from knobridge.api.deps import ChatServiceDep, ClockDep, SessionFactoryDep
from knobridge.api.openai_errors import OpenAIRoute, classify
from knobridge.api.openai_wire import (
    AskedQuestion,
    CompletionStream,
    OpenAIAnswerMessage,
    OpenAIChatCompletion,
    OpenAIChatCompletionRequest,
    OpenAIChoice,
    OpenAICompletionExtra,
    OpenAIModel,
    OpenAIModelExtra,
    OpenAIModelList,
    OpenAIUsage,
    map_messages,
    refuse_parameters,
    sources_footer,
    usage_of,
    with_history,
)
from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.apikeys.conversations import create_key_conversation, get_message
from knobridge.apikeys.products import KeyModel, key_models, list_key_products, resolve_model
from knobridge.conversations.chat import ChatService
from knobridge.conversations.turn import ChatEvent, ErrorEvent, PreparedTurn, StepEvent
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger

_log = get_logger(__name__)

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "Missing, malformed, unknown or revoked key (`invalid_api_key`)."},
    403: {"description": "Workspace of the key suspended (`workspace_suspended`)."},
    404: {
        "description": "Product missing, inactive or outside the key's scope (`model_not_found`)."
    },
}
_MODEL_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Workspace of the key suspended (`workspace_suspended`) or a level above "
        "the key's maximum (`level_not_allowed`)."
    },
}
_COMPLETION_ERRORS: dict[int | str, dict[str, object]] = {
    200: {
        "description": "With `stream: true`, `chat.completion.chunk` lines (`data: {...}`) "
        "ending in `data: [DONE]`. With `stream: false`, the completion as JSON.",
        "content": {SSE_MEDIA_TYPE: {"schema": {"type": "string"}}},
    },
    400: {
        "description": "Invalid body, refused parameter or messages, or a level without a model "
        "(`level_not_configured`) (OpenAI error shape)."
    },
    **_MODEL_ERRORS,
    413: {"description": "Body above 1 MiB (`payload_too_large`)."},
    429: {"description": "Provider rate limit (`provider_rate_limited`)."},
    502: {"description": "The provider failed (`provider_*`, `embedding_*`)."},
    503: {"description": "The provider is unavailable (`provider_unavailable`)."},
}

router = APIRouter(tags=["openai-compatible"], route_class=OpenAIRoute)


def _model_out(model: KeyModel, model_id: str | None = None) -> OpenAIModel:
    product = model.product
    if model_id is None:
        model_id = f"{product.name}:{model.level}" if model.level_explicit else product.name
    return OpenAIModel(
        id=model_id,
        created=int(product.created_at.timestamp()),
        knobridge=OpenAIModelExtra(
            product_id=product.id,
            level=model.level,
            level_explicit=model.level_explicit,
            description=product.description,
        ),
    )


@router.get("/models", responses=_ERRORS)
async def list_models(context: ApiKeyContextDep) -> OpenAIModelList:
    """The combinations the key may ask: per active product of its scope, by name, the product
    alone (the key's maximum level) and then ``<product>:<level>`` up to that maximum."""
    products = await list_key_products(context.db, context.identity)
    return OpenAIModelList(
        data=[_model_out(model) for model in key_models(context.identity, products)]
    )


@router.get("/models/{model:path}", responses=_MODEL_ERRORS)
async def get_model(model: str, context: ApiKeyContextDep) -> OpenAIModel:
    """One model, in any form ``model`` accepts (product name or id, with or without a level),
    with ``id`` equal to the value asked."""
    return _model_out(await resolve_model(context.db, context.identity, model), model)


async def _prepare(
    chat: ChatService,
    factory: SessionFactoryDep,
    identity: ApiKeyIdentity,
    model: str,
    asked: AskedQuestion,
) -> tuple[KeyModel, PreparedTurn]:
    """A new conversation of the key with the question saved (rolled back on any error)."""
    async with scoped_session(factory, workspace_id=identity.workspace_id, user_id=None) as db:
        resolved = await resolve_model(db, identity, model)
        conversation = await create_key_conversation(
            db, identity, resolved.product.id, resolved.level
        )
        turn = await chat.prepare(
            db,
            workspace_id=identity.workspace_id,
            conversation_id=conversation.id,
            reader=identity.reader,
            question=asked.question,
        )
        return resolved, turn


async def _consume(chat: ChatService, turn: PreparedTurn) -> ErrorEvent | None:
    """Run the whole turn; its ``error`` event, if the provider failed."""
    events = chat.stream(turn)
    failure: ErrorEvent | None = None
    try:
        async for event in events:
            if isinstance(event, ErrorEvent):
                failure = event
    finally:
        # Shielded: a client gone mid-answer still leaves the message settled.
        with anyio.CancelScope(shield=True):
            await events.aclose()
            await chat.settle(turn)
    return failure


class _SavedAnswer:
    """Reads the saved answer of a turn in its own short transaction."""

    def __init__(
        self, factory: SessionFactoryDep, clock: Clock, turn: PreparedTurn, model: KeyModel
    ) -> None:
        self._factory, self._clock, self._turn, self._model = factory, clock, turn, model

    async def read(self) -> tuple[str, OpenAICompletionExtra, OpenAIUsage | None]:
        turn = self._turn
        async with scoped_session(
            self._factory, workspace_id=turn.workspace_id, user_id=None
        ) as db:
            view = await get_message(
                db,
                workspace_id=turn.workspace_id,
                message_id=turn.message_id,
                now=self._clock.now(),
            )
        message = view.message
        extra = OpenAICompletionExtra(
            conversation_id=turn.conversation_id,
            message_id=message.id,
            product_id=self._model.product.id,
            level=self._model.level,
            status=view.status,
            citations=[CitationOut.model_validate(item) for item in message.citations],
            cost_usd=None if message.cost_usd is None else float(message.cost_usd),
            steps=message.steps,
        )
        usage = usage_of(view.status, message.input_tokens, message.output_tokens, message.model)
        return message.content, extra, usage

    async def cost(self) -> float | None:
        _, extra, _ = await self.read()
        return extra.cost_usd


@router.post("/chat/completions", response_model=OpenAIChatCompletion, responses=_COMPLETION_ERRORS)
async def create_chat_completion(
    body: OpenAIChatCompletionRequest,
    identity: ApiKeyIdentityDep,
    factory: SessionFactoryDep,
    chat: ChatServiceDep,
    clock: ClockDep,
) -> Response | OpenAIChatCompletion:
    """Ask a product, at the level of ``model``, in a new conversation of the key, as OpenAI's
    Chat Completions."""
    refuse_parameters(body)
    asked = map_messages(body.messages)
    resolved, turn = await _prepare(chat, factory, identity, body.model, asked)
    with_history(turn, asked.history)
    _log.info(
        "openai_completion_received",
        workspace_id=str(identity.workspace_id),
        api_key_id=str(identity.api_key_id),
        conversation_id=str(turn.conversation_id),
        stream=body.stream,
        history=len(asked.history),
    )
    completion_id = f"chatcmpl-{turn.message_id.hex}"
    created = int(turn.started_at.timestamp())
    append_sources = body.knobridge is None or body.knobridge.append_sources
    saved = _SavedAnswer(factory, clock, turn, resolved)
    if body.stream:
        stream = CompletionStream(
            completion_id=completion_id,
            created=created,
            model=body.model,
            conversation_id=turn.conversation_id,
            product_id=resolved.product.id,
            level=resolved.level,
            append_sources=append_sources,
            include_usage=body.stream_options is not None and body.stream_options.include_usage,
            cost=saved.cost,
        )
        return await _streamed(chat, turn, stream)
    failure = await _consume(chat, turn)
    if failure is not None:
        raise _failure_error(failure)
    content, extra, usage = await saved.read()
    if append_sources:
        content += sources_footer([item.model_dump() for item in extra.citations])
    return OpenAIChatCompletion(
        id=completion_id,
        created=created,
        model=body.model,
        choices=[OpenAIChoice(message=OpenAIAnswerMessage(content=content))],
        usage=usage,
        knobridge=extra,
    )


async def _first_chunk(events: AsyncGenerator[ChatEvent]) -> ChatEvent:
    """The first event that becomes a chunk (search steps have none); every turn ends with
    ``done`` or ``error``."""
    event = await anext(events)
    while isinstance(event, StepEvent):
        event = await anext(events)
    return event


async def _replay(head: ChatEvent, events: AsyncGenerator[ChatEvent]) -> AsyncGenerator[ChatEvent]:
    yield head
    async for event in events:
        yield event


async def _streamed(chat: ChatService, turn: PreparedTurn, stream: CompletionStream) -> Response:
    """The streamed completion, started only at its first chunk: after the search steps, so a
    provider error in a search round still leaves as a mapped JSON error with its status."""
    events = chat.stream(turn)

    async def close() -> None:
        # Shielded: a client gone mid-answer still leaves the message settled.
        with anyio.CancelScope(shield=True):
            await events.aclose()
            await chat.settle(turn)

    started = False
    try:
        head = await _first_chunk(events)
        if isinstance(head, ErrorEvent):
            raise _failure_error(head)
        started = True
    finally:
        if not started:
            await close()
    return ChatEventStream(_replay(head, events), on_close=close, frames=stream.frames)


def _failure_error(failure: ErrorEvent) -> KnoBridgeError:
    error = classify(failure.code, 500, failure.message)
    return KnoBridgeError(error.message, code=error.code, status_code=error.status)
