"""Helpers for the ticket ingest route tests: a workspace with a ``tickets`` source and its
ingest token created through the panel API, batch bodies and direct reads of the inbox.

Not a test module (pytest only collects ``test_*.py``); imported by its basename.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx2 as httpx
from api_support import ApiEnv, SessionFactory, run_db
from index_support import IndexWorld, build_world, create_source, source_path
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.ingestion.models import Run, Source
from knobridge.tenancy.models import Role
from knobridge.tickets.models import IngestToken, TicketInboxItem

INGEST = "/v1/ingest/tickets"


@dataclass(frozen=True)
class TicketsWorld:
    world: IndexWorld
    source_id: str
    token: str

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.world.workspace_id


def issue_token(api: ApiEnv, world: IndexWorld, source_id: str) -> httpx.Response:
    return api.client.post(
        source_path(world, source_id, "ingest-token"), headers=api.csrf_headers()
    )


def tickets_world(api: ApiEnv, *roles: Role) -> TicketsWorld:
    """A workspace whose first user (owner or admin, left logged in) creates a ``tickets``
    source and issues its token."""
    world = build_world(api, *(roles or (Role.ADMIN,)))
    source_id = create_source(api, world, kind="tickets", config={})
    response = issue_token(api, world, source_id)
    assert response.status_code == 201, response.text
    return TicketsWorld(world, source_id, response.json()["token"])


def ticket(external_id: str = "A-1", **fields: Any) -> dict[str, Any]:  # noqa: ANN401
    body: dict[str, Any] = {
        "external_id": external_id,
        "title": "Erro 4021 ao fechar o caixa",
        "status": "resolved",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T12:00:00Z",
    }
    body.update(fields)
    return body


def upsert(external_id: str = "A-1", **fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"op": "upsert", "ticket": ticket(external_id, **fields)}


def delete(external_id: str = "A-1", deleted_at: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"op": "delete", "external_id": external_id}
    if deleted_at is not None:
        item["deleted_at"] = deleted_at
    return item


def ingest(
    api: ApiEnv, token: str | None, *items: dict[str, Any], body: object = None
) -> httpx.Response:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return api.client.post(
        INGEST, json={"items": list(items)} if body is None else body, headers=headers
    )


def statuses(response: httpx.Response) -> list[str]:
    assert response.status_code == 202, response.text
    return [result["status"] for result in response.json()["results"]]


def inbox(api: ApiEnv, source_id: str) -> dict[str, TicketInboxItem]:
    async def scenario(factory: SessionFactory) -> dict[str, TicketInboxItem]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(TicketInboxItem).where(TicketInboxItem.source_id == uuid.UUID(source_id))
            )
            return {row.external_id: row for row in rows}

    return run_db(api.database_url, scenario)


def stored_token(api: ApiEnv, source_id: str) -> IngestToken | None:
    async def scenario(factory: SessionFactory) -> IngestToken | None:
        async with system_session(factory) as db:
            return (
                await db.scalars(
                    select(IngestToken).where(IngestToken.source_id == uuid.UUID(source_id))
                )
            ).one_or_none()

    return run_db(api.database_url, scenario)


def stored_source(api: ApiEnv, source_id: str) -> Source:
    async def scenario(factory: SessionFactory) -> Source:
        async with system_session(factory) as db:
            return await db.get_one(Source, uuid.UUID(source_id))

    return run_db(api.database_url, scenario)


def source_runs(api: ApiEnv, source_id: str) -> list[Run]:
    async def scenario(factory: SessionFactory) -> list[Run]:
        async with system_session(factory) as db:
            return list(await db.scalars(select(Run).where(Run.source_id == uuid.UUID(source_id))))

    return run_db(api.database_url, scenario)
