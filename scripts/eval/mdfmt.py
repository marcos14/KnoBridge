"""Markdown formatting shared by the report and the comparison (pt-BR numbers)."""

from __future__ import annotations

from collections.abc import Sequence

LEVEL_LABELS = {
    "end_user": "Usuário final",
    "support": "Suporte",
    "product_dev": "Desenvolvimento e produto",
}
VERDICT_LABELS = {
    "correct": "correta",
    "unknown": "não sei",
    "wrong": "errada",
    "leak": "vazamento",
    "error": "erro",
}
DASH = "—"


def _decimal(value: float, places: int) -> str:
    return f"{value:.{places}f}".replace(".", ",")


def pct(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return DASH
    return f"{_decimal(value * 100, 1)}%"


def num(value: object, places: int = 0) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return DASH
    if places == 0:
        return str(round(value))
    return _decimal(value, places)


def cost(value: object) -> str:
    return num(value, 4)


def cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return lines
