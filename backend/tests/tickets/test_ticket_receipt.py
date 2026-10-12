"""Pure parts of the ticket delivery: the 2xx answer read into ``ticket_id`` and ``url``, and
the start after the commit that tolerates Temporal down."""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from datetime import timedelta

import pytest

from fakes.ticket_webhook_starter import FakeTicketWebhookStarter
from knobridge.core.logging import configure_logging
from knobridge.core.settings import Settings
from knobridge.tickets.delivery import DELIVERY_WINDOW, parse_receipt, start_delivery


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            b'{"ticket_id": "48213", "url": "https://s.example.com/48213"}',
            ("48213", "https://s.example.com/48213"),
        ),
        (b'{"ticket_id": 48213}', ("48213", None)),
        (b'{"ticket_id": 4.5, "url": "HTTP://s.example.com"}', ("4.5", "HTTP://s.example.com")),
        (b'{"ticket_id": "  ", "url": "ftp://s.example.com"}', (None, None)),
        (b'{"ticket_id": true, "url": 7}', (None, None)),
        (
            json.dumps({"ticket_id": "x" * 201, "url": "https://e.com/" + "a" * 2000}).encode(),
            (None, None),
        ),
        (b"[1, 2]", (None, None)),
        (b"", (None, None)),
        (b"accepted", (None, None)),
        (b"\xff\xfe", (None, None)),
    ],
)
def test_parse_receipt_keeps_only_valid_fields(
    body: bytes, expected: tuple[str | None, str | None]
) -> None:
    assert parse_receipt(body) == expected


def test_start_delivery_hands_the_request_to_the_starter() -> None:
    starter = FakeTicketWebhookStarter()
    workspace_id, request_id = uuid.uuid4(), uuid.uuid4()

    started = asyncio.run(start_delivery(starter, workspace_id=workspace_id, request_id=request_id))

    assert started is True
    assert [(s.workspace_id, s.request_id, s.remaining) for s in starter.started] == [
        (workspace_id, request_id, DELIVERY_WINDOW)
    ]
    assert timedelta(hours=24) == DELIVERY_WINDOW


def test_start_delivery_with_temporal_down_only_logs() -> None:
    stream = io.StringIO()
    configure_logging(Settings(env="test"), stream=stream)
    starter = FakeTicketWebhookStarter(unavailable=True)
    request_id = uuid.uuid4()

    started = asyncio.run(start_delivery(starter, workspace_id=uuid.uuid4(), request_id=request_id))

    logged = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert started is False
    assert [
        entry["request_id"] for entry in logged if entry["event"] == "ticket_request_deferred"
    ] == [str(request_id)]
