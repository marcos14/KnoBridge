"""The card format (docs/specs/cards.md, "Formato do card"): the example, defaults, the
canonical payload and the extra rules, located at the field they blame."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from card_payload_support import CARD_EXAMPLE, card, minimal_card
from pydantic import ValidationError

from knobridge.ingestion.source_config import CardStatus, CardType
from knobridge.tickets.card_wire import CardDeleteItemIn, CardIn, CardLinkKind, CardUpsertItemIn
from knobridge.tickets.wire import canonical_payload, problems, serialized


def _problems(payload: dict[str, object]) -> list[dict[str, object]]:
    with pytest.raises(ValidationError) as caught:
        CardIn.model_validate_json(serialized(payload), strict=True)
    return [dict(problem) for problem in problems(caught.value)]


def test_card_example_is_valid() -> None:
    validated = CardIn.model_validate_json(serialized(CARD_EXAMPLE), strict=True)

    assert (validated.type, validated.status) == (CardType.FEATURE, CardStatus.DONE)
    assert validated.links[1].kind is CardLinkKind.COMMIT
    assert validated.comments[0].created_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def test_card_defaults_fill_the_canonical_payload() -> None:
    payload, digest = canonical_payload(CardIn.model_validate(minimal_card()))

    assert payload["tags"] == []
    assert payload["links"] == []
    assert payload["comments"] == []
    assert payload["custom_fields"] == {}
    assert payload["sprint"] is None
    assert payload["created_at"] == "2026-10-01T10:00:00Z"
    assert len(digest) == 64


def test_card_hash_ignores_the_offset_of_instants() -> None:
    first = canonical_payload(CardIn.model_validate(minimal_card()))[1]
    second = canonical_payload(
        CardIn.model_validate(
            minimal_card(
                created_at="2026-10-01T07:00:00-03:00", updated_at="2026-10-01T07:00:00-03:00"
            )
        )
    )[1]

    assert first == second


def test_card_display_number_falls_back_to_external_id() -> None:
    assert card().display_number == "PROJ-123"
    assert card(minimal_card()).display_number == "C-1"


def test_card_reference_date_is_done_at_or_updated_at() -> None:
    assert card().reference_date == (datetime(2026, 9, 29, 17, 40, tzinfo=UTC), "done")
    assert card(minimal_card()).reference_date == (
        datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
        "updated",
    )


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"status": "doing"}, {"loc": ["status"], "problem": "enum"}),
        ({"type": "improvement"}, {"loc": ["type"], "problem": "enum"}),
        ({"title": "  "}, {"loc": ["title"], "problem": "string_too_short"}),
        ({"tags": ["a", "a"]}, {"loc": ["tags"], "problem": "not_unique"}),
        ({"url": "ftp://x.test/1"}, {"loc": ["url"], "problem": "invalid_url"}),
        ({"board": "x"}, {"loc": ["board"], "problem": "extra_forbidden"}),
        (
            {"updated_at": "2026-09-30T10:00:00Z"},
            {"loc": ["updated_at"], "problem": "updated_at_before_created_at"},
        ),
        (
            {
                "sprint": {
                    "name": "S1",
                    "start_at": "2026-10-02T00:00:00Z",
                    "end_at": "2026-10-01T00:00:00Z",
                }
            },
            {"loc": ["sprint", "end_at"], "problem": "sprint_end_before_start"},
        ),
        (
            {"links": [{"kind": "url", "target": "Design"}]},
            {"loc": ["links", 0, "url"], "problem": "link_url_required"},
        ),
        (
            {"links": [{"kind": "commit", "target": "zzz1234"}]},
            {"loc": ["links", 0, "target"], "problem": "invalid_sha"},
        ),
        (
            {"comments": [{"body": "x"}]},
            {"loc": ["comments", 0, "created_at"], "problem": "missing"},
        ),
        (
            {"reporter": {"email": "nao-e-email"}},
            {"loc": ["reporter", "email"], "problem": "invalid_email"},
        ),
    ],
)
def test_card_rules_are_located_at_the_blamed_field(
    fields: dict[str, object], expected: dict[str, object]
) -> None:
    assert _problems(minimal_card(**fields)) == [expected]


def test_card_link_rules_accept_valid_links() -> None:
    validated = card(
        minimal_card(
            links=[
                {"kind": "url", "target": "Design", "url": "https://x.test/d"},
                {"kind": "commit", "target": "ABCDEF1234"},
                {"kind": "card", "target": "PROJ-100", "relation": "bloqueia"},
            ],
            sprint={"name": "S1", "start_at": "2026-10-01T00:00:00Z"},
        )
    )

    assert [link.kind for link in validated.links] == [
        CardLinkKind.URL,
        CardLinkKind.COMMIT,
        CardLinkKind.CARD,
    ]


def test_card_item_schemas_carry_the_card_names() -> None:
    assert CardUpsertItemIn.model_json_schema()["properties"]["card"]["$ref"].endswith("/CardIn")
    assert CardDeleteItemIn.model_json_schema()["title"] == "CardDeleteItemIn"
