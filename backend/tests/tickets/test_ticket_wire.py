"""The ticket format: the examples of the spec, the extra rules and the canonical payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from knobridge.tickets.wire import (
    MAX_PROBLEMS,
    TicketDeleteItemIn,
    TicketIn,
    canonical_ticket,
    problems,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tickets"


def valid_ticket(**fields: Any) -> dict[str, Any]:  # noqa: ANN401 - JSON test payload
    ticket: dict[str, Any] = json.loads((FIXTURES / "valid_ticket.json").read_text("utf-8"))
    ticket.update(fields)
    return ticket


def minimal(**fields: Any) -> dict[str, Any]:  # noqa: ANN401 - JSON test payload
    ticket: dict[str, Any] = {
        "external_id": "A-1",
        "title": "Erro",
        "status": "open",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    }
    ticket.update(fields)
    return ticket


def validate(ticket: dict[str, Any]) -> TicketIn:
    return TicketIn.model_validate_json(json.dumps(ticket), strict=True)


def found(ticket: dict[str, Any]) -> list[dict[str, Any]]:
    with pytest.raises(ValidationError) as caught:
        validate(ticket)
    return problems(caught.value)  # type: ignore[return-value]


def test_ticket_wire_accepts_spec_example() -> None:
    ticket = validate(valid_ticket())

    assert ticket.external_id == "4f6c2a10-0001"
    assert ticket.messages[1].public is False
    assert ticket.custom_fields == {"versao_sistema": "12.4.1", "loja": 3}


def test_ticket_wire_canonical_payload_fills_defaults_and_uses_utc() -> None:
    payload, _ = canonical_ticket(validate(minimal(created_at="2026-10-01T07:00:00-03:00")))

    assert payload["created_at"] == "2026-10-01T10:00:00Z"
    assert payload["tags"] == []
    assert payload["custom_fields"] == {}
    assert payload["requester"] is None


def test_ticket_wire_hash_ignores_offset_and_key_order() -> None:
    first = minimal(updated_at="2026-10-01T10:00:00Z", title="  Erro  ")
    second = dict(reversed(list(minimal(updated_at="2026-10-01T07:00:00-03:00").items())))

    assert canonical_ticket(validate(first))[1] == canonical_ticket(validate(second))[1]


def test_ticket_wire_hash_changes_with_content() -> None:
    assert (
        canonical_ticket(validate(minimal()))[1]
        != canonical_ticket(validate(minimal(title="Outro")))[1]
    )


def test_ticket_wire_reports_spec_invalid_example() -> None:
    ticket = json.loads((FIXTURES / "invalid_ticket.json").read_text("utf-8"))

    assert found(ticket) == [
        {"loc": ["title"], "problem": "string_too_short"},
        {"loc": ["status"], "problem": "enum"},
        {"loc": ["created_at"], "problem": "timezone_aware"},
        {"loc": ["requester", "phone"], "problem": "extra_forbidden"},
        {"loc": ["messages", 0, "created_at"], "problem": "missing"},
    ]


def test_ticket_wire_refuses_updated_before_created() -> None:
    ticket = minimal(created_at="2026-10-02T10:00:00Z")

    assert found(ticket) == [{"loc": ["updated_at"], "problem": "updated_at_before_created_at"}]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"title": "   "}, {"loc": ["title"], "problem": "string_too_short"}),
        ({"title": "a\x00b"}, {"loc": ["title"], "problem": "string_contains_nul"}),
        ({"url": "ftp://x.example.com"}, {"loc": ["url"], "problem": "invalid_url"}),
        ({"url": "https://"}, {"loc": ["url"], "problem": "invalid_url"}),
        (
            {"requester": {"email": "sem-arroba"}},
            {"loc": ["requester", "email"], "problem": "invalid_email"},
        ),
        ({"tags": ["a", " a "]}, {"loc": ["tags"], "problem": "not_unique"}),
        (
            {
                "messages": [
                    {
                        "role": "agent",
                        "body": "x",
                        "public": "true",
                        "created_at": "2026-10-01T10:00:00Z",
                    }
                ]
            },
            {"loc": ["messages", 0, "public"], "problem": "bool_type"},
        ),
        (
            {"custom_fields": {"bad key": 1}},
            {"loc": ["custom_fields"], "problem": "custom_field_key"},
        ),
        (
            {"custom_fields": {"k": [1]}},
            {"loc": ["custom_fields", "k"], "problem": "custom_field_type"},
        ),
        (
            {"custom_fields": {"k": "x" * 1001}},
            {"loc": ["custom_fields", "k"], "problem": "string_too_long"},
        ),
        (
            {"custom_fields": {"k": "a\x00"}},
            {"loc": ["custom_fields", "k"], "problem": "string_contains_nul"},
        ),
        ({"external_id": "a\nb"}, {"loc": ["external_id"], "problem": "string_pattern_mismatch"}),
        ({"number": ""}, {"loc": ["number"], "problem": "string_too_short"}),
    ],
)
def test_ticket_wire_extra_rules(fields: dict[str, Any], expected: dict[str, Any]) -> None:
    assert found(minimal(**fields)) == [expected]


def test_ticket_wire_custom_field_values_keep_their_types() -> None:
    ticket = validate(minimal(custom_fields={"s": " x ", "i": 3, "f": 1.5, "b": True, "n": None}))

    assert ticket.custom_fields == {"s": "x", "i": 3, "f": 1.5, "b": True, "n": None}


def test_ticket_wire_custom_field_refuses_infinite_number() -> None:
    with pytest.raises(ValidationError) as caught:
        TicketIn.model_validate(minimal(custom_fields={"k": float("inf")}))

    assert problems(caught.value)[0]["problem"] == "finite_number"


def test_ticket_wire_problems_are_capped() -> None:
    ticket = minimal(tags=[""] * 50, attachments=[{"name": ""}] * 30)

    assert len(found(ticket)) == MAX_PROBLEMS


def test_ticket_wire_delete_item_defaults_deleted_at() -> None:
    item = TicketDeleteItemIn.model_validate_json('{"op": "delete", "external_id": " A-1 "}')

    assert (item.external_id, item.deleted_at) == ("A-1", None)
