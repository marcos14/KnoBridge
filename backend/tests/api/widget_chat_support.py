"""Helpers for the tests of the visitor's conversation of the widget: a widget over the chat
world of ``chat_support``, the public calls with ``Origin`` and the visitor's token, the signing
secret written straight in the database and the example identity of ``docs/specs/widget.md``.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from chat_support import World, build_world, events
from fastapi import FastAPI
from sqlalchemy import update
from ticket_request_support import configured_world
from widget_api_support import SITE, create_widget

from knobridge.core.crypto import SecretBox
from knobridge.core.db import system_session
from knobridge.core.settings import Settings
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.tenancy.models import Role
from knobridge.widget.keys import SIGNING_SECRET_KEY_INFO, seal_signing_secret
from knobridge.widget.models import Widget

# The reproducible example of the spec ("Exemplo reproduzível"); test values only.
SPEC_SECRET = "kbs_teste-NAO-use-em-producao-0123456789abcdefg"  # noqa: S105 - spec test value
SPEC_IDENTITY = (
    "v1.eyJzdWIiOiJjbGllbnRlLTQyIiwibmFtZSI6IkFuYSBTb3V6YSIsImVtYWlsIjoiYW5hQGV4ZW1wbG8uY29tLmJy"
    "IiwiaWF0IjoxNzkxODAwMDAwLCJleHAiOjE3OTE4MDM2MDB9."
    "880cf2b97633c3f6e883162cbdb90e927e79642940f40d8f81f79a9e0b10bec2"
)
# Inside the validity of ``SPEC_IDENTITY`` (2026-10-12, 10:13:20 to 11:13:20 UTC).
SPEC_VALID_AT = datetime(2026, 10, 12, 10, 30, tzinfo=UTC)
QUESTION = "Como fecho o caixa?"


@dataclass(frozen=True)
class WidgetWorld:
    world: World
    widget: dict[str, Any]

    @property
    def key(self) -> str:
        return str(self.widget["public_key"])

    @property
    def widget_id(self) -> str:
        return str(self.widget["id"])


@dataclass(frozen=True)
class Opened:
    conversation_id: str
    token: str
    body: dict[str, Any]


def widget_world(
    api: ApiEnv, *, tickets: bool = False, model: str = "fake-model", **fields: object
) -> WidgetWorld:
    """An owner's workspace with the chat world's product (every level answering with
    ``model``) and a widget of it allowing ``SITE``; ``tickets`` gives the product a configured
    webhook (call ``ticket_request_support.install`` first)."""
    world = (
        configured_world(api, Role.OWNER) if tickets else build_world(api, Role.OWNER, model=model)
    )
    return WidgetWorld(world, create_widget(api, world.workspace_id, world.assistant_id, **fields))


def clear_level(api: ApiEnv, workspace_id: uuid.UUID, level: ResponseLevel) -> None:
    """Leave ``level`` without credential and model in the workspace."""

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(WorkspaceLevel.workspace_id == workspace_id, WorkspaceLevel.level == level)
                .values(credential_id=None, model=None)
            )

    run_db(api.database_url, scenario)


def conversations_path(key: str, conversation_id: str | None = None, suffix: str = "") -> str:
    base = f"/v1/widget/{key}/conversations"
    return (base if conversation_id is None else f"{base}/{conversation_id}") + suffix


def visitor_headers(token: str | None, origin: str = SITE) -> dict[str, str]:
    headers = {"Origin": origin}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def post_conversation(
    api: ApiEnv, key: str, body: dict[str, object] | None = None, origin: str = SITE
) -> httpx.Response:
    return api.client.post(conversations_path(key), json=body or {}, headers={"Origin": origin})


def open_conversation(api: ApiEnv, key: str, **body: object) -> Opened:
    response = post_conversation(api, key, body)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return Opened(str(created["conversation"]["id"]), str(created["visitor_token"]), created)


def ask_widget(
    api: ApiEnv, key: str, opened: Opened, question: str = QUESTION, token: str | None = None
) -> httpx.Response:
    return api.client.post(
        conversations_path(key, opened.conversation_id, "/messages"),
        json={"content": question},
        headers=visitor_headers(token or opened.token),
    )


def read_conversation(
    api: ApiEnv, key: str, opened: Opened, token: str | None = None, **params: object
) -> httpx.Response:
    return api.client.get(
        conversations_path(key, opened.conversation_id),
        params={name: str(value) for name, value in params.items()},
        headers=visitor_headers(token or opened.token),
    )


def answer_id(response: httpx.Response) -> str:
    """The id of the answer streamed in ``response``."""
    return str(events(response)[0][1]["message_id"])


def set_signing_secret(api: ApiEnv, widget_id: str, secret: str = SPEC_SECRET) -> None:
    """Store ``secret`` as the widget's signing secret (the panel only generates random ones)."""
    settings = cast(Settings, cast(FastAPI, api.client.app).state.settings)
    box = SecretBox.derive(settings.secret_key.get_secret_value(), info=SIGNING_SECRET_KEY_INFO)

    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            widget = await db.get(Widget, uuid.UUID(widget_id))
            assert widget is not None
            widget.signing_secret_ciphertext = seal_signing_secret(box, widget, secret)
            widget.signing_secret_created_at = datetime(2026, 10, 1, tzinfo=UTC)

    run_db(api.database_url, scenario)


def move_clock_to(api: ApiEnv, moment: datetime) -> None:
    api.clock.advance(moment - api.clock.now())
