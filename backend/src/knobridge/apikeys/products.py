"""The products a key sees as models in the OpenAI-compatible API (``docs/specs/api-publica.md``,
"Modelo = produto e nível").

Runs in a session scoped to the key's workspace. ``model`` is ``<product>`` or
``<product>:<level>``: a trailing ``:end_user``, ``:support`` or ``:product_dev`` is the level
and the rest is the product, by its exact name (case-sensitive) or its id. A product name never
ends in a level (``ck_products_name_without_level``), so the reading is never ambiguous. A
product that does not exist, is inactive or is outside the key's scope reads as missing (404
``model_not_found``), never as forbidden; a level above the key's maximum is 403
``level_not_allowed``; without a level, the key's maximum.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.apikeys.auth import ApiKeyIdentity
from knobridge.core.errors import NotFoundError
from knobridge.levels.level import ResponseLevel, levels_up_to
from knobridge.levels.policy import CeilingReason, check_level
from knobridge.products.models import Product

MODEL_NOT_FOUND = "model_not_found"
_LEVELS = {level.value: level for level in ResponseLevel}


@dataclass(frozen=True)
class KeyModel:
    """A model of the key: the product, the level it answers at and whether ``model`` named it."""

    product: Product
    level: ResponseLevel
    level_explicit: bool


def split_model(model: str) -> tuple[str, ResponseLevel | None]:
    """``(product, level)`` of ``model``; the level is ``None`` without a level suffix."""
    head, separator, tail = model.rpartition(":")
    if separator and tail in _LEVELS:
        return head, _LEVELS[tail]
    return model, None


def _visible(identity: ApiKeyIdentity) -> list[ColumnElement[bool]]:
    conditions = [Product.workspace_id == identity.workspace_id, Product.active.is_(True)]
    if identity.product_ids is not None:
        conditions.append(Product.id.in_(identity.product_ids))
    return conditions


async def list_key_products(
    db: AsyncSession, identity: ApiKeyIdentity, *, limit: int | None = None
) -> Sequence[Product]:
    """Active products of the key's scope, by name (at most ``limit``, when given)."""
    rows = await db.scalars(
        select(Product).where(*_visible(identity)).order_by(Product.name, Product.id).limit(limit)
    )
    return rows.all()


def key_models(identity: ApiKeyIdentity, products: Sequence[Product]) -> list[KeyModel]:
    """The combinations the key may ask: per product, without a level (the key's maximum) and
    then each level up to the maximum, in order."""
    return [
        model
        for product in products
        for model in (
            KeyModel(product, identity.max_level, level_explicit=False),
            *(KeyModel(product, level, True) for level in levels_up_to(identity.max_level)),
        )
    ]


def _as_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def find_key_product(
    db: AsyncSession, identity: ApiKeyIdentity, reference: str
) -> Product | None:
    """The visible product named ``reference`` (exact name or id; the id wins when both match),
    or ``None``. Also resolves the ``product`` argument of the MCP tools (``mcp/tools.py``)."""
    product_id = _as_uuid(reference)
    match = Product.name == reference
    if product_id is not None:
        match = or_(match, Product.id == product_id)
    found = (await db.scalars(select(Product).where(*_visible(identity), match))).all()
    if not found:
        return None
    return next((item for item in found if item.id == product_id), found[0])


async def resolve_model(db: AsyncSession, identity: ApiKeyIdentity, model: str) -> KeyModel:
    """The product and level of ``model``: 404 ``model_not_found`` for an unknown product (the
    whole value in the message), then 403 ``level_not_allowed`` above the key's maximum."""
    reference, level = split_model(model)
    product = await find_key_product(db, identity, reference)
    if product is None:
        raise NotFoundError(f"The model '{model}' does not exist.", code=MODEL_NOT_FOUND)
    effective = level or identity.max_level
    check_level(effective, identity.max_level, CeilingReason.API_KEY)
    return KeyModel(product, effective, level_explicit=level is not None)
