"""The ``kbi_`` token format: generation, prefix parsing and the constant-time check."""

from __future__ import annotations

import re

import pytest

from knobridge.security.tokens import hash_token
from knobridge.tickets.tokens import generate_ingest_token, ingest_token_prefix, token_matches


def test_generate_ingest_token_format_and_hash() -> None:
    token = generate_ingest_token()

    assert re.fullmatch(r"kbi_[a-z0-9]{8}_[A-Za-z0-9_-]{43}", token.value)
    assert token.prefix == token.value[4:12]
    assert token.hash == hash_token(token.value)


def test_generate_ingest_token_is_random() -> None:
    assert generate_ingest_token().value != generate_ingest_token().value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "kbr_abcdefgh_" + "a" * 43,
        "kbi_ABCDEFGH_" + "a" * 43,
        "kbi_abcdefgh_" + "a" * 42,
        "kbi_abcdefgh_" + "a" * 43 + "\n",
    ],
)
def test_ingest_token_prefix_refuses_malformed(value: str) -> None:
    assert ingest_token_prefix(value) is None


def test_ingest_token_prefix_of_well_formed() -> None:
    token = generate_ingest_token()

    assert ingest_token_prefix(token.value) == token.prefix


def test_token_matches_only_its_hash() -> None:
    token = generate_ingest_token()

    assert token_matches(token.value, token.hash)
    assert not token_matches(token.value, generate_ingest_token().hash)
    assert not token_matches(token.value, None)
