"""Maximum levels given to a person per product: the products they may name and recording them
for a new member (``docs/specs/produtos-e-niveis.md``, "Convites com nível").

Shared by the member levels (``members.py``) and the invitations (``tenancy/``), which store
the levels of an invitation and record them when it is accepted.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import MemberProductLevel
from knobridge.products.models import Product


@dataclass(frozen=True)
class LevelGrant:
    """The maximum level of a person in one product."""

    product_id: uuid.UUID
    max_level: ResponseLevel

    def as_json(self) -> dict[str, str]:
        return {"product_id": str(self.product_id), "max_level": self.max_level.value}

    @classmethod
    def from_json(cls, value: dict[str, str]) -> LevelGrant:
        return cls(uuid.UUID(value["product_id"]), ResponseLevel(value["max_level"]))


async def existing_products(
    db: AsyncSession, workspace_id: uuid.UUID, product_ids: Iterable[uuid.UUID], *, lock: bool
) -> set[uuid.UUID]:
    """The ids among ``product_ids`` that are products of the workspace; ``lock`` holds them
    (``FOR KEY SHARE``) until commit, so they cannot be deleted before a write that names
    them."""
    wanted = set(product_ids)
    if not wanted:
        return set()
    statement = select(Product.id).where(
        Product.workspace_id == workspace_id, Product.id.in_(wanted)
    )
    if lock:
        statement = statement.with_for_update(key_share=True)
    return set(await db.scalars(statement))


def missing_ids(wanted: Iterable[uuid.UUID], found: set[uuid.UUID]) -> list[str]:
    """The ids of ``wanted`` not in ``found``, sorted, for ``details.product_ids``."""
    return sorted({str(product_id) for product_id in wanted if product_id not in found})


async def record_grants(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID, grants: Sequence[LevelGrant]
) -> None:
    """Record the levels of a new member; a product deleted meanwhile is skipped."""
    found = await existing_products(
        db, workspace_id, (grant.product_id for grant in grants), lock=True
    )
    db.add_all(
        MemberProductLevel(
            workspace_id=workspace_id,
            product_id=grant.product_id,
            user_id=user_id,
            max_level=grant.max_level,
        )
        for grant in grants
        if grant.product_id in found
    )
    await db.flush()
