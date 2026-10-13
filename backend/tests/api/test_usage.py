"""``GET /v1/workspaces/{id}/usage``: tokens and estimated USD of a period, grouped.

Runs count by ``finished_at`` and answers (with a model) by ``created_at``, in ``[from, to)``;
unknown costs are counted apart, never as zero; columns that do not apply are null; one
statement for the totals and one for the rows; admins only; isolated per workspace.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from admin_chat_support import count_statements
from api_support import START, ApiEnv
from usage_support import (
    UsageWorld,
    add_answer,
    add_api_key,
    add_assistant,
    add_collection,
    add_conversation,
    add_run,
    add_source,
    usage_path,
    usage_world,
)

from knobridge.conversations.models import ConversationChannel, MessageStatus
from knobridge.ingestion.models import RunStatus
from knobridge.levels.level import ResponseLevel
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

FROM, TO = "2026-09-01T00:00:00Z", "2026-09-04T00:00:00Z"
PERIOD = {"from": FROM, "to": TO}


def _at(day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


_EMPTY_EMBEDDING: dict[str, object] = {
    "embedding_tokens": None,
    "embedding_cost_usd": None,
    "runs": None,
    "unpriced_runs": None,
}
_EMPTY_CHAT: dict[str, object] = {
    "chat_input_tokens": None,
    "chat_output_tokens": None,
    "chat_cost_usd": None,
    "answers": None,
    "unpriced_answers": None,
}


def _embedding(tokens: int, cost: float, runs: int, unpriced: int) -> dict[str, object]:
    return {
        "embedding_tokens": tokens,
        "embedding_cost_usd": cost,
        "runs": runs,
        "unpriced_runs": unpriced,
    }


def _chat(
    input_tokens: int, output_tokens: int, cost: float, answers: int, unpriced: int
) -> dict[str, object]:
    return {
        "chat_input_tokens": input_tokens,
        "chat_output_tokens": output_tokens,
        "chat_cost_usd": cost,
        "answers": answers,
        "unpriced_answers": unpriced,
    }


class Seeded:
    def __init__(self, api: ApiEnv) -> None:
        self.world: UsageWorld = usage_world(api, Role.OWNER)
        world = self.world
        self.docs = add_collection(api, world, "Docs")
        self.code = add_collection(api, world, "Código", model="fake-embedding")
        self.manual = add_source(api, world, self.docs, "Manual")
        self.repo = add_source(api, world, self.code, "Repo")
        add_run(api, world, self.manual, finished_at=_at(1, 10), tokens=1000, cost="0.000020")
        add_run(api, world, self.manual, finished_at=_at(2, 23, 59), tokens=500, cost="0.000010")
        add_run(api, world, self.repo, finished_at=_at(2), tokens=300, status=RunStatus.FAILED)
        # Outside the period: before it, at its (exclusive) end, still open.
        add_run(api, world, self.manual, finished_at=_at(1, 0) - timedelta(minutes=1), tokens=7)
        add_run(api, world, self.manual, finished_at=_at(4, 0), tokens=7, cost="1")
        add_run(api, world, self.manual, finished_at=None, tokens=7, status=RunStatus.RUNNING)
        self.sales = add_assistant(api, world, "Vendas")
        self.key = add_api_key(api, world, "Integração ERP")
        panel = add_conversation(api, world)
        add_answer(api, world, panel, at=_at(1), tokens=(100, 20), cost="0.000072")
        add_answer(api, world, panel, at=_at(3), tokens=(50, 10), cost="0.000036")
        add_answer(api, world, panel, at=_at(1), model=None, tokens=None, cost=None)
        add_answer(api, world, panel, at=_at(2), tokens=None, status=MessageStatus.FAILED)
        add_answer(api, world, panel, at=_at(4, 0), tokens=(9, 9), cost="1")
        sales = add_conversation(api, world, assistant_id=self.sales, level=ResponseLevel.SUPPORT)
        add_answer(
            api, world, sales, at=_at(2), model="claude-haiku-4-5", tokens=(10, 5), cost="0.000035"
        )
        through_api = add_conversation(api, world, api_key_id=self.key)
        add_answer(
            api,
            world,
            through_api,
            at=_at(3),
            tokens=(200, 40),
            cost="0.000144",
            channel=ConversationChannel.API,
        )


@pytest.fixture
def seeded(api: ApiEnv) -> Seeded:
    return Seeded(api)


def _report(api: ApiEnv, world: UsageWorld, group_by: str) -> dict[str, object]:
    response = api.client.get(usage_path(world), params={**PERIOD, "group_by": group_by})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def _rows(api: ApiEnv, world: UsageWorld, group_by: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = _report(api, world, group_by)["rows"]  # type: ignore[assignment]
    return rows


def test_usage_totals_of_the_period(api: ApiEnv, seeded: Seeded) -> None:
    body = _report(api, seeded.world, "product")

    assert body["period_start"] == "2026-09-01T00:00:00Z"
    assert body["period_end"] == "2026-09-04T00:00:00Z"
    assert body["group_by"] == "product"
    assert body["totals"] == {
        **_embedding(1800, 0.00003, 3, 1),
        **_chat(360, 75, 0.000287, 5, 1),
        "cost_usd": 0.000317,
    }


def test_usage_by_product(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "product") == [
        {
            "key": str(seeded.world.assistant_id),
            "label": "Suporte ERP",
            **_EMPTY_EMBEDDING,
            **_chat(350, 70, 0.000252, 4, 1),
            "cost_usd": 0.000252,
        },
        {
            "key": str(seeded.sales),
            "label": "Vendas",
            **_EMPTY_EMBEDDING,
            **_chat(10, 5, 0.000035, 1, 0),
            "cost_usd": 0.000035,
        },
    ]


def test_usage_by_level_has_the_three_levels_in_order(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "level") == [
        {
            "key": "end_user",
            "label": "end_user",
            **_EMPTY_EMBEDDING,
            **_chat(0, 0, 0.0, 0, 0),
            "cost_usd": 0.0,
        },
        {
            "key": "support",
            "label": "support",
            **_EMPTY_EMBEDDING,
            **_chat(10, 5, 0.000035, 1, 0),
            "cost_usd": 0.000035,
        },
        {
            "key": "product_dev",
            "label": "product_dev",
            **_EMPTY_EMBEDDING,
            **_chat(350, 70, 0.000252, 4, 1),
            "cost_usd": 0.000252,
        },
    ]


def test_usage_filtered_by_product_or_level_leaves_embeddings_out(
    api: ApiEnv, seeded: Seeded
) -> None:
    def report(**filters: str) -> dict[str, object]:
        response = api.client.get(
            usage_path(seeded.world), params={**PERIOD, "group_by": "day", **filters}
        )
        assert response.status_code == 200, response.text
        body: dict[str, object] = response.json()
        return body

    by_product = report(product_id=str(seeded.sales))
    by_level = report(level="product_dev")
    both = report(product_id=str(seeded.sales), level="product_dev")
    other = report(product_id=str(uuid.uuid4()))

    assert by_product["totals"] == {
        **_EMPTY_EMBEDDING,
        **_chat(10, 5, 0.000035, 1, 0),
        "cost_usd": 0.000035,
    }
    assert by_level["totals"] == {
        **_EMPTY_EMBEDDING,
        **_chat(350, 70, 0.000252, 4, 1),
        "cost_usd": 0.000252,
    }
    assert both["totals"] == {**_EMPTY_EMBEDDING, **_chat(0, 0, 0.0, 0, 0), "cost_usd": 0.0}
    assert other["rows"] == [
        {"key": day, "label": day, **_EMPTY_EMBEDDING, **_chat(0, 0, 0.0, 0, 0), "cost_usd": 0.0}
        for day in ("2026-09-01", "2026-09-02", "2026-09-03")
    ]
    rows: list[dict[str, object]] = by_product["rows"]  # type: ignore[assignment]
    assert [row["answers"] for row in rows] == [0, 1, 0]
    assert all(row["embedding_tokens"] is None for row in rows)


def test_usage_csv_name_carries_the_level(api: ApiEnv, seeded: Seeded) -> None:
    response = api.client.get(
        usage_path(seeded.world, "usage.csv"),
        params={**PERIOD, "group_by": "product", "level": "support"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="knobridge-uso-product-2026-09-01-2026-09-04-support.csv"'
    )
    lines = response.text.split("\r\n")
    assert lines[1] == f"{seeded.sales},Vendas,,,,,10,5,0.000035,1,0,0.000035"
    assert lines[2] == "total,Total,,,,,10,5,0.000035,1,0,0.000035"


def test_usage_by_source_and_collection(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "source") == [
        {
            "key": str(seeded.manual),
            "label": "Manual",
            **_embedding(1500, 0.00003, 2, 0),
            **_EMPTY_CHAT,
            "cost_usd": 0.00003,
        },
        {
            "key": str(seeded.repo),
            "label": "Repo",
            **_embedding(300, 0.0, 1, 1),
            **_EMPTY_CHAT,
            "cost_usd": 0.0,
        },
    ]
    assert [
        (row["key"], row["label"], row["embedding_tokens"])
        for row in _rows(api, seeded.world, "collection")
    ] == [(str(seeded.docs), "Docs", 1500), (str(seeded.code), "Código", 300)]


def test_usage_by_channel_and_api_key(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "channel") == [
        {
            "key": "api",
            "label": "API",
            **_EMPTY_EMBEDDING,
            **_chat(200, 40, 0.000144, 1, 0),
            "cost_usd": 0.000144,
        },
        {
            "key": "panel",
            "label": "Painel",
            **_EMPTY_EMBEDDING,
            **_chat(160, 35, 0.000143, 4, 1),
            "cost_usd": 0.000143,
        },
    ]
    assert _rows(api, seeded.world, "api_key") == [
        {
            "key": str(seeded.key),
            "label": "Integração ERP",
            **_EMPTY_EMBEDDING,
            **_chat(200, 40, 0.000144, 1, 0),
            "cost_usd": 0.000144,
        }
    ]


def test_usage_by_model_fills_the_side_of_each_model(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "model") == [
        {
            "key": "gpt-4.1-mini",
            "label": "gpt-4.1-mini",
            **_EMPTY_EMBEDDING,
            **_chat(350, 70, 0.000252, 4, 1),
            "cost_usd": 0.000252,
        },
        {
            "key": "claude-haiku-4-5",
            "label": "claude-haiku-4-5",
            **_EMPTY_EMBEDDING,
            **_chat(10, 5, 0.000035, 1, 0),
            "cost_usd": 0.000035,
        },
        {
            "key": "text-embedding-3-small",
            "label": "text-embedding-3-small",
            **_embedding(1500, 0.00003, 2, 0),
            **_EMPTY_CHAT,
            "cost_usd": 0.00003,
        },
        {
            "key": "fake-embedding",
            "label": "fake-embedding",
            **_embedding(300, 0.0, 1, 1),
            **_EMPTY_CHAT,
            "cost_usd": 0.0,
        },
    ]


def test_usage_by_day_lists_every_day_with_both_sides(api: ApiEnv, seeded: Seeded) -> None:
    assert _rows(api, seeded.world, "day") == [
        {
            "key": "2026-09-01",
            "label": "2026-09-01",
            **_embedding(1000, 0.00002, 1, 0),
            **_chat(100, 20, 0.000072, 1, 0),
            "cost_usd": 0.000092,
        },
        {
            "key": "2026-09-02",
            "label": "2026-09-02",
            **_embedding(800, 0.00001, 2, 1),
            **_chat(10, 5, 0.000035, 2, 1),
            "cost_usd": 0.000045,
        },
        {
            "key": "2026-09-03",
            "label": "2026-09-03",
            **_embedding(0, 0.0, 0, 0),
            **_chat(250, 50, 0.00018, 2, 0),
            "cost_usd": 0.00018,
        },
    ]


def test_usage_empty_workspace_has_zero_totals_and_seeded_rows(api: ApiEnv) -> None:
    world = usage_world(api, Role.ADMIN)

    body = _report(api, world, "channel")
    days = _rows(api, world, "day")

    assert body["totals"] == {
        **_embedding(0, 0.0, 0, 0),
        **_chat(0, 0, 0.0, 0, 0),
        "cost_usd": 0.0,
    }
    assert [row["key"] for row in body["rows"]] == ["api", "panel"]  # type: ignore[union-attr]
    assert [row["key"] for row in days] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert _rows(api, world, "source") == []


def test_usage_day_rows_of_an_unaligned_period(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    response = api.client.get(
        usage_path(world),
        params={"from": "2026-09-01T18:00:00", "to": "2026-09-03T00:00:01Z", "group_by": "day"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["period_start"] == "2026-09-01T18:00:00Z"
    assert [row["key"] for row in response.json()["rows"]] == [
        "2026-09-01",
        "2026-09-02",
        "2026-09-03",
    ]


def test_usage_default_period_is_the_30_days_before_now(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    response = api.client.get(usage_path(world), params={"group_by": "product"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["period_end"] == START.isoformat().replace("+00:00", "Z")
    assert body["period_start"] == (START - timedelta(days=30)).isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"from": TO, "to": FROM, "group_by": "day"}, "validation_error"),
        ({"from": FROM, "to": FROM, "group_by": "day"}, "validation_error"),
        (
            {"from": "2025-09-01T00:00:00Z", "to": "2026-09-03T00:00:00Z", "group_by": "day"},
            "usage_period_too_long",
        ),
        ({"group_by": "workspace"}, "validation_error"),
        ({"group_by": "assistant"}, "validation_error"),
        ({"group_by": "day", "level": "admin"}, "validation_error"),
        ({"group_by": "source", "level": "support"}, "validation_error"),
        ({"group_by": "collection", "product_id": str(uuid.uuid4())}, "validation_error"),
        ({}, "validation_error"),
    ],
)
def test_usage_rejects_invalid_queries(api: ApiEnv, params: dict[str, str], code: str) -> None:
    world = usage_world(api, Role.OWNER)

    response = api.client.get(usage_path(world), params=params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_usage_accepts_a_366_day_period(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    response = api.client.get(
        usage_path(world),
        params={"from": "2025-09-01T00:00:00Z", "to": "2026-09-02T00:00:00Z", "group_by": "day"},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["rows"]) == 366


@pytest.mark.parametrize("role", [Role.EDITOR, Role.VIEWER])
@pytest.mark.parametrize("suffix", ["usage", "usage.csv"])
def test_usage_is_for_admins(api: ApiEnv, role: Role, suffix: str) -> None:
    world = usage_world(api, Role.OWNER, role)
    api.login(world.users[1])

    response = api.client.get(usage_path(world, suffix), params={"group_by": "day"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_usage_requires_a_session(api: ApiEnv) -> None:
    response = api.client.get(f"/v1/workspaces/{uuid.uuid4()}/usage", params={"group_by": "day"})

    assert response.status_code == 401


def test_usage_is_isolated_between_workspaces(api: ApiEnv, seeded: Seeded) -> None:
    other = usage_world(api, Role.OWNER)
    collection = add_collection(api, other, "Outra")
    source = add_source(api, other, collection, "Outra fonte")
    add_run(api, other, source, finished_at=_at(2), tokens=99999, cost="5")
    add_answer(api, other, add_conversation(api, other), at=_at(2), tokens=(1, 1), cost="7")

    totals = _report(api, other, "source")["totals"]
    api.login(seeded.world.users[0])
    mine = _report(api, seeded.world, "source")
    foreign = api.client.get(usage_path(other), params={**PERIOD, "group_by": "day"})

    assert totals["cost_usd"] == 12.0  # type: ignore[index]
    assert mine["totals"]["embedding_tokens"] == 1800  # type: ignore[index]
    assert [row["label"] for row in mine["rows"]] == ["Manual", "Repo"]  # type: ignore[union-attr]
    assert foreign.status_code == 404


@pytest.mark.parametrize("group_by", ["product", "level", "model", "day"])
def test_usage_takes_a_constant_number_of_statements(
    api: ApiEnv, seeded: Seeded, group_by: str
) -> None:
    world = seeded.world
    params = {**PERIOD, "group_by": group_by}
    with count_statements(api) as before:
        api.client.get(usage_path(world), params=params)
    for index in range(3):
        extra = add_assistant(api, world, f"Extra {index}")
        add_answer(api, world, add_conversation(api, world, assistant_id=extra), at=_at(2))
    with count_statements(api) as after:
        response = api.client.get(usage_path(world), params=params)

    assert response.status_code == 200
    assert len(after) == len(before)
