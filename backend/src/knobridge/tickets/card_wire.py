"""The card format on the wire (docs/specs/cards.md, "Formato do card"): ``CardIn`` and its
parts, and the two items of a batch, ``CardUpsertItemIn`` and ``CardDeleteItemIn``.

The same conventions as the tickets (``wire.py``): unknown fields refused, texts stripped before
their length is checked and without NUL, instants normalized to UTC, strict validation from JSON.
The extra rules of a card are ``sprint_end_before_start``, ``link_url_required`` and
``invalid_sha``, located at the field they blame (``wire.problems``).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from pydantic_core import PydanticCustomError

from knobridge.ingestion.source_config import CardStatus, CardType
from knobridge.tickets.wire import (
    AttachmentName,
    Body,
    CustomFields,
    CustomValue,
    Email,
    ExternalId,
    Instant,
    Name200,
    Number,
    Tag,
    Tags,
    Text50,
    Text100,
    Text200,
    TicketBodyFormat,
    TicketDeleteItemIn,
    Title,
    Url,
    WireIn,
)

_SHA = re.compile(r"^[0-9A-Fa-f]{7,64}$")


class CardLinkKind(StrEnum):
    CARD = "card"
    TICKET = "ticket"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    URL = "url"


class CardPersonIn(WireIn):
    name: Text200 | None = None
    email: Email | None = None


class CardDescriptionIn(WireIn):
    body: Body
    body_format: TicketBodyFormat = TicketBodyFormat.TEXT


class CardSprintIn(WireIn):
    name: Name200
    start_at: Instant | None = None
    end_at: Instant | None = None

    @model_validator(mode="after")
    def _ends_after_start(self) -> Self:
        if self.start_at is not None and self.end_at is not None and self.end_at < self.start_at:
            raise PydanticCustomError("sprint_end_before_start", "end_at is before start_at.")
        return self


class CardLinkIn(WireIn):
    kind: CardLinkKind
    target: Name200
    relation: Text100 | None = None
    url: Url | None = None

    @model_validator(mode="after")
    def _kind_rules(self) -> Self:
        if self.kind is CardLinkKind.URL and self.url is None:
            raise PydanticCustomError("link_url_required", "A url link needs its url.")
        if self.kind is CardLinkKind.COMMIT and not _SHA.fullmatch(self.target):
            raise PydanticCustomError("invalid_sha", "A commit is 7 to 64 hex characters.")
        return self


class CardCommentIn(WireIn):
    id: Text200 | None = None
    author_name: Text200 | None = None
    body: Body
    body_format: TicketBodyFormat = TicketBodyFormat.TEXT
    created_at: Instant


class CardAttachmentIn(WireIn):
    name: AttachmentName


class CardIn(WireIn):
    """A card of the development tool of origin (docs/specs/cards.md, "Formato do card")."""

    external_id: ExternalId
    number: Number | None = None
    title: Title
    type: CardType
    status: CardStatus
    original_status: Text100 | None = None
    original_type: Text100 | None = None
    priority: Text50 | None = None
    product: Text200 | None = None
    tags: Tags = Field(default_factory=list[Tag])
    url: Url | None = None
    description: CardDescriptionIn | None = None
    acceptance_criteria: CardDescriptionIn | None = None
    sprint: CardSprintIn | None = None
    release: Text100 | None = None
    parent_external_id: ExternalId | None = None
    links: Annotated[list[CardLinkIn], Field(max_length=100)] = Field(
        default_factory=list[CardLinkIn]
    )
    reporter: CardPersonIn | None = None
    assignees: Annotated[list[CardPersonIn], Field(max_length=20)] = Field(
        default_factory=list[CardPersonIn]
    )
    comments: Annotated[list[CardCommentIn], Field(max_length=500)] = Field(
        default_factory=list[CardCommentIn]
    )
    attachments: Annotated[list[CardAttachmentIn], Field(max_length=100)] = Field(
        default_factory=list[CardAttachmentIn]
    )
    custom_fields: CustomFields = Field(default_factory=dict[str, CustomValue])
    created_at: Instant
    updated_at: Instant
    done_at: Instant | None = None

    @model_validator(mode="after")
    def _updated_after_created(self) -> Self:
        if self.updated_at < self.created_at:
            raise PydanticCustomError(
                "updated_at_before_created_at", "updated_at is before created_at."
            )
        return self

    @property
    def display_number(self) -> str:
        """What the citation shows: ``number``, or the ``external_id`` without one."""
        return self.number or self.external_id

    @property
    def reference_date(self) -> tuple[datetime, str]:
        """The date a citation shows and which one it is (``done`` or ``updated``)."""
        if self.done_at is not None:
            return self.done_at, "done"
        return self.updated_at, "updated"


class CardUpsertItemIn(WireIn):
    op: Literal["upsert"]
    card: CardIn


class CardDeleteItemIn(TicketDeleteItemIn):
    """The removal of a card: the same fields as a ticket's, under the card's schema name."""
