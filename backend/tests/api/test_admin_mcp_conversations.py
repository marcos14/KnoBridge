"""The administrative view with the ``mcp`` channel (``docs/specs/chat.md``, "Visão
administrativa"): the conversation of ``ask`` filtered by channel, with the key instead of the
user, its detail, and the key filter matching the key's ``api`` and ``mcp`` conversations."""

from __future__ import annotations

import pytest
from api_key_support import start_public_id
from api_support import ApiEnv
from mcp_chat_support import ask_args, ask_world
from mcp_support import call_tools, structured, world_key

pytestmark = pytest.mark.integration


def test_admin_view_shows_the_mcp_conversation_of_the_key(api: ApiEnv) -> None:
    world = ask_world(api)
    key = world_key(api, world.mcp)
    through_api = start_public_id(api, key, world.empty_product)
    through_mcp = str(structured(call_tools(api, key, ask_args("Vazio"))[0])["conversation_id"])
    path = f"/v1/workspaces/{world.workspace_id}/admin/conversations"

    by_channel = api.client.get(path, params={"channel": "mcp"})
    detail = api.client.get(f"{path}/{through_mcp}")

    assert by_channel.status_code == 200, by_channel.text
    (item,) = by_channel.json()["items"]
    assert (item["id"], item["channel"], item["user_id"]) == (through_mcp, "mcp", None)
    assert item["api_key_name"] is not None
    assert (detail.status_code, detail.json()["channel"]) == (200, "mcp")
    by_key = api.client.get(path, params={"api_key_id": item["api_key_id"]})
    assert {row["id"] for row in by_key.json()["items"]} == {through_api, through_mcp}
