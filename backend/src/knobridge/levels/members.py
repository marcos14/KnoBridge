"""The maximum level of each member in each product (``docs/specs/produtos-e-niveis.md``,
"Nível por membro e produto").

A member without a recorded value has the default of the role (``defaults.py``); a recorded
value (``explicit``) overrides it up or down and does not follow the role. Runs in the
caller's workspace-scoped session; ``user_product_levels`` is the exception, for ``/v1/me``,
which reads several workspaces in system mode, filtered by the ids it is given.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.errors import NotFoundError, ValidationError
from knobridge.levels.defaults import role_default_level
from knobridge.levels.grants import existing_products, missing_ids
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import MemberProductLevel
from knobridge.products.models import Product
from knobridge.tenancy.members import Member, MemberFilter, MemberService
from knobridge.tenancy.models import Membership, Role, User
from knobridge.tenancy.rbac import ensure_role_within


class MemberLevelProductInvalidError(ValidationError):
    code = "member_level_product_invalid"


@dataclass(frozen=True)
class ProductRef:
    id: uuid.UUID
    name: str
    active: bool


@dataclass(frozen=True)
class EffectiveLevel:
    """The maximum level of a person in a product and whether an admin recorded it."""

    product_id: uuid.UUID
    max_level: ResponseLevel
    explicit: bool


@dataclass(frozen=True)
class MemberLevels:
    """A member and their level in each product, in the order of the products given."""

    member: Member
    levels: list[EffectiveLevel]


@dataclass(frozen=True)
class MemberLevelsPage:
    products: list[ProductRef]
    items: list[MemberLevels]
    total: int


@dataclass(frozen=True)
class LevelChange:
    """``max_level`` ``None`` removes the recorded value (back to the role's default)."""

    product_id: uuid.UUID
    max_level: ResponseLevel | None


@dataclass(frozen=True)
class UserProductLevel:
    """A product of a workspace and the maximum level of one user in it (``/v1/me``)."""

    workspace_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    max_level: ResponseLevel
    explicit: bool


def effective_levels(
    role: Role, product_ids: Sequence[uuid.UUID], recorded: Mapping[uuid.UUID, ResponseLevel]
) -> list[EffectiveLevel]:
    """The level in each product: the recorded value or, without one, the role's default."""
    default = role_default_level(role)
    return [
        EffectiveLevel(product_id, recorded.get(product_id, default), product_id in recorded)
        for product_id in product_ids
    ]


async def recorded_levels(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: Sequence[uuid.UUID],
    product_ids: Sequence[uuid.UUID] | None = None,
) -> dict[uuid.UUID, dict[uuid.UUID, ResponseLevel]]:
    """Recorded values per user and product (one query); ``product_ids`` narrows them."""
    if not user_ids:
        return {}
    statement = select(
        MemberProductLevel.user_id, MemberProductLevel.product_id, MemberProductLevel.max_level
    ).where(
        MemberProductLevel.workspace_id == workspace_id,
        MemberProductLevel.user_id.in_(user_ids),
    )
    if product_ids is not None:
        statement = statement.where(MemberProductLevel.product_id.in_(product_ids))
    found: dict[uuid.UUID, dict[uuid.UUID, ResponseLevel]] = {}
    for user_id, product_id, max_level in await db.execute(statement):
        found.setdefault(user_id, {})[product_id] = max_level
    return found


async def user_product_levels(
    db: AsyncSession, *, user_id: uuid.UUID, roles: Mapping[uuid.UUID, Role]
) -> dict[uuid.UUID, list[UserProductLevel]]:
    """The user's level in each active product of the workspaces in ``roles`` (their role in
    each), ordered by product name; two queries whatever the number of workspaces. The
    session may be in system mode: every query is filtered by these workspace ids."""
    if not roles:
        return {}
    workspace_ids = list(roles)
    products = await db.execute(
        select(Product.workspace_id, Product.id, Product.name)
        .where(Product.workspace_id.in_(workspace_ids), Product.active.is_(True))
        .order_by(Product.name, Product.id)
    )
    recorded = {
        (workspace_id, product_id): max_level
        for workspace_id, product_id, max_level in await db.execute(
            select(
                MemberProductLevel.workspace_id,
                MemberProductLevel.product_id,
                MemberProductLevel.max_level,
            ).where(
                MemberProductLevel.workspace_id.in_(workspace_ids),
                MemberProductLevel.user_id == user_id,
            )
        )
    }
    found: dict[uuid.UUID, list[UserProductLevel]] = {}
    for workspace_id, product_id, name in products:
        level = recorded.get((workspace_id, product_id))
        found.setdefault(workspace_id, []).append(
            UserProductLevel(
                workspace_id=workspace_id,
                product_id=product_id,
                product_name=name,
                max_level=level or role_default_level(roles[workspace_id]),
                explicit=level is not None,
            )
        )
    return found


class MemberLevelService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)
        self._members = MemberService(clock)

    async def page(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: MemberFilter,
        limit: int,
        offset: int,
    ) -> MemberLevelsPage:
        """The member x product table: a page of members (as the member list) and every
        product of the workspace by name; four queries whatever the size."""
        members, total = await self._members.list_members(
            db, workspace_id=workspace_id, filters=filters, limit=limit, offset=offset
        )
        products = [
            ProductRef(product_id, name, active)
            for product_id, name, active in await db.execute(
                select(Product.id, Product.name, Product.active)
                .where(Product.workspace_id == workspace_id)
                .order_by(Product.name, Product.id)
            )
        ]
        product_ids = [product.id for product in products]
        recorded = await recorded_levels(
            db, workspace_id=workspace_id, user_ids=[member.user_id for member in members]
        )
        items = [
            MemberLevels(
                member, effective_levels(member.role, product_ids, recorded.get(member.user_id, {}))
            )
            for member in members
        ]
        return MemberLevelsPage(products=products, items=items, total=total)

    async def set_levels(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: Role,
        user_id: uuid.UUID,
        changes: Sequence[LevelChange],
        ip: str | None,
    ) -> MemberLevels:
        """Record or remove the member's level in the given products; the others stay.

        404 when the user is not a member, 403 ``role_not_allowed`` for a member whose role is
        above the caller's, 422 ``member_level_product_invalid`` for a product not in the
        workspace. Audited (``member_level.updated``) only when something changes.
        """
        row = (
            await db.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
            )
        ).one_or_none()
        if row is None:
            raise NotFoundError("Member not found.")
        membership, user = row
        ensure_role_within(actor_role, membership.role)
        wanted = [change.product_id for change in changes]
        found = await existing_products(db, workspace_id, wanted, lock=True)
        missing = missing_ids(wanted, found)
        if missing:
            raise MemberLevelProductInvalidError(
                "Some products do not exist in this workspace.",
                details={"product_ids": missing},
            )
        current = (
            await recorded_levels(
                db, workspace_id=workspace_id, user_ids=[user_id], product_ids=wanted
            )
        ).get(user_id, {})
        audit_changes: list[JSONValue] = []
        for change in changes:
            before = current.get(change.product_id)
            if before == change.max_level:
                continue
            await self._apply(db, workspace_id, user_id, change)
            audit_changes.append(
                {
                    "product_id": str(change.product_id),
                    "from": None if before is None else before.value,
                    "to": None if change.max_level is None else change.max_level.value,
                }
            )
        if audit_changes:
            await self._audit.record(
                db,
                action=AuditAction.MEMBER_LEVEL_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=AuditTarget("membership", str(membership.id)),
                metadata={"user_id": str(user_id), "changes": audit_changes},
                ip=ip,
            )
        page_products = await db.scalars(
            select(Product.id)
            .where(Product.workspace_id == workspace_id)
            .order_by(Product.name, Product.id)
        )
        product_ids = list(page_products)
        recorded = await recorded_levels(db, workspace_id=workspace_id, user_ids=[user_id])
        member = Member(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=membership.role,
            joined_at=membership.created_at,
        )
        return MemberLevels(
            member, effective_levels(membership.role, product_ids, recorded.get(user_id, {}))
        )

    @staticmethod
    async def _apply(
        db: AsyncSession,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        change: LevelChange,
    ) -> None:
        if change.max_level is None:
            await db.execute(
                delete(MemberProductLevel).where(
                    MemberProductLevel.workspace_id == workspace_id,
                    MemberProductLevel.user_id == user_id,
                    MemberProductLevel.product_id == change.product_id,
                )
            )
            return
        # An upsert, so a concurrent request recording the same pair cannot break the key.
        statement = insert(MemberProductLevel).values(
            workspace_id=workspace_id,
            product_id=change.product_id,
            user_id=user_id,
            max_level=change.max_level,
        )
        await db.execute(
            statement.on_conflict_do_update(
                index_elements=[MemberProductLevel.product_id, MemberProductLevel.user_id],
                set_={"max_level": statement.excluded.max_level, "updated_at": func.now()},
            )
        )
