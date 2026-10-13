"""The usage report as CSV (RFC 4180, comma, no BOM), safe to open in a spreadsheet.

Text that starts with ``=``, ``+``, ``-`` or ``@`` gets a leading ``'`` so a spreadsheet does
not run it as a formula (OWASP, CSV injection). Missing values are empty; USD has 6 places.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from knobridge.usage.report import ChatUsage, EmbeddingUsage, UsageReport, UsageRow

HEADER = (
    "key",
    "label",
    "embedding_tokens",
    "embedding_cost_usd",
    "runs",
    "unpriced_runs",
    "chat_input_tokens",
    "chat_output_tokens",
    "chat_cost_usd",
    "answers",
    "unpriced_answers",
    "cost_usd",
)
_FORMULA_PREFIXES = ("=", "+", "-", "@")
_USD = Decimal("0.000001")


def safe_text(value: str) -> str:
    """``value`` with a leading ``'`` when a spreadsheet would read it as a formula."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def usd(value: Decimal) -> str:
    return str(value.quantize(_USD))


def _embedding_cells(usage: EmbeddingUsage | None) -> list[str]:
    if usage is None:
        return ["", "", "", ""]
    return [str(usage.tokens), usd(usage.cost_usd), str(usage.runs), str(usage.unpriced_runs)]


def _chat_cells(usage: ChatUsage | None) -> list[str]:
    if usage is None:
        return ["", "", "", "", ""]
    return [
        str(usage.input_tokens),
        str(usage.output_tokens),
        usd(usage.cost_usd),
        str(usage.answers),
        str(usage.unpriced_answers),
    ]


def _line(row: UsageRow) -> list[str]:
    return [
        safe_text(row.key),
        safe_text(row.label),
        *_embedding_cells(row.embedding),
        *_chat_cells(row.chat),
        usd(row.cost_usd),
    ]


def usage_csv(report: UsageReport) -> str:
    """Header, one line per row and a last ``total`` line with every column."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(_line(row) for row in report.rows)
    totals = report.totals
    writer.writerow(
        _line(UsageRow(key="total", label="Total", embedding=totals.embedding, chat=totals.chat))
    )
    return buffer.getvalue()


def csv_filename(report: UsageReport) -> str:
    """``knobridge-uso-<group_by>-<from>-<to>.csv``, with ``-<level>`` when filtered by level
    (the product does not go in the name)."""
    start = report.period.start.date().isoformat()
    end = report.period.end.date().isoformat()
    level = None if report.chat_filter is None else report.chat_filter.level
    suffix = "" if level is None else f"-{level.value}"
    return f"knobridge-uso-{report.group_by.value}-{start}-{end}{suffix}.csv"
