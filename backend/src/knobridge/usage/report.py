"""The usage report of a workspace: tokens and estimated USD of embeddings and chat in a period.

Embedding usage comes from the runs closed in the period (``runs.finished_at``: the cost is
only set when a run closes); chat usage from the answers that called the LLM (assistant
messages with a ``model``), by their creation time. Unknown costs are never zero: sums take
the known costs only and the unpriced items are counted apart. One statement for the totals
and one for the rows, whatever the number of rows (``docs/specs/uso-e-custos.md``). Each
answer keeps the product and level of its conversation, so grouping and filtering by them
needs no join; embeddings belong to no product nor level and leave a filtered report.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    ColumnExpressionArgument,
    Numeric,
    Select,
    String,
    cast,
    func,
    literal,
    literal_column,
    select,
    true,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.models import ApiKey
from knobridge.conversations.models import (
    Conversation,
    ConversationChannel,
    Message,
    MessageRole,
)
from knobridge.core.errors import ValidationError
from knobridge.ingestion.models import Collection, Run, Source
from knobridge.levels.level import ResponseLevel, level_rank
from knobridge.products.models import Product
from knobridge.usage.period import Period
from knobridge.widget.models import Widget

ZERO = Decimal(0)
CHANNEL_LABELS = {
    ConversationChannel.PANEL: "Painel",
    ConversationChannel.API: "API",
    ConversationChannel.MCP: "MCP",
    ConversationChannel.WIDGET: "Widget",
}
# The channels where a key asks (``group_by=api_key``).
KEY_CHANNELS = (ConversationChannel.API, ConversationChannel.MCP)
_EMBEDDING, _CHAT = "embedding", "chat"
# Inlined (not bound) so the expression in SELECT and in GROUP BY is the same text.
_UTC = literal_column("'UTC'", String())
_DAY_FORMAT = literal_column("'YYYY-MM-DD'", String())


class UsageGroup(StrEnum):
    SOURCE = "source"
    COLLECTION = "collection"
    PRODUCT = "product"
    LEVEL = "level"
    CHANNEL = "channel"
    API_KEY = "api_key"
    WIDGET = "widget"
    MODEL = "model"
    DAY = "day"


_EMBEDDING_GROUPS = {UsageGroup.SOURCE, UsageGroup.COLLECTION, UsageGroup.MODEL, UsageGroup.DAY}
_CHAT_GROUPS = {
    UsageGroup.PRODUCT,
    UsageGroup.LEVEL,
    UsageGroup.CHANNEL,
    UsageGroup.API_KEY,
    UsageGroup.WIDGET,
    UsageGroup.MODEL,
    UsageGroup.DAY,
}


class UsageFilterInvalidError(ValidationError):
    """A product or level filter with a grouping that only has embeddings."""


@dataclass(frozen=True)
class ChatFilter:
    """Narrows the chat answers to a product and/or a level (``messages.product_id`` and
    ``messages.level``). Embeddings belong to neither, so a filtered report leaves them out."""

    product_id: uuid.UUID | None = None
    level: ResponseLevel | None = None

    @property
    def active(self) -> bool:
        return self.product_id is not None or self.level is not None


@dataclass(frozen=True)
class EmbeddingUsage:
    tokens: int = 0
    cost_usd: Decimal = ZERO
    runs: int = 0
    unpriced_runs: int = 0


@dataclass(frozen=True)
class ChatUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = ZERO
    answers: int = 0
    unpriced_answers: int = 0
    # Searches of the answers (``messages.steps``; null counts 0).
    searches: int = 0


@dataclass(frozen=True)
class UsageTotals:
    # ``None`` when the report is filtered by product or level.
    embedding: EmbeddingUsage | None
    chat: ChatUsage

    @property
    def cost_usd(self) -> Decimal:
        embedding = ZERO if self.embedding is None else self.embedding.cost_usd
        return embedding + self.chat.cost_usd


@dataclass(frozen=True)
class UsageRow:
    """One group; the side that does not apply to it is ``None`` (not zero)."""

    key: str
    label: str
    embedding: EmbeddingUsage | None = None
    chat: ChatUsage | None = None

    @property
    def cost_usd(self) -> Decimal:
        parts = (self.embedding, self.chat)
        return sum((part.cost_usd for part in parts if part is not None), ZERO)


@dataclass(frozen=True)
class UsageReport:
    period: Period
    group_by: UsageGroup
    totals: UsageTotals
    rows: list[UsageRow]
    # The product and level filter of the chat side, when any.
    chat_filter: ChatFilter | None = None


def runs_in(period: Period, workspace_id: uuid.UUID | None) -> list[ColumnElement[bool]]:
    """Runs closed in the period (of one workspace, or of all in system mode)."""
    conditions = [Run.finished_at >= period.start, Run.finished_at < period.end]
    if workspace_id is not None:
        conditions.append(Run.workspace_id == workspace_id)
    return conditions


def answers_in(
    period: Period, workspace_id: uuid.UUID | None, chat: ChatFilter | None = None
) -> list[ColumnElement[bool]]:
    """Answers that called the LLM, created in the period (and of the product and level of
    ``chat``, when given)."""
    conditions = [
        Message.role == MessageRole.ASSISTANT,
        Message.model.is_not(None),
        Message.created_at >= period.start,
        Message.created_at < period.end,
    ]
    if workspace_id is not None:
        conditions.append(Message.workspace_id == workspace_id)
    if chat is not None and chat.product_id is not None:
        conditions.append(Message.product_id == chat.product_id)
    if chat is not None and chat.level is not None:
        conditions.append(Message.level == chat.level)
    return conditions


def _int_sum(column: ColumnExpressionArgument[Any]) -> ColumnElement[int]:
    return cast(func.coalesce(func.sum(column), 0), BigInteger)


def _cost_sum(column: ColumnExpressionArgument[Any]) -> ColumnElement[Decimal]:
    return cast(func.coalesce(func.sum(column), 0), Numeric(18, 6))


def _count(where: ColumnElement[bool] | None = None) -> ColumnElement[int]:
    counted = func.count() if where is None else func.count().filter(where)
    return cast(counted, BigInteger)


def _embedding_values() -> tuple[ColumnElement[Any], ...]:
    """Six generic columns, aligned with ``_chat_values`` for the union of the rows."""
    return (
        _int_sum(Run.embedding_tokens),
        cast(literal(0), BigInteger),
        _cost_sum(Run.cost_usd),
        _count(),
        _count(Run.cost_usd.is_(None)),
        cast(literal(0), BigInteger),
    )


def _chat_values() -> tuple[ColumnElement[Any], ...]:
    return (
        _int_sum(Message.input_tokens),
        _int_sum(Message.output_tokens),
        _cost_sum(Message.cost_usd),
        _count(),
        _count(Message.cost_usd.is_(None)),
        _int_sum(Message.steps),
    )


def _embedding(values: Sequence[Any]) -> EmbeddingUsage:
    return EmbeddingUsage(
        tokens=values[0], cost_usd=values[2], runs=values[3], unpriced_runs=values[4]
    )


def _chat(values: Sequence[Any]) -> ChatUsage:
    return ChatUsage(
        input_tokens=values[0],
        output_tokens=values[1],
        cost_usd=values[2],
        answers=values[3],
        unpriced_answers=values[4],
        searches=values[5],
    )


async def usage_totals(
    db: AsyncSession,
    period: Period,
    workspace_id: uuid.UUID | None,
    chat_filter: ChatFilter | None = None,
) -> UsageTotals:
    """Totals of the period in one statement (``workspace_id=None``: the whole instance).
    Filtered by product or level, only the chat side (embeddings are ``None``)."""
    chat = select(*_chat_values()).where(*answers_in(period, workspace_id, chat_filter))
    if chat_filter is not None and chat_filter.active:
        return UsageTotals(embedding=None, chat=_chat((await db.execute(chat)).one()))
    embedding = select(*_embedding_values()).where(*runs_in(period, workspace_id)).subquery()
    answers = chat.subquery()
    row = (
        await db.execute(
            select(*embedding.c, *answers.c).select_from(embedding.join(answers, true()))
        )
    ).one()
    return UsageTotals(embedding=_embedding(row[:6]), chat=_chat(row[6:]))


def _day(column: ColumnExpressionArgument[Any]) -> ColumnElement[str]:
    return func.to_char(func.timezone(_UTC, column), _DAY_FORMAT)


def _embedding_part(
    group: UsageGroup, period: Period, workspace_id: uuid.UUID
) -> Select[Any] | None:
    if group not in _EMBEDDING_GROUPS:
        return None
    source_join = (Source.workspace_id == Run.workspace_id) & (Source.id == Run.source_id)
    collection_join = (Collection.workspace_id == Source.workspace_id) & (
        Collection.id == Source.collection_id
    )
    base = select().select_from(Run).where(*runs_in(period, workspace_id))
    if group is UsageGroup.SOURCE:
        key, label = cast(Source.id, String), Source.name
        base = base.join(Source, source_join).group_by(Source.id, Source.name)
    elif group is UsageGroup.COLLECTION:
        key, label = cast(Collection.id, String), Collection.name
        base = (
            base.join(Source, source_join)
            .join(Collection, collection_join)
            .group_by(Collection.id, Collection.name)
        )
    elif group is UsageGroup.MODEL:
        key = label = Collection.embedding_model
        base = (
            base.join(Source, source_join)
            .join(Collection, collection_join)
            .group_by(Collection.embedding_model)
        )
    else:
        key = label = _day(Run.finished_at)
        base = base.group_by(key)
    return base.add_columns(literal_column(f"'{_EMBEDDING}'"), key, label, *_embedding_values())


def _chat_part(
    group: UsageGroup, period: Period, workspace_id: uuid.UUID, chat: ChatFilter
) -> Select[Any] | None:
    if group not in _CHAT_GROUPS:
        return None
    conversation_join = (Conversation.workspace_id == Message.workspace_id) & (
        Conversation.id == Message.conversation_id
    )
    base = select().select_from(Message).where(*answers_in(period, workspace_id, chat))
    if group is UsageGroup.PRODUCT:
        # The message keeps its product: no join with the conversation.
        key, label = cast(Product.id, String), Product.name
        base = base.join(
            Product,
            (Product.workspace_id == Message.workspace_id) & (Product.id == Message.product_id),
        ).group_by(Product.id, Product.name)
    elif group is UsageGroup.LEVEL:
        key = label = cast(Message.level, String)
        base = base.group_by(Message.level)
    elif group is UsageGroup.API_KEY:
        key, label = cast(ApiKey.id, String), ApiKey.name
        base = (
            base.join(Conversation, conversation_join)
            .join(
                ApiKey,
                (ApiKey.workspace_id == Conversation.workspace_id)
                & (ApiKey.id == Conversation.api_key_id),
            )
            .where(Message.channel.in_(KEY_CHANNELS))
            .group_by(ApiKey.id, ApiKey.name)
        )
    elif group is UsageGroup.WIDGET:
        key, label = cast(Widget.id, String), Widget.name
        base = (
            base.join(Conversation, conversation_join)
            .join(
                Widget,
                (Widget.workspace_id == Conversation.workspace_id)
                & (Widget.id == Conversation.widget_id),
            )
            .where(Message.channel == ConversationChannel.WIDGET)
            .group_by(Widget.id, Widget.name)
        )
    elif group is UsageGroup.CHANNEL:
        key = label = cast(Message.channel, String)
        base = base.group_by(Message.channel)
    elif group is UsageGroup.MODEL:
        key = label = cast(Message.model, String)
        base = base.group_by(Message.model)
    else:
        key = label = _day(Message.created_at)
        base = base.group_by(key)
    return base.add_columns(literal_column(f"'{_CHAT}'"), key, label, *_chat_values())


def _days(period: Period) -> list[str]:
    first = period.start.date()
    last = (period.end - timedelta(microseconds=1)).date()
    return [
        (first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)
    ]


def _seed(group: UsageGroup, period: Period, *, chat_only: bool) -> dict[str, UsageRow]:
    """Rows that exist even without usage: every day of the period (without the embedding
    side when the report is filtered by product or level), every channel, the three levels."""
    if group is UsageGroup.DAY:
        embedding = None if chat_only else EmbeddingUsage()
        return {
            day: UsageRow(key=day, label=day, embedding=embedding, chat=ChatUsage())
            for day in _days(period)
        }
    if group is UsageGroup.CHANNEL:
        return {
            channel.value: UsageRow(key=channel.value, label=label, chat=ChatUsage())
            for channel, label in CHANNEL_LABELS.items()
        }
    if group is UsageGroup.LEVEL:
        return {
            level.value: UsageRow(key=level.value, label=level.value, chat=ChatUsage())
            for level in ResponseLevel
        }
    return {}


def _merge(
    group: UsageGroup, period: Period, rows: Iterable[Sequence[Any]], *, chat_only: bool
) -> list[UsageRow]:
    merged = _seed(group, period, chat_only=chat_only)
    for kind, key, label, *values in rows:
        row = merged.get(key) or UsageRow(key=key, label=label)
        if kind == _EMBEDDING:
            row = replace(row, embedding=_embedding(values))
        else:
            row = replace(row, chat=_chat(values))
        merged[key] = row
    if group is UsageGroup.DAY:
        return sorted(merged.values(), key=lambda row: date.fromisoformat(row.key))
    if group is UsageGroup.LEVEL:
        return sorted(merged.values(), key=lambda row: level_rank(ResponseLevel(row.key)))
    return sorted(merged.values(), key=lambda row: (-row.cost_usd, row.label))


async def usage_rows(
    db: AsyncSession,
    period: Period,
    workspace_id: uuid.UUID,
    group: UsageGroup,
    chat_filter: ChatFilter | None = None,
) -> list[UsageRow]:
    """The rows of ``group`` in one statement (embedding and chat sides in a union; only the
    chat side when filtered by product or level)."""
    chat = chat_filter or ChatFilter()
    embedding = None if chat.active else _embedding_part(group, period, workspace_id)
    parts = [
        part
        for part in (embedding, _chat_part(group, period, workspace_id, chat))
        if part is not None
    ]
    statement = parts[0] if len(parts) == 1 else union_all(*parts)
    result = await db.execute(statement)
    return _merge(group, period, result.all(), chat_only=chat.active)


async def usage_report(
    db: AsyncSession,
    *,
    period: Period,
    workspace_id: uuid.UUID,
    group: UsageGroup,
    chat_filter: ChatFilter | None = None,
) -> UsageReport:
    """Totals and rows of the workspace's usage in ``period`` (two statements). A product or
    level filter with a grouping that only has embeddings is 422 ``validation_error``."""
    if chat_filter is not None and chat_filter.active and group not in _CHAT_GROUPS:
        raise UsageFilterInvalidError(
            "The product and level filters only apply to groupings with chat answers.",
            details=[
                {
                    "loc": ["query", "group_by"],
                    "msg": "product_id and level need a grouping with chat answers.",
                    "type": "value_error",
                }
            ],
        )
    totals = await usage_totals(db, period, workspace_id, chat_filter)
    rows = await usage_rows(db, period, workspace_id, group, chat_filter)
    return UsageReport(
        period=period, group_by=group, totals=totals, rows=rows, chat_filter=chat_filter
    )
