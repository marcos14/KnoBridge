"""``GET /v1/admin/dashboard`` and ``GET /v1/admin/health``: the superadmin's view of the instance.

The database is shared by the whole session, so instance counts are checked by difference;
the usage period is in 2031, where only this module writes.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from admin_chat_support import count_statements
from api_support import START, ApiEnv
from fastapi import FastAPI
from usage_support import (
    UsageWorld,
    add_answer,
    add_collection,
    add_conversation,
    add_run,
    add_source,
    usage_world,
)

from fakes.temporal_probe import FakeTemporalProbe
from knobridge import __version__
from knobridge.api.admin_dashboard import get_temporal_probe
from knobridge.conversations.models import MessageStatus
from knobridge.ingestion.models import RunStatus
from knobridge.tenancy.models import Role, UserStatus, WorkspaceStatus

pytestmark = pytest.mark.integration

PERIOD = {"from": "2031-01-01T00:00:00Z", "to": "2031-01-08T00:00:00Z"}
IN_PERIOD = datetime(2031, 1, 2, 12, tzinfo=UTC)
NOW = START.isoformat().replace("+00:00", "Z")


def _superadmin(api: ApiEnv) -> None:
    api.login(api.create_user(superadmin=True))


def _dashboard(api: ApiEnv, params: dict[str, str] | None = None) -> dict[str, object]:
    response = api.client.get("/v1/admin/dashboard", params=PERIOD if params is None else params)
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _usage_world(api: ApiEnv) -> UsageWorld:
    return usage_world(api, Role.OWNER)


def test_admin_dashboard_counts_by_difference(api: ApiEnv) -> None:
    _superadmin(api)
    before = _dashboard(api)
    world = _usage_world(api)
    suspended = api.create_user()
    api.set_user_status(suspended.id, UserStatus.SUSPENDED)
    api.set_workspace_status(world.workspace_id, WorkspaceStatus.SUSPENDED)
    source = add_source(api, world, add_collection(api, world, "Docs"), "Manual")
    add_run(api, world, source, finished_at=START - timedelta(days=1), status=RunStatus.FAILED)
    add_run(api, world, source, finished_at=START - timedelta(days=8), status=RunStatus.FAILED)
    conversation = add_conversation(api, world)
    add_answer(api, world, conversation, at=START - timedelta(hours=1), status=MessageStatus.FAILED)
    _superadmin(api)

    after = _dashboard(api)

    def delta(group: str, field: str | None = None) -> int:
        old, new = before[group], after[group]
        if field is not None:
            old, new = old[field], new[field]  # type: ignore[index]
        return cast(int, new) - cast(int, old)

    assert delta("workspaces", "total") == 1
    assert delta("workspaces", "suspended") == 1
    assert delta("workspaces", "active") == 0
    assert delta("users", "total") == 3  # the owner, the suspended user, the new superadmin
    assert delta("users", "suspended") == 1
    assert delta("users", "superadmins") == 1
    assert delta("users", "active_30d") == 2  # owner and superadmin logged in
    assert delta("failed_runs_7d") == 1
    assert delta("failed_answers_7d") == 1


def test_admin_dashboard_recent_failures(api: ApiEnv) -> None:
    world = _usage_world(api)
    source = add_source(api, world, add_collection(api, world, "Docs"), "Manual")
    newest = START + timedelta(days=3650)
    run_id = add_run(
        api,
        world,
        source,
        finished_at=newest,
        status=RunStatus.FAILED,
        error="source_unavailable: x",
    )
    _superadmin(api)

    failures: list[dict[str, object]] = _dashboard(api)["recent_failures"]  # type: ignore[assignment]

    assert len(failures) <= 10
    assert failures[0] == {
        "run_id": str(run_id),
        "workspace_id": str(world.workspace_id),
        "workspace_name": failures[0]["workspace_name"],
        "source_id": str(source),
        "source_name": "Manual",
        "error": "source_unavailable: x",
        "finished_at": newest.isoformat().replace("+00:00", "Z"),
    }
    assert isinstance(failures[0]["workspace_name"], str)


def test_admin_dashboard_usage_of_the_period(api: ApiEnv) -> None:
    cheap, costly = _usage_world(api), _usage_world(api)
    for world, cost in ((cheap, "0.1"), (costly, "2")):
        source = add_source(api, world, add_collection(api, world, "Docs"), "Manual")
        add_run(api, world, source, finished_at=IN_PERIOD, tokens=100, cost=cost)
        add_answer(
            api, world, add_conversation(api, world), at=IN_PERIOD, tokens=(10, 2), cost=cost
        )
    add_answer(api, cheap, add_conversation(api, cheap), at=IN_PERIOD, tokens=None)
    _superadmin(api)

    usage: dict[str, object] = _dashboard(api)["usage"]  # type: ignore[assignment]

    assert usage["period_start"] == "2031-01-01T00:00:00Z"
    assert usage["period_end"] == "2031-01-08T00:00:00Z"
    assert {
        key: usage[key]
        for key in usage
        if key not in {"by_workspace", "period_start", "period_end"}
    } == {
        "embedding_tokens": 200,
        "embedding_cost_usd": 2.1,
        "runs": 2,
        "unpriced_runs": 0,
        "chat_input_tokens": 20,
        "chat_output_tokens": 4,
        "chat_cost_usd": 2.1,
        "answers": 3,
        "unpriced_answers": 1,
        "cost_usd": 4.2,
    }
    by_workspace: list[dict[str, object]] = usage["by_workspace"]  # type: ignore[assignment]
    assert [(item["workspace_id"], item["cost_usd"]) for item in by_workspace] == [
        (str(costly.workspace_id), 4.0),
        (str(cheap.workspace_id), 0.2),
    ]
    assert by_workspace[0]["embedding_tokens"] == 100
    assert (by_workspace[1]["chat_input_tokens"], by_workspace[1]["chat_output_tokens"]) == (10, 2)


def test_admin_dashboard_default_period_and_validation(api: ApiEnv) -> None:
    _superadmin(api)

    usage: dict[str, object] = _dashboard(api, {})["usage"]  # type: ignore[assignment]
    too_long = api.client.get(
        "/v1/admin/dashboard", params={"from": "2020-01-01T00:00:00Z", "to": "2031-01-01T00:00:00Z"}
    )

    assert usage["period_end"] == NOW
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "usage_period_too_long"


@pytest.mark.parametrize("path", ["/v1/admin/dashboard", "/v1/admin/health"])
def test_admin_dashboard_is_for_superadmins(api: ApiEnv, path: str) -> None:
    world = _usage_world(api)
    api.login(world.users[0])

    response = api.client.get(path)
    api.client.post("/v1/auth/logout", headers=api.csrf_headers())
    anonymous = api.client.get(path)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert anonymous.status_code == 401


def test_admin_dashboard_takes_a_constant_number_of_statements(api: ApiEnv) -> None:
    _superadmin(api)
    with count_statements(api) as before:
        _dashboard(api)
    for _ in range(2):
        world = _usage_world(api)
        source = add_source(api, world, add_collection(api, world, "Docs"), "Manual")
        add_run(api, world, source, finished_at=IN_PERIOD, cost="1", status=RunStatus.FAILED)
    _superadmin(api)
    with count_statements(api) as after:
        _dashboard(api)

    assert len(after) == len(before)


@pytest.fixture
def probe(api: ApiEnv) -> Generator[FakeTemporalProbe]:
    fake = FakeTemporalProbe(last_seen=START - timedelta(seconds=10))
    app = cast(FastAPI, api.client.app)
    app.dependency_overrides[get_temporal_probe] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_temporal_probe, None)


def _health(api: ApiEnv) -> dict[str, object]:
    response = api.client.get("/v1/admin/health")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_admin_health_all_services_ok(api: ApiEnv, probe: FakeTemporalProbe) -> None:
    _superadmin(api)

    body = _health(api)

    ok = {"status": "ok", "checked_at": NOW, "detail": None}
    assert body == {
        "version": __version__,
        "api": ok,
        "database": ok,
        "temporal": ok,
        "worker": ok,
    }


def test_admin_health_reports_temporal_down_in_the_body(
    api: ApiEnv, probe: FakeTemporalProbe
) -> None:
    probe.unavailable = True
    _superadmin(api)

    body = _health(api)

    assert body["temporal"] == {
        "status": "error",
        "checked_at": NOW,
        "detail": "temporal unreachable",
    }
    assert body["worker"] == {"status": "unknown", "checked_at": NOW, "detail": "temporal down"}
    assert body["database"]["status"] == "ok"  # type: ignore[index]


def test_admin_health_reports_an_absent_worker(api: ApiEnv, probe: FakeTemporalProbe) -> None:
    probe.last_seen = START - timedelta(seconds=61)
    _superadmin(api)

    body = _health(api)

    assert body["worker"] == {
        "status": "error",
        "checked_at": NOW,
        "detail": "no worker polling the task queue",
    }


def test_get_temporal_probe_reads_app_state(api: ApiEnv) -> None:
    app = cast(FastAPI, api.client.app)
    request = type("Request", (), {"app": app})()

    probe = get_temporal_probe(request)  # type: ignore[arg-type]

    assert type(probe).__name__ == "LazyTemporalHealthProbe"
