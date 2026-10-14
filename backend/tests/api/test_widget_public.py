"""Public routes of the widget (``/v1/widget/{public_key}/…``): the configuration, the order of
the checks (key, ``Origin``, availability, limit), CORS only for an accepted origin, the
preflight, the instance's own origin, the request limit with a frozen clock and the global
``CORSMiddleware`` kept off these paths."""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from api_support import CHEAP, START, ApiEnv, db_settings
from chat_support import build_world, error
from fastapi.testclient import TestClient
from widget_api_support import (
    SITE,
    config_path,
    create_widget,
    get_config,
    set_product_active,
    set_ticket_webhook,
    widgets_path,
)

from fakes.email_sender import FakeEmailSender
from knobridge.api.app import create_app
from knobridge.core.clock import FrozenClock
from knobridge.security.passwords import PasswordHasher
from knobridge.tenancy.models import Role, WorkspaceStatus

pytestmark = pytest.mark.integration

INSTANCE = "http://localhost:5173"  # KNOBRIDGE_PUBLIC_BASE_URL of the test settings
PANEL = "http://test"  # KNOBRIDGE_CORS_ORIGINS of the test settings
CORS = "access-control-allow-origin"


def _widget(api: ApiEnv, **fields: object) -> tuple[dict[str, object], str]:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, **fields)
    return widget, world.assistant_id


def test_widget_config_answers_with_cors(api: ApiEnv) -> None:
    widget, _ = _widget(api, title="Ajuda do ERP", theme="dark")

    response = get_config(api, str(widget["public_key"]))

    assert response.status_code == 200
    assert response.json() == {
        "public_key": widget["public_key"],
        "product_name": "Suporte",
        "language": "pt-BR",
        "title": "Ajuda do ERP",
        "greeting": "Olá! Como posso ajudar?",
        "placeholder": "Escreva sua pergunta",
        "mode": "bubble",
        "position": "bottom-right",
        "theme": "dark",
        "primary_color": "#2563eb",
        "feedback_enabled": True,
        "ticket_enabled": False,
        "identity_enabled": False,
        "level": "end_user",
        "question_max_chars": 8000,
    }
    assert response.headers["cache-control"] == "private, max-age=60"
    assert response.headers[CORS] == SITE
    assert response.headers["vary"] == "Origin"
    assert response.headers["access-control-expose-headers"] == "Retry-After"
    assert "access-control-allow-credentials" not in response.headers


def test_widget_config_resolves_title_tickets_and_identity(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    set_ticket_webhook(api, world.assistant_id)
    secret = f"{widgets_path(world.workspace_id, str(widget['id']))}/signing-secret"
    assert api.client.post(secret, headers=api.csrf_headers()).status_code == 201

    body = get_config(api, str(widget["public_key"])).json()

    assert body["title"] == "Suporte"
    assert (body["ticket_enabled"], body["identity_enabled"]) == (True, True)


@pytest.mark.parametrize("key", ["kbp_" + "0" * 24, "kbp_short", "nada"])
def test_widget_unknown_key_is_404_without_cors(api: ApiEnv, key: str) -> None:
    response = get_config(api, key)

    assert error(response) == (404, "not_found")
    assert CORS not in response.headers


@pytest.mark.parametrize(
    "origin", [None, "https://outro.example", "null", "http://app.cliente.example"]
)
def test_widget_origin_not_allowed_is_403_without_cors(api: ApiEnv, origin: str | None) -> None:
    widget, _ = _widget(api)

    response = get_config(api, str(widget["public_key"]), origin=origin)

    assert error(response) == (403, "widget_origin_not_allowed")
    assert CORS not in response.headers


def test_widget_accepts_wildcard_and_instance_origins(api: ApiEnv) -> None:
    widget, _ = _widget(api, allowed_origins=["https://*.cliente.example"])
    key = str(widget["public_key"])

    subdomain = get_config(api, key, origin="https://loja.cliente.example")
    instance = get_config(api, key, origin=INSTANCE)
    bare = get_config(api, key, origin="https://cliente.example")

    assert subdomain.status_code == 200
    assert subdomain.headers[CORS] == "https://loja.cliente.example"
    assert instance.status_code == 200
    assert instance.headers[CORS] == INSTANCE
    assert error(bare) == (403, "widget_origin_not_allowed")


def test_inactive_widget_is_unavailable_with_cors(api: ApiEnv) -> None:
    widget, _ = _widget(api, active=False)

    response = get_config(api, str(widget["public_key"]))

    assert error(response) == (404, "widget_unavailable")
    assert response.headers[CORS] == SITE


def test_inactive_product_makes_the_widget_unavailable(api: ApiEnv) -> None:
    widget, product_id = _widget(api)
    set_product_active(api, product_id, active=False)

    response = get_config(api, str(widget["public_key"]))

    assert error(response) == (404, "widget_unavailable")


def test_suspended_workspace_makes_the_widget_unavailable(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    api.set_workspace_status(world.workspace_id, WorkspaceStatus.SUSPENDED)

    response = get_config(api, str(widget["public_key"]))

    assert error(response) == (404, "widget_unavailable")


def test_widget_preflight_with_allowed_origin(api: ApiEnv) -> None:
    widget, _ = _widget(api)

    response = api.client.options(
        config_path(str(widget["public_key"])),
        headers={"Origin": SITE, "Access-Control-Request-Method": "GET"},
    )

    assert (response.status_code, response.content) == (204, b"")
    assert response.headers[CORS] == SITE
    assert response.headers["access-control-allow-methods"] == "GET, POST, OPTIONS"
    assert response.headers["access-control-allow-headers"] == "Authorization, Content-Type"
    assert response.headers["access-control-max-age"] == "600"
    assert response.headers["vary"] == "Origin"
    assert "access-control-allow-credentials" not in response.headers


def test_widget_preflight_of_any_public_path(api: ApiEnv) -> None:
    widget, _ = _widget(api)

    response = api.client.options(
        f"/v1/widget/{widget['public_key']}/conversations/x/messages",
        headers={"Origin": SITE, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 204


def test_widget_preflight_refused_origin_is_not_answered_by_the_panel_cors(api: ApiEnv) -> None:
    widget, _ = _widget(api)

    # The panel's origin is allowed by the global CORS, never on the widget's paths.
    response = api.client.options(
        config_path(str(widget["public_key"])),
        headers={"Origin": PANEL, "Access-Control-Request-Method": "GET"},
    )

    assert error(response) == (403, "widget_origin_not_allowed")
    assert CORS not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_panel_routes_keep_the_global_cors(api: ApiEnv) -> None:
    response = api.client.options(
        "/v1/health/live", headers={"Origin": PANEL, "Access-Control-Request-Method": "GET"}
    )

    assert response.status_code == 200
    assert response.headers[CORS] == PANEL
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.fixture
def limited_api(api: ApiEnv) -> Generator[tuple[ApiEnv, TestClient, FrozenClock]]:
    """A second app on the same database with a limit of two requests per minute."""
    clock = FrozenClock(START)
    settings = db_settings(api.database_url).model_copy(update={"widget_requests_per_minute": 2})
    app = create_app(
        settings, clock=clock, password_hasher=PasswordHasher(CHEAP), email_sender=FakeEmailSender()
    )
    with TestClient(app) as client:
        yield api, client, clock


def test_widget_request_limit_with_frozen_clock(
    limited_api: tuple[ApiEnv, TestClient, FrozenClock],
) -> None:
    api, client, clock = limited_api
    widget, _ = _widget(api)
    path = config_path(str(widget["public_key"]))
    headers = {"Origin": SITE}

    allowed = [client.get(path, headers=headers).status_code for _ in range(2)]
    clock.advance(timedelta(seconds=15.5))
    refused = client.get(path, headers=headers)
    preflight = client.options(path, headers={**headers, "Access-Control-Request-Method": "GET"})
    clock.advance(timedelta(seconds=45))
    again = client.get(path, headers=headers)

    assert allowed == [200, 200]
    assert error(refused) == (429, "rate_limited")
    assert refused.json()["error"]["details"] == {"limit": "widget_request", "retry_after": 45}
    assert refused.headers["retry-after"] == "45"
    assert refused.headers[CORS] == SITE
    assert error(preflight) == (429, "rate_limited")
    assert again.status_code == 200


def test_widget_request_limit_not_counted_for_refused_origins(
    limited_api: tuple[ApiEnv, TestClient, FrozenClock],
) -> None:
    api, client, _ = limited_api
    widget, _ = _widget(api)
    path = config_path(str(widget["public_key"]))

    refused = [client.get(path, headers={"Origin": "https://x.example"}) for _ in range(3)]
    accepted = client.get(path, headers={"Origin": SITE})

    assert {error(response) for response in refused} == {(403, "widget_origin_not_allowed")}
    assert accepted.status_code == 200
