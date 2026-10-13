"""Synthetic card payloads: an example matching the Markdown of docs/specs/cards.md and a
builder. Not a test module; imported by its basename."""

from __future__ import annotations

import copy

from knobridge.tickets.card_wire import CardIn

# A card whose Markdown is the "Markdown do card" example of docs/specs/cards.md.
CARD_EXAMPLE: dict[str, object] = {
    "external_id": "10001",
    "number": "PROJ-123",
    "title": "Permitir nota fiscal de exportação",
    "type": "feature",
    "status": "done",
    "original_status": "Done",
    "original_type": "Story",
    "priority": "alta",
    "product": "Faturamento",
    "tags": ["nfe", "exportação"],
    "url": "https://dev.exemplo.com.br/browse/PROJ-123",
    "description": {"body": "Emitir nota fiscal para cliente do exterior, sem CNPJ."},
    "acceptance_criteria": {
        "body": "- A nota de exportação sai sem CNPJ quando o cliente é estrangeiro.",
        "body_format": "markdown",
    },
    "sprint": {
        "name": "Sprint 42",
        "start_at": "2026-09-15T12:00:00Z",
        "end_at": "2026-09-29T20:00:00Z",
    },
    "release": "12.5",
    "parent_external_id": "PROJ-100",
    "links": [
        {"kind": "ticket", "target": "48213", "relation": "relaciona"},
        {"kind": "commit", "target": "3f9c2a1", "relation": "corrige"},
        {"kind": "pull_request", "target": "482"},
    ],
    "reporter": {"name": "Bruno Lima", "email": "bruno@exemplo.com.br"},
    "assignees": [{"name": "Carla Mendes"}],
    "comments": [
        {
            "author_name": "Carla Mendes",
            "body": "Implementado no fluxo de emissão; falta o teste de rejeição.",
            "created_at": "2026-09-20T07:00:00-03:00",
        }
    ],
    "attachments": [{"name": "layout-nfe-exportacao.png"}],
    "custom_fields": {"equipe": "fiscal"},
    "created_at": "2026-09-01T12:00:00Z",
    "updated_at": "2026-09-29T18:00:00Z",
    "done_at": "2026-09-29T17:40:00Z",
}

# The Markdown of the spec's layout for CARD_EXAMPLE (anonymized, with comments).
CARD_MARKDOWN = """\
# Card PROJ-123: Permitir nota fiscal de exportação

- Tipo: Funcionalidade (original: Story)
- Status: Concluído (original: Done)
- Prioridade: alta
- Produto: Faturamento
- Sprint: Sprint 42 (2026-09-15 a 2026-09-29)
- Versão: 12.5
- Card pai: PROJ-100
- Tags: nfe, exportação
- Criado em: 2026-09-01T12:00:00Z
- Atualizado em: 2026-09-29T18:00:00Z
- Concluído em: 2026-09-29T17:40:00Z

## Descrição

Emitir nota fiscal para cliente do exterior, sem CNPJ.

## Critérios de aceite

- A nota de exportação sai sem CNPJ quando o cliente é estrangeiro.

## Ligações

- Chamado 48213 (relaciona)
- Commit 3f9c2a1 (corrige)
- PR 482

## Comentários

**[RESPONSAVEL_1] · 2026-09-20T10:00:00Z**

Implementado no fluxo de emissão; falta o teste de rejeição.

## Campos adicionais

- equipe: fiscal

## Anexos

- layout-nfe-exportacao.png
"""


def minimal_card(**fields: object) -> dict[str, object]:
    """The smallest valid card, with ``fields`` on top."""
    payload: dict[str, object] = {
        "external_id": "C-1",
        "title": "Exportar relatório",
        "type": "task",
        "status": "backlog",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    }
    payload.update(fields)
    return payload


def card(payload: dict[str, object] | None = None, **fields: object) -> CardIn:
    """``payload`` (default: the example) validated, with ``fields`` replaced."""
    data = copy.deepcopy(CARD_EXAMPLE if payload is None else payload)
    data.update(fields)
    return CardIn.model_validate(data)
