"""Products of a workspace (``/v1/workspaces/{workspace_id}/products``;
``docs/specs/produtos-e-niveis.md``, "Produto").

Every member lists and reads them, but viewers only see active products (an inactive one is
404 for them). Owners, admins and editors create, update, duplicate and delete. Names are
unique per workspace (409 ``product_name_taken``) and cannot end in ``:<level>`` (422
``product_name_invalid``). An empty or null ``no_source_message`` stores the default "I don't
know, shall I open a ticket?" message. ``collection_ids`` are the collections the product
answers from, all of the same workspace (422 ``product_collection_invalid``). ``min_similarity``
is the retrieval threshold (0 to 1; omitted or null on create: the default).
``ticket_webhook_url`` is where ticket requests go (``null``: off), checked against the SSRF
rules when saved (422 ``webhook_url_invalid`` or ``webhook_destination_blocked``); its signing
secret and the test event live in ``api/ticket_webhook.py``. ``my_max_level`` is the reader's
maximum level in the product. The model of the answers is the level's (``api/levels.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, StringConstraints, model_validator

from knobridge.api.deps import ClientIpDep, WorkspaceContext, WorkspaceContextDep, require_role
from knobridge.api.listing import SearchQuery
from knobridge.api.ticket_webhook import DestinationValidatorDep
from knobridge.levels.defaults import role_default_level
from knobridge.levels.level import ResponseLevel
from knobridge.levels.members import recorded_levels
from knobridge.products.duplicate import duplicate_product
from knobridge.products.listing import ProductFilter, ProductSort
from knobridge.products.models import (
    DEFAULT_LANGUAGE,
    DEFAULT_MIN_SIMILARITY,
    MAX_SIMILARITY,
    MIN_SIMILARITY,
    TICKET_WEBHOOK_URL_MAX_LENGTH,
    Product,
    ProductTone,
)
from knobridge.products.service import ProductChanges, ProductService, ProductSettings
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least
from knobridge.tickets.webhook import check_webhook_url

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_COLLECTIONS = 100

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]


def get_product_service(request: Request) -> ProductService:
    return ProductService(request.app.state.clock)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Instructions = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]
# BCP 47 language tag, e.g. ``pt-BR``, ``en``, ``es-419``.
Language = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=35, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$"
    ),
]
NoSourceMessage = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
MinSimilarity = Annotated[float, Field(ge=MIN_SIMILARITY, le=MAX_SIMILARITY, allow_inf_nan=False)]
CollectionIds = Annotated[list[uuid.UUID], Field(max_length=MAX_COLLECTIONS)]
WebhookUrl = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=TICKET_WEBHOOK_URL_MAX_LENGTH
    ),
]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Workspace suspended."},
    404: {"description": "Workspace or product not found, or caller is not a member."},
}
_WRITE_ERRORS: dict[int | str, dict[str, object]] = {
    **_ERRORS,
    403: {
        "description": "Role below editor (`forbidden`), workspace suspended or CSRF failure "
        "(`csrf_failed`)."
    },
}
_SAVE_ERRORS: dict[int | str, dict[str, object]] = {
    **_WRITE_ERRORS,
    409: {"description": "Name already used in the workspace (`product_name_taken`)."},
    422: {
        "description": "Invalid body, name ending in `:<level>` (`product_name_invalid`), "
        "collection not in the workspace (`product_collection_invalid`), or webhook URL "
        "refused (`webhook_url_invalid`, `webhook_destination_blocked`, with "
        "`details.reason`)."
    },
}


def _unique(ids: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
    if ids is not None and len(set(ids)) != len(ids):
        raise ValueError("collection_ids must not repeat.")
    return ids


class ProductCreate(BaseModel):
    name: Name
    description: Description = ""
    instructions: Instructions = ""
    language: Language = DEFAULT_LANGUAGE
    tone: ProductTone = ProductTone.NEUTRAL
    # Empty or null: the default "no source" message.
    no_source_message: NoSourceMessage | None = None
    active: bool = True
    collection_ids: CollectionIds = Field(default_factory=lambda: [])
    # Omitted or null: ``DEFAULT_MIN_SIMILARITY``.
    min_similarity: MinSimilarity | None = None
    # ``https`` (``http`` only for an allowlisted development host); null: ticket requests off.
    ticket_webhook_url: WebhookUrl | None = None

    @model_validator(mode="after")
    def _distinct_collections(self) -> ProductCreate:
        _unique(self.collection_ids)
        return self


class ProductUpdate(BaseModel):
    """Fields to change; omitted (or null) fields stay. ``no_source_message`` empty or null
    restores the default message."""

    name: Name | None = None
    description: Description | None = None
    instructions: Instructions | None = None
    language: Language | None = None
    tone: ProductTone | None = None
    no_source_message: NoSourceMessage | None = None
    active: bool | None = None
    # Replaces the whole set when given.
    collection_ids: CollectionIds | None = None
    min_similarity: MinSimilarity | None = None
    # Unlike the other fields, null turns the webhook off; omitted keeps it.
    ticket_webhook_url: WebhookUrl | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> ProductUpdate:
        if not self.model_fields_set:
            raise ValueError("Give at least one field to change.")
        _unique(self.collection_ids)
        return self


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    instructions: str
    language: str
    tone: ProductTone
    no_source_message: str
    active: bool
    collection_ids: list[uuid.UUID]
    min_similarity: float
    ticket_webhook_url: str | None
    # URL and signing secret set: the chat may send ticket requests.
    ticket_webhook_configured: bool
    # When the current signing secret was generated (never the secret); null: none yet.
    ticket_webhook_secret_created_at: datetime | None
    # The reader's maximum level in this product (recorded by an admin or the role's default).
    my_max_level: ResponseLevel
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int


def _out(
    product: Product, collection_ids: list[uuid.UUID], my_max_level: ResponseLevel
) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        description=product.description,
        instructions=product.instructions,
        language=product.language,
        tone=product.tone,
        no_source_message=product.no_source_message,
        active=product.active,
        collection_ids=collection_ids,
        min_similarity=product.min_similarity,
        ticket_webhook_url=product.ticket_webhook_url,
        ticket_webhook_configured=product.ticket_webhook_configured,
        ticket_webhook_secret_created_at=product.ticket_webhook_secret_created_at,
        my_max_level=my_max_level,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _only_active(context: WorkspaceContext) -> bool:
    """Viewers only see active products; editors and above manage all of them."""
    return not role_at_least(context.role, Role.EDITOR)


async def _outs(
    context: WorkspaceContext, products: ProductService, items: list[Product]
) -> list[ProductOut]:
    """The products with their collections and the reader's level (two queries)."""
    ids = [item.id for item in items]
    links = await products.collections_of(context.db, context.workspace_id, ids)
    user_id = context.current.user.id
    recorded = (
        await recorded_levels(
            context.db, workspace_id=context.workspace_id, user_ids=[user_id], product_ids=ids
        )
    ).get(user_id, {})
    default = role_default_level(context.role)
    return [_out(item, links.get(item.id, []), recorded.get(item.id, default)) for item in items]


router = APIRouter(prefix="/workspaces/{workspace_id}/products", tags=["products"])


@router.get("", responses=_ERRORS)
async def list_products(
    context: WorkspaceContextDep,
    products: ProductServiceDep,
    query: SearchQuery = None,
    active: bool | None = None,
    collection_id: uuid.UUID | None = None,
    sort: ProductSort = "name",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    """Products (only the active ones for viewers); ``query`` matches name or description."""
    items, total = await products.list_products(
        context.db,
        workspace_id=context.workspace_id,
        filters=ProductFilter(
            active_only=_only_active(context),
            query=query,
            active=active,
            collection_id=collection_id,
            sort=sort,
        ),
        limit=limit,
        offset=offset,
    )
    return ProductPage(
        items=await _outs(context, products, items), total=total, limit=limit, offset=offset
    )


@router.get("/{product_id}", responses=_ERRORS)
async def get_product(
    product_id: uuid.UUID, context: WorkspaceContextDep, products: ProductServiceDep
) -> ProductOut:
    """One product (404 for viewers when it is inactive)."""
    product = await products.get(
        context.db,
        workspace_id=context.workspace_id,
        product_id=product_id,
        active_only=_only_active(context),
    )
    return (await _outs(context, products, [product]))[0]


@router.post(
    "",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses=_SAVE_ERRORS,
)
async def create_product(
    body: ProductCreate,
    context: EditorContext,
    products: ProductServiceDep,
    validator: DestinationValidatorDep,
    ip: ClientIpDep,
) -> ProductOut:
    """Create a product."""
    if body.ticket_webhook_url is not None:
        await check_webhook_url(validator, body.ticket_webhook_url)
    product = await products.create(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        settings=ProductSettings(
            name=body.name,
            description=body.description,
            instructions=body.instructions,
            language=body.language,
            tone=body.tone,
            no_source_message=body.no_source_message or "",
            active=body.active,
            collection_ids=tuple(body.collection_ids),
            min_similarity=(
                DEFAULT_MIN_SIMILARITY if body.min_similarity is None else body.min_similarity
            ),
            ticket_webhook_url=body.ticket_webhook_url,
        ),
        ip=ip,
    )
    return (await _outs(context, products, [product]))[0]


@router.patch("/{product_id}", dependencies=[Depends(require_csrf)], responses=_SAVE_ERRORS)
async def update_product(
    product_id: uuid.UUID,
    body: ProductUpdate,
    context: EditorContext,
    products: ProductServiceDep,
    validator: DestinationValidatorDep,
    ip: ClientIpDep,
) -> ProductOut:
    """Change any field; ``no_source_message`` empty or null restores the default and
    ``ticket_webhook_url`` null turns the webhook off."""
    if body.ticket_webhook_url is not None:
        await check_webhook_url(validator, body.ticket_webhook_url)
    no_source_message = body.no_source_message
    if no_source_message is None and "no_source_message" in body.model_fields_set:
        no_source_message = ""
    product = await products.update(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        product_id=product_id,
        changes=ProductChanges(
            name=body.name,
            description=body.description,
            instructions=body.instructions,
            language=body.language,
            tone=body.tone,
            no_source_message=no_source_message,
            active=body.active,
            collection_ids=None if body.collection_ids is None else tuple(body.collection_ids),
            min_similarity=body.min_similarity,
            ticket_webhook_url=body.ticket_webhook_url,
            ticket_webhook_url_given="ticket_webhook_url" in body.model_fields_set,
        ),
        ip=ip,
    )
    return (await _outs(context, products, [product]))[0]


@router.delete(
    "/{product_id}",
    status_code=HTTPStatus.NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    responses=_WRITE_ERRORS,
)
async def delete_product(
    product_id: uuid.UUID,
    context: EditorContext,
    products: ProductServiceDep,
    ip: ClientIpDep,
) -> None:
    """Delete a product with its conversations and the members' levels in it."""
    await products.delete(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        product_id=product_id,
        ip=ip,
    )


class ProductDuplicate(BaseModel):
    """Omitted or null ``name``: the original name with the first free copy suffix."""

    name: Name | None = None


@router.post(
    "/{product_id}/duplicate",
    status_code=HTTPStatus.CREATED,
    dependencies=[Depends(require_csrf)],
    responses={
        **_WRITE_ERRORS,
        409: {"description": "The given name is already used (`product_name_taken`)."},
        422: {"description": "Invalid body or name ending in `:<level>`."},
    },
)
async def duplicate(
    product_id: uuid.UUID,
    context: EditorContext,
    products: ProductServiceDep,
    ip: ClientIpDep,
    body: ProductDuplicate | None = None,
) -> ProductOut:
    """Copy the configuration and collections; the webhook keeps its URL, not its secret."""
    product = await duplicate_product(
        products,
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        product_id=product_id,
        name=None if body is None else body.name,
        ip=ip,
    )
    return (await _outs(context, products, [product]))[0]
