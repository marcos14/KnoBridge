"""Maximum level of each member in each product (``docs/specs/produtos-e-niveis.md``,
"Nível por membro e produto").

- ``GET /v1/workspaces/{workspace_id}/member-levels`` (owner or admin): the member x product
  table, paginated and filtered like the member list; ``products`` has every product (active
  or not) by name and each item one level per product, in the same order.
- ``PUT .../members/{user_id}/product-levels`` (owner or admin, with CSRF): records the given
  levels (``null`` removes the recorded value: back to the role's default); products left out
  stay. 404 for a non-member, 403 ``role_not_allowed`` for a member whose role is above the
  caller's, 422 ``member_level_product_invalid`` for a product not in the workspace.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, model_validator

from knobridge.api.deps import ClientIpDep, WorkspaceContext, require_role
from knobridge.api.listing import SearchQuery
from knobridge.levels.level import ResponseLevel
from knobridge.levels.members import (
    EffectiveLevel,
    LevelChange,
    MemberLevels,
    MemberLevelService,
)
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.members import MemberFilter, MemberSort
from knobridge.tenancy.models import Role

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
MAX_LEVEL_ITEMS = 200

AdminContext = Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]


def get_member_level_service(request: Request) -> MemberLevelService:
    return MemberLevelService(request.app.state.clock)


MemberLevelServiceDep = Annotated[MemberLevelService, Depends(get_member_level_service)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"description": "No live session (standard error shape)."},
    403: {"description": "Role below admin (`forbidden`) or workspace suspended."},
    404: {"description": "Workspace not found or caller is not a member."},
}


class ProductRefOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool


class MemberProductLevelOut(BaseModel):
    product_id: uuid.UUID
    max_level: ResponseLevel
    # Recorded by an admin; ``false``: the default of the role.
    explicit: bool


class MemberLevelsOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    role: Role
    levels: list[MemberProductLevelOut]


class MemberLevelsPage(BaseModel):
    products: list[ProductRefOut]
    items: list[MemberLevelsOut]
    total: int
    limit: int
    offset: int


class ProductLevelIn(BaseModel):
    product_id: uuid.UUID
    # ``null``: remove the recorded value (back to the role's default).
    max_level: ResponseLevel | None


class ProductLevelsUpdate(BaseModel):
    levels: Annotated[list[ProductLevelIn], Field(min_length=1, max_length=MAX_LEVEL_ITEMS)]

    @model_validator(mode="after")
    def _distinct_products(self) -> ProductLevelsUpdate:
        ids = [item.product_id for item in self.levels]
        if len(set(ids)) != len(ids):
            raise ValueError("A product appears more than once.")
        return self


def _level_out(level: EffectiveLevel) -> MemberProductLevelOut:
    return MemberProductLevelOut(
        product_id=level.product_id, max_level=level.max_level, explicit=level.explicit
    )


def _member_out(item: MemberLevels) -> MemberLevelsOut:
    return MemberLevelsOut(
        user_id=item.member.user_id,
        name=item.member.name,
        email=item.member.email,
        role=item.member.role,
        levels=[_level_out(level) for level in item.levels],
    )


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["levels"])


@router.get("/member-levels", responses=_ERRORS)
async def list_member_levels(
    context: AdminContext,
    levels: MemberLevelServiceDep,
    query: SearchQuery = None,
    role: Role | None = None,
    sort: MemberSort = "name",
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberLevelsPage:
    """Each member's maximum level in each product (``query`` matches name or e-mail)."""
    page = await levels.page(
        context.db,
        workspace_id=context.workspace_id,
        filters=MemberFilter(query=query, role=role, sort=sort),
        limit=limit,
        offset=offset,
    )
    return MemberLevelsPage(
        products=[
            ProductRefOut(id=product.id, name=product.name, active=product.active)
            for product in page.products
        ],
        items=[_member_out(item) for item in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.put(
    "/members/{user_id}/product-levels",
    dependencies=[Depends(require_csrf)],
    responses={
        **_ERRORS,
        403: {
            "description": "Role below admin (`forbidden`), member's role above the caller's "
            "(`role_not_allowed`), workspace suspended or CSRF failure (`csrf_failed`)."
        },
        404: {"description": "Workspace not found, or the user is not a member."},
        422: {
            "description": "Invalid body (`validation_error`) or product not in the workspace "
            "(`member_level_product_invalid`)."
        },
    },
)
async def set_member_levels(
    user_id: uuid.UUID,
    body: ProductLevelsUpdate,
    context: AdminContext,
    levels: MemberLevelServiceDep,
    ip: ClientIpDep,
) -> MemberLevelsOut:
    """Record or remove the member's maximum level in the given products."""
    item = await levels.set_levels(
        context.db,
        workspace_id=context.workspace_id,
        actor_id=context.current.user.id,
        actor_role=context.role,
        user_id=user_id,
        changes=[LevelChange(entry.product_id, entry.max_level) for entry in body.levels],
        ip=ip,
    )
    return _member_out(item)
