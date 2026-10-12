"""Search, filters and sort of the collection and source lists (plan 0008 F2.5): literal
wildcards, last-run semantics, nulls last, 422 for unknown values, a constant number of
statements and workspace isolation."""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from admin_chat_support import count_statements
from api_support import ApiEnv
from index_support import (
    IndexOverrides,
    IndexWorld,
    add_documents,
    add_run,
    base,
    build_world,
    create_source,
    error_code,
    install,
    post_collection,
)

from knobridge.ingestion.models import RunStatus
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration


@pytest.fixture
def index(api: ApiEnv) -> Generator[IndexOverrides]:
    overrides = install(api)
    yield overrides
    overrides.clear()


def _names(api: ApiEnv, path: str, **params: str | int) -> list[str]:
    response = api.client.get(path, params=params)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()["items"]]


def _collection(api: ApiEnv, world: IndexWorld, name: str, **fields: object) -> str:
    response = post_collection(api, world.workspace_id, world.provider_id, name=name, **fields)
    assert response.status_code == 201, response.text
    collection_id: str = response.json()["id"]
    return collection_id


def test_collection_list_search_filter_and_sort(api: ApiEnv, index: IndexOverrides) -> None:
    other = build_world(api, Role.OWNER)
    _collection(api, other, "Manuais do ERP")  # same words, another workspace
    world = build_world(api, Role.OWNER, Role.VIEWER)
    manuals = _collection(api, world, "Manuais do ERP")
    _collection(api, world, "100%_off", description="Promoções")
    big = create_source(api, world, collection_id=manuals)
    add_documents(api, world, big, {"a.md": 1, "b.md": 1, "c.md": 1})
    first = api.client.get(f"{base(world.workspace_id)}/collections/{world.collection_id}")
    first_name = first.json()["name"]
    path = f"{base(world.workspace_id)}/collections"

    api.login(world.users[1])  # viewers list too
    by_name = _names(api, path, query="manuais")
    by_description = _names(api, path, query="PROMO")
    literal = _names(api, path, query="%_")
    no_wildcard = _names(api, path, query="_")
    ascending = _names(api, path)
    descending = _names(api, path, sort="-name")
    by_documents = _names(api, path, sort="-document_count")
    of_provider = _names(api, path, provider_id=world.provider_id)
    of_unknown = _names(api, path, provider_id=str(uuid.uuid4()))

    assert by_name == ["Manuais do ERP"]
    assert by_description == literal == no_wildcard == ["100%_off"]
    # By the database collation, whatever it is: descending is the default order reversed.
    assert sorted(ascending) == sorted([first_name, "Manuais do ERP", "100%_off"])
    assert descending == list(reversed(ascending))
    assert by_documents[0] == "Manuais do ERP"
    assert sorted(of_provider) == sorted([first_name, "Manuais do ERP", "100%_off"])
    assert of_unknown == []


def test_collection_list_dates_and_invalid_values(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    _collection(api, world, "b")
    _collection(api, world, "a")
    path = f"{base(world.workspace_id)}/collections"

    created = _names(api, path, sort="created_at")
    created_desc = _names(api, path, sort="-created_at")
    updated_desc = _names(api, path, sort="-updated_at")
    bad_sort = api.client.get(path, params={"sort": "provider"})
    long_query = api.client.get(path, params={"query": "x" * 201})

    assert created[1:] == ["b", "a"]
    assert created_desc == list(reversed(created)) == updated_desc
    assert error_code(bad_sort) == (422, "validation_error")
    assert error_code(long_query) == (422, "validation_error")


def test_collection_list_statements_do_not_grow_with_the_page(api: ApiEnv) -> None:
    world = build_world(api, Role.OWNER)
    for number in range(3):
        _collection(api, world, f"c{number}")
    path = f"{base(world.workspace_id)}/collections"

    with count_statements(api) as one:
        _names(api, path, limit=1, sort="-document_count", query="c")
    with count_statements(api) as many:
        _names(api, path, limit=50, sort="-document_count", query="c")

    assert len(one) == len(many)


def test_source_list_search_filters_and_last_run(api: ApiEnv, index: IndexOverrides) -> None:
    other = build_world(api, Role.OWNER)
    create_source(api, other, name="alpha docs")
    world = build_world(api, Role.EDITOR)
    second = _collection(api, world, "segunda")
    alpha = create_source(api, world, name="alpha docs")
    beta = create_source(api, world, name="beta", active=False)
    create_source(api, world, name="gamma", kind="tickets", config={}, collection_id=second)
    create_source(api, world, name="100%_off")
    add_run(api, world, alpha, RunStatus.SUCCEEDED)
    add_run(api, world, alpha, RunStatus.FAILED)
    add_run(api, world, beta, RunStatus.SUCCEEDED)
    path = f"{base(world.workspace_id)}/sources"

    assert _names(api, path, query="ALPHA") == ["alpha docs"]
    assert _names(api, path, query="%_") == ["100%_off"]
    assert _names(api, path, kind="tickets") == ["gamma"]
    assert _names(api, path, active="false") == ["beta"]
    assert _names(api, path, collection_id=second) == ["gamma"]
    # Only the newest run counts: alpha's last run failed.
    assert _names(api, path, last_run_status="failed") == ["alpha docs"]
    assert _names(api, path, last_run_status="succeeded") == ["beta"]
    assert _names(api, path, last_run_status="never") == ["100%_off", "gamma"]
    assert _names(api, path, last_run_status="running") == []


def test_source_list_sorts_with_sources_without_runs_last(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.OWNER)
    older = create_source(api, world, name="b-older")
    newer = create_source(api, world, name="a-newer")
    create_source(api, world, name="c-never")
    add_run(api, world, older, RunStatus.SUCCEEDED)
    add_run(api, world, newer, RunStatus.SUCCEEDED)
    path = f"{base(world.workspace_id)}/sources"

    by_run = _names(api, path, sort="last_run_at")
    by_run_desc = _names(api, path, sort="-last_run_at")
    by_name_desc = _names(api, path, sort="-name")
    created = _names(api, path, sort="created_at")
    updated_desc = _names(api, path, sort="-updated_at")
    bad = api.client.get(path, params={"sort": "kind"})
    bad_status = api.client.get(path, params={"last_run_status": "done"})

    assert by_run == ["b-older", "a-newer", "c-never"]
    assert by_run_desc == ["a-newer", "b-older", "c-never"]
    assert by_name_desc == ["c-never", "b-older", "a-newer"]
    assert created == ["b-older", "a-newer", "c-never"]
    assert updated_desc == list(reversed(created))
    assert error_code(bad) == (422, "validation_error")
    assert error_code(bad_status) == (422, "validation_error")


def test_source_list_statements_do_not_grow_with_the_page(
    api: ApiEnv, index: IndexOverrides
) -> None:
    world = build_world(api, Role.OWNER)
    for number in range(3):
        source_id = create_source(api, world, name=f"s{number}")
        add_run(api, world, source_id, RunStatus.SUCCEEDED)
    path = f"{base(world.workspace_id)}/sources"
    params = {"sort": "-last_run_at", "last_run_status": "succeeded", "query": "s"}

    with count_statements(api) as one:
        _names(api, path, limit=1, **params)
    with count_statements(api) as many:
        names = _names(api, path, limit=50, **params)

    assert len(names) == 3
    assert len(one) == len(many)
