"""The Markdown of a card and its document for the index (docs/specs/cards.md, "Markdown do
card").

Pure, like the ticket's (``markdown.py``, whose body conversion, renderer and sections it
reuses): bodies converted to Markdown, every indexed text anonymized when the source asks, then
the layout assembled. The reporter and the assignees are never rendered: they only declare the
names to replace (``[RELATOR]``, ``[RESPONSAVEL_n]``); comment authors not declared by them are
numbered after the assignees.
"""

from __future__ import annotations

from datetime import UTC, datetime

from knobridge.audit.models import JSONValue
from knobridge.ingestion.chunking import (
    CARD_ACCEPTANCE,
    CARD_ATTACHMENTS,
    CARD_COMMENTS,
    CARD_DESCRIPTION,
    CARD_FIELDS,
    CARD_LINKS,
)
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.source_config import (
    CARD_STATUS_LABELS,
    CARD_TYPE_LABELS,
    CardStatus,
)
from knobridge.tickets.anonymize import NameBook, TicketAnonymizer
from knobridge.tickets.card_wire import (
    CardCommentIn,
    CardDescriptionIn,
    CardIn,
    CardLinkIn,
    CardLinkKind,
    CardSprintIn,
)
from knobridge.tickets.markdown import (
    RenderedDocument,
    Renderer,
    custom_fields,
    labeled,
    list_lines,
    section,
    utc,
)

URI_PREFIX = "card:"
REPORTER = "[RELATOR]"
ASSIGNEE = "RESPONSAVEL"
LINK_LABELS = {
    CardLinkKind.CARD: "Card",
    CardLinkKind.TICKET: "Chamado",
    CardLinkKind.COMMIT: "Commit",
    CardLinkKind.PULL_REQUEST: "PR",
    CardLinkKind.URL: "Link",
}
# The line of a comment without a known author.
COMMENT = "Comentário"


def declared_card_names(card: CardIn) -> dict[str, str]:
    """Folded name → marker: the reporter, then the assignees and the other comment authors,
    numbered in order of first appearance."""
    book = NameBook()
    if card.reporter is not None:
        book.add(card.reporter.name, REPORTER, first_name=True)
    people = [person.name for person in card.assignees]
    people += [comment.author_name for comment in card.comments]
    book.number(people, ASSIGNEE)
    return book.names


def _day(instant: datetime) -> str:
    return instant.astimezone(UTC).date().isoformat()


def _sprint(sprint: CardSprintIn | None, render: Renderer) -> str:
    if sprint is None:
        return ""
    name = render.inline(sprint.name)
    start, end = sprint.start_at, sprint.end_at
    if start is not None and end is not None:
        return f"{name} ({_day(start)} a {_day(end)})"
    if start is not None:
        return f"{name} (desde {_day(start)})"
    if end is not None:
        return f"{name} (até {_day(end)})"
    return name


def _metadata_lines(card: CardIn, render: Renderer, original_status: str) -> list[str]:
    finished = "Cancelado em" if card.status is CardStatus.CANCELLED else "Concluído em"
    lines = [
        ("Tipo", labeled(CARD_TYPE_LABELS[card.type], render.inline(card.original_type))),
        ("Status", labeled(CARD_STATUS_LABELS[card.status], original_status)),
        ("Prioridade", render.inline(card.priority)),
        ("Produto", render.inline(card.product)),
        ("Sprint", _sprint(card.sprint, render)),
        ("Versão", render.inline(card.release)),
        ("Card pai", card.parent_external_id or ""),
        ("Tags", ", ".join(render.inline(tag) for tag in card.tags)),
        ("Criado em", utc(card.created_at)),
        ("Atualizado em", utc(card.updated_at)),
        (finished, utc(card.done_at) if card.done_at else ""),
    ]
    return list_lines(lines)


def _link(link: CardLinkIn, render: Renderer) -> str:
    # Identifiers stay as they are; only the label of a plain link is free text.
    target = render.inline(link.target) if link.kind is CardLinkKind.URL else link.target
    line = f"- {LINK_LABELS[link.kind]} {target}"
    if relation := render.inline(link.relation):
        line += f" ({relation})"
    if link.kind is CardLinkKind.URL and link.url is not None:
        line += f": {link.url}"
    return line


def selected_comments(card: CardIn) -> list[CardCommentIn]:
    """The comments by date, ties by payload order."""
    chosen = [(comment.created_at, index, comment) for index, comment in enumerate(card.comments)]
    return [comment for _, _, comment in sorted(chosen, key=lambda entry: entry[:2])]


def _comments(card: CardIn, render: Renderer) -> str:
    entries: list[str] = []
    for comment in selected_comments(card):
        line = f"**{render.person(comment.author_name) or COMMENT} · {utc(comment.created_at)}**"
        body = render.body(comment.body, comment.body_format)
        entries.append(f"{line}\n\n{body}" if body else line)
    return "\n\n".join(entries)


def _body(text: CardDescriptionIn | None, render: Renderer) -> str | None:
    return None if text is None else render.body(text.body, text.body_format)


def render_card(card: CardIn, *, anonymize: bool, include_comments: bool) -> RenderedDocument:
    """The card's Markdown (ending with one newline), title, citation metadata and hash."""
    render = Renderer(TicketAnonymizer(declared_card_names(card)) if anonymize else None)
    title = render.inline(card.title)
    original_status = render.inline(card.original_status)
    blocks = [
        f"# Card {card.display_number}: {title}",
        "\n".join(_metadata_lines(card, render, original_status)),
    ]
    if (description := _body(card.description, render)) is not None:
        blocks.append(section(CARD_DESCRIPTION, description))
    if (acceptance := _body(card.acceptance_criteria, render)) is not None:
        blocks.append(section(CARD_ACCEPTANCE, acceptance))
    if card.links:
        blocks.append(section(CARD_LINKS, "\n".join(_link(link, render) for link in card.links)))
    if include_comments and card.comments:
        blocks.append(section(CARD_COMMENTS, _comments(card, render)))
    if fields := custom_fields(card.custom_fields, render):
        blocks.append(section(CARD_FIELDS, fields))
    if card.attachments:
        names = "\n".join(f"- {render.inline(a.name)}" for a in card.attachments)
        blocks.append(section(CARD_ATTACHMENTS, names))
    markdown = "\n\n".join(blocks) + "\n"

    date, date_kind = card.reference_date
    metadata: dict[str, JSONValue] = {
        "kind": DocumentKind.CARD.value,
        "external_id": card.external_id,
        "card_number": card.display_number,
        "title": title,
        "card_type": card.type.value,
        "card_status": card.status.value,
        "original_status": original_status or None,
        "sprint": None if card.sprint is None else render.inline(card.sprint.name),
        "release": render.inline(card.release) or None,
        "date": utc(date),
        "date_kind": date_kind,
        "url": card.url,
    }
    uri = URI_PREFIX + card.external_id
    return RenderedDocument.of(card.external_id, uri, title, markdown, metadata)
