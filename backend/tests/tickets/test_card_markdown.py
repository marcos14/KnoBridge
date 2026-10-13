"""The Markdown of a card (docs/specs/cards.md, "Markdown do card"): the spec's layout, the
metadata, anonymization, comments on and off, omitted sections and lines, and its chunks."""

from __future__ import annotations

from card_payload_support import CARD_EXAMPLE, CARD_MARKDOWN, card, minimal_card

from knobridge.connectors.base import DocumentRef, RawDocument
from knobridge.ingestion.chunking import chunk_document
from knobridge.ingestion.models import DocumentKind
from knobridge.ingestion.parsing import ParsedDocument, ParsedKind
from knobridge.tickets.card_markdown import declared_card_names, render_card, selected_comments


def test_render_card_matches_the_spec_layout() -> None:
    document = render_card(card(), anonymize=True, include_comments=True)

    assert document.markdown == CARD_MARKDOWN
    assert (document.key, document.uri) == ("10001", "card:10001")
    assert document.title == "Permitir nota fiscal de exportação"


def test_render_card_metadata_for_the_citation() -> None:
    document = render_card(card(), anonymize=True, include_comments=True)

    assert document.metadata == {
        "kind": "card",
        "external_id": "10001",
        "card_number": "PROJ-123",
        "title": "Permitir nota fiscal de exportação",
        "card_type": "feature",
        "card_status": "done",
        "original_status": "Done",
        "sprint": "Sprint 42",
        "release": "12.5",
        "date": "2026-09-29T17:40:00Z",
        "date_kind": "done",
        "url": "https://dev.exemplo.com.br/browse/PROJ-123",
    }


def test_render_card_hash_is_stable_and_follows_the_settings() -> None:
    first = render_card(card(), anonymize=True, include_comments=True)
    again = render_card(card(), anonymize=True, include_comments=True)
    plain = render_card(card(), anonymize=False, include_comments=True)

    assert first.digest == again.digest
    assert first.digest != plain.digest


def test_render_card_anonymizes_people_and_numbers_everywhere() -> None:
    payload = minimal_card(
        title="Ligar para Bruno no (11) 98765-4321",
        reporter={"name": "Bruno Lima"},
        assignees=[{"name": "Carla Mendes"}, {"name": "Davi Rocha"}],
        description={
            "body": "Carla falou com bruno.lima@exemplo.com.br sobre o CPF 529.982.247-25."
        },
        sprint={"name": "Sprint da Carla"},
        links=[
            {"kind": "url", "target": "Doc da Carla", "relation": "Davi", "url": "https://x.test"}
        ],
        comments=[
            {"author_name": "Eva Souza", "body": "Ok, Davi.", "created_at": "2026-10-01T11:00:00Z"},
            {"author_name": "  ", "body": "Sem autor.", "created_at": "2026-10-01T12:00:00Z"},
        ],
    )

    document = render_card(card(payload), anonymize=True, include_comments=True)

    assert document.title == "Ligar para [RELATOR] no [TELEFONE]"
    assert "[RESPONSAVEL_1] falou com [EMAIL] sobre o CPF [CPF]." in document.markdown
    assert "- Sprint: Sprint da [RESPONSAVEL_1]" in document.markdown
    assert "- Link Doc da [RESPONSAVEL_1] ([RESPONSAVEL_2]): https://x.test" in document.markdown
    assert "**[RESPONSAVEL_3] · 2026-10-01T11:00:00Z**\n\nOk, [RESPONSAVEL_2]." in document.markdown
    assert "**Comentário · 2026-10-01T12:00:00Z**\n\nSem autor." in document.markdown
    assert document.metadata["sprint"] == "Sprint da [RESPONSAVEL_1]"
    assert "Bruno" not in document.markdown
    assert "Carla" not in document.markdown


def test_declared_card_names_number_assignees_then_comment_authors() -> None:
    payload = minimal_card(
        reporter={"name": "Bruno Lima"},
        assignees=[{"name": "Carla Mendes"}, {"name": None}],
        comments=[
            {"author_name": "Bruno Lima", "body": "a", "created_at": "2026-10-01T11:00:00Z"},
            {"author_name": "Eva", "body": "b", "created_at": "2026-10-01T11:00:00Z"},
        ],
    )

    assert declared_card_names(card(payload)) == {
        "bruno lima": "[RELATOR]",
        "bruno": "[RELATOR]",
        "carla mendes": "[RESPONSAVEL_1]",
        "carla": "[RESPONSAVEL_1]",
        "eva": "[RESPONSAVEL_2]",
    }


def test_render_card_without_anonymization_keeps_names() -> None:
    document = render_card(card(), anonymize=False, include_comments=True)

    assert "**Carla Mendes · 2026-09-20T10:00:00Z**" in document.markdown
    assert "Bruno" not in document.markdown


def test_render_card_without_comments_drops_the_section() -> None:
    document = render_card(card(), anonymize=True, include_comments=False)

    assert "## Comentários" not in document.markdown
    assert "## Campos adicionais" in document.markdown


def test_render_minimal_card_has_only_the_lines_with_value() -> None:
    document = render_card(card(minimal_card()), anonymize=True, include_comments=True)

    assert document.markdown == (
        "# Card C-1: Exportar relatório\n\n"
        "- Tipo: Tarefa\n"
        "- Status: Backlog\n"
        "- Criado em: 2026-10-01T10:00:00Z\n"
        "- Atualizado em: 2026-10-01T10:00:00Z\n"
    )
    assert document.metadata["sprint"] is None
    assert document.metadata["release"] is None
    assert document.metadata["original_status"] is None
    assert document.metadata["date_kind"] == "updated"


def test_render_card_original_equal_to_the_label_is_not_repeated() -> None:
    payload = minimal_card(status="in_progress", original_status="em andamento", type="bug")

    document = render_card(card(payload), anonymize=False, include_comments=True)

    assert "- Status: Em andamento\n" in document.markdown
    assert "- Tipo: Bug\n" in document.markdown


def test_render_cancelled_card_says_when_it_was_cancelled() -> None:
    payload = minimal_card(status="cancelled", done_at="2026-10-02T09:00:00Z")

    document = render_card(card(payload), anonymize=False, include_comments=True)

    assert "- Cancelado em: 2026-10-02T09:00:00Z" in document.markdown


def test_render_card_sprint_with_one_date() -> None:
    since = render_card(
        card(minimal_card(sprint={"name": "S1", "start_at": "2026-10-01T00:00:00Z"})),
        anonymize=False,
        include_comments=True,
    )
    until = render_card(
        card(minimal_card(sprint={"name": "S1", "end_at": "2026-10-15T00:00:00Z"})),
        anonymize=False,
        include_comments=True,
    )

    assert "- Sprint: S1 (desde 2026-10-01)" in since.markdown
    assert "- Sprint: S1 (até 2026-10-15)" in until.markdown


def test_render_card_bodies_open_no_section_and_html_is_converted() -> None:
    payload = minimal_card(
        description={"body": "<h2>Contexto</h2><p>Texto <b>forte</b></p>", "body_format": "html"},
        acceptance_criteria={"body": "# Regra\n\nvale"},
    )

    document = render_card(card(payload), anonymize=False, include_comments=True)

    assert "## Descrição\n\n**Contexto**\n\nTexto **forte**" in document.markdown
    assert "## Critérios de aceite\n\n**Regra**\n\nvale" in document.markdown


def test_selected_comments_by_date_then_payload_order() -> None:
    payload = minimal_card(
        comments=[
            {"id": "b", "body": "b", "created_at": "2026-10-01T12:00:00Z"},
            {"id": "a", "body": "a", "created_at": "2026-10-01T11:00:00Z"},
            {"id": "c", "body": "c", "created_at": "2026-10-01T12:00:00Z"},
        ]
    )

    assert [comment.id for comment in selected_comments(card(payload))] == ["a", "b", "c"]


def _chunks(payload: dict[str, object]) -> list[dict[str, object]]:
    document = render_card(card(payload), anonymize=True, include_comments=True)
    raw = RawDocument(
        ref=DocumentRef(document.key, DocumentKind.CARD),
        title=document.title,
        uri=document.uri,
        content=document.markdown.encode(),
        extension="md",
        metadata=document.metadata,
        digest=document.digest,
    )
    parsed = ParsedDocument.of(raw, ParsedKind.CARD, raw.title, document.markdown)
    return [
        {"content": chunk.content, "display": chunk.display, **chunk.meta}
        for chunk in chunk_document(parsed)
    ]


def test_card_chunks_join_the_head_description_and_acceptance() -> None:
    first, *rest = _chunks(CARD_EXAMPLE)

    assert first["section"] == "description"
    assert str(first["content"]).startswith(
        "card: PROJ-123 · Permitir nota fiscal de exportação\nstatus: done\nsection: Descrição\n\n"
        "# Card PROJ-123"
    )
    assert "## Critérios de aceite" in str(first["display"])
    assert [chunk["section"] for chunk in rest] == ["links", "comments", "fields", "attachments"]
    assert all(chunk["sprint"] == "Sprint 42" for chunk in rest)
    assert {chunk["kind"] for chunk in [first, *rest]} == {"card"}
    assert "start_line" not in first


def test_card_without_sections_is_one_description_chunk() -> None:
    (only,) = _chunks(minimal_card())

    assert only["section"] == "description"
    assert only["card_number"] == "C-1"


def test_card_head_joins_the_first_section_when_there_is_no_description() -> None:
    first, *_ = _chunks(minimal_card(links=[{"kind": "pull_request", "target": "7"}]))

    assert first["section"] == "links"
    assert "# Card C-1" in str(first["display"])
