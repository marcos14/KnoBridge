"""Tickets from the panel (docs/specs/chamados.md, "Upload no painel" and "Prévia do chamado"):
``POST /v1/workspaces/{workspace_id}/sources/{source_id}/tickets/upload`` and ``.../preview``.

Session routes, editor or above, with CSRF. The upload takes ``multipart/form-data`` with one
``file`` (``.json`` or ``.jsonl``) and parses it here, not through FastAPI's form handling, so the
50 MiB limit is enforced while the body streams in (a declared ``Content-Length`` above it is
refused before reading); the file is spooled by the multipart parser (memory up to 1 MiB, then a
temporary file) and read back in blocks by ``tickets/upload.py``. The answer comes after every
block is committed, with the sync of the source already asked for (trigger ``ingest``). The
preview renders one ticket with the source's settings and writes nothing; its body is capped by
the body limit middleware (``body_limit.py``). The cards' routes (``card_uploads.py``) reuse
``handle_upload`` and the schemas of the answers.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Literal, cast

from anyio import to_thread
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, PlainValidator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from knobridge.api.body_limit import KIB, MIB, PayloadTooLargeError
from knobridge.api.deps import (
    ClientIpDep,
    ClockDep,
    SessionFactoryDep,
    SyncStarterDep,
    WorkspaceContext,
    require_role,
)
from knobridge.api.ingest import TicketIngestCounts
from knobridge.core.clock import Clock
from knobridge.core.errors import ValidationError
from knobridge.core.logging import get_logger
from knobridge.ingestion.source_config import (
    SourceKind,
    TicketsSourceConfig,
    parse_source_config,
)
from knobridge.ingestion.sync import SyncStarter
from knobridge.security.csrf import require_csrf
from knobridge.tenancy.models import Role
from knobridge.tickets.ingest import ItemStatus
from knobridge.tickets.ingest_sync import SyncOutcome, request_ingest_sync
from knobridge.tickets.push import TICKETS, PushKind
from knobridge.tickets.upload import (
    UploadReport,
    audit_upload,
    preview_ticket,
    require_active,
    tickets_source,
    upload_tickets,
)
from knobridge.tickets.upload_files import (
    UploadEmptyError,
    count_json_elements,
    json_elements,
    jsonl_elements,
    upload_format,
)
from knobridge.tickets.wire import TicketIn

UPLOAD_MAX_BYTES = 50 * MIB
# Room for the multipart envelope around the file (boundary lines and part headers).
ENVELOPE_BYTES = 64 * KIB
_MAX_FIELDS = 10

EditorContext = Annotated[WorkspaceContext, Depends(require_role(Role.EDITOR))]

_log = get_logger(__name__)


def _too_large() -> PayloadTooLargeError:
    return PayloadTooLargeError(
        "The file is above 50 MiB.", details={"max_bytes": UPLOAD_MAX_BYTES}
    )


def _invalid_upload(problem: str) -> ValidationError:
    return ValidationError(
        "Send multipart/form-data with one file field.",
        details=[{"loc": ["body", "file"], "problem": problem}],
    )


async def _limited(request: Request, limit: int) -> AsyncGenerator[bytes]:
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise _too_large()
        yield chunk


async def _read_form(request: Request) -> FormData:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise _invalid_upload("multipart_required")
    limit = UPLOAD_MAX_BYTES + ENVELOPE_BYTES
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise _too_large()
    parser = MultiPartParser(
        request.headers, _limited(request, limit), max_files=1, max_fields=_MAX_FIELDS
    )
    try:
        return await parser.parse()
    except MultiPartException as exc:
        raise _invalid_upload("multipart_invalid") from exc


def _file(form: FormData) -> UploadFile:
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise _invalid_upload("missing")
    if upload.size is not None and upload.size > UPLOAD_MAX_BYTES:
        raise _too_large()
    return upload


class TicketUploadError(BaseModel):
    line: int | None
    index: int | None
    external_id: str | None
    code: str
    message: str
    details: object | None


class TicketUploadOut(BaseModel):
    format: Literal["json", "jsonl"]
    total: int
    counts: TicketIngestCounts
    errors: list[TicketUploadError]
    errors_truncated: bool
    sync: Literal["started", "pending", "deferred", "none"]
    run_id: uuid.UUID | None


def _keep(value: object) -> object:
    return value


class TicketPreviewIn(BaseModel):
    """The ticket is validated like an upsert item (strict), so it arrives raw."""

    model_config = ConfigDict(extra="forbid")

    ticket: Annotated[object, PlainValidator(_keep, json_schema_input_type=TicketIn)]


class TicketPreviewMarker(BaseModel):
    marker: str
    count: int


class TicketPreviewOut(BaseModel):
    title: str
    markdown: str
    markers: list[TicketPreviewMarker]
    anonymize: bool
    include_internal_notes: bool


UPLOAD_BODY: dict[str, object] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "title": "TicketUploadIn",
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "A .json (list or {items}) or .jsonl file, up to "
                            "50 MiB.",
                        }
                    },
                }
            }
        },
    }
}


def session_errors(kind: SourceKind) -> dict[int | str, dict[str, object]]:
    """The errors of a session route on a source of ``kind``."""
    return {
        401: {"description": "No live session (standard error shape)."},
        403: {
            "description": "Role below editor (`forbidden`), workspace suspended or CSRF "
            "failure (`csrf_failed`)."
        },
        404: {
            "description": f"Workspace not found or caller not a member, or not a `{kind.value}` "
            "source of the workspace (`source_not_found`)."
        },
    }


_SESSION_ERRORS = session_errors(SourceKind.TICKETS)
UPLOAD_ERRORS: dict[int | str, dict[str, object]] = {
    409: {"description": "Source deactivated (`source_inactive`)."},
    413: {"description": "File above 50 MiB (`payload_too_large`, `details.max_bytes`)."},
    422: {
        "description": "Not a .json/.jsonl file (`upload_format_unsupported`), malformed "
        "JSON (`upload_invalid_json`), empty file (`upload_empty`) or no file field "
        "(`validation_error`)."
    },
}


def _upload_out(
    report: UploadReport, sync: SyncOutcome, run_id: uuid.UUID | None
) -> TicketUploadOut:
    return TicketUploadOut(
        format=report.format,
        total=report.total,
        counts=TicketIngestCounts(**{s.value: total for s, total in report.counts.items()}),
        errors=[
            TicketUploadError(
                line=error.line,
                index=error.index,
                external_id=error.external_id,
                code=error.code,
                message=error.message,
                details=error.details,
            )
            for error in report.errors
        ],
        errors_truncated=report.errors_truncated,
        sync=sync,
        run_id=run_id,
    )


router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


@router.post(
    "/{source_id}/tickets/upload",
    dependencies=[Depends(require_csrf)],
    openapi_extra=UPLOAD_BODY,
    responses={**_SESSION_ERRORS, **UPLOAD_ERRORS},
)
async def upload_ticket_file(
    source_id: uuid.UUID,
    request: Request,
    context: EditorContext,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> TicketUploadOut:
    """Validate and write every ticket or removal of the file (the rules of the API, in blocks
    of 100), then ask for the sync of the source; the counts and the rejected items."""
    return await handle_upload(
        source_id, request, context, factory, starter, clock, ip, kind=TICKETS
    )


async def handle_upload(
    source_id: uuid.UUID,
    request: Request,
    context: WorkspaceContext,
    factory: async_sessionmaker[AsyncSession],
    starter: SyncStarter,
    clock: Clock,
    ip: str | None,
    *,
    kind: PushKind,
) -> TicketUploadOut:
    """The upload of a file of tickets or cards into the source of ``kind``."""
    workspace_id = context.workspace_id
    source = require_active(
        await tickets_source(
            context.db, workspace_id=workspace_id, source_id=source_id, kind=kind.source_kind
        )
    )
    form = await _read_form(request)
    try:
        upload = _file(form)
        file_format = upload_format(upload.filename)
        if file_format == "json":
            if not await to_thread.run_sync(count_json_elements, upload.file):
                raise UploadEmptyError("The file has no items.")
            elements = json_elements(upload.file)
        else:
            elements = jsonl_elements(upload.file)
        report = await upload_tickets(
            factory,
            workspace_id=workspace_id,
            user_id=context.current.user.id,
            source_id=source_id,
            file_format=file_format,
            elements=elements,
            now=clock.now(),
            kind=kind,
        )
    finally:
        await form.close()
    if not report.total:
        raise UploadEmptyError("The file has no items.")
    sync: SyncOutcome = "none"
    run_id: uuid.UUID | None = None
    if report.counts[ItemStatus.QUEUED]:
        sync, run_id = await request_ingest_sync(
            factory, starter, clock, workspace_id=workspace_id, source_id=source_id
        )
    await audit_upload(
        context.db,
        clock,
        source=source,
        actor_id=context.current.user.id,
        filename=upload.filename or "",
        report=report,
        ip=ip,
        kind=kind,
    )
    _log.info(
        f"{kind.source_kind.value}_uploaded",
        workspace_id=str(workspace_id),
        source_id=str(source_id),
        run_id=None if run_id is None else str(run_id),
        sync=sync,
        total=report.total,
        **{status.value: total for status, total in report.counts.items()},
    )
    return _upload_out(report, sync, run_id)


@router.post(
    "/{source_id}/tickets/preview",
    dependencies=[Depends(require_csrf)],
    responses={
        **_SESSION_ERRORS,
        413: {"description": "Body above 2 MiB (`payload_too_large`)."},
        422: {
            "description": "Ticket outside the format (`validation_error` with `{loc, problem}`"
            " relative to the ticket) or above 1 MiB (`ticket_too_large`)."
        },
    },
)
async def preview_ticket_markdown(
    source_id: uuid.UUID, body: TicketPreviewIn, context: EditorContext
) -> TicketPreviewOut:
    """The Markdown the index would get for this ticket, anonymized with the source's settings;
    nothing is written."""
    source = await tickets_source(
        context.db, workspace_id=context.workspace_id, source_id=source_id
    )
    config = cast("TicketsSourceConfig", parse_source_config(SourceKind.TICKETS, source.config))
    preview = preview_ticket(body.ticket, config)
    return TicketPreviewOut(
        title=preview.title,
        markdown=preview.markdown,
        markers=[TicketPreviewMarker(marker=m, count=n) for m, n in preview.markers.items()],
        anonymize=preview.anonymize,
        include_internal_notes=preview.include_internal_notes,
    )
