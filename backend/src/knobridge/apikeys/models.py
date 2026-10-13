"""``ApiKey``: a key that opens the public API of a workspace (``docs/specs/api-publica.md``,
decision in ``docs/adr/0007-chaves-e-api-publica.md``).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). The key
``kbk_<prefix>_<secret>`` is shown once and stored only as the SHA-256 hash of the whole
string; ``key_prefix`` is unique in the whole instance because authentication looks the key up
in system mode, before the workspace is known. ``product_ids`` limits the key to some
products (``None`` means every active product of the workspace); it has no foreign key, so
a deleted product simply drops out of the scope. ``max_level`` caps the level of its questions
(``docs/specs/produtos-e-niveis.md``). Keys are never deleted, only revoked: the
conversations made with a key keep pointing at it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import User, Workspace

# The tables these models reference by name. Importing them here puts them in the metadata
# wherever the key model is used alone; without them, the first flush fails with
# ``NoReferencedTableError``.
REFERENCED_MODELS = (Workspace, User)

NAME_MAX_LENGTH = 200
KEY_PREFIX_LENGTH = 8
SHA256_HEX_LENGTH = 64
MAX_SCOPED_PRODUCTS = 100


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A ``kbk_`` key of the workspace; revoking it is final."""

    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign key of ``conversations``.
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint("length(name) > 0", name="name_not_empty"),
        CheckConstraint(
            f"key_prefix ~ '^[a-z0-9]{{{KEY_PREFIX_LENGTH}}}$'", name="key_prefix_format"
        ),
        CheckConstraint(f"key_hash ~ '^[0-9a-f]{{{SHA256_HEX_LENGTH}}}$'", name="key_hash_format"),
        # A scope lists 1 to 100 products and no null; no scope is ``NULL``, never ``{}``.
        CheckConstraint(
            "product_ids IS NULL OR (cardinality(product_ids) BETWEEN 1 AND "
            f"{MAX_SCOPED_PRODUCTS} AND array_position(product_ids, NULL) IS NULL)",
            name="product_ids_size",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    # Public part of the key, unique in the instance: the lookup key in system mode.
    key_prefix: Mapped[str] = mapped_column(String(KEY_PREFIX_LENGTH), nullable=False, unique=True)
    # SHA-256 (hex) of the whole key; the key itself is shown once and never stored.
    key_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    # Products the key may talk to; ``None`` = every active product of the workspace.
    product_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(Uuid[uuid.UUID]()), nullable=True, default=None
    )
    # Highest level the key may ask at, in any product of its scope; chosen on creation.
    max_level: Mapped[ResponseLevel] = mapped_column(
        str_enum(ResponseLevel, "max_level"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Last authenticated request, written at most once a minute.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
