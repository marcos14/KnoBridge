"""The checks every public widget request goes through, in the order of ``docs/specs/widget.md``
("Checagem de ``Origin``"):

1. unknown or malformed public key: 404 ``not_found`` without CORS;
2. ``Origin`` absent or not allowed: 403 ``widget_origin_not_allowed`` without CORS;
3. widget or product inactive, or workspace suspended: 404 ``widget_unavailable``;
4. the general request limit: 429 ``rate_limited``;

then the route. The key is looked up in system mode (the workspace is not known yet); the
``Origin`` check is not authentication (a program forges the header), the limits are what
holds abuse back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from http import HTTPStatus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.db import system_session
from knobridge.core.errors import ForbiddenError, KnoBridgeError, NotFoundError
from knobridge.products.models import Product
from knobridge.tenancy.models import Workspace, WorkspaceStatus
from knobridge.widget.keys import is_public_key
from knobridge.widget.models import Widget
from knobridge.widget.origins import Origin, origin_allowed, request_origin

# Longest question the widget sends (``question_max_chars`` of the public configuration).
QUESTION_MAX_CHARS = 8000


class WidgetOriginNotAllowedError(ForbiddenError):
    code = "widget_origin_not_allowed"


class WidgetUnavailableError(KnoBridgeError):
    code = "widget_unavailable"
    status_code = HTTPStatus.NOT_FOUND


@dataclass(frozen=True)
class PublicWidget:
    """A widget found by its public key, with its product and the status of its workspace."""

    widget: Widget
    product: Product
    workspace_status: WorkspaceStatus

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.widget.workspace_id

    @property
    def available(self) -> bool:
        return (
            self.widget.active
            and self.product.active
            and self.workspace_status is WorkspaceStatus.ACTIVE
        )

    @property
    def ticket_available(self) -> bool:
        return self.widget.ticket_enabled and self.product.ticket_webhook_configured


async def find_public_widget(db: AsyncSession, public_key: str) -> PublicWidget | None:
    """The widget of ``public_key`` with its product and workspace status (system mode)."""
    if not is_public_key(public_key):
        return None
    row = (
        await db.execute(
            select(Widget, Product, Workspace.status)
            .join(
                Product,
                (Product.workspace_id == Widget.workspace_id) & (Product.id == Widget.product_id),
            )
            .join(Workspace, Workspace.id == Widget.workspace_id)
            .where(Widget.public_key == public_key)
        )
    ).one_or_none()
    if row is None:
        return None
    widget, product, status = row
    return PublicWidget(widget=widget, product=product, workspace_status=status)


async def resolve_public_widget(
    factory: async_sessionmaker[AsyncSession], public_key: str
) -> PublicWidget:
    """Step 1: the widget of ``public_key`` (short system-mode transaction), or 404."""
    async with system_session(factory) as db:
        found = await find_public_widget(db, public_key)
    if found is None:
        raise NotFoundError("Not found.")
    return found


def accepted_origin(
    found: PublicWidget, origin_header: str | None, *, instance: Origin | None
) -> Origin:
    """Step 2: the request origin when the widget (or the instance itself) allows it."""
    origin = request_origin(origin_header)
    if origin is None or not origin_allowed(
        origin, found.widget.allowed_origins, instance=instance
    ):
        raise WidgetOriginNotAllowedError("This origin may not use the widget.")
    return origin


def ensure_available(found: PublicWidget) -> None:
    """Step 3: widget and product active and workspace not suspended, or 404."""
    if not found.available:
        raise WidgetUnavailableError("The chat is unavailable.")
