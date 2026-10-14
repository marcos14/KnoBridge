"""Widgets of a workspace (``/v1/workspaces/{workspace_id}/widgets``), managed from the panel.

Owners and admins only (403 ``forbidden`` below): a widget opens a product to the public and
spends the workspace's LLM, as API keys do. Writes require CSRF. The signing secret ``kbs_`` is
answered once by ``POST .../signing-secret``; no route shows it again. Contract in
``docs/specs/widget.md`` ("Configuração no painel"); logic in ``widget/service.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    SettingsDep,
    WorkspaceContext,
    require_role,
)
from knobridge.api.listing import SearchQuery
from knobridge.core.crypto import SecretBox
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.widget.keys import SIGNING_SECRET_KEY_INFO
from knobridge.widget.models import (
    DEFAULT_GREETING,
    DEFAULT_MESSAGES_PER_DAY,
    DEFAULT_MESSAGES_PER_IP_PER_HOUR,
    DEFAULT_PLACEHOLDER,
    DEFAULT_PRIMARY_COLOR,
    GREETING_MAX_LENGTH,
    MAX_ALLOWED_ORIGINS,
    MAX_MESSAGES_PER_DAY,
    MAX_MESSAGES_PER_IP_PER_HOUR,
    NAME_MAX_LENGTH,
    PLACEHOLDER_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    WidgetMode,
    WidgetPosition,
    WidgetTheme,
)
from knobridge.widget.service import WidgetFilter, WidgetService, WidgetSettings, WidgetView

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_MAX_LENGTH)
]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TITLE_MAX_LENGTH)]
Greeting = Annotated[str, StringConstraints(max_length=GREETING_MAX_LENGTH)]
Placeholder = Annotated[str, StringConstraints(max_length=PLACEHOLDER_MAX_LENGTH)]
Origins = Annotated[list[str], Field(min_length=1, max_length=MAX_ALLOWED_ORIGINS)]
PerIpPerHour = Annotated[int, Field(ge=1, le=MAX_MESSAGES_PER_IP_PER_HOUR)]
PerDay = Annotated[int, Field(ge=1, le=MAX_MESSAGES_PER_DAY)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace or widget not found (`not_found`)."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below admin (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_INVALID: dict[int | str, dict[str, object]] = {
    409: {"description": "Name already used in the workspace (`widget_name_taken`)."},
    422: {
        "description": "Invalid body (`validation_error`), product outside the workspace "
        "(`widget_product_invalid`) or invalid origins (`widget_origin_invalid`, "
        "`details.origins[{origin, reason}]`)."
    },
}


class WidgetCreate(BaseModel):
    product_id: uuid.UUID
    name: Name
    allowed_origins: Origins
    active: bool = True
    mode: WidgetMode = WidgetMode.BUBBLE
    position: WidgetPosition = WidgetPosition.BOTTOM_RIGHT
    theme: WidgetTheme = WidgetTheme.AUTO
    primary_color: Color = DEFAULT_PRIMARY_COLOR
    # ``null`` or empty: the product's name.
    title: Title | None = None
    # Empty: no greeting.
    greeting: Greeting = DEFAULT_GREETING
    placeholder: Placeholder = DEFAULT_PLACEHOLDER
    feedback_enabled: bool = True
    ticket_enabled: bool = True
    messages_per_ip_per_hour: PerIpPerHour = DEFAULT_MESSAGES_PER_IP_PER_HOUR
    messages_per_day: PerDay = DEFAULT_MESSAGES_PER_DAY


class WidgetUpdate(BaseModel):
    """Fields to change; omitted fields stay, ``title: null`` is the product's name again.
    ``product_id`` never changes (another product, another widget): unknown fields are 422."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    allowed_origins: Origins | None = None
    active: bool | None = None
    mode: WidgetMode | None = None
    position: WidgetPosition | None = None
    theme: WidgetTheme | None = None
    primary_color: Color | None = None
    title: Title | None = None
    greeting: Greeting | None = None
    placeholder: Placeholder | None = None
    feedback_enabled: bool | None = None
    ticket_enabled: bool | None = None
    messages_per_ip_per_hour: PerIpPerHour | None = None
    messages_per_day: PerDay | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> WidgetUpdate:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        for name in self.model_fields_set - {"title"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class WidgetOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    name: str
    public_key: str
    allowed_origins: list[str]
    active: bool
    mode: WidgetMode
    position: WidgetPosition
    theme: WidgetTheme
    primary_color: str
    title: str | None
    greeting: str
    placeholder: str
    feedback_enabled: bool
    ticket_enabled: bool
    # ``ticket_enabled`` and the product has its ticket webhook.
    ticket_available: bool
    messages_per_ip_per_hour: int
    messages_per_day: int
    signing_secret_configured: bool
    signing_secret_created_at: datetime | None
    created_by: uuid.UUID | None
    created_by_name: str | None
    created_at: datetime
    updated_at: datetime


class WidgetPage(BaseModel):
    items: list[WidgetOut]
    total: int
    limit: int
    offset: int


class WidgetSigningSecretOut(BaseModel):
    # Shown once: the server keeps only its ciphertext.
    secret: str
    created_at: datetime


def widget_out(view: WidgetView) -> WidgetOut:
    widget = view.widget
    return WidgetOut(
        id=widget.id,
        product_id=widget.product_id,
        product_name=view.product_name,
        name=widget.name,
        public_key=widget.public_key,
        allowed_origins=list(widget.allowed_origins),
        active=widget.active,
        mode=widget.mode,
        position=widget.position,
        theme=widget.theme,
        primary_color=widget.primary_color,
        title=widget.title,
        greeting=widget.greeting,
        placeholder=widget.placeholder,
        feedback_enabled=widget.feedback_enabled,
        ticket_enabled=widget.ticket_enabled,
        ticket_available=view.ticket_available,
        messages_per_ip_per_hour=widget.messages_per_ip_per_hour,
        messages_per_day=widget.messages_per_day,
        signing_secret_configured=widget.signing_secret_ciphertext is not None,
        signing_secret_created_at=widget.signing_secret_created_at,
        created_by=widget.created_by,
        created_by_name=view.created_by_name,
        created_at=widget.created_at,
        updated_at=widget.updated_at,
    )


def get_widget_service(clock: ClockDep, settings: SettingsDep) -> WidgetService:
    box = SecretBox.derive(settings.secret_key.get_secret_value(), info=SIGNING_SECRET_KEY_INFO)
    return WidgetService(clock, box)


WidgetServiceDep = Annotated[WidgetService, Depends(get_widget_service)]

router = APIRouter(prefix="/workspaces/{workspace_id}/widgets", tags=["widgets"])


@router.get("", responses=_ERRORS)
async def list_widgets(
    context: AdminContext,
    widgets: WidgetServiceDep,
    query: SearchQuery = None,
    product_id: uuid.UUID | None = None,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> WidgetPage:
    """Widgets by name; ``query`` matches the name. Never the signing secret."""
    items, total = await widgets.list_widgets(
        context.db,
        workspace_id=context.workspace_id,
        filters=WidgetFilter(product_id=product_id, active=active, query=query),
        limit=limit,
        offset=offset,
    )
    return WidgetPage(
        items=[widget_out(item) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("/{widget_id}", responses=_ERRORS)
async def get_widget(
    widget_id: uuid.UUID, context: AdminContext, widgets: WidgetServiceDep
) -> WidgetOut:
    view = await widgets.get(context.db, workspace_id=context.workspace_id, widget_id=widget_id)
    return widget_out(view)


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={**_WRITE_ERRORS, **_INVALID},
)
async def create_widget(
    body: WidgetCreate, context: AdminContext, widgets: WidgetServiceDep, ip: ClientIpDep
) -> WidgetOut:
    """Create a widget of a product; its public key ``kbp_…`` is generated here."""
    view = await widgets.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        product_id=body.product_id,
        name=body.name,
        allowed_origins=body.allowed_origins,
        settings=WidgetSettings(
            active=body.active,
            mode=body.mode,
            position=body.position,
            theme=body.theme,
            primary_color=body.primary_color,
            title=body.title,
            greeting=body.greeting,
            placeholder=body.placeholder,
            feedback_enabled=body.feedback_enabled,
            ticket_enabled=body.ticket_enabled,
            messages_per_ip_per_hour=body.messages_per_ip_per_hour,
            messages_per_day=body.messages_per_day,
        ),
        ip=ip,
    )
    return widget_out(view)


@router.patch(
    "/{widget_id}",
    dependencies=[Depends(require_csrf)],
    responses={**_WRITE_ERRORS, **_INVALID},
)
async def update_widget(
    widget_id: uuid.UUID,
    body: WidgetUpdate,
    context: AdminContext,
    widgets: WidgetServiceDep,
    ip: ClientIpDep,
) -> WidgetOut:
    """Change the given fields; ``allowed_origins`` replaces the list."""
    view = await widgets.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        widget_id=widget_id,
        # In declaration order, so the audited ``fields`` are stable.
        changes={
            name: getattr(body, name)
            for name in WidgetUpdate.model_fields
            if name in body.model_fields_set
        },
        ip=ip,
    )
    return widget_out(view)


@router.delete(
    "/{widget_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def delete_widget(
    widget_id: uuid.UUID, context: AdminContext, widgets: WidgetServiceDep, ip: ClientIpDep
) -> Response:
    """Delete the widget and its conversations; its public key stops at once."""
    await widgets.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        widget_id=widget_id,
        ip=ip,
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.post(
    "/{widget_id}/signing-secret",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def rotate_widget_signing_secret(
    widget_id: uuid.UUID, context: AdminContext, widgets: WidgetServiceDep, ip: ClientIpDep
) -> WidgetSigningSecretOut:
    """Generate or replace the signing secret and return it, the only time it is shown."""
    issued = await widgets.rotate_signing_secret(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        widget_id=widget_id,
        ip=ip,
    )
    return WidgetSigningSecretOut(secret=issued.secret, created_at=issued.created_at)


@router.delete(
    "/{widget_id}/signing-secret",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def remove_widget_signing_secret(
    widget_id: uuid.UUID, context: AdminContext, widgets: WidgetServiceDep, ip: ClientIpDep
) -> Response:
    """Delete the signing secret: signed identities are refused, anonymous visitors go on."""
    await widgets.remove_signing_secret(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        widget_id=widget_id,
        ip=ip,
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)
