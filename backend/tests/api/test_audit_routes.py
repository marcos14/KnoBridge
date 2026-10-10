"""``GET /v1/workspaces/{workspace_id}/audit``: role check, filters, pagination, isolation."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from api_support import START, ApiEnv, SessionFactory, run_db

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import FrozenClock
from knobridge.core.db import system_session
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


def _record(
    api: ApiEnv,
    workspace_id: uuid.UUID,
    events: list[tuple[AuditAction, uuid.UUID | None]],
) -> None:
    """Record events one minute apart, starting at START."""

    async def scenario(factory: SessionFactory) -> None:
        clock = FrozenClock(START)
        audit = AuditService(clock)
        async with system_session(factory) as db:
            for action, actor in events:
                await audit.record(
                    db,
                    action=action,
                    workspace_id=workspace_id,
                    actor_user_id=actor,
                    target=AuditTarget("workspace", str(workspace_id)),
                    metadata={"note": "seed"},
                    ip="10.0.0.1",
                )
                clock.advance(timedelta(minutes=1))

    run_db(api.database_url, scenario)


def test_audit_endpoint_lists_newest_first(api: ApiEnv) -> None:
    admin = api.create_user()
    workspace = api.create_workspace({admin.id: Role.ADMIN})
    _record(
        api,
        workspace,
        [(AuditAction.WORKSPACE_CREATED, admin.id), (AuditAction.WORKSPACE_UPDATED, admin.id)],
    )
    api.login(admin)

    response = api.client.get(f"/v1/workspaces/{workspace}/audit")

    body = response.json()
    assert response.status_code == 200
    assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
    assert [item["action"] for item in body["items"]] == ["workspace.updated", "workspace.created"]
    first = body["items"][0]
    assert first["actor_user_id"] == str(admin.id)
    assert (first["target_type"], first["target_id"]) == ("workspace", str(workspace))
    assert first["details"] == {"note": "seed"}
    assert first["ip_address"] == "10.0.0.1"
    assert first["occurred_at"] == "2026-10-10T12:01:00Z"


def test_audit_endpoint_applies_filters_and_pagination(api: ApiEnv) -> None:
    owner, other = api.create_user(), api.create_user()
    workspace = api.create_workspace({owner.id: Role.OWNER, other.id: Role.VIEWER})
    _record(
        api,
        workspace,
        [
            (AuditAction.WORKSPACE_CREATED, owner.id),
            (AuditAction.WORKSPACE_UPDATED, owner.id),
            (AuditAction.WORKSPACE_UPDATED, other.id),
            (AuditAction.WORKSPACE_UPDATED, owner.id),
        ],
    )
    api.login(owner)
    url = f"/v1/workspaces/{workspace}/audit"

    by_action = api.client.get(url, params={"action": "workspace.updated", "limit": 1}).json()
    by_actor = api.client.get(url, params={"actor_user_id": str(other.id)}).json()
    by_period = api.client.get(
        url,
        params={"occurred_from": "2026-10-10T12:01:00Z", "occurred_to": "2026-10-10T12:03:00Z"},
    ).json()
    second_page = api.client.get(url, params={"limit": 2, "offset": 2}).json()

    assert (by_action["total"], len(by_action["items"])) == (3, 1)
    assert by_actor["total"] == 1
    assert by_period["total"] == 2
    assert [item["occurred_at"] for item in second_page["items"]] == [
        "2026-10-10T12:01:00Z",
        "2026-10-10T12:00:00Z",
    ]


def test_audit_endpoint_validates_query(api: ApiEnv) -> None:
    admin = api.create_user()
    workspace = api.create_workspace({admin.id: Role.ADMIN})
    api.login(admin)
    url = f"/v1/workspaces/{workspace}/audit"

    too_big = api.client.get(url, params={"limit": 201})
    unknown_action = api.client.get(url, params={"action": "nope"})

    assert too_big.status_code == unknown_action.status_code == 422


def test_audit_endpoint_requires_admin(api: ApiEnv) -> None:
    editor = api.create_user()
    workspace = api.create_workspace({editor.id: Role.EDITOR})
    api.login(editor)

    response = api.client.get(f"/v1/workspaces/{workspace}/audit")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_audit_endpoint_isolated_by_workspace(api: ApiEnv) -> None:
    user_a, user_b = api.create_user(), api.create_user()
    workspace_a = api.create_workspace({user_a.id: Role.OWNER})
    workspace_b = api.create_workspace({user_b.id: Role.OWNER})
    _record(api, workspace_a, [(AuditAction.WORKSPACE_CREATED, user_a.id)])
    _record(api, workspace_b, [(AuditAction.WORKSPACE_UPDATED, user_b.id)])
    api.login(user_a)

    own = api.client.get(f"/v1/workspaces/{workspace_a}/audit")
    foreign = api.client.get(f"/v1/workspaces/{workspace_b}/audit")

    assert [item["action"] for item in own.json()["items"]] == ["workspace.created"]
    assert own.json()["total"] == 1
    assert foreign.status_code == 404
