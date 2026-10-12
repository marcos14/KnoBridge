"""Building blocks of the paginated lists: text search and sorting.

Text search is a case-insensitive substring (``ILIKE``) over one or more columns, with the
``LIKE`` wildcards of the term made literal. Sorting takes the contract's value (``name``,
``-name``, ...) and maps it to a column: ascending or descending, nulls always last, ties
broken by the given column (the id) so pages never overlap.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import ColumnElement, SQLColumnExpression, UnaryExpression, or_

# Longest ``query`` the lists accept (the API validates it).
QUERY_MAX_LENGTH = 200
LIKE_ESCAPE = "\\"


def escape_like(term: str) -> str:
    """Make ``term`` literal inside a ``LIKE`` pattern (escape character ``\\``)."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def text_match(term: str, *columns: SQLColumnExpression[str]) -> ColumnElement[bool]:
    """Any of ``columns`` contains ``term``, ignoring case."""
    pattern = f"%{escape_like(term)}%"
    return or_(*(column.ilike(pattern, escape=LIKE_ESCAPE) for column in columns))


# ``Any``: the sortable columns of one list mix types (text, timestamps, counts).
type SortColumns = Mapping[str, SQLColumnExpression[Any]]


def sort_order(
    sort: str, columns: SortColumns, tiebreak: SQLColumnExpression[Any]
) -> tuple[UnaryExpression[Any], SQLColumnExpression[Any]]:
    """``ORDER BY`` for ``sort`` (a key of ``columns``, ``-`` in front for descending)."""
    column = columns[sort.removeprefix("-")]
    ordered = column.desc() if sort.startswith("-") else column.asc()
    return ordered.nulls_last(), tiebreak
