"""Shared helpers of the widget tests: a database runner, a widget builder and a seeded
workspace with a product and a widget. Not a test module; imported by its basename."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from knobridge.core.db import create_session_factory, system_session
from knobridge.products.models import Product, ProductTone
from knobridge.tenancy.models import Workspace
from knobridge.widget.keys import generate_public_key
from knobridge.widget.models import Widget

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class Seeded:
    workspace_id: uuid.UUID
    product_id: uuid.UUID
    widget_id: uuid.UUID
    public_key: str


def run_db[T](database_url: str, scenario: Callable[[SessionFactory], Awaitable[T]]) -> T:
    async def run() -> T:
        engine = create_async_engine(database_url, poolclass=NullPool)
        try:
            return await scenario(create_session_factory(engine))
        finally:
            await engine.dispose()

    return asyncio.run(run())


def new_widget(workspace_id: uuid.UUID, product_id: uuid.UUID, **fields: object) -> Widget:
    values: dict[str, object] = {
        "name": f"Site {uuid.uuid4().hex[:8]}",
        "public_key": generate_public_key(),
        "allowed_origins": ["https://app.cliente.example"],
        **fields,
    }
    return Widget(workspace_id=workspace_id, product_id=product_id, **values)


async def seed(factory: SessionFactory) -> Seeded:
    """A new workspace with a product and a widget of it."""
    async with system_session(factory) as db:
        workspace = Workspace(name="W", slug=f"w-{uuid.uuid4().hex[:12]}")
        db.add(workspace)
        await db.flush()
        product = Product(
            workspace_id=workspace.id,
            name="ERP",
            description="",
            instructions="",
            language="pt-BR",
            tone=ProductTone.NEUTRAL,
            no_source_message="Sem fonte.",
        )
        db.add(product)
        await db.flush()
        widget = new_widget(workspace.id, product.id)
        db.add(widget)
        await db.flush()
        return Seeded(workspace.id, product.id, widget.id, widget.public_key)
