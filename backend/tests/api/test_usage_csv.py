"""``GET /v1/workspaces/{id}/usage.csv``: the usage report as an attachment, safe for a
spreadsheet."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from api_support import ApiEnv
from usage_support import (
    add_answer,
    add_collection,
    add_conversation,
    add_run,
    add_source,
    usage_path,
    usage_world,
)

from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

PARAMS = {"from": "2026-09-01T00:00:00Z", "to": "2026-09-03T00:00:00Z"}
HEADER = (
    "key,label,embedding_tokens,embedding_cost_usd,runs,unpriced_runs,chat_input_tokens,"
    "chat_output_tokens,chat_cost_usd,answers,chat_searches,unpriced_answers,cost_usd"
)


def test_usage_csv_has_rows_and_a_total_line(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)
    collection = add_collection(api, world, "Docs")
    risky = add_source(api, world, collection, '=HYPERLINK("http://x")')
    quoted = add_source(api, world, collection, 'Repo, "principal"\nnovo')
    at = datetime(2026, 9, 1, 12, tzinfo=UTC)
    add_run(api, world, risky, finished_at=at, tokens=1000, cost="0.00002")
    add_run(api, world, quoted, finished_at=at, tokens=10)
    add_answer(api, world, add_conversation(api, world), at=at, tokens=(100, 20), cost="0.000072")

    response = api.client.get(
        usage_path(world, "usage.csv"), params={**PARAMS, "group_by": "source"}
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="knobridge-uso-source-2026-09-01-2026-09-03.csv"'
    )
    assert not response.content.startswith(b"\xef\xbb\xbf")
    assert response.text.split("\r\n") == [
        HEADER,
        f'{risky},"\'=HYPERLINK(""http://x"")",1000,0.000020,1,0,,,,,,,0.000020',
        f'{quoted},"Repo, ""principal""\nnovo",10,0.000000,1,1,,,,,,,0.000000',
        "total,Total,1010,0.000020,2,1,100,20,0.000072,1,0,0,0.000092",
        "",
    ]


def test_usage_csv_validates_like_the_json_report(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)

    response = api.client.get(
        usage_path(world, "usage.csv"),
        params={"from": "2026-09-03T00:00:00Z", "to": "2026-09-01T00:00:00Z", "group_by": "day"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_usage_csv_by_day_lists_empty_days(api: ApiEnv) -> None:
    world = usage_world(api, Role.ADMIN)

    response = api.client.get(usage_path(world, "usage.csv"), params={**PARAMS, "group_by": "day"})

    lines = response.text.split("\r\n")
    assert lines[1] == "2026-09-01,2026-09-01,0,0.000000,0,0,0,0,0.000000,0,0,0,0.000000"
    assert lines[2].startswith("2026-09-02,")
    assert lines[3].startswith("total,Total,0,")
