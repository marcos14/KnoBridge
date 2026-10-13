"""The minimum level of a source through the API (``docs/specs/produtos-e-niveis.md``, "Quem
muda e o que acontece"): the kind's default, set and changed only by owners and admins, the
chunks recomputed in the same request without reindexing, the audit and the list filter."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from api_support import ApiEnv, SessionFactory, run_db
from index_support import (
    IndexOverrides,
    add_documents,
    base,
    build_world,
    create_source,
    error_code,
    install,
    post_source,
    source_path,
)
from sqlalchemy import select

from knobridge.core.db import system_session
from knobridge.ingestion.models import Chunk, Document
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _chunk_levels(api: ApiEnv, source_id: str) -> set[ResponseLevel]:
    async def scenario(factory: SessionFactory) -> set[ResponseLevel]:
        async with system_session(factory) as db:
            rows = await db.scalars(
                select(Chunk.min_level)
                .join(Document, Document.id == Chunk.document_id)
                .where(Document.source_id == uuid.UUID(source_id))
            )
            return set(rows)

    return run_db(api.database_url, scenario)


def test_source_starts_at_the_default_of_its_kind(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)

    folder = post_source(api, world).json()
    tickets = post_source(api, world, kind="tickets", config={}).json()

    assert (folder["min_level"], folder["min_level_is_default"]) == ("end_user", True)
    assert (tickets["min_level"], tickets["min_level_is_default"]) == ("support", True)


def test_only_admins_set_a_level_other_than_the_default(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR, Role.ADMIN)

    refused = post_source(api, world, min_level="support")
    default = post_source(api, world, min_level="end_user")
    api.login(world.users[1])
    allowed = post_source(api, world, min_level="support")

    assert error_code(refused) == (403, "forbidden")
    assert refused.json()["error"]["details"] == {"required_role": "admin"}
    assert default.status_code == 201
    assert allowed.status_code == 201, allowed.text
    assert (allowed.json()["min_level"], allowed.json()["min_level_is_default"]) == (
        "support",
        False,
    )


def test_level_change_recomputes_the_chunks_and_is_audited(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.OWNER)
    source_id = create_source(api, world, name="Manual")
    add_documents(api, world, source_id, {"docs/a.md": 2, "docs/b.md": 1})
    before = _chunk_levels(api, source_id)

    response = api.client.patch(
        source_path(world, source_id), json={"min_level": "support"}, headers=api.csrf_headers()
    )
    unchanged = api.client.patch(
        source_path(world, source_id), json={"min_level": "support"}, headers=api.csrf_headers()
    )

    assert response.status_code == 200, response.text
    assert (response.json()["min_level"], response.json()["min_level_is_default"]) == (
        "support",
        False,
    )
    # Written straight to the database, the chunks had the column default (product_dev).
    assert before == {ResponseLevel.PRODUCT_DEV}
    assert _chunk_levels(api, source_id) == {ResponseLevel.SUPPORT}
    assert index.starter.started == []
    assert unchanged.status_code == 200
    events = [
        details
        for action, details in api.workspace_audit(world.workspace_id)
        if action == "source.min_level_changed"
    ]
    assert events == [{"name": "Manual", "from": "end_user", "to": "support"}]


def test_editor_cannot_change_the_level_but_edits_the_rest(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)

    refused = api.client.patch(
        source_path(world, source_id), json={"min_level": "support"}, headers=api.csrf_headers()
    )
    same = api.client.patch(
        source_path(world, source_id),
        json={"min_level": "end_user", "name": "Renomeada"},
        headers=api.csrf_headers(),
    )

    assert error_code(refused) == (403, "forbidden")
    assert refused.json()["error"]["details"] == {"required_role": "admin"}
    assert same.status_code == 200, same.text
    assert (same.json()["name"], same.json()["min_level"]) == ("Renomeada", "end_user")


def test_sources_filter_by_level(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.OWNER)
    folder = create_source(api, world)
    tickets = create_source(api, world, kind="tickets", config={})

    def listed(level: str) -> list[str]:
        response = api.client.get(
            f"{base(world.workspace_id)}/sources", params={"min_level": level}
        )
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert listed("end_user") == [folder]
    assert listed("support") == [tickets]
    assert listed("product_dev") == []
