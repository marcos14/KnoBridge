"""Per-item validation of a batch (``check_items``): no database, no clock."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from knobridge.tickets.ingest import (
    DeleteItem,
    ItemResult,
    ItemStatus,
    UpsertItem,
    check_items,
    count,
)
from knobridge.tickets.wire import MAX_TICKET_BYTES


def ticket(external_id: str = "A-1", **fields: Any) -> dict[str, Any]:  # noqa: ANN401
    body: dict[str, Any] = {
        "external_id": external_id,
        "title": "Erro 4021",
        "status": "resolved",
        "created_at": "2026-10-01T10:00:00-03:00",
        "updated_at": "2026-10-01T11:00:00-03:00",
    }
    body.update(fields)
    return body


def upsert(**fields: Any) -> dict[str, Any]:  # noqa: ANN401
    return {"op": "upsert", "ticket": ticket(**fields)}


def rejected(item: object) -> ItemResult:
    assert isinstance(item, ItemResult)
    assert item.status is ItemStatus.REJECTED
    return item


def test_check_items_accepts_upsert_with_canonical_payload() -> None:
    [item] = check_items([upsert()])

    assert isinstance(item, UpsertItem)
    assert (item.index, item.external_id) == (0, "A-1")
    assert item.updated_at == datetime(2026, 10, 1, 14, 0, tzinfo=UTC)
    assert item.payload["updated_at"] == "2026-10-01T14:00:00Z"
    assert len(item.content_hash) == 64


def test_check_items_invalid_item_does_not_sink_batch() -> None:
    items = check_items([upsert(status="em andamento"), upsert(external_id="A-2")])

    error = rejected(items[0]).error
    assert error is not None
    assert (error.code, error.details) == (
        "validation_error",
        [{"loc": ["status"], "problem": "enum"}],
    )
    assert rejected(items[0]).external_id == "A-1"
    assert isinstance(items[1], UpsertItem)


def test_check_items_without_valid_external_id_reports_null() -> None:
    [item] = check_items([upsert(external_id="")])

    assert rejected(item).external_id is None


def test_check_items_ticket_too_large() -> None:
    [item] = check_items([upsert(title="x" * MAX_TICKET_BYTES)])

    error = rejected(item).error
    assert error is not None
    assert (error.code, error.details) == ("ticket_too_large", {"max_bytes": MAX_TICKET_BYTES})
    assert rejected(item).external_id == "A-1"


def test_check_items_duplicate_in_batch_points_at_first() -> None:
    items = check_items([upsert(), {"op": "delete", "external_id": "A-1"}])

    error = rejected(items[1]).error
    assert error is not None
    assert (error.code, error.details) == ("duplicate_in_batch", {"first_index": 0})
    assert rejected(items[1]).op == "delete"


def test_check_items_rejected_item_does_not_block_later_duplicate() -> None:
    items = check_items([upsert(title=""), upsert()])

    assert rejected(items[0]).external_id == "A-1"
    assert isinstance(items[1], UpsertItem)


def test_check_items_upsert_shape_problems() -> None:
    items = check_items(
        [
            {"op": "upsert"},
            {"op": "upsert", "ticket": "x"},
            {"op": "upsert", "ticket": ticket(), "extra": 1},
            {"op": "upsert", "ticket": ticket(title=""), "extra": 1},
        ]
    )

    details = [rejected(item).error.details for item in items]  # type: ignore[union-attr]
    assert details == [
        [{"loc": ["ticket"], "problem": "missing"}],
        [{"loc": ["ticket"], "problem": "model_type"}],
        [{"loc": ["extra"], "problem": "extra_forbidden"}],
        [
            {"loc": ["extra"], "problem": "extra_forbidden"},
            {"loc": ["title"], "problem": "string_too_short"},
        ],
    ]
    assert rejected(items[2]).external_id == "A-1"


def test_check_items_delete_with_and_without_date() -> None:
    items = check_items(
        [
            {"op": "delete", "external_id": "A-1", "deleted_at": "2026-10-02T05:00:00-03:00"},
            {"op": "delete", "external_id": "A-2"},
        ]
    )

    assert items == [
        DeleteItem(0, "A-1", datetime(2026, 10, 2, 8, 0, tzinfo=UTC)),
        DeleteItem(1, "A-2", None),
    ]


def test_check_items_invalid_delete() -> None:
    items = check_items(
        [
            {"op": "delete", "external_id": "A-1", "deleted_at": "2026-10-02 05:00:00"},
            {"op": "delete"},
        ]
    )

    assert rejected(items[0]).external_id == "A-1"
    assert rejected(items[0]).error.details == [  # type: ignore[union-attr]
        {"loc": ["deleted_at"], "problem": "timezone_aware"}
    ]
    assert rejected(items[1]).external_id is None


def test_count_totals_every_status() -> None:
    results = [
        ItemResult(0, "upsert", "A", ItemStatus.QUEUED),
        ItemResult(1, "upsert", "B", ItemStatus.QUEUED),
        ItemResult(2, "delete", "C", ItemStatus.STALE),
    ]

    assert count(results) == {
        ItemStatus.QUEUED: 2,
        ItemStatus.UNCHANGED: 0,
        ItemStatus.STALE: 1,
        ItemStatus.REJECTED: 0,
    }
