"""Every problem of the fictitious Vértice ERP, the support team's domain and the base dates."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from synthetic_tickets.catalog_gestao import GESTAO
from synthetic_tickets.catalog_loja import LOJA
from synthetic_tickets.problem import Problem

PROBLEMS: tuple[Problem, ...] = LOJA + GESTAO

ERP_NAME = "Vértice ERP"
SUPPORT_DOMAIN = "suporte.vertice.example"
TICKET_URL = f"https://{SUPPORT_DOMAIN}/chamados/{{number}}"

# Tickets open between these instants (Brasília time, fixed: no real clock, rule of section 5).
BRT = timezone(timedelta(hours=-3))
FIRST_DAY = datetime(2025, 11, 3, 8, 0, tzinfo=BRT)
SPAN_DAYS = 300

STATUS_WEIGHTS: dict[str, int] = {"resolved": 45, "closed": 20, "pending": 15, "open": 20}
ORIGINAL_STATUS: dict[str, tuple[str, ...]] = {
    "open": ("Novo", "Em atendimento"),
    "pending": ("Aguardando cliente", "Aguardando fornecedor"),
    "resolved": ("Resolvido pelo atendente",),
    "closed": ("Encerrado", "Fechado automaticamente"),
}
PRIORITIES = ("baixa", "média", "alta", "urgente")
