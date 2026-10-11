"""Runner token format, prefix parsing and the constant-time hash check."""

from __future__ import annotations

import hashlib
import re

import pytest

from knobridge.harness.tokens import generate_runner_token, token_matches, token_prefix

TOKEN_FORMAT = re.compile(r"^kbr_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")


def test_generate_runner_token_has_spec_format() -> None:
    token = generate_runner_token()

    match = TOKEN_FORMAT.fullmatch(token.value)
    assert match is not None
    assert match.group(1) == token.prefix
    assert token.hash == hashlib.sha256(token.value.encode()).hexdigest()


def test_generate_runner_token_is_random() -> None:
    assert generate_runner_token().value != generate_runner_token().value


@pytest.mark.parametrize(
    "value",
    ["", "kbr_abc_x", "kbr_ABCDEFGH_" + "a" * 43, "kbx_abcdefgh_" + "a" * 43, "kbr_abcdefgh_a"],
)
def test_token_prefix_refuses_malformed(value: str) -> None:
    assert token_prefix(value) is None


def test_token_prefix_of_valid_token() -> None:
    token = generate_runner_token()

    assert token_prefix(token.value) == token.prefix


def test_token_matches_only_its_hash() -> None:
    token = generate_runner_token()
    other = generate_runner_token()

    assert token_matches(token.value, token.hash)
    assert not token_matches(token.value, other.hash)


def test_token_matches_without_runner_is_false() -> None:
    assert not token_matches(generate_runner_token().value, None)
