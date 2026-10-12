"""Search and sort building blocks of the lists, compiled for PostgreSQL (no database)."""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.dialects import postgresql

from knobridge.core.listing import escape_like, sort_order, text_match

_ITEMS = Table(
    "items", MetaData(), Column("id", Integer), Column("name", String), Column("note", String)
)
_COLUMNS = {"name": _ITEMS.c.name, "note": _ITEMS.c.note}


def _sql(sort: str) -> str:
    statement = select(_ITEMS.c.id).order_by(*sort_order(sort, _COLUMNS, _ITEMS.c.id))
    return str(statement.compile(dialect=postgresql.dialect()))


def test_escape_like_makes_wildcards_literal() -> None:
    assert escape_like(r"100%_a\b") == r"100\%\_a\\b"


def test_text_match_is_case_insensitive_over_every_column() -> None:
    condition = text_match("50%", _ITEMS.c.name, _ITEMS.c.note)

    sql = str(condition.compile(dialect=postgresql.dialect()))

    assert sql.count("ILIKE") == 2
    assert condition.compile().params == {"name_1": "%50\\%%", "note_1": "%50\\%%"}


def test_sort_order_ascending_with_nulls_last_and_tiebreak() -> None:
    sql = _sql("name")

    assert sql.endswith("ORDER BY items.name ASC NULLS LAST, items.id")


def test_sort_order_descending_keeps_nulls_last() -> None:
    sql = _sql("-note")

    assert sql.endswith("ORDER BY items.note DESC NULLS LAST, items.id")
