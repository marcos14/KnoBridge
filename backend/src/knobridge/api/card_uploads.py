"""Cards from the panel (docs/specs/cards.md, "Rotas"):
``POST /v1/workspaces/{workspace_id}/sources/{source_id}/cards/upload`` and ``.../preview``.

The same routes as the tickets' (``ticket_uploads.py``), on a ``cards`` source: the upload goes
through ``handle_upload`` (50 MiB read while streaming, blocks of 100, sync asked for, audited
as ``source.cards_uploaded``) and answers ``TicketUploadOut``; the preview renders one card with
the source's settings and writes nothing (its body is capped at 2 MiB by ``body_limit.py``). A
source that is not a ``cards`` source of the workspace is 404 ``source_not_found``.
"""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, PlainValidator

from knobridge.api.deps import ClientIpDep, ClockDep, SessionFactoryDep, SyncStarterDep
from knobridge.api.ticket_uploads import (
    UPLOAD_BODY,
    UPLOAD_ERRORS,
    EditorContext,
    TicketPreviewMarker,
    TicketUploadOut,
    handle_upload,
    session_errors,
)
from knobridge.ingestion.source_config import CardsSourceConfig, SourceKind, parse_source_config
from knobridge.security.csrf import require_csrf
from knobridge.tickets.card_wire import CardIn
from knobridge.tickets.push import CARDS
from knobridge.tickets.upload import preview_card, tickets_source

_SESSION_ERRORS = session_errors(SourceKind.CARDS)


def _keep(value: object) -> object:
    return value


class CardPreviewIn(BaseModel):
    """The card is validated like an upsert item (strict), so it arrives raw."""

    model_config = ConfigDict(extra="forbid")

    card: Annotated[object, PlainValidator(_keep, json_schema_input_type=CardIn)]


class CardPreviewOut(BaseModel):
    title: str
    markdown: str
    markers: list[TicketPreviewMarker]
    anonymize: bool
    include_comments: bool


router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


@router.post(
    "/{source_id}/cards/upload",
    dependencies=[Depends(require_csrf)],
    openapi_extra=UPLOAD_BODY,
    responses={**_SESSION_ERRORS, **UPLOAD_ERRORS},
)
async def upload_card_file(
    source_id: uuid.UUID,
    request: Request,
    context: EditorContext,
    factory: SessionFactoryDep,
    starter: SyncStarterDep,
    clock: ClockDep,
    ip: ClientIpDep,
) -> TicketUploadOut:
    """Validate and write every card or removal of the file (the rules of the API, in blocks
    of 100), then ask for the sync of the source; the counts and the rejected items."""
    return await handle_upload(source_id, request, context, factory, starter, clock, ip, kind=CARDS)


@router.post(
    "/{source_id}/cards/preview",
    dependencies=[Depends(require_csrf)],
    responses={
        **_SESSION_ERRORS,
        413: {"description": "Body above 2 MiB (`payload_too_large`)."},
        422: {
            "description": "Card outside the format (`validation_error` with `{loc, problem}`"
            " relative to the card) or above 1 MiB (`card_too_large`)."
        },
    },
)
async def preview_card_markdown(
    source_id: uuid.UUID, body: CardPreviewIn, context: EditorContext
) -> CardPreviewOut:
    """The Markdown the index would get for this card, anonymized with the source's settings;
    nothing is written."""
    source = await tickets_source(
        context.db, workspace_id=context.workspace_id, source_id=source_id, kind=SourceKind.CARDS
    )
    config = cast("CardsSourceConfig", parse_source_config(SourceKind.CARDS, source.config))
    preview = preview_card(body.card, config)
    return CardPreviewOut(
        title=preview.title,
        markdown=preview.markdown,
        markers=[TicketPreviewMarker(marker=m, count=n) for m, n in preview.markers.items()],
        anonymize=preview.anonymize,
        include_comments=preview.include_comments,
    )
