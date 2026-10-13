"""The workspace dashboard (home screen): cards and the first steps checklist, two statements.

Runs in the caller's workspace-scoped session; every subquery filters by ``workspace_id``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ColumnElement,
    ColumnExpressionArgument,
    Exists,
    ScalarSelect,
    exists,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.conversations.admin import as_utc
from knobridge.conversations.models import (
    Conversation,
    Feedback,
    FeedbackRating,
    Message,
    MessageRole,
    MessageStatus,
)
from knobridge.core.models import Base
from knobridge.ingestion.models import Collection, Document, Run, RunStatus, Source
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.llm.models import ProviderCredential
from knobridge.products.models import Product, ProductCollection
from knobridge.usage.period import Period
from knobridge.usage.report import answers_in, runs_in

RECENT_FAILURES = timedelta(days=7)
# Order of the setup flow; the panel shows the pending ones.
CHECKLIST_KEYS = ("provider", "collection", "source", "levels", "product", "chat")


@dataclass(frozen=True)
class MonthCost:
    embedding_cost_usd: Decimal
    chat_cost_usd: Decimal
    # Some run or answer of the month had no price.
    partial: bool

    @property
    def cost_usd(self) -> Decimal:
        return self.embedding_cost_usd + self.chat_cost_usd


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    done: bool


@dataclass(frozen=True)
class WorkspaceDashboard:
    month_start: datetime
    documents: int
    sources_total: int
    sources_active: int
    failed_runs: int
    conversations_month: int
    feedback_up: int
    feedback_down: int
    # ``None`` unless the caller may see costs (owner and admin).
    cost_month: MonthCost | None
    checklist: list[ChecklistItem]


def month_start(now: datetime) -> datetime:
    """First instant of the current month, in UTC."""
    return as_utc(now).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _count(model: type[Base], *conditions: ColumnElement[bool]) -> ScalarSelect[int]:
    return select(func.count()).select_from(model).where(*conditions).scalar_subquery()


def _sum(
    column: ColumnExpressionArgument[Any], *conditions: ColumnElement[bool]
) -> ScalarSelect[Decimal]:
    return select(func.coalesce(func.sum(column), 0)).where(*conditions).scalar_subquery()


def _feedback(
    workspace_id: uuid.UUID, since: datetime, rating: FeedbackRating
) -> ScalarSelect[int]:
    return (
        select(func.count())
        .select_from(Feedback)
        .join(
            Message,
            (Message.workspace_id == Feedback.workspace_id) & (Message.id == Feedback.message_id),
        )
        .where(
            Feedback.workspace_id == workspace_id,
            Feedback.rating == rating,
            Message.created_at >= since,
        )
        .scalar_subquery()
    )


async def _cards(db: AsyncSession, workspace_id: uuid.UUID, now: datetime) -> tuple[Any, ...]:
    month = Period(start=month_start(now), end=datetime.max.replace(tzinfo=now.tzinfo))
    runs, answers = runs_in(month, workspace_id), answers_in(month, workspace_id)
    row = (
        await db.execute(
            select(
                _count(Document, Document.workspace_id == workspace_id),
                _count(Source, Source.workspace_id == workspace_id),
                _count(Source, Source.workspace_id == workspace_id, Source.active.is_(True)),
                _count(
                    Run,
                    Run.workspace_id == workspace_id,
                    Run.status == RunStatus.FAILED,
                    Run.finished_at >= now - RECENT_FAILURES,
                ),
                _count(
                    Conversation,
                    Conversation.workspace_id == workspace_id,
                    Conversation.created_at >= month.start,
                ),
                _feedback(workspace_id, month.start, FeedbackRating.UP),
                _feedback(workspace_id, month.start, FeedbackRating.DOWN),
                _sum(Run.cost_usd, *runs),
                _sum(Message.cost_usd, *answers),
                exists().where(*runs, Run.cost_usd.is_(None))
                | exists().where(*answers, Message.cost_usd.is_(None)),
            )
        )
    ).one()
    return tuple(row)


def _checklist_conditions(workspace_id: uuid.UUID) -> list[Exists]:
    return [
        exists().where(ProviderCredential.workspace_id == workspace_id),
        exists().where(Collection.workspace_id == workspace_id),
        exists().where(
            Source.workspace_id == workspace_id,
            Run.workspace_id == Source.workspace_id,
            Run.source_id == Source.id,
            Run.status == RunStatus.SUCCEEDED,
        ),
        # The end-user level answers: the level every member asks at by default.
        exists().where(
            WorkspaceLevel.workspace_id == workspace_id,
            WorkspaceLevel.level == ResponseLevel.END_USER,
            WorkspaceLevel.model.is_not(None),
        ),
        exists().where(
            Product.workspace_id == workspace_id,
            Product.active.is_(True),
            ProductCollection.workspace_id == Product.workspace_id,
            ProductCollection.product_id == Product.id,
        ),
        exists().where(
            Message.workspace_id == workspace_id,
            Message.role == MessageRole.ASSISTANT,
            Message.status == MessageStatus.COMPLETED,
            func.jsonb_array_length(Message.citations) > 0,
        ),
    ]


async def workspace_dashboard(
    db: AsyncSession, *, workspace_id: uuid.UUID, now: datetime, with_cost: bool
) -> WorkspaceDashboard:
    """The cards and the checklist (two statements); the cost only ``with_cost``."""
    cards = await _cards(db, workspace_id, now)
    done = (await db.execute(select(*_checklist_conditions(workspace_id)))).one()
    cost = MonthCost(embedding_cost_usd=cards[7], chat_cost_usd=cards[8], partial=cards[9])
    return WorkspaceDashboard(
        month_start=month_start(now),
        documents=cards[0],
        sources_total=cards[1],
        sources_active=cards[2],
        failed_runs=cards[3],
        conversations_month=cards[4],
        feedback_up=cards[5],
        feedback_down=cards[6],
        cost_month=cost if with_cost else None,
        checklist=[
            ChecklistItem(key=key, done=bool(value))
            for key, value in zip(CHECKLIST_KEYS, done, strict=True)
        ],
    )
