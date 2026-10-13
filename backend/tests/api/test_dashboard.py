"""``GET /v1/workspaces/{id}/dashboard``: the cards and first steps of the Início screen.

Any member reads it; the month's cost only for owners and admins. The clock is frozen at
``START`` (2026-10-10 12:00 UTC), so the month starts on 2026-10-01.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from admin_chat_support import count_statements
from api_support import START, ApiEnv, SessionFactory, run_db
from sqlalchemy import update
from usage_support import (
    UsageWorld,
    add_answer,
    add_collection,
    add_conversation,
    add_run,
    add_source,
    usage_path,
    usage_world,
)

from knobridge.conversations.models import Feedback, FeedbackRating, MessageStatus
from knobridge.core.db import system_session
from knobridge.ingestion.models import RunStatus
from knobridge.levels.level import ResponseLevel
from knobridge.levels.models import WorkspaceLevel
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

MONTH = datetime(2026, 10, 1, tzinfo=UTC)
CHECKLIST_KEYS = ["provider", "collection", "source", "levels", "product", "chat"]


def _dashboard(api: ApiEnv, world: UsageWorld) -> dict[str, object]:
    response = api.client.get(usage_path(world, "dashboard"))
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _rate(api: ApiEnv, world: UsageWorld, message_id: uuid.UUID, rating: FeedbackRating) -> None:
    async def scenario(factory: SessionFactory) -> None:
        async with system_session(factory) as db:
            db.add(
                Feedback(
                    workspace_id=world.workspace_id,
                    message_id=message_id,
                    user_id=world.users[0].id,
                    rating=rating,
                )
            )

    run_db(api.database_url, scenario)


def _link_product(api: ApiEnv, world: UsageWorld, collection_id: uuid.UUID) -> None:
    response = api.client.patch(
        usage_path(world, f"products/{world.assistant_id}"),
        json={"collection_ids": [str(collection_id)]},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text


def test_dashboard_cards_of_the_month(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)
    collection = add_collection(api, world, "Docs")
    manual = add_source(api, world, collection, "Manual")
    add_source(api, world, collection, "Antiga", active=False)
    add_run(api, world, manual, finished_at=START - timedelta(days=1), tokens=10, cost="0.5")
    add_run(api, world, manual, finished_at=START - timedelta(days=2), status=RunStatus.FAILED)
    # Failed more than 7 days ago, and in the previous month.
    add_run(
        api, world, manual, finished_at=MONTH - timedelta(days=3), cost="9", status=RunStatus.FAILED
    )
    conversation = add_conversation(api, world, created_at=MONTH + timedelta(days=1))
    add_conversation(api, world, created_at=MONTH - timedelta(days=1))
    liked = add_answer(api, world, conversation, at=MONTH + timedelta(days=2), cost="0.25")
    disliked = add_answer(api, world, conversation, at=MONTH + timedelta(days=2), tokens=None)
    old = add_answer(api, world, conversation, at=MONTH - timedelta(days=2), cost="4")
    _rate(api, world, liked, FeedbackRating.UP)
    _rate(api, world, disliked, FeedbackRating.DOWN)
    _rate(api, world, old, FeedbackRating.UP)

    body = _dashboard(api, world)

    assert body["month_start"] == "2026-10-01T00:00:00Z"
    assert body["documents"] == 0
    assert body["sources"] == {"total": 2, "active": 1}
    assert body["failed_runs"] == 1
    assert body["conversations_month"] == 1
    assert body["feedback_month"] == {"up": 1, "down": 1}
    assert body["cost_month"] == {
        "embedding_cost_usd": 0.5,
        "chat_cost_usd": 0.25,
        "cost_usd": 0.75,
        "partial": True,
    }


def test_dashboard_cost_is_not_partial_when_everything_is_priced(api: ApiEnv) -> None:
    world = usage_world(api, Role.ADMIN)
    collection = add_collection(api, world, "Docs")
    add_run(api, world, add_source(api, world, collection, "Manual"), finished_at=START, cost="1")

    assert _dashboard(api, world)["cost_month"] == {
        "embedding_cost_usd": 1.0,
        "chat_cost_usd": 0.0,
        "cost_usd": 1.0,
        "partial": False,
    }


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
def test_dashboard_hides_the_cost_below_admin(api: ApiEnv, role: Role) -> None:
    world = usage_world(api, Role.OWNER, role)
    api.login(world.users[1])

    body = _dashboard(api, world)

    assert body["cost_month"] is None
    assert body["sources"] == {"total": 0, "active": 0}


def test_dashboard_checklist_follows_the_setup(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    def done() -> dict[str, bool]:
        items: list[dict[str, object]] = _dashboard(api, world)["checklist"]  # type: ignore[assignment]
        assert [item["key"] for item in items] == CHECKLIST_KEYS
        return {str(item["key"]): bool(item["done"]) for item in items}

    # The world already has a provider on every level and a product (without a collection).
    assert done() == dict.fromkeys(CHECKLIST_KEYS, False) | {"provider": True, "levels": True}
    collection = add_collection(api, world, "Docs")
    source = add_source(api, world, collection, "Manual")
    add_run(api, world, source, finished_at=START, status=RunStatus.FAILED)
    assert done()["collection"]
    assert not done()["source"]
    add_run(api, world, source, finished_at=START)
    _link_product(api, world, collection)
    conversation = add_conversation(api, world)
    add_answer(api, world, conversation, at=START)  # completed, without citations
    add_answer(api, world, conversation, at=START, cited=True, status=MessageStatus.FAILED)
    assert done() == dict.fromkeys(CHECKLIST_KEYS, True) | {"chat": False}
    add_answer(api, world, conversation, at=START, cited=True)
    assert done() == dict.fromkeys(CHECKLIST_KEYS, True)


def test_dashboard_inactive_product_does_not_count(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)
    _link_product(api, world, add_collection(api, world, "Docs"))
    response = api.client.patch(
        usage_path(world, f"products/{world.assistant_id}"),
        json={"active": False},
        headers=api.csrf_headers(),
    )
    assert response.status_code == 200, response.text

    items: list[dict[str, object]] = _dashboard(api, world)["checklist"]  # type: ignore[assignment]

    assert {"key": "product", "done": False} in items


def test_dashboard_levels_item_needs_the_end_user_model(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    async def clear(factory: SessionFactory, level: ResponseLevel) -> None:
        async with system_session(factory) as db:
            await db.execute(
                update(WorkspaceLevel)
                .where(
                    WorkspaceLevel.workspace_id == world.workspace_id,
                    WorkspaceLevel.level == level,
                )
                .values(credential_id=None, model=None)
            )

    def levels_done() -> bool:
        items: list[dict[str, object]] = _dashboard(api, world)["checklist"]  # type: ignore[assignment]
        return {str(item["key"]): bool(item["done"]) for item in items}["levels"]

    run_db(api.database_url, lambda factory: clear(factory, ResponseLevel.PRODUCT_DEV))
    still_done = levels_done()
    run_db(api.database_url, lambda factory: clear(factory, ResponseLevel.END_USER))

    assert still_done
    assert not levels_done()


def test_dashboard_is_isolated_between_workspaces(api: ApiEnv) -> None:
    mine = usage_world(api, Role.OWNER)
    other = usage_world(api, Role.OWNER)
    collection = add_collection(api, other, "Docs")
    add_run(api, other, add_source(api, other, collection, "Manual"), finished_at=START, cost="3")
    add_conversation(api, other, created_at=START)

    response = api.client.get(usage_path(mine, "dashboard"))
    api.login(mine.users[0])
    body = _dashboard(api, mine)

    assert response.status_code == 404
    assert body["sources"] == {"total": 0, "active": 0}
    assert body["conversations_month"] == 0
    assert body["cost_month"] == {
        "embedding_cost_usd": 0.0,
        "chat_cost_usd": 0.0,
        "cost_usd": 0.0,
        "partial": False,
    }


def test_dashboard_takes_a_constant_number_of_statements(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)
    with count_statements(api) as before:
        _dashboard(api, world)
    collection = add_collection(api, world, "Docs")
    for index in range(3):
        source = add_source(api, world, collection, f"Fonte {index}")
        add_run(api, world, source, finished_at=START, status=RunStatus.FAILED)
    with count_statements(api) as after:
        _dashboard(api, world)

    assert len(after) == len(before)
