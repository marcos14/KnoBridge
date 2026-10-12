"""The upload of a file of tickets from the panel and the preview of one ticket
(docs/specs/chamados.md, "Upload no painel" and "Prévia do chamado").

The upload reuses the rules of ``POST /v1/ingest/tickets``: each element becomes an item (a pure
ticket, without ``op``, is an upsert), is validated by ``check_indexed_items`` and written by
``apply_items``. Items go in blocks of ``BATCH_SIZE``, each in its own transaction scoped to the
workspace with the source held (``FOR KEY SHARE``), so a file of any size never sits in memory
nor in one long transaction; ``duplicate_in_batch`` still covers the whole file. Reading and
validating a block runs in a worker thread, off the event loop. Only rejected items are kept,
up to ``MAX_ERRORS``.

The preview validates one ticket like an upsert and renders its Markdown with the source's
settings, writing nothing.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from itertools import islice
from typing import cast

from anyio import to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.audit.actions import AuditAction
from knobridge.audit.models import JSONValue
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.db import scoped_session
from knobridge.core.errors import NotFoundError, ValidationError
from knobridge.ingestion.errors import SourceInactiveError
from knobridge.ingestion.models import Source
from knobridge.ingestion.source_config import SourceKind, TicketsSourceConfig
from knobridge.tickets.ingest import (
    CheckedItem,
    ItemError,
    ItemResult,
    ItemStatus,
    UpsertItem,
    apply_items,
    check_indexed_items,
    check_items,
    readable_id,
)
from knobridge.tickets.markdown import render_ticket
from knobridge.tickets.upload_files import INVALID_LINE, UploadFormat
from knobridge.tickets.wire import TicketIn

BATCH_SIZE = 100
MAX_ERRORS = 1000
FILENAME_MAX_LENGTH = 255
_MARKER = re.compile(
    r"\[(?:EMAIL|IP|CNPJ|CPF|CARTAO|TELEFONE|SOLICITANTE|ORGANIZACAO|ATENDENTE_\d+|CLIENTE_\d+)\]"
)


async def tickets_source(
    db: AsyncSession, *, workspace_id: uuid.UUID, source_id: uuid.UUID, lock: bool = False
) -> Source:
    """The ``tickets`` source of the workspace (held ``FOR KEY SHARE`` with ``lock``), or 404
    ``source_not_found``."""
    query = select(Source).where(
        Source.workspace_id == workspace_id,
        Source.id == source_id,
        Source.kind == SourceKind.TICKETS,
    )
    if lock:
        query = query.with_for_update(key_share=True)
    source = (await db.scalars(query)).one_or_none()
    if source is None:
        raise NotFoundError("Source not found.", code="source_not_found")
    return source


def require_active(source: Source) -> Source:
    if not source.active:
        raise SourceInactiveError("The source is inactive.")
    return source


def _rejected(index: int, external_id: str | None, problem: dict[str, JSONValue]) -> ItemResult:
    error = ItemError("validation_error", "The item does not match the ticket format.", [problem])
    return ItemResult(index, "upsert", external_id, ItemStatus.REJECTED, error)


def as_item(index: int, element: object) -> dict[str, object] | ItemResult:
    """The API item of an element of the file: an item with ``op``, or a pure ticket read as an
    upsert. Anything else is rejected on its own line."""
    if element is INVALID_LINE:
        error = ItemError("invalid_json", "The line is not valid JSON.", None)
        return ItemResult(index, "upsert", None, ItemStatus.REJECTED, error)
    if not isinstance(element, dict):
        return _rejected(index, None, {"loc": [], "problem": "model_type"})
    fields = cast("dict[str, object]", element)
    if "op" not in fields:
        return {"op": "upsert", "ticket": fields}
    if fields["op"] not in ("upsert", "delete"):
        external_id = readable_id(fields.get("external_id"))
        return _rejected(index, external_id, {"loc": ["op"], "problem": "literal_error"})
    return fields


def check_block(
    elements: Iterator[tuple[int, object]], first_index: dict[str, int]
) -> list[CheckedItem]:
    """The next block of up to ``BATCH_SIZE`` elements, validated (empty at the end)."""
    checked: list[CheckedItem] = []
    items: list[tuple[int, Mapping[str, object]]] = []
    for index, element in islice(elements, BATCH_SIZE):
        item = as_item(index, element)
        if isinstance(item, ItemResult):
            checked.append(item)
        else:
            items.append((index, item))
    checked.extend(check_indexed_items(items, first_index))
    # Back in file order, for the order of the errors.
    return sorted(checked, key=lambda item: item.index)


@dataclass(frozen=True)
class UploadError:
    line: int | None
    index: int | None
    external_id: str | None
    code: str
    message: str
    details: object


@dataclass
class UploadReport:
    format: UploadFormat
    total: int = 0
    counts: dict[ItemStatus, int] = field(default_factory=lambda: dict.fromkeys(ItemStatus, 0))
    errors: list[UploadError] = field(default_factory=list[UploadError])
    errors_truncated: bool = False

    def add(self, result: ItemResult) -> None:
        self.total += 1
        self.counts[result.status] += 1
        if result.error is None:
            return
        if len(self.errors) == MAX_ERRORS:
            self.errors_truncated = True
            return
        line, index = (result.index, None) if self.format == "jsonl" else (None, result.index)
        error = result.error
        self.errors.append(
            UploadError(line, index, result.external_id, error.code, error.message, error.details)
        )


async def upload_tickets(
    factory: async_sessionmaker[AsyncSession],
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source_id: uuid.UUID,
    file_format: UploadFormat,
    elements: Iterator[tuple[int, object]],
    now: datetime,
) -> UploadReport:
    """Validate and write every element, a block per transaction; the report of the file."""
    report = UploadReport(file_format)
    first_index: dict[str, int] = {}
    while checked := await to_thread.run_sync(check_block, elements, first_index):
        async with scoped_session(factory, workspace_id=workspace_id, user_id=user_id) as db:
            require_active(
                await tickets_source(db, workspace_id=workspace_id, source_id=source_id, lock=True)
            )
            results = await apply_items(
                db, workspace_id=workspace_id, source_id=source_id, items=checked, now=now
            )
        for result in results:
            report.add(result)
    return report


async def audit_upload(
    db: AsyncSession,
    clock: Clock,
    *,
    source: Source,
    actor_id: uuid.UUID,
    filename: str,
    report: UploadReport,
    ip: str | None,
) -> None:
    """``source.tickets_uploaded``: the file name and the counts, never the content."""
    await AuditService(clock).record(
        db,
        action=AuditAction.SOURCE_TICKETS_UPLOADED,
        workspace_id=source.workspace_id,
        actor_user_id=actor_id,
        target=AuditTarget("source", str(source.id)),
        metadata={
            "name": source.name,
            "filename": filename[:FILENAME_MAX_LENGTH],
            "format": report.format,
            "total": report.total,
            "counts": {status.value: total for status, total in report.counts.items()},
        },
        ip=ip,
    )


@dataclass(frozen=True)
class TicketPreview:
    title: str
    markdown: str
    # Marker → how many times the anonymization applied it, in order of first appearance.
    markers: dict[str, int]
    anonymize: bool
    include_internal_notes: bool


def preview_ticket(raw: object, config: TicketsSourceConfig) -> TicketPreview:
    """The Markdown of one ticket with the source's settings; an invalid ticket is 422 with the
    same ``code`` and ``details`` an upsert item would get."""
    [checked] = check_items([{"op": "upsert", "ticket": raw}])
    if isinstance(checked, ItemResult):
        error = cast("ItemError", checked.error)
        raise ValidationError(error.message, code=error.code, details=error.details)
    ticket = TicketIn.model_validate(cast("UpsertItem", checked).payload)
    notes = config.include_internal_notes
    document = render_ticket(ticket, anonymize=config.anonymize, include_internal_notes=notes)
    markers: dict[str, int] = {}
    if config.anonymize:
        # Markers already written in the ticket itself were not applied by the anonymization.
        plain = render_ticket(ticket, anonymize=False, include_internal_notes=notes)
        written = Counter(_MARKER.findall(plain.markdown))
        for marker, total in Counter(_MARKER.findall(document.markdown)).items():
            if total > written[marker]:
                markers[marker] = total - written[marker]
    return TicketPreview(document.title, document.markdown, markers, config.anonymize, notes)
