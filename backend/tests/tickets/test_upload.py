"""The pure parts of the upload and the preview: elements as items, blocks validated with
duplicates across the whole file, the report and the preview of one ticket. The writes are
covered by ``tests/api/test_ticket_upload.py``."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from ticket_payload_support import SPEC_EXAMPLE, SPEC_MARKDOWN, minimal

from knobridge.core.errors import ValidationError
from knobridge.ingestion.source_config import TicketsSourceConfig
from knobridge.tickets import upload
from knobridge.tickets.ingest import (
    ItemError,
    ItemResult,
    ItemStatus,
    UpsertItem,
    check_indexed_items,
)
from knobridge.tickets.upload import UploadReport, as_item, check_block, preview_ticket
from knobridge.tickets.upload_files import INVALID_LINE
from knobridge.tickets.wire import MAX_TICKET_BYTES


def _numbered(*elements: object, start: int = 0) -> Iterator[tuple[int, object]]:
    return iter(enumerate(elements, start=start))


def test_as_item_reads_a_pure_ticket_as_upsert() -> None:
    assert as_item(0, minimal()) == {"op": "upsert", "ticket": minimal()}


def test_as_item_keeps_api_items() -> None:
    item = {"op": "delete", "external_id": "T-1"}

    assert as_item(3, item) is item


def test_as_item_invalid_line() -> None:
    result = as_item(7, INVALID_LINE)

    assert result == ItemResult(
        7,
        "upsert",
        None,
        ItemStatus.REJECTED,
        ItemError("invalid_json", "The line is not valid JSON.", None),
    )


def test_as_item_refuses_what_is_not_an_object() -> None:
    result = as_item(2, [1, 2])

    assert isinstance(result, ItemResult)
    assert result.error is not None
    assert (result.error.code, result.error.details) == (
        "validation_error",
        [{"loc": [], "problem": "model_type"}],
    )


def test_as_item_refuses_unknown_op() -> None:
    result = as_item(1, {"op": "merge", "external_id": "T-9"})

    assert isinstance(result, ItemResult)
    assert result.external_id == "T-9"
    assert result.error is not None
    assert result.error.details == [{"loc": ["op"], "problem": "literal_error"}]


def test_check_indexed_items_keeps_duplicates_across_calls() -> None:
    first_index: dict[str, int] = {}
    [first] = check_indexed_items([(10, {"op": "upsert", "ticket": minimal()})], first_index)
    [second] = check_indexed_items([(25, {"op": "delete", "external_id": "T-1"})], first_index)

    assert isinstance(first, UpsertItem)
    assert first.index == 10
    assert isinstance(second, ItemResult)
    assert second.error is not None
    assert (second.index, second.error.code, second.error.details) == (
        25,
        "duplicate_in_batch",
        {"first_index": 10},
    )


def test_check_block_takes_blocks_in_file_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upload, "BATCH_SIZE", 3)
    elements = _numbered(
        minimal(external_id="A"),
        INVALID_LINE,
        minimal(external_id="B"),
        minimal(external_id="A"),
        start=1,
    )
    first_index: dict[str, int] = {}

    block = check_block(elements, first_index)
    rest = check_block(elements, first_index)
    end = check_block(elements, first_index)

    assert [item.index for item in block] == [1, 2, 3]
    assert [type(item) for item in block] == [UpsertItem, ItemResult, UpsertItem]
    [duplicate] = rest
    assert isinstance(duplicate, ItemResult)
    assert duplicate.error is not None
    assert duplicate.error.details == {"first_index": 1}
    assert end == []


def _rejected(index: int) -> ItemResult:
    error = ItemError("validation_error", "bad", [{"loc": ["title"], "problem": "missing"}])
    return ItemResult(index, "upsert", f"T-{index}", ItemStatus.REJECTED, error)


def test_upload_report_jsonl_errors_by_line() -> None:
    report = UploadReport("jsonl")

    report.add(ItemResult(1, "upsert", "T-1", ItemStatus.QUEUED))
    report.add(_rejected(3))

    assert report.total == 2
    assert report.counts == {
        ItemStatus.QUEUED: 1,
        ItemStatus.UNCHANGED: 0,
        ItemStatus.STALE: 0,
        ItemStatus.REJECTED: 1,
    }
    [error] = report.errors
    assert (error.line, error.index, error.external_id, error.code) == (
        3,
        None,
        "T-3",
        "validation_error",
    )
    assert error.details == [{"loc": ["title"], "problem": "missing"}]
    assert not report.errors_truncated


def test_upload_report_json_errors_by_index_and_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload, "MAX_ERRORS", 2)
    report = UploadReport("json")

    for index in range(3):
        report.add(_rejected(index))

    assert [(e.line, e.index) for e in report.errors] == [(None, 0), (None, 1)]
    assert report.errors_truncated
    assert report.counts[ItemStatus.REJECTED] == 3


def test_preview_ticket_renders_with_markers() -> None:
    preview = preview_ticket(SPEC_EXAMPLE, TicketsSourceConfig())

    assert preview.markdown == SPEC_MARKDOWN
    assert preview.title == "Erro 4021 ao fechar o caixa"
    assert preview.markers == {"[TELEFONE]": 1, "[ATENDENTE_1]": 1, "[SOLICITANTE]": 1}
    assert (preview.anonymize, preview.include_internal_notes) == (True, False)


def test_preview_ticket_without_anonymization_has_no_markers() -> None:
    config = TicketsSourceConfig(anonymize=False, include_internal_notes=True)

    preview = preview_ticket(SPEC_EXAMPLE, config)

    assert preview.markers == {}
    assert "(11) 98765-4321" in preview.markdown
    assert "sangria pendente no turno anterior" in preview.markdown
    assert (preview.anonymize, preview.include_internal_notes) == (False, True)


def test_preview_ticket_ignores_markers_written_in_the_ticket() -> None:
    ticket = minimal(
        messages=[
            {
                "role": "customer",
                "body": "Campos [EMAIL] e [CPF] vazios; escrevam para ana@exemplo.com.br",
                "created_at": "2026-10-01T10:00:00Z",
            }
        ]
    )

    preview = preview_ticket(ticket, TicketsSourceConfig())

    assert preview.markdown.count("[EMAIL]") == 2
    assert preview.markers == {"[EMAIL]": 1}


def test_preview_ticket_invalid_ticket_is_422_with_problems() -> None:
    with pytest.raises(ValidationError) as caught:
        preview_ticket(minimal(status="lost", title=""), TicketsSourceConfig())

    assert caught.value.code == "validation_error"
    assert caught.value.status_code == 422
    assert caught.value.details == [
        {"loc": ["title"], "problem": "string_too_short"},
        {"loc": ["status"], "problem": "enum"},
    ]


def test_preview_ticket_not_an_object() -> None:
    with pytest.raises(ValidationError) as caught:
        preview_ticket("ticket", TicketsSourceConfig())

    assert caught.value.details == [{"loc": ["ticket"], "problem": "model_type"}]


def test_preview_ticket_too_large() -> None:
    big = minimal(
        messages=[{"role": "customer", "body": "x" * 99_000, "created_at": "2026-10-01T10:00:00Z"}]
        * 11
    )

    with pytest.raises(ValidationError) as caught:
        preview_ticket(big, TicketsSourceConfig())

    assert caught.value.code == "ticket_too_large"
    assert caught.value.details == {"max_bytes": MAX_TICKET_BYTES}
