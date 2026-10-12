"""``POST .../sources/{sid}/tickets/preview``: one ticket rendered as the index would get it,
anonymized with the source's settings, writing nothing; roles, CSRF, limits and isolation."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx2 as httpx
import pytest
from api_support import ApiEnv
from index_support import IndexOverrides, build_world, create_source, error_code, install
from index_support import source_path as path_of
from ingest_support import TicketsWorld, inbox, source_runs, ticket, tickets_world

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


@pytest.fixture
def tickets(api: ApiEnv, index: IndexOverrides) -> TicketsWorld:
    return tickets_world(api, Role.ADMIN, Role.EDITOR, Role.VIEWER)


def personal_ticket() -> dict[str, Any]:
    return ticket(
        "P-1",
        number="7001",
        requester={"name": "Carla Dias", "email": "carla@exemplo.com.br"},
        messages=[
            {
                "role": "customer",
                "author_name": "Carla Dias",
                "body": "Sou a Carla, CPF 529.982.247-25, e-mail carla@exemplo.com.br.",
                "created_at": "2026-10-01T10:30:00Z",
            },
            {
                "role": "agent",
                "author_name": "Davi Rocha",
                "public": False,
                "body": "Nota interna do Davi.",
                "created_at": "2026-10-01T11:00:00Z",
            },
        ],
    )


def preview(
    api: ApiEnv, world: TicketsWorld, body: object, *, csrf: bool = True, source: str = ""
) -> httpx.Response:
    return api.client.post(
        path_of(world.world, source or world.source_id, "tickets/preview"),
        json=body,
        headers=api.csrf_headers() if csrf else {},
    )


def test_preview_renders_anonymized_markdown_with_markers(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = preview(api, tickets, {"ticket": personal_ticket()})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Erro 4021 ao fechar o caixa"
    assert body["markdown"].startswith("# Chamado 7001: Erro 4021 ao fechar o caixa\n")
    assert "Sou a [SOLICITANTE], CPF [CPF], e-mail [EMAIL]." in body["markdown"]
    assert "Carla" not in body["markdown"]
    assert "Nota interna" not in body["markdown"]
    assert body["markers"] == [
        {"marker": "[SOLICITANTE]", "count": 1},
        {"marker": "[CPF]", "count": 1},
        {"marker": "[EMAIL]", "count": 1},
    ]
    assert (body["anonymize"], body["include_internal_notes"]) == (True, False)


def test_preview_follows_the_source_settings(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    changed = api.client.patch(
        path_of(tickets.world, tickets.source_id),
        json={"config": {"anonymize": False, "include_internal_notes": True}},
        headers=api.csrf_headers(),
    )
    assert changed.status_code == 200, changed.text

    body = preview(api, tickets, {"ticket": personal_ticket()}).json()

    assert "Sou a Carla, CPF 529.982.247-25" in body["markdown"]
    assert "Nota interna do Davi." in body["markdown"]
    assert body["markers"] == []
    assert (body["anonymize"], body["include_internal_notes"]) == (False, True)


def test_preview_writes_nothing(api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld) -> None:
    before = api.workspace_audit(tickets.workspace_id)

    response = preview(api, tickets, {"ticket": personal_ticket()})

    assert response.status_code == 200
    assert inbox(api, tickets.source_id) == {}
    assert source_runs(api, tickets.source_id) == []
    assert index.starter.started == []
    assert api.workspace_audit(tickets.workspace_id) == before


def test_preview_invalid_ticket_is_422_relative_to_the_ticket(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = preview(api, tickets, {"ticket": ticket(status="lost", tags=["a", "a"])})

    assert error_code(response) == (422, "validation_error")
    assert response.json()["error"]["details"] == [
        {"loc": ["status"], "problem": "enum"},
        {"loc": ["tags"], "problem": "not_unique"},
    ]


def test_preview_strict_like_the_api(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = preview(api, tickets, {"ticket": ticket(messages="nenhuma")})

    assert error_code(response) == (422, "validation_error")
    assert response.json()["error"]["details"] == [{"loc": ["messages"], "problem": "list_type"}]


def test_preview_envelope_is_validated(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    missing = preview(api, tickets, {})
    extra = preview(api, tickets, {"ticket": ticket(), "op": "upsert"})

    assert error_code(missing) == (422, "validation_error")
    assert error_code(extra) == (422, "validation_error")


def test_preview_body_above_2_mib_is_413(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    response = api.client.post(
        path_of(tickets.world, tickets.source_id, "tickets/preview"),
        content=json.dumps({"ticket": ticket(title="x" * (2 * 1024 * 1024))}),
        headers={**api.csrf_headers(), "content-type": "application/json"},
    )

    assert error_code(response) == (413, "payload_too_large")


@pytest.mark.parametrize(("user", "status"), [(1, 200), (2, 403)])
def test_preview_needs_editor(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld, user: int, status: int
) -> None:
    api.login(tickets.world.users[user])

    response = preview(api, tickets, {"ticket": ticket()})

    assert response.status_code == status, response.text


def test_preview_needs_csrf(api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld) -> None:
    response = preview(api, tickets, {"ticket": ticket()}, csrf=False)

    assert error_code(response) == (403, "csrf_failed")


def test_preview_of_inactive_source_still_works(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    api.client.patch(
        path_of(tickets.world, tickets.source_id),
        json={"active": False},
        headers=api.csrf_headers(),
    )

    assert preview(api, tickets, {"ticket": ticket()}).status_code == 200


def test_preview_of_folder_source_is_404(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    folder = create_source(api, tickets.world)

    response = preview(api, tickets, {"ticket": ticket()}, source=folder)

    assert error_code(response) == (404, "source_not_found")


def test_preview_of_other_workspace_source_is_404(
    api: ApiEnv, index: IndexOverrides, tickets: TicketsWorld
) -> None:
    other = build_world(api, Role.ADMIN)

    response = api.client.post(
        path_of(other, tickets.source_id, "tickets/preview"),
        json={"ticket": ticket()},
        headers=api.csrf_headers(),
    )

    assert error_code(response) == (404, "source_not_found")
