"""Helpers for the widget route tests: the panel paths, creating a widget, the public paths and
direct writes for what the panel cannot set (a product's ticket webhook, a widget conversation).

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx2 as httpx
from api_support import START, ApiEnv, SessionFactory, run_db
from sqlalchemy import select

from knobridge.conversations.models import Conversation, ConversationChannel
from knobridge.core.db import system_session
from knobridge.levels.level import ResponseLevel
from knobridge.products.models import Product
from knobridge.widget.models import Widget

SITE = "https://app.cliente.example"


def widgets_path(workspace_id: uuid.UUID, widget_id: str | None = None) -> str:
    base = f"/v1/workspaces/{workspace_id}/widgets"
    return base if widget_id is None else f"{base}/{widget_id}"


def post_widget(
    api: ApiEnv, workspace_id: uuid.UUID, product_id: str, **fields: object
) -> httpx.Response:
    body: dict[str, object] = {
        "product_id": product_id,
        "name": f"Site {uuid.uuid4().hex[:8]}",
        "allowed_origins": [SITE],
        **fields,
    }
    return api.client.post(widgets_path(workspace_id), json=body, headers=api.csrf_headers())


def create_widget(
    api: ApiEnv, workspace_id: uuid.UUID, product_id: str, **fields: object
) -> dict[str, Any]:
    response = post_widget(api, workspace_id, product_id, **fields)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def config_path(public_key: str) -> str:
    return f"/v1/widget/{public_key}/config"


def get_config(api: ApiEnv, public_key: str, origin: str | None = SITE) -> httpx.Response:
    headers = {} if origin is None else {"Origin": origin}
    return api.client.get(config_path(public_key), headers=headers)


def set_ticket_webhook(api: ApiEnv, product_id: str) -> None:
    """Give the product a ticket webhook (URL and secret) without the panel's SSRF checks."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            product = await db.get(Product, uuid.UUID(product_id))
            assert product is not None
            product.ticket_webhook_url = "https://hooks.example/tickets"
            product.ticket_webhook_secret_ciphertext = "v1.x"  # noqa: S105 - a stand-in
            product.ticket_webhook_secret_created_at = START

    run_db(api.database_url, scenario)


def set_product_active(api: ApiEnv, product_id: str, *, active: bool) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            product = await db.get(Product, uuid.UUID(product_id))
            assert product is not None
            product.active = active

    run_db(api.database_url, scenario)


def add_widget_conversation(api: ApiEnv, widget: dict[str, Any]) -> uuid.UUID:
    """A visitor's conversation of the widget, written straight in the database."""

    async def scenario(factory: SessionFactory) -> uuid.UUID:
        async with system_session(factory) as db:
            stored = await db.get(Widget, uuid.UUID(widget["id"]))
            assert stored is not None
            conversation = Conversation(
                workspace_id=stored.workspace_id,
                product_id=stored.product_id,
                widget_id=stored.id,
                visitor_token_hash="b" * 64,
                channel=ConversationChannel.WIDGET,
                level=ResponseLevel.END_USER,
            )
            db.add(conversation)
            await db.flush()
            return conversation.id

    return run_db(api.database_url, scenario)


def conversation_exists(api: ApiEnv, conversation_id: uuid.UUID) -> bool:
    async def scenario(factory: SessionFactory) -> bool:
        async with system_session(factory) as db:
            found = await db.scalar(
                select(Conversation.id).where(Conversation.id == conversation_id)
            )
            return found is not None

    return run_db(api.database_url, scenario)


def stored_widget(api: ApiEnv, widget_id: str) -> Widget | None:
    async def scenario(factory: SessionFactory) -> Widget | None:
        async with system_session(factory) as db:
            return await db.get(Widget, uuid.UUID(widget_id))

    return run_db(api.database_url, scenario)
