"""Cards through the same per-item validation (``check_items`` with ``CARDS``), the upload's
element reading and the preview: no database, no clock."""

from __future__ import annotations

import pytest
from card_payload_support import CARD_EXAMPLE, CARD_MARKDOWN, minimal_card

from knobridge.core.errors import ValidationError
from knobridge.ingestion.source_config import CardsSourceConfig
from knobridge.tickets.ingest import DeleteItem, ItemResult, ItemStatus, UpsertItem, check_items
from knobridge.tickets.push import CARDS
from knobridge.tickets.upload import as_item, check_block, preview_card
from knobridge.tickets.wire import MAX_TICKET_BYTES


def rejected(item: object) -> ItemResult:
    assert isinstance(item, ItemResult)
    assert item.status is ItemStatus.REJECTED
    return item


def test_card_upsert_is_accepted_under_the_card_key() -> None:
    [item] = check_items([{"op": "upsert", "card": minimal_card()}], CARDS)

    assert isinstance(item, UpsertItem)
    assert (item.external_id, item.payload["type"]) == ("C-1", "task")


def test_card_invalid_item_names_the_card_format() -> None:
    [item] = check_items([{"op": "upsert", "card": minimal_card(status="open")}], CARDS)

    error = rejected(item).error
    assert error is not None
    assert (error.code, error.message, error.details) == (
        "validation_error",
        "The item does not match the card format.",
        [{"loc": ["status"], "problem": "enum"}],
    )
    assert rejected(item).external_id == "C-1"


def test_card_item_with_ticket_key_is_rejected() -> None:
    [item] = check_items([{"op": "upsert", "ticket": minimal_card()}], CARDS)

    error = rejected(item).error
    assert error is not None
    assert error.details == [
        {"loc": ["ticket"], "problem": "extra_forbidden"},
        {"loc": ["card"], "problem": "missing"},
    ]


def test_card_above_one_mib_is_card_too_large() -> None:
    big = minimal_card(description={"body": "x" * 99_000})
    big["comments"] = [
        {"body": "y" * 99_000, "created_at": "2026-10-01T10:00:00Z"} for _ in range(11)
    ]

    [item] = check_items([{"op": "upsert", "card": big}], CARDS)

    error = rejected(item).error
    assert error is not None
    assert (error.code, error.message, error.details) == (
        "card_too_large",
        "The card is above 1 MiB.",
        {"max_bytes": MAX_TICKET_BYTES},
    )


def test_card_delete_items_and_their_errors() -> None:
    items = check_items(
        [{"op": "delete", "external_id": "C-9"}, {"op": "delete", "external_id": ""}], CARDS
    )

    assert isinstance(items[0], DeleteItem)
    error = rejected(items[1]).error
    assert error is not None
    assert error.message == "The item does not match the card format."


def test_as_item_reads_a_pure_card_as_upsert() -> None:
    assert as_item(0, minimal_card(), CARDS) == {"op": "upsert", "card": minimal_card()}


def test_as_item_refuses_what_is_not_a_card_object() -> None:
    error = rejected(as_item(2, [1], CARDS)).error

    assert error is not None
    assert error.message == "The item does not match the card format."


def test_check_block_validates_cards() -> None:
    elements = iter([(1, minimal_card()), (2, minimal_card(type="saga"))])

    first, second = check_block(elements, {}, CARDS)

    assert isinstance(first, UpsertItem)
    assert rejected(second).index == 2


def test_preview_card_renders_with_markers() -> None:
    preview = preview_card(CARD_EXAMPLE, CardsSourceConfig())

    assert preview.markdown == CARD_MARKDOWN
    assert preview.title == "Permitir nota fiscal de exportação"
    assert preview.markers == {"[RESPONSAVEL_1]": 1}
    assert (preview.anonymize, preview.include_comments) == (True, True)


def test_preview_card_without_anonymization_or_comments() -> None:
    config = CardsSourceConfig(anonymize=False, include_comments=False)

    preview = preview_card(CARD_EXAMPLE, config)

    assert preview.markers == {}
    assert "## Comentários" not in preview.markdown
    assert (preview.anonymize, preview.include_comments) == (False, False)


def test_preview_card_invalid_card_is_422() -> None:
    with pytest.raises(ValidationError) as caught:
        preview_card(minimal_card(title=""), CardsSourceConfig())

    assert caught.value.code == "validation_error"
    assert caught.value.details == [{"loc": ["title"], "problem": "string_too_short"}]
