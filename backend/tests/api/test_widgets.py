"""Widget routes of the panel: create with the spec's defaults, origins normalized or refused
with a reason, roles, CSRF, edit, delete with the widget's conversations, the signing secret
shown once and never again (nor in the audit or the logs), filters and workspace isolation."""

from __future__ import annotations

import re
import uuid

import pytest
from api_support import ApiEnv
from chat_support import build_world, error
from structlog.testing import capture_logs
from widget_api_support import (
    SITE,
    add_widget_conversation,
    conversation_exists,
    create_widget,
    post_widget,
    set_ticket_webhook,
    stored_widget,
    widgets_path,
)

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

PUBLIC_KEY = re.compile(r"^kbp_[a-z0-9]{24}$")
SECRET = re.compile(r"^kbs_[A-Za-z0-9_-]{43}$")


def _events(api: ApiEnv, workspace_id: uuid.UUID) -> list[tuple[str, dict[str, object]]]:
    return [e for e in api.workspace_audit(workspace_id) if e[0].startswith("widget.")]


def test_create_widget_with_defaults(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)

    response = post_widget(
        api,
        world.workspace_id,
        world.assistant_id,
        name="Site público",
        allowed_origins=["HTTPS://App.Cliente.Example:443", "https://*.cliente.example"],
    )

    assert response.status_code == 201
    body = response.json()
    assert PUBLIC_KEY.fullmatch(body["public_key"])
    assert body == {
        **body,
        "product_id": world.assistant_id,
        "product_name": "Suporte",
        "name": "Site público",
        "allowed_origins": [SITE, "https://*.cliente.example"],
        "active": True,
        "mode": "bubble",
        "position": "bottom-right",
        "theme": "auto",
        "primary_color": "#2563eb",
        "title": None,
        "greeting": "Olá! Como posso ajudar?",
        "placeholder": "Escreva sua pergunta",
        "feedback_enabled": True,
        "ticket_enabled": True,
        "ticket_available": False,
        "messages_per_ip_per_hour": 30,
        "messages_per_day": 1000,
        "signing_secret_configured": False,
        "signing_secret_created_at": None,
        "created_by": str(world.users[0].id),
        "created_by_name": "Test User",
    }
    assert _events(api, world.workspace_id) == [
        (
            "widget.created",
            {
                "name": "Site público",
                "product_id": world.assistant_id,
                "public_key": body["public_key"],
                "allowed_origins": [SITE, "https://*.cliente.example"],
            },
        )
    ]


def test_create_widget_with_appearance(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    set_ticket_webhook(api, world.assistant_id)

    body = create_widget(
        api,
        world.workspace_id,
        world.assistant_id,
        mode="inline",
        position="bottom-left",
        theme="dark",
        primary_color="#AABBCC",
        title="  Ajuda do ERP  ",
        greeting="",
        placeholder="Pergunte",
        feedback_enabled=False,
        messages_per_ip_per_hour=1000,
        messages_per_day=100_000,
    )

    assert (body["mode"], body["position"], body["theme"]) == ("inline", "bottom-left", "dark")
    assert (body["primary_color"], body["title"], body["greeting"]) == (
        "#aabbcc",
        "Ajuda do ERP",
        "",
    )
    assert body["feedback_enabled"] is False
    assert body["ticket_available"] is True
    assert (body["messages_per_ip_per_hour"], body["messages_per_day"]) == (1000, 100_000)


def test_create_widget_blank_title_is_the_product_name(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)

    body = create_widget(api, world.workspace_id, world.assistant_id, title="   ")

    assert body["title"] is None


@pytest.mark.parametrize(
    ("origins", "expected"),
    [
        (["ftp://a.example"], [{"origin": "ftp://a.example", "reason": "scheme_not_allowed"}]),
        (
            ["https://a.example/app"],
            [{"origin": "https://a.example/app", "reason": "path_not_allowed"}],
        ),
        (["*"], [{"origin": "*", "reason": "wildcard_not_allowed"}]),
        (["a.example"], [{"origin": "a.example", "reason": "malformed"}]),
        (
            [SITE, SITE.upper()],
            [{"origin": SITE.upper(), "reason": "duplicate"}],
        ),
    ],
)
def test_create_widget_refuses_invalid_origins(
    api: ApiEnv, origins: list[str], expected: list[dict[str, str]]
) -> None:
    world = build_world(api, Role.OWNER)

    response = post_widget(api, world.workspace_id, world.assistant_id, allowed_origins=origins)

    assert error(response) == (422, "widget_origin_invalid")
    assert response.json()["error"]["details"] == {"origins": expected}


@pytest.mark.parametrize(
    "fields",
    [
        {"allowed_origins": []},
        {"allowed_origins": [f"https://s{n}.example" for n in range(51)]},
        {"name": "   "},
        {"primary_color": "blue"},
        {"title": "x" * 81},
        {"greeting": "x" * 501},
        {"placeholder": "x" * 121},
        {"messages_per_ip_per_hour": 0},
        {"messages_per_day": 100_001},
        {"mode": "popup"},
    ],
)
def test_create_widget_validates_body(api: ApiEnv, fields: dict[str, object]) -> None:
    world = build_world(api, Role.OWNER)

    response = post_widget(api, world.workspace_id, world.assistant_id, **fields)

    assert error(response) == (422, "validation_error")


def test_create_widget_refuses_product_of_other_workspace(api: ApiEnv) -> None:
    other = build_world(api, Role.OWNER)
    world = build_world(api, Role.OWNER)

    response = post_widget(api, world.workspace_id, other.assistant_id)
    missing = post_widget(api, world.workspace_id, str(uuid.uuid4()))

    assert error(response) == (422, "widget_product_invalid")
    assert error(missing) == (422, "widget_product_invalid")


def test_create_widget_refuses_repeated_name(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    create_widget(api, world.workspace_id, world.assistant_id, name="Site")

    response = post_widget(api, world.workspace_id, world.assistant_id, name="Site")

    assert error(response) == (409, "widget_name_taken")


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
@pytest.mark.parametrize(
    "action", ["list", "get", "create", "update", "delete", "rotate", "remove"]
)
def test_widgets_require_admin(api: ApiEnv, role: Role, action: str) -> None:
    world = build_world(api, Role.OWNER, role)
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    api.login(world.users[1])
    headers = api.csrf_headers()
    path = widgets_path(world.workspace_id, widget["id"])
    client = api.client

    if action == "list":
        response = client.get(widgets_path(world.workspace_id))
    elif action == "get":
        response = client.get(path)
    elif action == "create":
        response = post_widget(api, world.workspace_id, world.assistant_id)
    elif action == "update":
        response = client.patch(path, json={"name": "X"}, headers=headers)
    elif action == "delete":
        response = client.delete(path, headers=headers)
    elif action == "rotate":
        response = client.post(f"{path}/signing-secret", headers=headers)
    else:
        response = client.delete(f"{path}/signing-secret", headers=headers)

    assert error(response) == (403, "forbidden")


def test_widget_writes_require_csrf(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    path = widgets_path(world.workspace_id, widget["id"])

    responses = [
        api.client.post(
            widgets_path(world.workspace_id),
            json={"product_id": world.assistant_id, "name": "X", "allowed_origins": [SITE]},
        ),
        api.client.patch(path, json={"name": "Y"}),
        api.client.delete(path),
        api.client.post(f"{path}/signing-secret"),
        api.client.delete(f"{path}/signing-secret"),
    ]

    assert {error(response) for response in responses} == {(403, "csrf_failed")}


def test_update_widget_changes_given_fields(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, title="Ajuda")
    path = widgets_path(world.workspace_id, widget["id"])

    response = api.client.patch(
        path,
        json={
            "name": "Sistema logado",
            "allowed_origins": ["https://*.portal.example", "http://localhost:3000"],
            "active": False,
            "primary_color": "#FF0000",
            "title": None,
            "messages_per_day": 50,
        },
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sistema logado"
    assert body["allowed_origins"] == ["https://*.portal.example", "http://localhost:3000"]
    assert (body["active"], body["primary_color"], body["title"]) == (False, "#ff0000", None)
    assert body["messages_per_day"] == 50
    assert (body["public_key"], body["mode"]) == (widget["public_key"], "bubble")
    [updated] = [d for a, d in _events(api, world.workspace_id) if a == "widget.updated"]
    assert updated == {
        "name": "Sistema logado",
        "fields": [
            "name",
            "allowed_origins",
            "active",
            "primary_color",
            "title",
            "messages_per_day",
        ],
    }


def test_update_widget_without_changes_is_not_audited(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, name="Site")

    response = api.client.patch(
        widgets_path(world.workspace_id, widget["id"]),
        json={"name": "Site", "allowed_origins": [SITE.upper()]},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200
    assert [a for a, _ in _events(api, world.workspace_id)] == ["widget.created"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"product_id": str(uuid.uuid4())},
        {"name": None},
        {"active": None},
        {"allowed_origins": []},
        {"unknown": 1},
    ],
)
def test_update_widget_validates_body(api: ApiEnv, body: dict[str, object]) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id)

    response = api.client.patch(
        widgets_path(world.workspace_id, widget["id"]), json=body, headers=api.csrf_headers()
    )

    assert error(response) == (422, "validation_error")


def test_update_widget_refuses_invalid_origin_and_taken_name(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    create_widget(api, world.workspace_id, world.assistant_id, name="Outro")
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    path = widgets_path(world.workspace_id, widget["id"])

    origin = api.client.patch(
        path, json={"allowed_origins": ["https://a.example/"]}, headers=api.csrf_headers()
    )
    name = api.client.patch(path, json={"name": "Outro"}, headers=api.csrf_headers())

    assert error(origin) == (422, "widget_origin_invalid")
    assert error(name) == (409, "widget_name_taken")


def test_delete_widget_deletes_its_conversations(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, name="Site")
    conversation_id = add_widget_conversation(api, widget)
    path = widgets_path(world.workspace_id, widget["id"])

    response = api.client.delete(path, headers=api.csrf_headers())

    assert (response.status_code, response.content) == (204, b"")
    assert error(api.client.get(path)) == (404, "not_found")
    assert stored_widget(api, widget["id"]) is None
    assert conversation_exists(api, conversation_id) is False
    [deleted] = [d for a, d in _events(api, world.workspace_id) if a == "widget.deleted"]
    assert deleted == {"name": "Site", "conversation_count": 1}


def test_signing_secret_shown_once_and_never_again(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, name="Site")
    path = widgets_path(world.workspace_id, widget["id"])

    with capture_logs() as logs:
        response = api.client.post(f"{path}/signing-secret", headers=api.csrf_headers())
        secret = response.json()["secret"]
        read = api.client.get(path)
        listing = api.client.get(widgets_path(world.workspace_id))
        patched = api.client.patch(path, json={"active": True}, headers=api.csrf_headers())

    assert response.status_code == 201
    assert SECRET.fullmatch(secret)
    assert response.json()["created_at"] == read.json()["signing_secret_created_at"]
    assert read.json()["signing_secret_configured"] is True
    for later in (read, listing, patched):
        assert secret not in later.text
        assert secret[4:] not in later.text
    assert secret not in str(logs)
    stored = stored_widget(api, widget["id"])
    assert stored is not None
    assert stored.signing_secret_ciphertext is not None
    assert secret not in stored.signing_secret_ciphertext
    audit = api.workspace_audit(world.workspace_id)
    assert all(secret not in str(details) for _, details in audit)
    assert ("widget.signing_secret_rotated", {"name": "Site"}) in _events(api, world.workspace_id)


def test_rotating_the_signing_secret_replaces_it(api: ApiEnv) -> None:
    world = build_world(api, Role.ADMIN)
    widget = create_widget(api, world.workspace_id, world.assistant_id)
    path = f"{widgets_path(world.workspace_id, widget['id'])}/signing-secret"

    first = api.client.post(path, headers=api.csrf_headers()).json()["secret"]
    second = api.client.post(path, headers=api.csrf_headers()).json()["secret"]

    assert first != second


def test_remove_signing_secret(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    widget = create_widget(api, world.workspace_id, world.assistant_id, name="Site")
    path = widgets_path(world.workspace_id, widget["id"])
    api.client.post(f"{path}/signing-secret", headers=api.csrf_headers())

    removed = api.client.delete(f"{path}/signing-secret", headers=api.csrf_headers())
    again = api.client.delete(f"{path}/signing-secret", headers=api.csrf_headers())

    assert (removed.status_code, again.status_code) == (204, 204)
    body = api.client.get(path).json()
    assert (body["signing_secret_configured"], body["signing_secret_created_at"]) == (False, None)
    removals = [a for a, _ in _events(api, world.workspace_id) if a.endswith("_removed")]
    assert removals == ["widget.signing_secret_removed"]


def test_list_widgets_filters_and_pages(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    other_product = api.client.post(
        f"/v1/workspaces/{world.workspace_id}/products",
        json={"name": "Loja"},
        headers=api.csrf_headers(),
    ).json()["id"]
    create_widget(api, world.workspace_id, world.assistant_id, name="Balcão_1")
    create_widget(api, world.workspace_id, world.assistant_id, name="Alfa", active=False)
    create_widget(api, world.workspace_id, other_product, name="Beta")
    path = widgets_path(world.workspace_id)

    def names(**params: str | int) -> list[str]:
        response = api.client.get(path, params=params)
        assert response.status_code == 200, response.text
        return [item["name"] for item in response.json()["items"]]

    assert names() == ["Alfa", "Balcão_1", "Beta"]
    assert names(product_id=other_product) == ["Beta"]
    assert names(active="false") == ["Alfa"]
    assert names(query="CÃO_") == ["Balcão_1"]
    assert names(query="%") == []
    page = api.client.get(path, params={"limit": 1, "offset": 1}).json()
    assert ([item["name"] for item in page["items"]], page["total"]) == (["Balcão_1"], 3)


def test_widgets_isolated_by_workspace(api: ApiEnv) -> None:
    other = build_world(api, Role.OWNER)
    foreign = create_widget(api, other.workspace_id, other.assistant_id)
    world = build_world(api, Role.OWNER)
    create_widget(api, world.workspace_id, world.assistant_id, name="Meu")
    foreign_in_mine = widgets_path(world.workspace_id, foreign["id"])

    listing = api.client.get(widgets_path(world.workspace_id)).json()
    read = api.client.get(foreign_in_mine)
    patched = api.client.patch(foreign_in_mine, json={"name": "X"}, headers=api.csrf_headers())
    deleted = api.client.delete(foreign_in_mine, headers=api.csrf_headers())
    rotated = api.client.post(f"{foreign_in_mine}/signing-secret", headers=api.csrf_headers())
    elsewhere = api.client.get(widgets_path(other.workspace_id))

    assert [item["name"] for item in listing["items"]] == ["Meu"]
    assert {error(r) for r in (read, patched, deleted, rotated, elsewhere)} == {(404, "not_found")}
    assert stored_widget(api, foreign["id"]) is not None
