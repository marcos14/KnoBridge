"""The usage report as CSV: RFC 4180 quoting, empty nulls, 6 places and formula protection."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from knobridge.usage.csv_export import HEADER, csv_filename, safe_text, usage_csv, usd
from knobridge.usage.period import Period
from knobridge.usage.report import (
    ChatUsage,
    EmbeddingUsage,
    UsageGroup,
    UsageReport,
    UsageRow,
    UsageTotals,
)

PERIOD = Period(datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=SUM(A1:A2)", "'=SUM(A1:A2)"),
        ("+55 11", "'+55 11"),
        ("-1", "'-1"),
        ("@cmd", "'@cmd"),
        ("Suporte = ERP", "Suporte = ERP"),
        ("", ""),
    ],
)
def test_safe_text_neutralizes_formulas(value: str, expected: str) -> None:
    assert safe_text(value) == expected


def test_usd_has_six_places() -> None:
    assert usd(Decimal("0.0584")) == "0.058400"
    assert usd(Decimal(0)) == "0.000000"


def test_usage_csv_lines() -> None:
    chat = ChatUsage(
        input_tokens=98000,
        output_tokens=12000,
        cost_usd=Decimal("0.0584"),
        answers=120,
        unpriced_answers=3,
    )
    report = UsageReport(
        period=PERIOD,
        group_by=UsageGroup.ASSISTANT,
        totals=UsageTotals(
            embedding=EmbeddingUsage(tokens=1250000, cost_usd=Decimal("0.025"), runs=14),
            chat=chat,
        ),
        rows=[
            UsageRow(key="6f1c", label="Suporte, ERP", chat=chat),
            UsageRow(key="7a2d", label="-Vendas", embedding=EmbeddingUsage()),
        ],
    )

    lines = usage_csv(report).split("\r\n")

    assert lines == [
        ",".join(HEADER),
        '6f1c,"Suporte, ERP",,,,,98000,12000,0.058400,120,3,0.058400',
        "7a2d,'-Vendas,0,0.000000,0,0,,,,,,0.000000",
        "total,Total,1250000,0.025000,14,0,98000,12000,0.058400,120,3,0.083400",
        "",
    ]


def test_csv_filename_has_group_and_dates() -> None:
    report = UsageReport(
        period=PERIOD,
        group_by=UsageGroup.API_KEY,
        totals=UsageTotals(EmbeddingUsage(), ChatUsage()),
        rows=[],
    )

    assert csv_filename(report) == "knobridge-uso-api_key-2026-09-01-2026-10-01.csv"
