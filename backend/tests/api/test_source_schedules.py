"""Source schedules through the API: the Temporal Schedule (a fake ``ScheduleManager``) follows
the source on create, update, pause, deactivation and delete; ``next_run_at`` comes from the
clock; an invalid cron is a 422 that touches nothing; Temporal down never blocks the source."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import cast

import pytest
from api_support import ApiEnv
from fastapi import FastAPI
from index_support import (
    IndexOverrides,
    base,
    build_world,
    create_source,
    error_code,
    install,
    post_source,
    source_path,
)

from fakes.schedule_manager import FakeScheduleManager
from knobridge.ingestion.schedule import SourceSchedule
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

# The API fixture's frozen clock is 2026-10-10 12:00 UTC (a Saturday).
NEXT_3AM = "2026-10-11T03:00:00Z"
NEXT_MONDAY_230 = "2026-10-12T02:30:00Z"


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _patch(api: ApiEnv, path: str, **fields: object) -> dict[str, object]:
    response = api.client.patch(path, json=fields, headers=api.csrf_headers())
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_schedule_created_with_source_cron(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)

    response = post_source(api, world, schedule_cron=" 0  3 * * *", schedule_enabled=True)

    assert response.status_code == 201, response.text
    source_id = uuid.UUID(response.json()["id"])
    assert response.json()["next_run_at"] == NEXT_3AM
    assert index.schedules.schedules == {
        source_id: SourceSchedule(world.workspace_id, source_id, "0 3 * * *", paused=False)
    }


def test_schedule_created_paused_when_disabled(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)

    response = post_source(api, world, schedule_cron="0 3 * * *")

    source_id = uuid.UUID(response.json()["id"])
    assert response.json()["next_run_at"] is None
    assert index.schedules.schedules[source_id].paused is True


def test_source_without_cron_has_no_schedule(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)

    _patch(api, source_path(world, source_id), name="Renamed", active=False)
    deleted = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert deleted.status_code == 204
    assert index.schedules.calls == []


def test_schedule_updated_and_paused(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world, schedule_cron="0 3 * * *", schedule_enabled=True)
    path, key = source_path(world, source_id), uuid.UUID(source_id)

    changed = _patch(api, path, schedule_cron="30 2 * * 1")
    cron = index.schedules.schedules[key].cron
    paused = _patch(api, path, schedule_enabled=False)
    paused_state = index.schedules.schedules[key].paused
    renamed = _patch(api, path, name="Only the name")
    calls_after_rename = len(index.schedules.calls)

    assert (changed["next_run_at"], cron) == (NEXT_MONDAY_230, "30 2 * * 1")
    assert (paused["next_run_at"], paused_state) == (None, True)
    assert renamed["next_run_at"] is None
    assert calls_after_rename == 3  # create, cron change, pause; the rename touches nothing


def test_schedule_removed_when_source_deactivated_and_back(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world, schedule_cron="0 3 * * *", schedule_enabled=True)
    path, key = source_path(world, source_id), uuid.UUID(source_id)

    inactive = _patch(api, path, active=False)
    removed = key not in index.schedules.schedules
    # An inactive source has no schedule to touch when its cron changes.
    _patch(api, path, schedule_cron="0 4 * * *")
    calls_while_inactive = list(index.schedules.calls)
    active = _patch(api, path, active=True)

    assert (inactive["next_run_at"], removed) == (None, True)
    assert calls_while_inactive == [("apply", key), ("remove", key)]
    assert active["next_run_at"] == "2026-10-11T04:00:00Z"
    assert index.schedules.schedules[key].cron == "0 4 * * *"


def test_schedule_removed_with_source(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    deleted_id = create_source(api, world, schedule_cron="0 3 * * *", schedule_enabled=True)
    cleared_id = create_source(api, world, schedule_cron="0 5 * * *")

    deleted = api.client.delete(source_path(world, deleted_id), headers=api.csrf_headers())
    cleared = _patch(api, source_path(world, cleared_id), schedule_cron=None)

    assert deleted.status_code == 204
    assert cleared["schedule_cron"] is None
    assert index.schedules.schedules == {}
    assert index.schedules.calls[-2:] == [
        ("remove", uuid.UUID(deleted_id)),
        ("remove", uuid.UUID(cleared_id)),
    ]


def test_invalid_cron_returns_422(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    source_id = create_source(api, world)

    created = post_source(api, world, schedule_cron="0 3 * *", schedule_enabled=True)
    updated = api.client.patch(
        source_path(world, source_id),
        json={"schedule_cron": "61 * * * *"},
        headers=api.csrf_headers(),
    )

    assert error_code(created) == (422, "source_schedule_invalid")
    assert error_code(updated) == (422, "source_schedule_invalid")
    assert index.schedules.calls == []


def test_source_saved_when_temporal_unavailable(api: ApiEnv, index: IndexOverrides) -> None:
    index.schedules.unavailable = True
    world = build_world(api, Role.EDITOR)

    created = post_source(api, world, schedule_cron="0 3 * * *", schedule_enabled=True)
    source_id = created.json()["id"]
    paused = api.client.patch(
        source_path(world, source_id),
        json={"schedule_enabled": False},
        headers=api.csrf_headers(),
    )
    deleted = api.client.delete(source_path(world, source_id), headers=api.csrf_headers())

    assert (created.status_code, created.json()["next_run_at"]) == (201, NEXT_3AM)
    assert (paused.status_code, paused.json()["schedule_enabled"]) == (200, False)
    assert deleted.status_code == 204


def test_list_sources_shows_next_run(api: ApiEnv, index: IndexOverrides) -> None:
    world = build_world(api, Role.EDITOR)
    create_source(api, world, name="a-scheduled", schedule_cron="0 3 * * *", schedule_enabled=True)
    create_source(api, world, name="b-manual")

    response = api.client.get(f"{base(world.workspace_id)}/sources")

    assert [item["next_run_at"] for item in response.json()["items"]] == [NEXT_3AM, None]


def test_schedule_manager_comes_from_app_state(api: ApiEnv) -> None:
    manager = FakeScheduleManager()
    cast(FastAPI, api.client.app).state.schedule_manager = manager
    world = build_world(api, Role.OWNER)

    source_id = create_source(api, world, schedule_cron="0 3 * * *")

    assert list(manager.schedules) == [uuid.UUID(source_id)]
