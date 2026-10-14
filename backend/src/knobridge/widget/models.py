"""``Widget`` and ``RateLimitCounter``: the embeddable chat of a product and the counters of
its public routes (``docs/specs/widget.md``, decision in ``docs/adr/0009-canais-mcp-e-widget.md``).

``widgets`` is workspace data with forced row-level security; the public routes look a widget
up by ``public_key`` (unique in the instance, not a secret) in system mode, then work in its
workspace. The optional signing secret ``kbs_`` is kept only as AES-256-GCM ciphertext
(``docs/adr/0003-segredos-cifrados.md``). ``rate_limit_counters`` has no workspace: like
``login_attempts`` it is reachable only in system mode, and its key is an HMAC that hides the
widget and the client IP.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.products.models import Product
from knobridge.tenancy.models import User, Workspace

# The tables these models reference by name, so the metadata is complete wherever they are used.
REFERENCED_MODELS = (Workspace, User, Product)

NAME_MAX_LENGTH = 200
PUBLIC_KEY_LENGTH = 28  # ``kbp_`` + 24
MAX_ALLOWED_ORIGINS = 50
ORIGIN_MAX_LENGTH = 255
TITLE_MAX_LENGTH = 80
GREETING_MAX_LENGTH = 500
PLACEHOLDER_MAX_LENGTH = 120
MAX_MESSAGES_PER_IP_PER_HOUR = 1000
MAX_MESSAGES_PER_DAY = 100_000
DEFAULT_PRIMARY_COLOR = "#2563eb"
DEFAULT_GREETING = "Olá! Como posso ajudar?"
DEFAULT_PLACEHOLDER = "Escreva sua pergunta"
DEFAULT_MESSAGES_PER_IP_PER_HOUR = 30
DEFAULT_MESSAGES_PER_DAY = 1000
SHA256_HEX_LENGTH = 64


class WidgetMode(StrEnum):
    BUBBLE = "bubble"
    INLINE = "inline"


class WidgetPosition(StrEnum):
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"


class WidgetTheme(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class Widget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A widget of a product: public key, allowed origins, appearance, features and limits."""

    __tablename__ = "widgets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign key of ``conversations``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "product_id"],
            ["products.workspace_id", "products.id"],
            ondelete="CASCADE",
        ),
        Index(None, "workspace_id", "product_id"),
        CheckConstraint("length(name) > 0", name="name_not_empty"),
        CheckConstraint("public_key ~ '^kbp_[a-z0-9]{24}$'", name="public_key_format"),
        CheckConstraint(
            f"cardinality(allowed_origins) BETWEEN 1 AND {MAX_ALLOWED_ORIGINS}"
            " AND array_position(allowed_origins, NULL) IS NULL",
            name="allowed_origins_size",
        ),
        CheckConstraint("primary_color ~ '^#[0-9a-f]{6}$'", name="primary_color_format"),
        CheckConstraint(
            f"messages_per_ip_per_hour BETWEEN 1 AND {MAX_MESSAGES_PER_IP_PER_HOUR}",
            name="messages_per_ip_per_hour_range",
        ),
        CheckConstraint(
            f"messages_per_day BETWEEN 1 AND {MAX_MESSAGES_PER_DAY}",
            name="messages_per_day_range",
        ),
        CheckConstraint(
            "(signing_secret_ciphertext IS NULL) = (signing_secret_created_at IS NULL)",
            name="signing_secret_created_at",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Fixed once created (an application rule): another product means another widget.
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    # ``kbp_…``: goes in the host page and in the public paths, so it is stored in clear.
    public_key: Mapped[str] = mapped_column(String(PUBLIC_KEY_LENGTH), nullable=False, unique=True)
    # Normalized origins (``widget/origins.py``); the instance's own origin is always allowed.
    allowed_origins: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    mode: Mapped[WidgetMode] = mapped_column(
        str_enum(WidgetMode, "mode"),
        nullable=False,
        default=WidgetMode.BUBBLE,
        server_default=WidgetMode.BUBBLE.value,
    )
    position: Mapped[WidgetPosition] = mapped_column(
        str_enum(WidgetPosition, "position"),
        nullable=False,
        default=WidgetPosition.BOTTOM_RIGHT,
        server_default=WidgetPosition.BOTTOM_RIGHT.value,
    )
    theme: Mapped[WidgetTheme] = mapped_column(
        str_enum(WidgetTheme, "theme"),
        nullable=False,
        default=WidgetTheme.AUTO,
        server_default=WidgetTheme.AUTO.value,
    )
    primary_color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        default=DEFAULT_PRIMARY_COLOR,
        server_default=DEFAULT_PRIMARY_COLOR,
    )
    # ``None``: the product's name.
    title: Mapped[str | None] = mapped_column(String(TITLE_MAX_LENGTH), nullable=True)
    # Empty: no greeting.
    greeting: Mapped[str] = mapped_column(
        String(GREETING_MAX_LENGTH),
        nullable=False,
        default=DEFAULT_GREETING,
        server_default=DEFAULT_GREETING,
    )
    placeholder: Mapped[str] = mapped_column(
        String(PLACEHOLDER_MAX_LENGTH),
        nullable=False,
        default=DEFAULT_PLACEHOLDER,
        server_default=DEFAULT_PLACEHOLDER,
    )
    feedback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    # Holds only while the product has its ticket webhook configured.
    ticket_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    messages_per_ip_per_hour: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MESSAGES_PER_IP_PER_HOUR,
        server_default=str(DEFAULT_MESSAGES_PER_IP_PER_HOUR),
    )
    messages_per_day: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=DEFAULT_MESSAGES_PER_DAY,
        server_default=str(DEFAULT_MESSAGES_PER_DAY),
    )
    # ``kbs_…`` sealed by ``widget/secrets.py``; ``None``: no signed identity.
    signing_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    signing_secret_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class RateLimitCounter(Base):
    """One fixed window of a rate limit: hits so far and when the window ends."""

    __tablename__ = "rate_limit_counters"
    __table_args__ = (
        CheckConstraint("hits >= 1", name="hits_positive"),
        Index(None, "window_ends_at"),
    )

    # HMAC-SHA256 (hex) of ``<scope>|<widget_id>|<ip>``: never the widget or the IP in clear.
    key_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, nullable=False)
    window_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
