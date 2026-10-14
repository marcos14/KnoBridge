"""Manage the widgets of a workspace from the panel: list, create, edit, delete and the signing
secret (``docs/specs/widget.md``, "Configuração no painel").

Runs in the caller's workspace-scoped session (``WorkspaceContext.db``); owners and admins only
(the route checks the role). The signing secret ``kbs_`` is returned once by
:meth:`WidgetService.rotate_signing_secret` and stored only as ciphertext. Audit metadata
carries names, ids, the public key, origins and the changed fields, never the secret.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.conversations.models import Conversation
from knobridge.core.clock import Clock
from knobridge.core.crypto import SecretBox
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.core.listing import text_match
from knobridge.products.models import Product
from knobridge.tenancy.models import User
from knobridge.widget.keys import generate_public_key, generate_signing_secret, seal_signing_secret
from knobridge.widget.models import Widget, WidgetMode, WidgetPosition, WidgetTheme
from knobridge.widget.origins import normalize_origins


class WidgetNameTakenError(ConflictError):
    code = "widget_name_taken"


class WidgetProductInvalidError(ValidationError):
    code = "widget_product_invalid"


# Fields a ``PATCH`` may change (``product_id`` never changes: another product, another widget).
EDITABLE_FIELDS = frozenset(
    {
        "name",
        "allowed_origins",
        "active",
        "mode",
        "position",
        "theme",
        "primary_color",
        "title",
        "greeting",
        "placeholder",
        "feedback_enabled",
        "ticket_enabled",
        "messages_per_ip_per_hour",
        "messages_per_day",
    }
)


@dataclass(frozen=True)
class WidgetFilter:
    product_id: uuid.UUID | None = None
    active: bool | None = None
    query: str | None = None


@dataclass(frozen=True)
class WidgetSettings:
    """Appearance, features and limits of a new widget (the defaults of the spec)."""

    active: bool = True
    mode: WidgetMode = WidgetMode.BUBBLE
    position: WidgetPosition = WidgetPosition.BOTTOM_RIGHT
    theme: WidgetTheme = WidgetTheme.AUTO
    primary_color: str = "#2563eb"
    title: str | None = None
    greeting: str = "Olá! Como posso ajudar?"
    placeholder: str = "Escreva sua pergunta"
    feedback_enabled: bool = True
    ticket_enabled: bool = True
    messages_per_ip_per_hour: int = 30
    messages_per_day: int = 1000


@dataclass(frozen=True)
class WidgetView:
    widget: Widget
    product_name: str
    # The product has its ticket webhook (URL and secret): the widget's tickets can be delivered.
    product_ticket_webhook: bool
    created_by_name: str | None

    @property
    def ticket_available(self) -> bool:
        return self.widget.ticket_enabled and self.product_ticket_webhook


@dataclass(frozen=True)
class IssuedSigningSecret:
    secret: str  # plain value: shown once, never stored or logged
    created_at: datetime


def _blank_to_none(title: str | None) -> str | None:
    return title or None


def _normalized(name: str, value: object) -> object:
    """The value as stored: origins normalized, color in lower case, empty title as ``None``."""
    if name == "allowed_origins":
        return normalize_origins(cast(Sequence[str], value))
    if name == "primary_color":
        return cast(str, value).lower()
    if name == "title":
        return _blank_to_none(cast(str | None, value))
    return value


class WidgetService:
    def __init__(self, clock: Clock, box: SecretBox) -> None:
        self._clock = clock
        self._box = box
        self._audit = AuditService(clock)

    async def list_widgets(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: WidgetFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[WidgetView], int]:
        """A page of widgets by name (then id); two statements whatever the page size."""
        conditions: list[ColumnElement[bool]] = [Widget.workspace_id == workspace_id]
        if filters.product_id is not None:
            conditions.append(Widget.product_id == filters.product_id)
        if filters.active is not None:
            conditions.append(Widget.active.is_(filters.active))
        if filters.query:
            conditions.append(text_match(filters.query, Widget.name))
        total = await db.scalar(select(func.count()).select_from(Widget).where(*conditions))
        rows = await db.execute(
            self._view_query()
            .where(*conditions)
            .order_by(Widget.name, Widget.id)
            .limit(limit)
            .offset(offset)
        )
        return [self._view(*row) for row in rows], total or 0

    async def get(
        self, db: AsyncSession, *, workspace_id: uuid.UUID, widget_id: uuid.UUID
    ) -> WidgetView:
        row = (
            await db.execute(
                self._view_query()
                .where(Widget.workspace_id == workspace_id, Widget.id == widget_id)
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Widget not found.")
        return self._view(*row)

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        product_id: uuid.UUID,
        name: str,
        allowed_origins: Sequence[str],
        settings: WidgetSettings,
        ip: str | None,
    ) -> WidgetView:
        origins = normalize_origins(allowed_origins)
        await self._ensure_product(db, workspace_id, product_id)
        await self._ensure_name_free(db, workspace_id, name)
        widget = Widget(
            workspace_id=workspace_id,
            product_id=product_id,
            name=name,
            public_key=generate_public_key(),
            allowed_origins=origins,
            active=settings.active,
            mode=settings.mode,
            position=settings.position,
            theme=settings.theme,
            primary_color=settings.primary_color.lower(),
            title=_blank_to_none(settings.title),
            greeting=settings.greeting,
            placeholder=settings.placeholder,
            feedback_enabled=settings.feedback_enabled,
            ticket_enabled=settings.ticket_enabled,
            messages_per_ip_per_hour=settings.messages_per_ip_per_hour,
            messages_per_day=settings.messages_per_day,
            created_by=actor_id,
        )
        db.add(widget)
        await self._flush(db)
        await self._record(
            db,
            AuditAction.WIDGET_CREATED,
            widget,
            actor_id,
            ip,
            {
                "product_id": str(product_id),
                "public_key": widget.public_key,
                "allowed_origins": list[JSONValue](origins),
            },
        )
        return await self.get(db, workspace_id=workspace_id, widget_id=widget.id)

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        widget_id: uuid.UUID,
        changes: Mapping[str, object],
        ip: str | None,
    ) -> WidgetView:
        """Apply the given fields (``EDITABLE_FIELDS``); audits only what really changed."""
        widget = (await self.get(db, workspace_id=workspace_id, widget_id=widget_id)).widget
        applied: dict[str, object] = {}
        for name, value in changes.items():
            if name not in EDITABLE_FIELDS:
                raise ValidationError(f"Field {name} cannot be changed.")
            applied[name] = _normalized(name, value)
        new_name = applied.get("name")
        if isinstance(new_name, str) and new_name != widget.name:
            await self._ensure_name_free(db, workspace_id, new_name)
        fields: list[JSONValue] = []
        for name, value in applied.items():
            if getattr(widget, name) != value:
                setattr(widget, name, value)
                fields.append(name)
        if fields:
            await self._flush(db)
            await self._record(
                db, AuditAction.WIDGET_UPDATED, widget, actor_id, ip, {"fields": fields}
            )
        return await self.get(db, workspace_id=workspace_id, widget_id=widget_id)

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        widget_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Delete the widget; its conversations go with it (cascade)."""
        widget = (await self.get(db, workspace_id=workspace_id, widget_id=widget_id)).widget
        conversation_count = await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.workspace_id == workspace_id, Conversation.widget_id == widget.id)
        )
        await self._record(
            db,
            AuditAction.WIDGET_DELETED,
            widget,
            actor_id,
            ip,
            {"conversation_count": conversation_count or 0},
        )
        await db.delete(widget)
        await db.flush()

    async def rotate_signing_secret(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        widget_id: uuid.UUID,
        ip: str | None,
    ) -> IssuedSigningSecret:
        """Generate or replace the secret; identities signed with the old one stop at once."""
        widget = (await self.get(db, workspace_id=workspace_id, widget_id=widget_id)).widget
        secret = generate_signing_secret()
        created_at = self._clock.now()
        widget.signing_secret_ciphertext = seal_signing_secret(self._box, widget, secret)
        widget.signing_secret_created_at = created_at
        await db.flush()
        await self._record(db, AuditAction.WIDGET_SIGNING_SECRET_ROTATED, widget, actor_id, ip, {})
        return IssuedSigningSecret(secret=secret, created_at=created_at)

    async def remove_signing_secret(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        widget_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Forget the secret (signed identities are refused from now on); idempotent."""
        widget = (await self.get(db, workspace_id=workspace_id, widget_id=widget_id)).widget
        if widget.signing_secret_ciphertext is None:
            return
        widget.signing_secret_ciphertext = None
        widget.signing_secret_created_at = None
        await db.flush()
        await self._record(db, AuditAction.WIDGET_SIGNING_SECRET_REMOVED, widget, actor_id, ip, {})

    @staticmethod
    def _view_query() -> Select[Widget, Product, str]:
        return (
            select(Widget, Product, User.name)
            .join(
                Product,
                (Product.workspace_id == Widget.workspace_id) & (Product.id == Widget.product_id),
            )
            .outerjoin(User, User.id == Widget.created_by)
        )

    @staticmethod
    def _view(widget: Widget, product: Product, created_by_name: str | None) -> WidgetView:
        return WidgetView(
            widget=widget,
            product_name=product.name,
            product_ticket_webhook=product.ticket_webhook_configured,
            created_by_name=created_by_name,
        )

    async def _record(
        self,
        db: AsyncSession,
        action: AuditAction,
        widget: Widget,
        actor_id: uuid.UUID,
        ip: str | None,
        extra: dict[str, JSONValue],
    ) -> None:
        await self._audit.record(
            db,
            action=action,
            workspace_id=widget.workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("widget", str(widget.id)),
            metadata={"name": widget.name, **extra},
            ip=ip,
        )

    @staticmethod
    async def _ensure_product(
        db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID
    ) -> None:
        found = await db.scalar(
            select(exists().where(Product.workspace_id == workspace_id, Product.id == product_id))
        )
        if not found:
            raise WidgetProductInvalidError(
                "The product must belong to the workspace.",
                details={"product_id": str(product_id)},
            )

    @staticmethod
    async def _ensure_name_free(db: AsyncSession, workspace_id: uuid.UUID, name: str) -> None:
        taken = await db.scalar(
            select(exists().where(Widget.workspace_id == workspace_id, Widget.name == name))
        )
        if taken:
            raise WidgetNameTakenError("A widget with this name already exists.")

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # The name was checked just before, so only a concurrent request with the same name
            # gets here (a public key collision has odds of 1 in 36^24 per pair).
            raise WidgetNameTakenError("A widget with this name already exists.") from exc
