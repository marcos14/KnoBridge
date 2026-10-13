"""The level configuration of a workspace: credential, model, temperature and instructions of
each level (``docs/specs/produtos-e-niveis.md``, "Configuração dos níveis no workspace").

Runs in the caller's workspace-scoped session. The credential must belong to the same
workspace: it is looked up under the workspace filter (and RLS) and locked with
``FOR KEY SHARE`` until the transaction ends; the composite foreign key is the last barrier.
``instructions`` ``None`` keeps the KnoBridge default text (``defaults.py``). The audit
carries the level, the changed fields and the new credential and model, never the
instructions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, ValidationError
from knobridge.levels.defaults import default_instructions
from knobridge.levels.level import ResponseLevel, level_rank
from knobridge.levels.models import WorkspaceLevel
from knobridge.llm.chat_pricing import ChatPriceTable, ModelPrice
from knobridge.llm.models import ProviderCredential, ProviderKind

# Reference answer of the cost estimate shown next to each level.
REFERENCE_INPUT_TOKENS = 4000
REFERENCE_OUTPUT_TOKENS = 600


class LevelProviderInvalidError(ValidationError):
    code = "level_provider_invalid"


class LevelNotConfiguredError(ConflictError):
    """The level has no credential and model in the workspace (``details.level``)."""

    code = "level_not_configured"


@dataclass(frozen=True)
class LevelView:
    """One level of the workspace as the API shows it."""

    level: ResponseLevel
    provider_id: uuid.UUID | None
    provider_name: str | None
    provider_kind: ProviderKind | None
    model: str | None
    temperature: float
    instructions: str
    instructions_is_default: bool
    default_instructions: str
    price: ModelPrice | None
    estimated_cost_per_answer_usd: Decimal | None
    updated_at: datetime

    @property
    def configured(self) -> bool:
        return self.provider_id is not None and self.model is not None


@dataclass(frozen=True)
class LevelChanges:
    """Fields to change, each applied only when its ``*_given`` flag is set (``None`` then
    clears the credential or the model, or restores the default instructions)."""

    provider_id: uuid.UUID | None = None
    provider_id_given: bool = False
    model: str | None = None
    model_given: bool = False
    temperature: float | None = None
    instructions: str | None = None
    instructions_given: bool = False


@dataclass(frozen=True)
class AnswerSettings:
    """What an answer of a level uses: the credential, model and temperature, and the
    instructions (the workspace's text, or the KnoBridge default)."""

    level: ResponseLevel
    credential: ProviderCredential
    model: str
    temperature: float
    instructions: str


def _invalid(field: str, message: str) -> ValidationError:
    return ValidationError(
        "Request validation failed.",
        details=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def not_configured(level: ResponseLevel) -> LevelNotConfiguredError:
    return LevelNotConfiguredError(
        "The level has no provider and model in this workspace.",
        details={"level": level.value},
    )


async def answer_settings(
    db: AsyncSession, *, workspace_id: uuid.UUID, level: ResponseLevel
) -> AnswerSettings:
    """The configuration of ``level`` with its credential (one query); 409
    ``level_not_configured`` when the level has no credential and model (the inner join
    finds no row: credential and model are set or cleared together)."""
    row = (
        await db.execute(
            select(WorkspaceLevel, WorkspaceLevel.model, ProviderCredential)
            .join(
                ProviderCredential,
                (ProviderCredential.workspace_id == WorkspaceLevel.workspace_id)
                & (ProviderCredential.id == WorkspaceLevel.credential_id),
            )
            .where(
                WorkspaceLevel.workspace_id == workspace_id,
                WorkspaceLevel.level == level,
                WorkspaceLevel.model.is_not(None),
            )
        )
    ).one_or_none()
    if row is None:
        raise not_configured(level)
    settings, model, credential = row
    assert model is not None  # noqa: S101 - filtered by the query above
    return AnswerSettings(
        level=level,
        credential=credential,
        model=model,
        temperature=settings.temperature,
        instructions=(
            default_instructions(level) if settings.instructions is None else settings.instructions
        ),
    )


class WorkspaceLevelService:
    def __init__(self, clock: Clock, prices: ChatPriceTable) -> None:
        self._audit = AuditService(clock)
        self._prices = prices

    async def list_levels(self, db: AsyncSession, *, workspace_id: uuid.UUID) -> list[LevelView]:
        """The three levels in order, with the name and kind of their credential."""
        rows = await db.execute(
            select(WorkspaceLevel, ProviderCredential.name, ProviderCredential.kind)
            .outerjoin(
                ProviderCredential,
                (ProviderCredential.workspace_id == WorkspaceLevel.workspace_id)
                & (ProviderCredential.id == WorkspaceLevel.credential_id),
            )
            .where(WorkspaceLevel.workspace_id == workspace_id)
        )
        views = [self._view(row, name, kind) for row, name, kind in rows]
        return sorted(views, key=lambda view: level_rank(view.level))

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        level: ResponseLevel,
        changes: LevelChanges,
        ip: str | None,
    ) -> LevelView:
        """Apply the given fields; audited only when something actually changes."""
        row = await self._get(db, workspace_id, level)
        credential_id = changes.provider_id if changes.provider_id_given else row.credential_id
        model = changes.model if changes.model_given else row.model
        if (credential_id is None) != (model is None):
            raise _invalid(
                "model" if model is None else "provider_id",
                "provider_id and model are set or cleared together.",
            )
        if changes.provider_id_given and changes.provider_id is not None:
            await self._lock_credential(db, workspace_id, changes.provider_id)
        wanted: dict[str, tuple[bool, object]] = {
            "credential_id": (changes.provider_id_given, changes.provider_id),
            "model": (changes.model_given, changes.model),
            "temperature": (changes.temperature is not None, changes.temperature),
            "instructions": (changes.instructions_given, changes.instructions),
        }
        fields: list[str] = []
        for attribute, (given, value) in wanted.items():
            if given and value != getattr(row, attribute):
                setattr(row, attribute, value)
                fields.append("provider_id" if attribute == "credential_id" else attribute)
        if fields:
            await db.flush()
            # ``updated_at`` is set by the database; load it now (no lazy IO in async code).
            await db.refresh(row)
            metadata: dict[str, JSONValue] = {"level": level.value, "fields": list(fields)}
            if "provider_id" in fields:
                metadata["provider_id"] = (
                    None if row.credential_id is None else str(row.credential_id)
                )
            if "model" in fields:
                metadata["model"] = row.model
            await self._audit.record(
                db,
                action=AuditAction.WORKSPACE_LEVEL_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=AuditTarget("workspace_level", level.value),
                metadata=metadata,
                ip=ip,
            )
        views = await self.list_levels(db, workspace_id=workspace_id)
        return next(view for view in views if view.level == level)

    def _view(
        self, row: WorkspaceLevel, provider_name: str | None, provider_kind: ProviderKind | None
    ) -> LevelView:
        price = None if row.model is None else self._prices.price(row.model)
        return LevelView(
            level=row.level,
            provider_id=row.credential_id,
            provider_name=provider_name,
            provider_kind=provider_kind,
            model=row.model,
            temperature=row.temperature,
            instructions=(
                default_instructions(row.level) if row.instructions is None else row.instructions
            ),
            instructions_is_default=row.instructions is None,
            default_instructions=default_instructions(row.level),
            price=price,
            estimated_cost_per_answer_usd=self._prices.cost(
                row.model, REFERENCE_INPUT_TOKENS, REFERENCE_OUTPUT_TOKENS
            ),
            updated_at=row.updated_at,
        )

    @staticmethod
    async def _get(
        db: AsyncSession, workspace_id: uuid.UUID, level: ResponseLevel
    ) -> WorkspaceLevel:
        # Every workspace has its three levels (created with it or by migration 0018).
        return (
            await db.scalars(
                select(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id, WorkspaceLevel.level == level)
                .with_for_update()
            )
        ).one()

    @staticmethod
    async def _lock_credential(
        db: AsyncSession, workspace_id: uuid.UUID, credential_id: uuid.UUID
    ) -> None:
        """Refuse a credential that is not in the workspace; hold it until commit."""
        found = (
            await db.scalars(
                select(ProviderCredential.id)
                .where(
                    ProviderCredential.workspace_id == workspace_id,
                    ProviderCredential.id == credential_id,
                )
                .with_for_update(key_share=True)
            )
        ).one_or_none()
        if found is None:
            raise LevelProviderInvalidError(
                "The provider does not exist in this workspace.",
                details={"provider_id": str(credential_id)},
            )
