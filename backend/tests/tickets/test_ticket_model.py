"""``TicketIn`` as the renderer uses it: defaults, citation number and date, custom field types.

The validation problems of the wire format are covered by ``test_ticket_wire.py``."""

from __future__ import annotations

from datetime import UTC, datetime

from ticket_payload_support import message, minimal, ticket

from knobridge.ingestion.source_config import TicketStatus
from knobridge.tickets.wire import TicketBodyFormat, TicketMessageRole


def test_ticket_model_accepts_the_spec_example() -> None:
    parsed = ticket()

    assert parsed.status is TicketStatus.RESOLVED
    assert parsed.messages[1].public is False
    assert parsed.messages[2].body_format is TicketBodyFormat.HTML
    assert parsed.custom_fields == {"versao_sistema": "12.4.1", "loja": 3}
    assert parsed.display_number == "48213"
    assert parsed.reference_date == (datetime(2026, 10, 1, 12, 10, tzinfo=UTC), "resolved")


def test_ticket_model_fills_defaults_of_the_minimal_ticket() -> None:
    parsed = ticket(minimal(messages=[message("  oi  ")]))

    assert (parsed.tags, parsed.assignees, parsed.attachments, parsed.custom_fields) == (
        [],
        [],
        [],
        {},
    )
    assert parsed.messages[0].role is TicketMessageRole.CUSTOMER
    assert parsed.messages[0].public is True
    assert parsed.messages[0].body == "oi"
    assert parsed.display_number == "T-1"
    assert parsed.reference_date[1] == "updated"


def test_ticket_model_keeps_custom_field_types() -> None:
    fields = {"flag": True, "count": 2, "ratio": 1.5, "name": " x ", "none": None}

    parsed = ticket(minimal(custom_fields=fields))

    assert parsed.custom_fields == {
        "flag": True,
        "count": 2,
        "ratio": 1.5,
        "name": "x",
        "none": None,
    }
