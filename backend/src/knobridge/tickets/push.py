"""The two kinds of record pushed into the inbox: tickets (docs/specs/chamados.md) and cards
(docs/specs/cards.md).

They share the token, the inbox, the ``updated_at`` rule, the upload and the internal connector;
what differs is named here: the source kind, the key of the record in an upsert item, its model,
the error of a record above 1 MiB and the audit action of an upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from knobridge.audit.actions import AuditAction
from knobridge.ingestion.source_config import SourceKind
from knobridge.tickets.card_wire import CardIn
from knobridge.tickets.wire import TicketIn


@dataclass(frozen=True, slots=True)
class PushKind:
    source_kind: SourceKind
    # The key of the record in an upsert item, and the noun of the error messages.
    item_key: Literal["ticket", "card"]
    model: type[TicketIn] | type[CardIn]
    too_large_code: str
    upload_action: AuditAction


TICKETS = PushKind(
    SourceKind.TICKETS, "ticket", TicketIn, "ticket_too_large", AuditAction.SOURCE_TICKETS_UPLOADED
)
CARDS = PushKind(
    SourceKind.CARDS, "card", CardIn, "card_too_large", AuditAction.SOURCE_CARDS_UPLOADED
)
