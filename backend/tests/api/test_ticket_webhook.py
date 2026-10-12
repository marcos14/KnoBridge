"""Ticket webhook of an assistant: the URL saved under the SSRF rules (fake resolver), the
``kbw_`` secret shown once and stored encrypted, the signed test event (mock transport, verified
by a test receiver), roles, CSRF, audit, logs and isolation."""

from __future__ import annotations

import io
import json
import uuid
from collections.abc import Generator
from datetime import timedelta
from typing import cast

import httpx2
import pytest
from api_support import START, ApiEnv, SessionFactory, db_settings, run_db
from chat_support import World, build_world
from fastapi import FastAPI
from sqlalchemy import select

from knobridge.api.ticket_webhook import get_outbound_resolver, get_outbound_transport
from knobridge.assistants.models import Assistant
from knobridge.core.crypto import SecretBox
from knobridge.core.db import system_session
from knobridge.core.logging import configure_logging
from knobridge.core.outbound import SystemResolver
from knobridge.tenancy.models import Role
from knobridge.tickets.signature import verify_signature
from knobridge.tickets.webhook_secret import TICKET_WEBHOOK_KEY_INFO, open_webhook_secret

pytestmark = pytest.mark.integration

HOOK_HOST = "hooks.example.com"
HOOK_URL = f"https://{HOOK_HOST}/knobridge"
PUBLIC_IP = "93.184.216.34"


class FakeResolver:
    def __init__(self) -> None:
        self.table: dict[str, list[str]] = {HOOK_HOST: [PUBLIC_IP]}

    async def resolve(self, host: str, port: int) -> list[str]:
        if host not in self.table:
            raise OSError("does not resolve")
        return self.table[host]


class Destination:
    """The fake webhook receiver behind the mock transport."""

    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []
        self.answer: httpx2.Response | Exception = httpx2.Response(204)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class Hooks:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.resolver = FakeResolver()
        self.destination = Destination()
        app.dependency_overrides[get_outbound_resolver] = lambda: self.resolver
        app.dependency_overrides[get_outbound_transport] = lambda: httpx2.MockTransport(
            self.destination
        )

    def clear(self) -> None:
        self.app.dependency_overrides.pop(get_outbound_resolver, None)
        self.app.dependency_overrides.pop(get_outbound_transport, None)


@pytest.fixture
def hooks(api: ApiEnv) -> Generator[Hooks]:
    overrides = Hooks(cast(FastAPI, api.client.app))
    yield overrides
    overrides.clear()


def _assistant_path(world: World, suffix: str = "") -> str:
    return f"/v1/workspaces/{world.workspace_id}/assistants/{world.assistant_id}{suffix}"


def _patch(api: ApiEnv, world: World, body: dict[str, object]) -> httpx2.Response:
    return api.client.patch(_assistant_path(world), json=body, headers=api.csrf_headers())


def _rotate(api: ApiEnv, world: World) -> httpx2.Response:
    return api.client.post(
        _assistant_path(world, "/ticket-webhook/secret"), headers=api.csrf_headers()
    )


def _test(api: ApiEnv, world: World) -> httpx2.Response:
    return api.client.post(
        _assistant_path(world, "/ticket-webhook/test"), headers=api.csrf_headers()
    )


def _error(response: httpx2.Response) -> tuple[int, str, object]:
    error = response.json()["error"]
    return response.status_code, error["code"], error["details"]


def _configured(api: ApiEnv, hooks: Hooks, *roles: Role) -> tuple[World, str]:
    world = build_world(api, *(roles or (Role.ADMIN,)), ticket_webhook_url=HOOK_URL)
    secret: str = _rotate(api, world).json()["secret"]
    return world, secret


def _stored(api: ApiEnv, assistant_id: str) -> Assistant:
    async def scenario(factory: SessionFactory) -> Assistant:
        async with system_session(factory) as db:
            return (
                await db.scalars(select(Assistant).where(Assistant.id == uuid.UUID(assistant_id)))
            ).one()

    return run_db(api.database_url, scenario)


def _box(api: ApiEnv) -> SecretBox:
    key = db_settings(api.database_url).secret_key.get_secret_value()
    return SecretBox.derive(key, info=TICKET_WEBHOOK_KEY_INFO)


def _events(api: ApiEnv, world: World, action: str) -> list[dict[str, object]]:
    return [d for a, d in api.workspace_audit(world.workspace_id) if a == action]


def test_create_assistant_with_webhook_url(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.EDITOR, ticket_webhook_url=f" {HOOK_URL} ")

    body = api.client.get(_assistant_path(world)).json()

    assert body["ticket_webhook_url"] == HOOK_URL
    assert body["ticket_webhook_configured"] is False
    assert body["ticket_webhook_secret_created_at"] is None


def test_assistant_without_webhook_by_default(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN)

    body = api.client.get(_assistant_path(world)).json()

    assert (body["ticket_webhook_url"], body["ticket_webhook_configured"]) == (None, False)


@pytest.mark.parametrize(
    ("url", "code", "reason"),
    [
        (f"http://{HOOK_HOST}/x", "webhook_url_invalid", "scheme_not_https"),
        (f"https://user:pw@{HOOK_HOST}/x", "webhook_url_invalid", "credentials_in_url"),
        ("https://unknown.example.com/x", "webhook_url_invalid", "host_unresolvable"),
        ("https://10.0.0.8/x", "webhook_destination_blocked", "private"),
        ("https://127.0.0.1/x", "webhook_destination_blocked", "loopback"),
        ("https://169.254.169.254/x", "webhook_destination_blocked", "link_local"),
        ("https://internal.example.com/x", "webhook_destination_blocked", "private"),
    ],
)
def test_update_refuses_unsafe_webhook_url(
    api: ApiEnv, hooks: Hooks, url: str, code: str, reason: str
) -> None:
    hooks.resolver.table["internal.example.com"] = [PUBLIC_IP, "172.20.0.4"]
    world = build_world(api, Role.ADMIN)

    response = _patch(api, world, {"ticket_webhook_url": url})

    assert _error(response) == (422, code, {"reason": reason})
    assert _stored(api, world.assistant_id).ticket_webhook_url is None


def test_create_refuses_private_webhook_url(api: ApiEnv, hooks: Hooks) -> None:
    hooks.resolver.table[HOOK_HOST] = ["192.168.10.2"]
    world = build_world(api, Role.ADMIN)

    response = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/assistants",
        json={
            "name": "Outro",
            "provider_id": world.provider_id,
            "model": "fake-model",
            "ticket_webhook_url": HOOK_URL,
        },
        headers=api.csrf_headers(),
    )

    assert _error(response) == (422, "webhook_destination_blocked", {"reason": "private"})


def test_webhook_url_longer_than_limit_refused(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN)

    response = _patch(api, world, {"ticket_webhook_url": HOOK_URL + "/" + "a" * 2000})

    assert response.status_code == 422


def test_update_webhook_url_audited_by_field_name(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN)

    response = _patch(api, world, {"ticket_webhook_url": HOOK_URL + "?token=abc"})

    assert response.status_code == 200, response.text
    updated = _events(api, world, "assistant.updated")
    assert {"name": "Suporte", "fields": ["ticket_webhook_url"]} in updated
    assert all("token=abc" not in json.dumps(event) for event in updated)


def test_update_omitted_url_keeps_and_null_turns_off(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)

    kept = _patch(api, world, {"name": "Suporte 2"}).json()
    cleared = _patch(api, world, {"ticket_webhook_url": None}).json()

    assert (kept["ticket_webhook_url"], kept["ticket_webhook_configured"]) == (HOOK_URL, True)
    assert (cleared["ticket_webhook_url"], cleared["ticket_webhook_configured"]) == (None, False)
    assert cleared["ticket_webhook_secret_created_at"] is not None


def test_update_same_url_is_not_audited(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN, ticket_webhook_url=HOOK_URL)

    response = _patch(api, world, {"ticket_webhook_url": HOOK_URL})

    assert response.status_code == 200
    assert _events(api, world, "assistant.updated") == []


def test_generate_secret_shows_it_once_and_stores_ciphertext(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN, ticket_webhook_url=HOOK_URL)

    response = _rotate(api, world)

    assert response.status_code == 201, response.text
    secret = response.json()["secret"]
    assert secret.startswith("kbw_")
    assert len(secret) == 47
    assert response.json()["created_at"] == START.isoformat().replace("+00:00", "Z")
    stored = _stored(api, world.assistant_id)
    assert stored.ticket_webhook_secret_ciphertext is not None
    assert secret not in stored.ticket_webhook_secret_ciphertext
    assert open_webhook_secret(_box(api), stored) == secret
    shown = api.client.get(_assistant_path(world))
    assert secret not in shown.text
    assert shown.json()["ticket_webhook_configured"] is True
    listed = api.client.get(f"/v1/workspaces/{world.workspace_id}/assistants")
    assert secret not in listed.text


def test_generate_secret_again_replaces_it(api: ApiEnv, hooks: Hooks) -> None:
    world, first = _configured(api, hooks)
    api.clock.advance(timedelta(minutes=5))

    second = _rotate(api, world).json()

    assert second["secret"] != first
    stored = _stored(api, world.assistant_id)
    assert open_webhook_secret(_box(api), stored) == second["secret"]
    assert stored.ticket_webhook_secret_created_at == START + timedelta(minutes=5)


def test_generate_secret_audited_without_secret(api: ApiEnv, hooks: Hooks) -> None:
    world, secret = _configured(api, hooks)

    events = _events(api, world, "assistant.ticket_webhook_secret_rotated")

    assert events == [{"name": "Suporte"}]
    assert all(secret not in json.dumps(d) for _, d in api.workspace_audit(world.workspace_id))


@pytest.mark.parametrize(("role", "status"), [(Role.OWNER, 201), (Role.EDITOR, 403)])
def test_generate_secret_needs_owner_or_admin(
    api: ApiEnv, hooks: Hooks, role: Role, status: int
) -> None:
    world = build_world(api, Role.ADMIN, role)
    api.login(world.users[1])

    response = _rotate(api, world)

    assert response.status_code == status, response.text


def test_generate_secret_needs_csrf(api: ApiEnv, hooks: Hooks) -> None:
    world = build_world(api, Role.ADMIN)

    response = api.client.post(_assistant_path(world, "/ticket-webhook/secret"))

    assert _error(response)[:2] == (403, "csrf_failed")


def test_send_test_event_signed_and_pinned(api: ApiEnv, hooks: Hooks) -> None:
    world, secret = _configured(api, hooks)

    response = _test(api, world)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["ok"], body["status"], body["error"]) == (True, 204, None)
    request = hooks.destination.requests[0]
    assert str(request.url) == f"https://{PUBLIC_IP}/knobridge"
    assert request.headers["Host"] == HOOK_HOST
    assert request.extensions["sni_hostname"] == HOOK_HOST
    assert request.headers["KnoBridge-Event"] == "ticket.test"
    assert request.headers["KnoBridge-Delivery"] == body["delivery_id"]
    assert request.headers["Content-Type"] == "application/json"
    now = int(START.timestamp())
    assert verify_signature(
        request.headers["KnoBridge-Signature"], secret=secret, body=request.content, now=now
    )
    assert request.headers["KnoBridge-Signature"].startswith(f"t={now},v1=")
    event = json.loads(request.content)
    assert event == {
        "event": "ticket.test",
        "version": 1,
        "id": body["delivery_id"],
        "created_at": "2026-10-10T12:00:00Z",
        "workspace": {"id": str(world.workspace_id), "name": event["workspace"]["name"]},
        "assistant": {"id": world.assistant_id, "name": "Suporte"},
    }
    assert isinstance(event["workspace"]["name"], str)


def test_send_test_reports_rejection(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    hooks.destination.answer = httpx2.Response(500)

    body = _test(api, world).json()

    assert (body["ok"], body["status"]) == (False, 500)
    assert (body["error"]["code"], body["error"]["details"]) == (
        "webhook_rejected",
        {"status": 500},
    )


def test_send_test_reports_redirect_as_rejection(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    hooks.destination.answer = httpx2.Response(301, headers={"Location": "https://10.0.0.1/"})

    body = _test(api, world).json()

    assert body["error"]["code"] == "webhook_rejected"
    assert len(hooks.destination.requests) == 1


def test_send_test_reports_timeout(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    hooks.destination.answer = httpx2.ReadTimeout("slow")

    body = _test(api, world).json()

    assert (body["ok"], body["status"]) == (False, None)
    assert body["error"]["code"] == "webhook_unreachable"
    assert body["error"]["details"] == {"reason": "timeout"}


def test_send_test_checks_destination_again(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    hooks.resolver.table[HOOK_HOST] = ["10.1.1.1"]

    body = _test(api, world).json()

    assert body["error"]["code"] == "webhook_destination_blocked"
    assert body["error"]["details"] == {"reason": "private"}
    assert hooks.destination.requests == []


def test_send_test_reports_unresolvable_host(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    hooks.resolver.table.clear()

    body = _test(api, world).json()

    assert body["error"]["code"] == "webhook_url_invalid"
    assert body["error"]["details"] == {"reason": "host_unresolvable"}


def test_send_test_audited_with_outcome(api: ApiEnv, hooks: Hooks) -> None:
    world, secret = _configured(api, hooks)
    hooks.destination.answer = httpx2.Response(503)

    _test(api, world)

    events = _events(api, world, "assistant.ticket_webhook_tested")
    assert events == [
        {"name": "Suporte", "ok": False, "status": 503, "error_code": "webhook_rejected"}
    ]
    assert secret not in json.dumps(events)


@pytest.mark.parametrize("missing", ["url", "secret"])
def test_send_test_needs_url_and_secret(api: ApiEnv, hooks: Hooks, missing: str) -> None:
    if missing == "url":
        world, _ = _configured(api, hooks)
        _patch(api, world, {"ticket_webhook_url": None})
    else:
        world = build_world(api, Role.ADMIN, ticket_webhook_url=HOOK_URL)

    response = _test(api, world)

    assert _error(response)[:2] == (409, "ticket_webhook_not_configured")
    assert hooks.destination.requests == []


@pytest.mark.parametrize(("role", "status"), [(Role.EDITOR, 200), (Role.VIEWER, 403)])
def test_send_test_needs_editor(api: ApiEnv, hooks: Hooks, role: Role, status: int) -> None:
    world, _ = _configured(api, hooks, Role.ADMIN, role)
    api.login(world.users[1])

    response = _test(api, world)

    assert response.status_code == status, response.text


def test_send_test_needs_csrf(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)

    response = api.client.post(_assistant_path(world, "/ticket-webhook/test"))

    assert _error(response)[:2] == (403, "csrf_failed")


def test_webhook_routes_isolated_between_workspaces(api: ApiEnv, hooks: Hooks) -> None:
    world, _ = _configured(api, hooks)
    other = build_world(api, Role.OWNER)
    foreign = World(other.workspace_id, other.users, other.provider_id, world.assistant_id)

    rotated = _rotate(api, foreign)
    tested = _test(api, foreign)

    assert _error(rotated)[:2] == (404, "not_found")
    assert _error(tested)[:2] == (404, "not_found")
    assert hooks.destination.requests == []


def test_webhook_secret_never_logged(api: ApiEnv, hooks: Hooks) -> None:
    stream = io.StringIO()
    configure_logging(db_settings(api.database_url), stream=stream)

    world, secret = _configured(api, hooks)
    _test(api, world)

    logged = stream.getvalue()
    assert '"ticket_webhook_tested"' in logged
    assert secret not in logged


def test_outbound_defaults_are_system_resolver_and_default_transport() -> None:
    assert isinstance(get_outbound_resolver(), SystemResolver)
    assert get_outbound_transport() is None
