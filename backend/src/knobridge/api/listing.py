"""Query parameters shared by the paginated lists."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query

from knobridge.core.listing import QUERY_MAX_LENGTH

# Case-insensitive substring; empty means no search.
SearchQuery = Annotated[
    str | None,
    Query(max_length=QUERY_MAX_LENGTH, description="Case-insensitive substring."),
]
