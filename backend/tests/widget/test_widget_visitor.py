"""The visitor's conversation token ``kbv_`` (``widget/visitor.py``): format, hash and the
``Authorization`` header."""

from __future__ import annotations

import hashlib
import re

import pytest

from knobridge.widget.visitor import (
    InvalidVisitorTokenError,
    generate_visitor_token,
    hash_visitor_token,
    visitor_token_hash,
)


def test_visitor_token_has_the_spec_format_and_is_new_each_time() -> None:
    first, second = generate_visitor_token(), generate_visitor_token()

    assert re.fullmatch(r"kbv_[A-Za-z0-9_-]{43}", first)
    assert first != second


def test_visitor_token_hash_is_the_sha256_hex_of_the_whole_token() -> None:
    token = generate_visitor_token()

    assert hash_visitor_token(token) == hashlib.sha256(token.encode()).hexdigest()


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_visitor_token_hash_reads_the_bearer_header(scheme: str) -> None:
    token = generate_visitor_token()

    assert visitor_token_hash(f"{scheme} {token}") == hash_visitor_token(token)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Basic kbv_" + "a" * 43,
        "Bearer kbk_" + "a" * 43,
        "Bearer kbv_" + "a" * 42,
        "Bearer kbv_" + "a" * 44,
        "Bearer kbv_" + "a" * 42 + "!",
    ],
    ids=["absent", "empty", "no-token", "scheme", "prefix", "short", "long", "character"],
)
def test_visitor_token_hash_refuses_missing_or_malformed_tokens(header: str | None) -> None:
    with pytest.raises(InvalidVisitorTokenError) as caught:
        visitor_token_hash(header)

    assert (caught.value.status_code, caught.value.code) == (401, "invalid_visitor_token")
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}
