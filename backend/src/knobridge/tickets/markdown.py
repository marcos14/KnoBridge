"""The Markdown of a ticket and its document for the index (docs/specs/chamados.md, "Markdown do
chamado").

Pure functions over a validated ``TicketIn``: message bodies are converted to Markdown (HTML by
the parser's converter), headings inside them become bold so a body never opens a section, then
every indexed text is anonymized (when the source asks) before the layout is assembled. The
requester and assignees are never rendered: they only tell the anonymizer which names to replace.
The pieces shared with the card's Markdown (``card_markdown.py``) are public here: the body
conversion, the ``Renderer``, the sections, the custom fields and the ``RenderedDocument``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from knobridge.audit.models import JSONValue
from knobridge.ingestion.chunking import (
    TICKET_ATTACHMENTS,
    TICKET_CONVERSATION,
    TICKET_FIELDS,
    TICKET_PROBLEM,
    TICKET_RESOLUTION,
)
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import html_to_markdown
from knobridge.ingestion.source_config import TICKET_STATUS_LABELS
from knobridge.tickets.anonymize import TicketAnonymizer
from knobridge.tickets.wire import TicketBodyFormat, TicketIn, TicketMessageIn, TicketMessageRole

URI_PREFIX = "ticket:"
ROLE_LABELS = {
    TicketMessageRole.CUSTOMER: "Cliente",
    TicketMessageRole.AGENT: "Atendente",
    TicketMessageRole.SYSTEM: "Sistema",
}
INTERNAL_NOTE = " (nota interna)"
# The same ATX heading the chunker cuts at, so whatever it would cut at is neutralized.
_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", re.MULTILINE)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


@dataclass(frozen=True, slots=True)
class RenderedDocument:
    """What the inbox connector returns for a ticket or a card: the citation data and the
    hash."""

    key: str
    uri: str
    title: str
    markdown: str
    metadata: dict[str, JSONValue]
    # SHA-256 (hex) of the Markdown and the citation metadata.
    digest: str

    @classmethod
    def of(
        cls, key: str, uri: str, title: str, markdown: str, metadata: dict[str, JSONValue]
    ) -> RenderedDocument:
        payload = json.dumps({"markdown": markdown, "meta": metadata}, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return cls(key, uri, title, markdown, metadata, digest)


def utc(instant: datetime) -> str:
    """An instant in UTC with ``Z`` (``2026-09-30T17:02:00Z``)."""
    return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")


def inline(text: str) -> str:
    """Whitespace collapsed: a single-line field with a line break would end its list item or
    heading early."""
    return " ".join(text.split())


def _close_open_fence(text: str) -> str:
    """Close a code fence the body left open, or it would swallow the sections after it."""
    fence: str | None = None
    for line in text.split("\n"):
        match = _FENCE.match(line)
        if match is None:
            continue
        marker = match.group(1)
        if fence is None:
            fence = marker
        elif marker[0] == fence[0] and len(marker) >= len(fence):
            fence = None
    return text if fence is None else f"{text}\n{fence}"


def convert_body(body: str, body_format: TicketBodyFormat) -> str:
    """A message or resolution body as Markdown that opens no section of its own."""
    text = body.replace("\r\n", "\n")
    if body_format is TicketBodyFormat.HTML:
        text = html_to_markdown(text)
    text = _HEADING.sub(r"**\1**", text)
    return _close_open_fence(text).strip()


class Renderer:
    """Texts as they go into the index: on one line or converted, then anonymized when there
    is an anonymizer."""

    def __init__(self, anonymizer: TicketAnonymizer | None) -> None:
        self._anonymizer = anonymizer
        self.clean: Callable[[str], str] = anonymizer.text if anonymizer is not None else str

    def inline(self, value: str | None) -> str:
        return self.clean(inline(value)) if value else ""

    def body(self, body: str, body_format: TicketBodyFormat) -> str:
        return self.clean(convert_body(body, body_format))

    def person(self, name: str | None) -> str | None:
        """An author: the marker (or ``None`` when undeclared) with anonymization, else the
        name on one line (``None`` when empty)."""
        if self._anonymizer is not None:
            return self._anonymizer.author(name)
        return inline(name or "") or None


def _metadata_lines(ticket: TicketIn, render: Renderer, original: str) -> list[str]:
    tags = ", ".join(render.inline(tag) for tag in ticket.tags)
    lines = [
        ("Status", labeled(TICKET_STATUS_LABELS[ticket.status], original)),
        ("Prioridade", render.inline(ticket.priority)),
        ("Categoria", render.inline(ticket.category)),
        ("Produto", render.inline(ticket.product)),
        ("Tags", tags),
        ("Aberto em", utc(ticket.created_at)),
        ("Atualizado em", utc(ticket.updated_at)),
        ("Resolvido em", utc(ticket.resolved_at) if ticket.resolved_at else ""),
    ]
    return list_lines(lines)


def labeled(label: str, original: str) -> str:
    """A normalized value in pt-BR, with ``(original: …)`` when the origin calls it otherwise."""
    if original and original.casefold() != label.casefold():
        return f"{label} (original: {original})"
    return label


def list_lines(lines: list[tuple[str, str]]) -> list[str]:
    """``- <name>: <value>`` for each line with a value."""
    return [f"- {name}: {value}" for name, value in lines if value]


def selected_messages(ticket: TicketIn, *, include_internal_notes: bool) -> list[TicketMessageIn]:
    """Public messages (and internal notes when included), by date, ties by payload order."""
    chosen = [
        (message.created_at, index, message)
        for index, message in enumerate(ticket.messages)
        if message.public or include_internal_notes
    ]
    return [message for _, _, message in sorted(chosen, key=lambda entry: entry[:2])]


def section(title: str, body: str) -> str:
    return f"## {title}\n\n{body}" if body else f"## {title}"


def _conversation(messages: list[TicketMessageIn], render: Renderer) -> str:
    entries: list[str] = []
    for message in messages:
        role = ROLE_LABELS[message.role] + ("" if message.public else INTERNAL_NOTE)
        author = (
            None if message.role is TicketMessageRole.SYSTEM else render.person(message.author_name)
        )
        who = f"{role} {author}" if author else role
        line = f"**{who} · {utc(message.created_at)}**"
        body = render.body(message.body, message.body_format)
        entries.append(f"{line}\n\n{body}" if body else line)
    return "\n\n".join(entries)


def _field_value(value: str | int | float | bool, render: Renderer) -> str:
    if isinstance(value, bool):
        return "sim" if value else "não"
    if isinstance(value, str):
        return render.inline(value)
    return str(value)


def custom_fields(fields: Mapping[str, str | int | float | bool | None], render: Renderer) -> str:
    """``- <key>: <value>`` by key, without the null values."""
    return "\n".join(
        f"- {key}: {_field_value(value, render)}".rstrip()
        for key, value in sorted(fields.items())
        if value is not None
    )


def render_ticket(
    ticket: TicketIn, *, anonymize: bool, include_internal_notes: bool
) -> RenderedDocument:
    """The ticket's Markdown (ending with one newline), title, citation metadata and hash."""
    render = Renderer(TicketAnonymizer.for_ticket(ticket) if anonymize else None)
    title = render.inline(ticket.title)
    original = render.inline(ticket.original_status)
    blocks = [
        f"# Chamado {ticket.display_number}: {title}",
        "\n".join(_metadata_lines(ticket, render, original)),
    ]
    messages = selected_messages(ticket, include_internal_notes=include_internal_notes)
    problem = next((m for m in messages if m.role is TicketMessageRole.CUSTOMER), None)
    if problem is None and messages:
        problem = messages[0]
    if problem is not None:
        blocks.append(section(TICKET_PROBLEM, render.body(problem.body, problem.body_format)))
    if ticket.resolution is not None:
        resolution = render.body(ticket.resolution.body, ticket.resolution.body_format)
        blocks.append(section(TICKET_RESOLUTION, resolution))
    rest = [message for message in messages if message is not problem]
    if rest:
        blocks.append(section(TICKET_CONVERSATION, _conversation(rest, render)))
    if fields := custom_fields(ticket.custom_fields, render):
        blocks.append(section(TICKET_FIELDS, fields))
    if ticket.attachments:
        names = "\n".join(f"- {render.inline(a.name)}" for a in ticket.attachments)
        blocks.append(section(TICKET_ATTACHMENTS, names))
    markdown = "\n\n".join(blocks) + "\n"

    date, date_kind = ticket.reference_date
    metadata: dict[str, JSONValue] = {
        "kind": DocumentKind.TICKET.value,
        "external_id": ticket.external_id,
        "ticket_number": ticket.display_number,
        "title": title,
        "ticket_status": ticket.status.value,
        "original_status": original or None,
        "date": utc(date),
        "date_kind": date_kind,
        "url": ticket.url,
    }
    uri = URI_PREFIX + ticket.external_id
    return RenderedDocument.of(ticket.external_id, uri, title, markdown, metadata)
