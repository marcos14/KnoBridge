"""Manage the products of a workspace: list, get, create, update, delete
(``docs/specs/produtos-e-niveis.md``, "Produto").

Runs in the caller's workspace-scoped session (the route's ``WorkspaceContext.db``). The
collections the product answers from are looked up under the workspace filter (and RLS) and
locked with ``FOR KEY SHARE`` until the transaction ends (a collection of another workspace,
or one that does not exist, is 422 ``product_collection_invalid``); the composite foreign keys
are the last barrier. Updating ``collection_ids`` replaces the whole set. An empty "no source"
message falls back to ``DEFAULT_NO_SOURCE_MESSAGE`` (rule 8 of AGENTS.md). Audit metadata
carries names, collection ids and changed fields, never the instructions nor the webhook URL.
The model of the answers is not the product's: it belongs to each level of the workspace.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.conversations.models import Conversation
from knobridge.core.clock import Clock
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.ingestion.models import Collection
from knobridge.products.listing import ProductFilter, page_products
from knobridge.products.models import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_NO_SOURCE_MESSAGE,
    NAME_LEVEL_SUFFIX_PATTERN,
    Product,
    ProductCollection,
    ProductTone,
)


class ProductNameTakenError(ConflictError):
    code = "product_name_taken"


class ProductNameInvalidError(ValidationError):
    code = "product_name_invalid"


class ProductCollectionInvalidError(ValidationError):
    code = "product_collection_invalid"


@dataclass(frozen=True)
class ProductSettings:
    """Everything a product is created with (already validated at the boundary)."""

    name: str
    description: str
    instructions: str
    language: str
    tone: ProductTone
    # Empty means the default message.
    no_source_message: str
    active: bool
    # Collections the product answers from (no collection: every answer is "no source").
    collection_ids: tuple[uuid.UUID, ...] = ()
    min_similarity: float = DEFAULT_MIN_SIMILARITY
    # Already checked against the SSRF rules by the caller; ``None``: ticket requests off.
    ticket_webhook_url: str | None = None


@dataclass(frozen=True)
class ProductChanges:
    """Fields to change; ``None`` keeps the current value. An empty ``no_source_message``
    resets it to the default."""

    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    language: str | None = None
    tone: ProductTone | None = None
    no_source_message: str | None = None
    active: bool | None = None
    # Replaces the whole set when given.
    collection_ids: tuple[uuid.UUID, ...] | None = None
    min_similarity: float | None = None
    # Applied only when ``ticket_webhook_url_given`` (``None`` then turns the webhook off).
    ticket_webhook_url: str | None = None
    ticket_webhook_url_given: bool = False


def no_source_message_or_default(message: str) -> str:
    return message or DEFAULT_NO_SOURCE_MESSAGE


def check_name(name: str) -> None:
    """A name cannot end in ``:<level>``: it is a ``model`` of the OpenAI-compatible API."""
    if re.search(NAME_LEVEL_SUFFIX_PATTERN, name):
        raise ProductNameInvalidError(
            "A product name cannot end in ':end_user', ':support' or ':product_dev'."
        )


def _target(product: Product) -> AuditTarget:
    return AuditTarget("product", str(product.id))


class ProductService:
    def __init__(self, clock: Clock) -> None:
        self._audit = AuditService(clock)

    async def list_products(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        filters: ProductFilter,
        limit: int,
        offset: int,
    ) -> tuple[list[Product], int]:
        """A page of the workspace's products (``listing.py``)."""
        return await page_products(
            db, workspace_id=workspace_id, filters=filters, limit=limit, offset=offset
        )

    async def get(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        product_id: uuid.UUID,
        active_only: bool = False,
    ) -> Product:
        """One product; an inactive one is "not found" when ``active_only``."""
        product = await self._get(db, workspace_id, product_id)
        if active_only and not product.active:
            raise NotFoundError("Product not found.")
        return product

    async def create(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        settings: ProductSettings,
        ip: str | None,
        duplicated_from: Product | None = None,
    ) -> Product:
        """Create a product; ``duplicated_from`` (the original) goes to the audit."""
        check_name(settings.name)
        await self._lock_collections(db, workspace_id, settings.collection_ids)
        product = Product(
            workspace_id=workspace_id,
            name=settings.name,
            description=settings.description,
            instructions=settings.instructions,
            language=settings.language,
            tone=settings.tone,
            no_source_message=no_source_message_or_default(settings.no_source_message),
            active=settings.active,
            min_similarity=settings.min_similarity,
            ticket_webhook_url=settings.ticket_webhook_url,
        )
        db.add(product)
        await self._flush(db)
        await self._link(db, product, settings.collection_ids)
        await db.refresh(product)
        metadata: dict[str, JSONValue] = {
            "name": product.name,
            "collection_ids": [str(cid) for cid in dict.fromkeys(settings.collection_ids)],
        }
        if duplicated_from is not None:
            metadata["duplicated_from"] = str(duplicated_from.id)
        await self._audit.record(
            db,
            action=AuditAction.PRODUCT_CREATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(product),
            metadata=metadata,
            ip=ip,
        )
        return product

    async def update(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        product_id: uuid.UUID,
        changes: ProductChanges,
        ip: str | None,
    ) -> Product:
        """Apply the given fields; audited only when something actually changes."""
        if changes.name is not None:
            check_name(changes.name)
        product = await self._get(db, workspace_id, product_id)
        if changes.collection_ids is not None:
            await self._lock_collections(db, workspace_id, changes.collection_ids)
        wanted: dict[str, object] = {
            "name": changes.name,
            "description": changes.description,
            "instructions": changes.instructions,
            "language": changes.language,
            "tone": changes.tone,
            "no_source_message": (
                None
                if changes.no_source_message is None
                else no_source_message_or_default(changes.no_source_message)
            ),
            "active": changes.active,
            "min_similarity": changes.min_similarity,
        }
        fields: list[str] = []
        for attribute, value in wanted.items():
            if value is not None and value != getattr(product, attribute):
                setattr(product, attribute, value)
                fields.append(attribute)
        if (
            changes.ticket_webhook_url_given
            and changes.ticket_webhook_url != product.ticket_webhook_url
        ):
            # Audited by name only: a URL may carry a token of the destination.
            product.ticket_webhook_url = changes.ticket_webhook_url
            fields.append("ticket_webhook_url")
        if fields:
            # Before the link table: a name clash must surface as ``product_name_taken``.
            await self._flush(db)
        if changes.collection_ids is not None and await self._relink(
            db, product, changes.collection_ids
        ):
            fields.append("collection_ids")
        if fields:
            # ``updated_at`` is set by the database; load it now (no lazy IO in async code).
            await db.refresh(product)
            await self._audit.record(
                db,
                action=AuditAction.PRODUCT_UPDATED,
                workspace_id=workspace_id,
                actor_user_id=actor_id,
                target=_target(product),
                metadata={"name": product.name, "fields": list(fields)},
                ip=ip,
            )
        return product

    async def delete(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        product_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """Delete the product; its conversations and member levels go with it (cascade)."""
        product = await self._get(db, workspace_id, product_id)
        conversation_count = await db.scalar(
            select(func.count())
            .select_from(Conversation)
            .where(
                Conversation.workspace_id == workspace_id,
                Conversation.product_id == product.id,
            )
        )
        await db.delete(product)
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.PRODUCT_DELETED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=_target(product),
            metadata={"name": product.name, "conversation_count": conversation_count or 0},
            ip=ip,
        )

    async def collections_of(
        self, db: AsyncSession, workspace_id: uuid.UUID, product_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """The collection ids of each product (one query), ordered by id."""
        if not product_ids:
            return {}
        rows = await db.execute(
            select(ProductCollection.product_id, ProductCollection.collection_id)
            .where(
                ProductCollection.workspace_id == workspace_id,
                ProductCollection.product_id.in_(product_ids),
            )
            .order_by(ProductCollection.product_id, ProductCollection.collection_id)
        )
        found: dict[uuid.UUID, list[uuid.UUID]] = {}
        for product_id, collection_id in rows:
            found.setdefault(product_id, []).append(collection_id)
        return found

    async def _relink(
        self, db: AsyncSession, product: Product, collection_ids: Sequence[uuid.UUID]
    ) -> bool:
        """Replace the product's collections; ``False`` when the set is unchanged."""
        current = await self.collections_of(db, product.workspace_id, [product.id])
        if set(current.get(product.id, [])) == set(collection_ids):
            return False
        await db.execute(
            delete(ProductCollection).where(
                ProductCollection.workspace_id == product.workspace_id,
                ProductCollection.product_id == product.id,
            )
        )
        await self._link(db, product, collection_ids)
        # Only the link table changed: bump ``updated_at`` of the product explicitly.
        await db.execute(
            update(Product)
            .where(Product.workspace_id == product.workspace_id, Product.id == product.id)
            .values(updated_at=func.now())
        )
        return True

    @staticmethod
    async def _link(
        db: AsyncSession, product: Product, collection_ids: Sequence[uuid.UUID]
    ) -> None:
        db.add_all(
            ProductCollection(
                workspace_id=product.workspace_id,
                product_id=product.id,
                collection_id=collection_id,
            )
            for collection_id in dict.fromkeys(collection_ids)
        )
        await db.flush()

    @staticmethod
    async def _lock_collections(
        db: AsyncSession, workspace_id: uuid.UUID, collection_ids: Sequence[uuid.UUID]
    ) -> None:
        """Refuse collections that are not in the workspace; hold them until commit."""
        wanted = set(collection_ids)
        if not wanted:
            return
        found = set(
            await db.scalars(
                select(Collection.id)
                .where(Collection.workspace_id == workspace_id, Collection.id.in_(wanted))
                .with_for_update(key_share=True)
            )
        )
        missing = sorted(str(cid) for cid in wanted - found)
        if missing:
            raise ProductCollectionInvalidError(
                "Some collections do not exist in this workspace.",
                details={"collection_ids": missing},
            )

    @staticmethod
    async def _get(db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID) -> Product:
        product = (
            await db.scalars(
                select(Product).where(
                    Product.workspace_id == workspace_id, Product.id == product_id
                )
            )
        ).one_or_none()
        if product is None:
            raise NotFoundError("Product not found.")
        return product

    @staticmethod
    async def _flush(db: AsyncSession) -> None:
        try:
            await db.flush()
        except IntegrityError as exc:
            # Collections are checked and locked first and the other values are validated,
            # so only uq_products_workspace_id_name is left to break. The caller's
            # transaction is now failed and rolls back when this propagates.
            raise ProductNameTakenError(
                "A product with this name already exists in the workspace."
            ) from exc
