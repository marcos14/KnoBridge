"""``search_knowledge`` with the instance's reranker (plan 0011 F2.1): the product's ``rerank``
option reorders the results (``score`` stays the fused score), the option off and a failing
reranker keep the RRF order. The reranker is ``FakeReranker`` (reverses the order)."""

from __future__ import annotations

from typing import cast

import pytest
from api_support import ApiEnv
from mcp_support import (
    QUERY,
    call_tools,
    keys_of,
    mcp_world,
    structured,
    world_key,
)

from fakes.reranker import FakeReranker, fake_instance
from knobridge.retrieval.rerank import RerankerError

pytestmark = pytest.mark.integration


def _search(product: str) -> tuple[str, dict[str, object]]:
    return "search_knowledge", {"product": product, "query": QUERY, "limit": 2}


def test_search_knowledge_reranks_with_the_product_option(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    (plain,) = call_tools(api, key, _search(world.product_name))
    fake = FakeReranker()

    (reranked,) = call_tools(api, key, _search(world.product_name), reranker=fake_instance(fake))

    rrf = keys_of(structured(plain))
    assert len(rrf) == 2
    (call,) = fake.calls
    assert (call.query, len(call.chunk_ids), call.limit) == (QUERY, 3, 2)
    # The fake reverses the three candidates: the last of the RRF order comes first.
    assert keys_of(structured(reranked))[1] == rrf[1]
    assert keys_of(structured(reranked))[0] not in rrf
    results = cast(list[dict[str, object]], structured(reranked)["results"])
    assert all(isinstance(item["score"], float) for item in results)


def test_search_knowledge_keeps_the_order_with_the_option_off(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    patched = api.client.patch(
        f"/v1/workspaces/{world.workspace_id}/products/{world.product_id}",
        json={"rerank": False},
        headers=api.csrf_headers(),
    )
    assert patched.status_code == 200, patched.text
    (plain,) = call_tools(api, key, _search(world.product_name))
    fake = FakeReranker()

    (result,) = call_tools(api, key, _search(world.product_name), reranker=fake_instance(fake))

    assert keys_of(structured(result)) == keys_of(structured(plain))
    assert fake.calls == []


def test_search_knowledge_keeps_the_order_when_the_reranker_fails(api: ApiEnv) -> None:
    world = mcp_world(api)
    key = world_key(api, world)
    (plain,) = call_tools(api, key, _search(world.product_name))
    fake = FakeReranker(error=RerankerError("The reranker answered 500."))

    (result,) = call_tools(api, key, _search(world.product_name), reranker=fake_instance(fake))

    assert keys_of(structured(result)) == keys_of(structured(plain))
    assert len(fake.calls) == 1
