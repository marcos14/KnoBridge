"""``POST /v1/workspaces/{id}/collections/{cid}/search``: access, response shape, validation,
provider errors and a constant number of statements."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import cast

import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv
from fastapi import FastAPI
from search_support import Passage, add_passages, build_search_world, search_path

from fakes.embedding_provider import RecordingEmbeddingFactory, RecordingEmbeddingProvider
from knobridge.api.deps import get_embedding_provider_factory, get_search_service
from knobridge.llm.errors import ProviderRateLimitError
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

QUERY = "fechamento caixa relatório"
CODE = Passage(
    "path: src/caixa/fechamento.ts\nsymbol: fecharCaixa\n\n"
    "// O fechamento de caixa exige o relatório Z\nexport function fecharCaixa() {}",
    key="src/caixa/fechamento.ts",
    position=2,
    meta={
        "path": "src/caixa/fechamento.ts",
        "symbol": "fecharCaixa",
        "start_line": 10,
        "end_line": 11,
        "language": "typescript",
    },
)


@pytest.fixture
def failing_embeddings(api: ApiEnv) -> Generator[RecordingEmbeddingProvider]:
    app = cast(FastAPI, api.client.app)
    provider = RecordingEmbeddingProvider(ProviderRateLimitError("Slow down.", provider="fake"))
    factory = RecordingEmbeddingFactory(provider)
    app.dependency_overrides[get_embedding_provider_factory] = lambda: factory
    yield provider
    app.dependency_overrides.pop(get_embedding_provider_factory, None)


def test_search_endpoint_returns_scored_chunks_with_citation(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER, Role.EDITOR)
    (chunk_id,) = add_passages(api, world, CODE)
    api.login(world.users[1])

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200, response.text
    (result,) = response.json()["results"]
    scores = result.pop("scores")
    assert scores["vector"] > 0.3
    assert scores["fts"] > 0
    assert scores["fused"] > 0
    document = result.pop("document")
    assert document == {
        "id": document["id"],
        "source_id": str(world.source_id),
        "kind": "file",
        "key": "src/caixa/fechamento.ts",
        "title": "fechamento.ts",
        "uri": "https://git.example.test/repo/blob/main/src/caixa/fechamento.ts",
    }
    assert result == {
        "chunk_id": str(chunk_id),
        "position": 2,
        "path": "src/caixa/fechamento.ts",
        "symbol": "fecharCaixa",
        "start_line": 10,
        "end_line": 11,
        "snippet": "// O fechamento de caixa exige o relatório Z\nexport function fecharCaixa() {}",
        "meta": CODE.meta,
    }


def test_search_endpoint_refuses_a_viewer(api: ApiEnv) -> None:
    """A viewer asks at ``end_user`` in the chat; here it would read every chunk."""
    world = build_search_world(api, Role.OWNER, Role.VIEWER)
    add_passages(api, world, CODE)
    api.login(world.users[1])

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    assert response.json()["error"]["details"] == {"required_role": "editor"}


def test_search_endpoint_filters_by_level(api: ApiEnv) -> None:
    world = build_search_world(api, Role.EDITOR)
    add_passages(api, world, CODE)

    def keys(body: dict[str, object]) -> list[object]:
        response = api.client.post(
            search_path(world.workspace_id, world.collection_id),
            json={"query": QUERY, **body},
            headers=api.csrf_headers(),
        )
        assert response.status_code == 200, response.text
        return [item["document"]["key"] for item in response.json()["results"]]

    # The passage is code: ``product_dev`` (the default, every chunk) only.
    assert keys({}) == ["src/caixa/fechamento.ts"]
    assert keys({"level": "product_dev"}) == ["src/caixa/fechamento.ts"]
    assert keys({"level": "support"}) == []
    assert keys({"level": "end_user"}) == []


def test_search_endpoint_returns_empty_for_unrelated_question(api: ApiEnv) -> None:
    world = build_search_world(api, Role.EDITOR)
    add_passages(api, world, CODE)

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": "receita de bolo de chocolate"},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_search_endpoint_applies_limit_and_min_similarity(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    add_passages(
        api,
        world,
        *(Passage(f"O fechamento de caixa exige o relatório {n}", f"d/{n}.md") for n in range(3)),
        Passage("Caixa e fechamento do turno", "d/weak.md"),
    )
    path = search_path(world.workspace_id, world.collection_id)

    limited = api.client.post(path, json={"query": QUERY, "limit": 2}, headers=api.csrf_headers())
    strict = api.client.post(
        path, json={"query": QUERY, "min_similarity": 0.9}, headers=api.csrf_headers()
    )

    assert len(limited.json()["results"]) == 2
    # Above every vector similarity: only the full-text matches (all three terms) remain.
    assert sorted(r["document"]["key"] for r in strict.json()["results"]) == [
        "d/0.md",
        "d/1.md",
        "d/2.md",
    ]


def test_search_endpoint_requires_membership(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    outsider = api.create_user()
    api.create_workspace({outsider.id: Role.OWNER})
    api.login(outsider)

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_search_endpoint_requires_a_session(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    api.client.post("/v1/auth/logout", headers=api.csrf_headers())
    api.client.get("/v1/auth/csrf")

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_search_endpoint_requires_csrf(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id), json={"query": QUERY}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_search_endpoint_hides_collections_of_other_workspaces(api: ApiEnv) -> None:
    other = build_search_world(api, Role.OWNER)
    add_passages(api, other, CODE)
    mine = build_search_world(api, Role.OWNER)

    response = api.client.post(
        search_path(mine.workspace_id, other.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Collection not found.", "details": None}
    }


def test_search_endpoint_unknown_collection_is_404(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)

    response = api.client.post(
        search_path(world.workspace_id, uuid.uuid4()),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"query": "   "},
        {"query": "x" * 2001},
        {"query": QUERY, "limit": 0},
        {"query": QUERY, "limit": 51},
        {"query": QUERY, "min_similarity": 1.5},
    ],
)
def test_search_endpoint_validates_body(api: ApiEnv, body: dict[str, object]) -> None:
    world = build_search_world(api, Role.OWNER)

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id), json=body, headers=api.csrf_headers()
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_endpoint_reports_provider_errors(
    api: ApiEnv, failing_embeddings: RecordingEmbeddingProvider
) -> None:
    world = build_search_world(api, Role.OWNER)

    response = api.client.post(
        search_path(world.workspace_id, world.collection_id),
        json={"query": QUERY},
        headers=api.csrf_headers(),
    )

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "provider_rate_limited",
            "message": "Slow down.",
            "details": {"provider": "fake", "status": None},
        }
    }
    assert failing_embeddings.closed


def test_search_endpoint_uses_constant_statements(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    path = search_path(world.workspace_id, world.collection_id)
    add_passages(api, world, Passage("O fechamento de caixa exige o relatório", "a/0.md"))
    with count_statements(api) as one:
        first = api.client.post(path, json={"query": QUERY}, headers=api.csrf_headers())
    add_passages(
        api,
        world,
        *(Passage(f"O fechamento de caixa exige o relatório {n}", f"b/{n}.md") for n in range(8)),
    )
    with count_statements(api) as nine:
        second = api.client.post(path, json={"query": QUERY}, headers=api.csrf_headers())

    assert len(first.json()["results"]) == 1
    assert len(second.json()["results"]) == 9
    assert len(one) == len(nine)


class _SpySearch:
    """Records the floor the route passes and finds nothing."""

    def __init__(self) -> None:
        self.min_similarity: object = None

    async def search(self, db: object, **kwargs: object) -> list[object]:
        self.min_similarity = kwargs["min_similarity"]
        return []


def test_search_endpoint_defaults_min_similarity_to_035(api: ApiEnv) -> None:
    world = build_search_world(api, Role.OWNER)
    app = cast(FastAPI, api.client.app)
    spy = _SpySearch()
    app.dependency_overrides[get_search_service] = lambda: spy
    try:
        response = api.client.post(
            search_path(world.workspace_id, world.collection_id),
            json={"query": QUERY},
            headers=api.csrf_headers(),
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)

    assert response.status_code == 200, response.text
    assert spy.min_similarity == 0.35
