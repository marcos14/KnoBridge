"""The Markdown of a ticket (docs/specs/chamados.md, "Markdown do chamado") and its document."""

from __future__ import annotations

import asyncio

from ticket_payload_support import SPEC_MARKDOWN, message, minimal, ticket

from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import parse_document
from knobridge.tickets.markdown import convert_body, render_ticket, selected_messages
from knobridge.tickets.wire import TicketBodyFormat


def test_rendered_ticket_chunks_carry_its_citation_metadata() -> None:
    document = render_ticket(ticket(), anonymize=True, include_internal_notes=False)
    raw = RawDocument(
        ref=DocumentRef(document.key, DocumentKind.TICKET),
        title=document.title,
        uri=document.uri,
        content=document.markdown.encode(),
        metadata=document.metadata,
        digest=document.digest,
    )

    chunks = chunk_document(asyncio.run(parse_document(raw)))

    assert [c.meta["section"] for c in chunks] == [
        "problem",
        "conversation",
        "fields",
        "attachments",
    ]
    assert all(c.meta["external_id"] == "4f6c2a10-0001" for c in chunks)
    assert chunks[0].display.startswith("# Chamado 48213: Erro 4021 ao fechar o caixa\n\n- Status:")
    assert chunks[0].content.startswith(
        "ticket: 48213 · Erro 4021 ao fechar o caixa\nstatus: resolved\nsection: Problema\n\n"
    )


def test_render_ticket_matches_the_spec_layout() -> None:
    document = render_ticket(ticket(), anonymize=True, include_internal_notes=False)

    assert document.markdown == SPEC_MARKDOWN


def test_render_ticket_metadata_and_identity() -> None:
    document = render_ticket(ticket(), anonymize=True, include_internal_notes=False)

    assert (document.key, document.uri, document.title) == (
        "4f6c2a10-0001",
        "ticket:4f6c2a10-0001",
        "Erro 4021 ao fechar o caixa",
    )
    assert document.metadata == {
        "kind": "ticket",
        "external_id": "4f6c2a10-0001",
        "ticket_number": "48213",
        "title": "Erro 4021 ao fechar o caixa",
        "ticket_status": "resolved",
        "original_status": "Resolvido pelo atendente",
        "date": "2026-10-01T12:10:00Z",
        "date_kind": "resolved",
        "url": "https://suporte.exemplo.com.br/chamados/48213",
    }


def test_render_ticket_excludes_internal_notes_by_default() -> None:
    document = render_ticket(ticket(), anonymize=True, include_internal_notes=False)

    assert "sangria pendente no turno anterior" not in document.markdown
    assert "nota interna" not in document.markdown


def test_render_ticket_includes_internal_notes_when_asked() -> None:
    document = render_ticket(ticket(), anonymize=True, include_internal_notes=True)

    assert (
        "**Atendente (nota interna) [ATENDENTE_1] · 2026-09-30T18:20:00Z**\n\n"
        "Cliente com sangria pendente no turno anterior.\n\n"
        "**Atendente [ATENDENTE_1] · 2026-10-01T12:05:00Z**"
    ) in document.markdown


def test_render_ticket_without_anonymization_shows_names_but_never_requester_data() -> None:
    document = render_ticket(ticket(), anonymize=False, include_internal_notes=False)

    assert "Meu telefone é (11) 98765-4321." in document.markdown
    assert "**Atendente Bruno Lima · 2026-10-01T12:05:00Z**" in document.markdown
    assert "Olá Ana, finalize" in document.markdown
    assert "ana.souza@exemplo.com.br" not in document.markdown
    assert "Padaria Exemplo" not in document.markdown


def test_render_ticket_keeps_markers_stable_across_fields() -> None:
    payload = minimal(
        title="Ana Souza não emite nota",
        tags=["ana souza"],
        requester={"name": "Ana Souza"},
        attachments=[{"name": "print-ana.png"}],
        custom_fields={"contato": "ANA"},
        messages=[message("Sou a Ana."), message("Oi Ana", role="agent", minute=1)],
    )

    document = render_ticket(ticket(payload), anonymize=True, include_internal_notes=False)

    assert document.title == "[SOLICITANTE] não emite nota"
    assert document.markdown.count("[SOLICITANTE]") == 6
    assert "- print-[SOLICITANTE].png" in document.markdown
    assert "**Atendente · 2026-10-01T10:01:00Z**" in document.markdown


def test_render_ticket_minimal_keeps_only_title_and_dates() -> None:
    document = render_ticket(ticket(minimal()), anonymize=True, include_internal_notes=False)

    assert document.markdown == (
        "# Chamado T-1: Falha ao emitir\n\n"
        "- Status: Aberto\n"
        "- Aberto em: 2026-10-01T10:00:00Z\n"
        "- Atualizado em: 2026-10-01T10:00:00Z\n"
    )
    assert document.metadata["date_kind"] == "updated"
    assert document.metadata["original_status"] is None
    assert document.metadata["url"] is None


def test_render_ticket_status_omits_original_equal_to_the_label() -> None:
    payload = minimal(status="closed", original_status="fechado", priority="  ")

    document = render_ticket(ticket(payload), anonymize=True, include_internal_notes=False)

    assert "- Status: Fechado\n" in document.markdown
    assert "Prioridade" not in document.markdown


def test_render_ticket_problem_falls_back_to_the_first_selected_message() -> None:
    payload = minimal(
        messages=[
            message("depois", role="agent", minute=5, author_name="Bia Nunes"),
            message("primeiro", role="system", minute=1, author_name="Robô"),
            message("nota", role="customer", minute=0, public=False),
        ]
    )

    document = render_ticket(ticket(payload), anonymize=True, include_internal_notes=False)

    assert "## Problema\n\nprimeiro\n\n## Conversa\n\n**Atendente [ATENDENTE_1] ·" in (
        document.markdown
    )
    assert "Robô" not in document.markdown


def test_render_ticket_custom_fields_sorted_with_booleans_and_nulls() -> None:
    fields = {"b": True, "a": False, "c": None, "d": 1.5, "e": "", "f": "linha\nnova"}

    document = render_ticket(
        ticket(minimal(custom_fields=fields)), anonymize=False, include_internal_notes=False
    )

    assert "## Campos adicionais\n\n- a: não\n- b: sim\n- d: 1.5\n- e:\n- f: linha nova\n" in (
        document.markdown
    )


def test_render_ticket_conversation_keeps_header_of_an_empty_body() -> None:
    payload = minimal(
        messages=[
            message("problema"),
            message("<p></p>", role="customer", minute=1, body_format="html"),
        ]
    )

    document = render_ticket(ticket(payload), anonymize=False, include_internal_notes=False)

    assert document.markdown.endswith("## Conversa\n\n**Cliente · 2026-10-01T10:01:00Z**\n")


def test_render_ticket_empty_resolution_keeps_the_heading() -> None:
    payload = minimal(resolution={"body": "<br>", "body_format": "html"})

    document = render_ticket(ticket(payload), anonymize=False, include_internal_notes=False)

    assert document.markdown.endswith("## Solução\n")


def test_render_ticket_hash_is_stable_and_follows_content() -> None:
    first = render_ticket(ticket(), anonymize=True, include_internal_notes=False)
    again = render_ticket(ticket(), anonymize=True, include_internal_notes=False)
    other = render_ticket(ticket(status="closed"), anonymize=True, include_internal_notes=False)

    assert first.digest == again.digest
    assert len(first.digest) == 64
    assert other.digest != first.digest


def test_convert_body_turns_headings_into_bold_and_closes_fences() -> None:
    body = "# Título\r\n  ## Sub ##\r\n####### não\r\n```sh\r\necho"

    assert convert_body(body, TicketBodyFormat.MARKDOWN) == (
        "**Título**\n**Sub**\n####### não\n```sh\necho\n```"
    )


def test_convert_body_converts_html_and_drops_scripts() -> None:
    body = "<h2>Passo</h2><script>x()</script><style>p{}</style><p>Use <b>F5</b></p>"

    assert convert_body(body, TicketBodyFormat.HTML) == "**Passo**\n\nUse **F5**"


def test_convert_body_keeps_closed_fences() -> None:
    body = "~~~\ncode\n~~~~\n```\n```"

    assert convert_body(body, TicketBodyFormat.TEXT) == body


def test_convert_body_ignores_a_shorter_or_other_fence_inside_an_open_one() -> None:
    body = "````\n```\n~~~~\ncode"

    assert convert_body(body, TicketBodyFormat.TEXT) == f"{body}\n````"


def test_render_ticket_system_message_has_no_author() -> None:
    payload = minimal(
        messages=[
            message("problema"),
            message("status mudou", role="system", minute=1, author_name="Robô"),
        ]
    )

    for anonymize in (True, False):
        document = render_ticket(ticket(payload), anonymize=anonymize, include_internal_notes=False)

        assert "**Sistema · 2026-10-01T10:01:00Z**\n\nstatus mudou\n" in document.markdown


def test_selected_messages_order_by_date_then_payload_position() -> None:
    payload = minimal(
        messages=[message("b", minute=2), message("a1", minute=1), message("a2", minute=1)]
    )

    bodies = [m.body for m in selected_messages(ticket(payload), include_internal_notes=False)]

    assert bodies == ["a1", "a2", "b"]
