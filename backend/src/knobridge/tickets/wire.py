"""The ticket format on the wire (docs/specs/chamados.md, "Formato do chamado"): ``TicketIn``
and its parts, and the two items of a batch, ``TicketUpsertItemIn`` and ``TicketDeleteItemIn``.

Requests refuse unknown fields. Texts are stripped before their length is checked, never hold
NUL, and lengths count code points. Instants need an offset and are normalized to UTC, so the
canonical JSON of a ticket (``canonical_payload``) and its ``content_hash`` do not depend on how
the origin wrote them. Schema names are the contract published in the OpenAPI. The card format
(``card_wire.py``) reuses these texts, the checks and ``problems``.

Items are validated from JSON in strict mode (``validate_json(..., strict=True)``): a boolean is
``true``/``false``, never ``"true"`` or ``1``. The problems of an invalid item are reported as
``{"loc", "problem"}`` (``problems``), ``problem`` being the Pydantic error type or one of the
extra rules of the spec (``updated_at_before_created_at``, ``invalid_url``...).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainValidator,
    StringConstraints,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticCustomError

from knobridge.audit.models import JSONValue
from knobridge.ingestion.source_config import TicketStatus
from knobridge.tickets.models import EXTERNAL_ID_MAX_LENGTH, URL_MAX_LENGTH

MAX_TICKET_BYTES = 1_048_576
MAX_PROBLEMS = 50
BODY_MAX_LENGTH = 100_000
CUSTOM_FIELDS_MAX = 50
CUSTOM_VALUE_MAX_LENGTH = 1000
_CUSTOM_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_UPDATED_BEFORE_CREATED = "updated_at_before_created_at"


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise PydanticCustomError("string_contains_nul", "Text must not contain NUL.")
    return value


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def _email(value: str) -> str:
    if not _EMAIL.fullmatch(value):
        raise PydanticCustomError("invalid_email", "Not an e-mail address.")
    return value


def _url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise PydanticCustomError("invalid_url", "The URL needs http(s) and a host.")
    return value


def _distinct(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise PydanticCustomError("not_unique", "Items must not repeat.")
    return value


def _custom_value(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PydanticCustomError("finite_number", "Number must be finite.")
        return value
    if isinstance(value, str):
        text = _no_nul(value.strip())
        if len(text) > CUSTOM_VALUE_MAX_LENGTH:
            raise PydanticCustomError("string_too_long", "Text is too long.")
        return text
    raise PydanticCustomError("custom_field_type", "Value must be text, number, boolean or null.")


def _custom_keys(value: dict[str, object]) -> dict[str, object]:
    if not all(_CUSTOM_KEY.fullmatch(key) for key in value):
        raise PydanticCustomError("custom_field_key", "Invalid custom field name.")
    return value


_NoNul = AfterValidator(_no_nul)


def _strip(min_length: int, max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


ExternalId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EXTERNAL_ID_MAX_LENGTH,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
Instant = Annotated[AwareDatetime, AfterValidator(_utc)]
# Texts: stripped, then measured; one alias per length range of the spec.
Text50 = Annotated[str, _strip(0, 50), _NoNul]
Text100 = Annotated[str, _strip(0, 100), _NoNul]
Text200 = Annotated[str, _strip(0, 200), _NoNul]
Name200 = Annotated[str, _strip(1, 200), _NoNul]
Number = Annotated[str, _strip(1, 50), _NoNul]
Title = Annotated[str, _strip(1, 500), _NoNul]
Tag = Annotated[str, _strip(1, 100), _NoNul]
AttachmentName = Annotated[str, _strip(1, 255), _NoNul]
Body = Annotated[str, _strip(1, BODY_MAX_LENGTH), _NoNul]
Email = Annotated[str, _strip(0, 320), _NoNul, AfterValidator(_email)]
Url = Annotated[str, _strip(0, URL_MAX_LENGTH), _NoNul, AfterValidator(_url)]
CustomValue = Annotated[
    str | int | float | bool | None,
    PlainValidator(_custom_value, json_schema_input_type=str | int | float | bool | None),
]
Tags = Annotated[list[Tag], Field(max_length=50), AfterValidator(_distinct)]
CustomFields = Annotated[
    dict[str, CustomValue], Field(max_length=CUSTOM_FIELDS_MAX), AfterValidator(_custom_keys)
]


class TicketBodyFormat(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    HTML = "html"


class TicketMessageRole(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class WireIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class TicketPersonIn(WireIn):
    name: Text200 | None = None
    email: Email | None = None


class TicketRequesterIn(TicketPersonIn):
    organization: Text200 | None = None


class TicketMessageIn(WireIn):
    id: Text200 | None = None
    role: TicketMessageRole
    author_name: Text200 | None = None
    public: bool = True
    body: Body
    body_format: TicketBodyFormat = TicketBodyFormat.TEXT
    created_at: Instant


class TicketResolutionIn(WireIn):
    body: Body
    body_format: TicketBodyFormat = TicketBodyFormat.TEXT


class TicketAttachmentIn(WireIn):
    name: AttachmentName


class TicketIn(WireIn):
    """A ticket of the system of origin (docs/specs/chamados.md, "Campos")."""

    external_id: ExternalId
    number: Number | None = None
    title: Title
    status: TicketStatus
    original_status: Text100 | None = None
    priority: Text50 | None = None
    category: Text200 | None = None
    product: Text200 | None = None
    tags: Tags = Field(default_factory=list[Tag])
    url: Url | None = None
    created_at: Instant
    updated_at: Instant
    resolved_at: Instant | None = None
    requester: TicketRequesterIn | None = None
    assignees: Annotated[list[TicketPersonIn], Field(max_length=20)] = Field(
        default_factory=list[TicketPersonIn]
    )
    messages: Annotated[list[TicketMessageIn], Field(max_length=500)] = Field(
        default_factory=list[TicketMessageIn]
    )
    resolution: TicketResolutionIn | None = None
    attachments: Annotated[list[TicketAttachmentIn], Field(max_length=100)] = Field(
        default_factory=list[TicketAttachmentIn]
    )
    custom_fields: CustomFields = Field(default_factory=dict[str, CustomValue])

    @model_validator(mode="after")
    def _updated_after_created(self) -> Self:
        if self.updated_at < self.created_at:
            raise PydanticCustomError(_UPDATED_BEFORE_CREATED, "updated_at is before created_at.")
        return self

    @property
    def display_number(self) -> str:
        """What the citation shows: ``number``, or the ``external_id`` without one."""
        return self.number or self.external_id

    @property
    def reference_date(self) -> tuple[datetime, str]:
        """The date a citation shows and which one it is (``resolved`` or ``updated``)."""
        if self.resolved_at is not None:
            return self.resolved_at, "resolved"
        return self.updated_at, "updated"


class TicketUpsertItemIn(WireIn):
    op: Literal["upsert"]
    ticket: TicketIn


class TicketDeleteItemIn(WireIn):
    op: Literal["delete"]
    external_id: ExternalId
    # Omitted: the server clock.
    deleted_at: Instant | None = None


type Problem = dict[str, JSONValue]


# Cross-field rules are raised by their model, located at the model: the field they blame.
CROSS_FIELD_RULES = {
    _UPDATED_BEFORE_CREATED: "updated_at",
    "sprint_end_before_start": "end_at",
    "link_url_required": "url",
    "invalid_sha": "target",
}


def problems(error: PydanticValidationError) -> list[Problem]:
    """The first ``MAX_PROBLEMS`` errors as ``{"loc", "problem"}``."""
    found: list[Problem] = []
    for item in error.errors(include_url=False)[:MAX_PROBLEMS]:
        loc: list[JSONValue] = list(item["loc"])
        if (blamed := CROSS_FIELD_RULES.get(item["type"])) is not None:
            loc.append(blamed)
        found.append({"loc": loc, "problem": item["type"]})
    return found


def serialized(value: object) -> bytes:
    """Compact UTF-8 JSON of a decoded value (what the 1 MiB limit of a ticket measures)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def canonical_payload(item: WireIn) -> tuple[dict[str, JSONValue], str]:
    """The stored payload of a ticket or a card (defaults filled in, instants in UTC with
    ``Z``) and its SHA-256."""
    payload: dict[str, JSONValue] = item.model_dump(mode="json")
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return payload, hashlib.sha256(canonical.encode("utf-8")).hexdigest()
