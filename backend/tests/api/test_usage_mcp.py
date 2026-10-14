"""Uso e custos with the ``mcp`` channel (``docs/specs/uso-e-custos.md``, "Canais MCP e
widget"): the ``mcp`` line of ``group_by=channel`` and ``group_by=api_key`` adding the key's
answers of the ``api`` and ``mcp`` channels."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from api_support import ApiEnv
from usage_support import add_answer, add_api_key, add_conversation, usage_path, usage_world

from knobridge.conversations.models import ConversationChannel
from knobridge.tenancy.models import Role

pytestmark = pytest.mark.integration

PERIOD = {"from": "2026-09-01T00:00:00Z", "to": "2026-09-04T00:00:00Z"}
AT = datetime(2026, 9, 2, 12, tzinfo=UTC)


def _rows(api: ApiEnv, path: str, group_by: str) -> dict[str, tuple[object, object, object]]:
    response = api.client.get(path, params={**PERIOD, "group_by": group_by})
    assert response.status_code == 200, response.text
    return {
        row["key"]: (row["label"], row["answers"], row["chat_cost_usd"])
        for row in response.json()["rows"]
    }


def test_usage_counts_mcp_answers_by_channel_and_by_key(api: ApiEnv) -> None:
    world = usage_world(api, Role.OWNER)
    key = add_api_key(api, world, "Claude Code")
    through_api = add_conversation(api, world, api_key_id=key)
    through_mcp = add_conversation(api, world, api_key_id=key, channel=ConversationChannel.MCP)
    add_answer(api, world, through_api, at=AT, cost="0.000100", channel=ConversationChannel.API)
    add_answer(api, world, through_mcp, at=AT, cost="0.000200", channel=ConversationChannel.MCP)
    add_answer(api, world, through_mcp, at=AT, cost="0.000050", channel=ConversationChannel.MCP)
    path = usage_path(world)

    channels = _rows(api, path, "channel")
    keys = _rows(api, path, "api_key")

    assert channels["mcp"] == ("MCP", 2, 0.00025)
    assert channels["api"] == ("API", 1, 0.0001)
    assert channels["panel"] == ("Painel", 0, 0.0)
    assert keys == {str(key): ("Claude Code", 3, 0.00035)}
