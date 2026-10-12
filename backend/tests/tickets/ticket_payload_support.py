"""Synthetic ticket payloads: the valid example of docs/specs/chamados.md and a builder."""

from __future__ import annotations

import copy

from knobridge.tickets.wire import TicketIn

# The "Exemplo válido" of docs/specs/chamados.md, verbatim.
SPEC_EXAMPLE: dict[str, object] = {
    "external_id": "4f6c2a10-0001",
    "number": "48213",
    "title": "Erro 4021 ao fechar o caixa",
    "status": "resolved",
    "original_status": "Resolvido pelo atendente",
    "priority": "alta",
    "category": "Financeiro",
    "product": "Caixa",
    "tags": ["caixa", "fechamento"],
    "url": "https://suporte.exemplo.com.br/chamados/48213",
    "created_at": "2026-09-30T14:02:00-03:00",
    "updated_at": "2026-10-01T09:15:00-03:00",
    "resolved_at": "2026-10-01T09:10:00-03:00",
    "requester": {
        "name": "Ana Souza",
        "email": "ana.souza@exemplo.com.br",
        "organization": "Padaria Exemplo",
    },
    "assignees": [{"name": "Bruno Lima", "email": "bruno@suporte.exemplo.com.br"}],
    "messages": [
        {
            "role": "customer",
            "author_name": "Ana Souza",
            "body": "Ao fechar o caixa aparece o erro 4021. Meu telefone é (11) 98765-4321.",
            "created_at": "2026-09-30T14:02:00-03:00",
        },
        {
            "role": "agent",
            "author_name": "Bruno Lima",
            "public": False,
            "body": "Cliente com sangria pendente no turno anterior.",
            "created_at": "2026-09-30T15:20:00-03:00",
        },
        {
            "role": "agent",
            "author_name": "Bruno Lima",
            "body_format": "html",
            "body": "<p>Olá Ana, finalize a <b>sangria pendente</b> e tente de novo.</p>",
            "created_at": "2026-10-01T09:05:00-03:00",
        },
    ],
    "resolution": {
        "body": (
            "O erro 4021 indica sangria pendente. Finalizar a sangria do turno anterior "
            "libera o fechamento."
        ),
        "body_format": "text",
    },
    "attachments": [{"name": "tela-erro-4021.png"}],
    "custom_fields": {"versao_sistema": "12.4.1", "loja": 3},
}

# The Markdown of the spec's layout for SPEC_EXAMPLE (anonymized, without internal notes).
SPEC_MARKDOWN = """\
# Chamado 48213: Erro 4021 ao fechar o caixa

- Status: Resolvido (original: Resolvido pelo atendente)
- Prioridade: alta
- Categoria: Financeiro
- Produto: Caixa
- Tags: caixa, fechamento
- Aberto em: 2026-09-30T17:02:00Z
- Atualizado em: 2026-10-01T12:15:00Z
- Resolvido em: 2026-10-01T12:10:00Z

## Problema

Ao fechar o caixa aparece o erro 4021. Meu telefone é [TELEFONE].

## Solução

O erro 4021 indica sangria pendente. Finalizar a sangria do turno anterior libera o fechamento.

## Conversa

**Atendente [ATENDENTE_1] · 2026-10-01T12:05:00Z**

Olá [SOLICITANTE], finalize a **sangria pendente** e tente de novo.

## Campos adicionais

- loja: 3
- versao_sistema: 12.4.1

## Anexos

- tela-erro-4021.png
"""


def minimal(**fields: object) -> dict[str, object]:
    """The smallest valid ticket, with ``fields`` on top."""
    payload: dict[str, object] = {
        "external_id": "T-1",
        "title": "Falha ao emitir",
        "status": "open",
        "created_at": "2026-10-01T10:00:00Z",
        "updated_at": "2026-10-01T10:00:00Z",
    }
    payload.update(fields)
    return payload


def message(
    body: str, *, role: str = "customer", minute: int = 0, **fields: object
) -> dict[str, object]:
    return {
        "role": role,
        "body": body,
        "created_at": f"2026-10-01T10:{minute:02d}:00Z",
        **fields,
    }


def ticket(payload: dict[str, object] | None = None, **fields: object) -> TicketIn:
    """``payload`` (default: the spec example) validated, with ``fields`` replaced."""
    data = copy.deepcopy(SPEC_EXAMPLE if payload is None else payload)
    data.update(fields)
    return TicketIn.model_validate(data)
