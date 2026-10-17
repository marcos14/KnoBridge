"""``WorkspaceLevel``: the credential, model, temperature and instructions of each level in a
workspace, and ``MemberProductLevel``: the maximum level a member set by an admin has in a
product (``docs/specs/produtos-e-niveis.md``).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). Every
workspace has exactly three ``WorkspaceLevel`` rows, created with it (``create_workspace_levels``)
or by migration ``0018``. A member without a ``MemberProductLevel`` row in a product has the
default of the role; the row only exists when an admin set a value.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, str_enum
from knobridge.levels.level import (
    DEFAULT_MAX_STEPS,
    DEFAULT_TEMPERATURE,
    MAX_MAX_STEPS,
    MAX_TEMPERATURE,
    MIN_MAX_STEPS,
    MIN_TEMPERATURE,
    ResponseLevel,
)
from knobridge.llm.models import ProviderCredential
from knobridge.products.models import Product
from knobridge.tenancy.models import Membership, Workspace

# The tables these models reference by name; importing them puts them in the metadata
# wherever these models are used alone (otherwise the flush fails with
# ``NoReferencedTableError``).
REFERENCED_MODELS = (Workspace, Membership, Product, ProviderCredential)


def _default_max_steps(context: DefaultExecutionContext) -> int:
    """The level's own default (no database default: it differs per level)."""
    return DEFAULT_MAX_STEPS[ResponseLevel(context.get_current_parameters()["level"])]


class WorkspaceLevel(TimestampMixin, Base):
    """One level of a workspace. ``instructions`` ``None`` means the KnoBridge default text of
    the level, so the workspace gets the improvements of later versions."""

    __tablename__ = "workspace_levels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
        ),
        # A level answers only with both a credential and a model.
        CheckConstraint("(credential_id IS NULL) = (model IS NULL)", name="model_with_credential"),
        CheckConstraint(
            f"temperature >= {MIN_TEMPERATURE} AND temperature <= {MAX_TEMPERATURE}",
            name="temperature_range",
        ),
        CheckConstraint(
            f"max_steps >= {MIN_MAX_STEPS} AND max_steps <= {MAX_MAX_STEPS}",
            name="max_steps_range",
        ),
        # Serves the ``NO ACTION`` check when a credential is deleted.
        Index(None, "workspace_id", "credential_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[ResponseLevel] = mapped_column(str_enum(ResponseLevel, "level"), primary_key=True)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    temperature: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=DEFAULT_TEMPERATURE,
        server_default=text(str(DEFAULT_TEMPERATURE)),
    )
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Most searches of an answer at this level (multi-step search, docs/specs/chat.md).
    max_steps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=_default_max_steps)
    # The model that refused tool calls at this level (written by the chat turn); while it is
    # the level's model, answers use the single search. Cleared when the model changes.
    tools_unsupported_model: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MemberProductLevel(TimestampMixin, Base):
    """The maximum level an admin set for a member in a product. Deleting the product or the
    membership deletes it."""

    __tablename__ = "member_product_levels"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
        # Serves the member's levels and the cascade from ``memberships``.
        Index(None, "workspace_id", "user_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    max_level: Mapped[ResponseLevel] = mapped_column(
        str_enum(ResponseLevel, "max_level"), nullable=False
    )


async def create_workspace_levels(db: AsyncSession, workspace_id: uuid.UUID) -> None:
    """The three levels of a new workspace, without a model and with the default instructions
    (the checklist of the home page asks for the configuration)."""
    db.add_all(WorkspaceLevel(workspace_id=workspace_id, level=level) for level in ResponseLevel)
    await db.flush()
