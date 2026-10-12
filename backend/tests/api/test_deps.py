"""Shared dependencies: ``require_superadmin``, ``workspace_context``, ``require_role``, and
``client_ip`` behind uvicorn's proxy-headers handling.

Probe routes are added to the real app so the dependencies run exactly as in production.
No ``from __future__ import annotations`` here: the role probes are built in a loop and
FastAPI must see their ``Depends(require_role(minimum))`` evaluated, not as a string.
"""

import uuid
from collections.abc import Generator
from typing import Annotated

import pytest
from api_support import CHEAP, START, ApiEnv, db_settings
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import text
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from fakes.email_sender import FakeEmailSender
from knobridge.api.app import create_app
from knobridge.api.deps import (
    WorkspaceContext,
    WorkspaceContextDep,
    client_ip,
    require_role,
    require_superadmin,
)
from knobridge.core.clock import FrozenClock
from knobridge.security.passwords import PasswordHasher
from knobridge.tenancy.auth import AuthenticatedUser
from knobridge.tenancy.models import Role, WorkspaceStatus

probe = APIRouter(prefix="/v1/probe")


@probe.get("/superadmin")
async def superadmin_probe(
    current: Annotated[AuthenticatedUser, Depends(require_superadmin)],
) -> dict[str, str]:
    return {"user_id": str(current.user.id)}


@probe.get("/workspaces/{workspace_id}/context")  # noqa: FAST003 - read by workspace_context
async def context_probe(context: WorkspaceContextDep) -> dict[str, str]:
    # The scoped session must carry the workspace selected by the path.
    scoped = await context.db.scalar(text("SELECT current_setting('app.workspace_id', true)"))
    return {"role": context.role.value, "scoped_workspace": str(scoped)}


def _role_probe(minimum: Role) -> None:
    @probe.get(f"/workspaces/{{workspace_id}}/at-least-{minimum.value}")
    async def role_probe(
        context: Annotated[WorkspaceContext, Depends(require_role(minimum))],
    ) -> dict[str, str]:
        return {"role": context.role.value}


for _minimum in Role:
    _role_probe(_minimum)


@pytest.fixture
def probe_api(app_database_url: str) -> Generator[ApiEnv]:
    clock = FrozenClock(START)
    hasher = PasswordHasher(CHEAP)
    app = create_app(db_settings(app_database_url), clock=clock, password_hasher=hasher)
    app.include_router(probe)
    with TestClient(app) as client:
        yield ApiEnv(
            client=client,
            clock=clock,
            database_url=app_database_url,
            hasher=hasher,
            emails=FakeEmailSender(),
        )


@pytest.mark.integration
def test_require_superadmin_allows_superadmin(probe_api: ApiEnv) -> None:
    admin = probe_api.create_user(superadmin=True)
    probe_api.login(admin)

    response = probe_api.client.get("/v1/probe/superadmin")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(admin.id)}


@pytest.mark.integration
def test_require_superadmin_rejects_regular_user(probe_api: ApiEnv) -> None:
    probe_api.login(probe_api.create_user())

    response = probe_api.client.get("/v1/probe/superadmin")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.integration
def test_workspace_context_scopes_session_for_member(probe_api: ApiEnv) -> None:
    user = probe_api.create_user()
    workspace = probe_api.create_workspace({user.id: Role.EDITOR})
    probe_api.login(user)

    response = probe_api.client.get(f"/v1/probe/workspaces/{workspace}/context")

    assert response.status_code == 200
    assert response.json() == {"role": "editor", "scoped_workspace": str(workspace)}


@pytest.mark.integration
def test_workspace_context_rejects_non_member(probe_api: ApiEnv) -> None:
    user, owner = probe_api.create_user(superadmin=True), probe_api.create_user()
    foreign = probe_api.create_workspace({owner.id: Role.OWNER})
    probe_api.login(user)

    foreign_response = probe_api.client.get(f"/v1/probe/workspaces/{foreign}/context")
    missing_response = probe_api.client.get(f"/v1/probe/workspaces/{uuid.uuid4()}/context")

    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.json() == missing_response.json()
    assert foreign_response.json()["error"]["code"] == "not_found"


@pytest.mark.integration
def test_workspace_context_rejects_suspended_workspace(probe_api: ApiEnv) -> None:
    user = probe_api.create_user()
    workspace = probe_api.create_workspace({user.id: Role.OWNER}, status=WorkspaceStatus.SUSPENDED)
    probe_api.login(user)

    response = probe_api.client.get(f"/v1/probe/workspaces/{workspace}/context")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "workspace_suspended"


@pytest.mark.integration
def test_workspace_context_requires_session(probe_api: ApiEnv) -> None:
    response = probe_api.client.get(f"/v1/probe/workspaces/{uuid.uuid4()}/context")

    assert response.status_code == 401


@pytest.mark.integration
def test_require_role_hierarchy(probe_api: ApiEnv) -> None:
    order = [Role.VIEWER, Role.EDITOR, Role.ADMIN, Role.OWNER]
    outcomes: dict[tuple[Role, Role], int] = {}
    for role in order:
        user = probe_api.create_user()
        workspace = probe_api.create_workspace({user.id: role})
        probe_api.login(user)
        for minimum in order:
            url = f"/v1/probe/workspaces/{workspace}/at-least-{minimum.value}"
            outcomes[(role, minimum)] = probe_api.client.get(url).status_code

    expected = {
        (role, minimum): 200 if order.index(role) >= order.index(minimum) else 403
        for role in order
        for minimum in order
    }
    assert outcomes == expected


@pytest.mark.integration
def test_require_role_error_names_required_role(probe_api: ApiEnv) -> None:
    user = probe_api.create_user()
    workspace = probe_api.create_workspace({user.id: Role.VIEWER})
    probe_api.login(user)

    response = probe_api.client.get(f"/v1/probe/workspaces/{workspace}/at-least-admin")

    assert response.json()["error"] == {
        "code": "forbidden",
        "message": "Your role does not allow this action.",
        "details": {"required_role": "admin"},
    }


def test_client_ip_is_none_without_peer() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    assert client_ip(request) is None


def test_client_ip_reads_peer_address() -> None:
    request = Request(
        {"type": "http", "method": "GET", "path": "/", "headers": [], "client": ("10.1.2.3", 1)}
    )

    assert client_ip(request) == "10.1.2.3"


async def _ip_probe(request: Request) -> dict[str, str | None]:
    return {"ip": client_ip(request)}


def _behind_proxy_headers(trusted: str, peer: str) -> TestClient:
    """``client_ip`` behind uvicorn's proxy-headers handling, as ``serve`` turns it on."""
    peer_app = FastAPI()
    peer_app.add_api_route("/ip", _ip_probe)
    peer_app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted)
    return TestClient(peer_app, client=(peer, 1))


def test_client_ip_comes_from_forwarded_header_of_trusted_proxy() -> None:
    client = _behind_proxy_headers("172.30.57.10", "172.30.57.10")

    response = client.get("/ip", headers={"X-Forwarded-For": "203.0.113.7"})

    assert response.json() == {"ip": "203.0.113.7"}


def test_client_ip_ignores_forwarded_header_of_untrusted_peer() -> None:
    client = _behind_proxy_headers("172.30.57.10", "198.51.100.9")

    response = client.get("/ip", headers={"X-Forwarded-For": "203.0.113.7"})

    assert response.json() == {"ip": "198.51.100.9"}


def test_client_ip_ignores_spoofed_entries_before_the_trusted_proxy() -> None:
    # nginx appends the address it saw to whatever X-Forwarded-For the client sent.
    client = _behind_proxy_headers("172.30.57.0/24", "172.30.57.10")

    response = client.get("/ip", headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.7"})

    assert response.json() == {"ip": "203.0.113.7"}
