"""``kbk_`` key values: format, prefix parsing and the constant-time hash check (no database)."""

from __future__ import annotations

import hashlib
import re

import pytest

from knobridge.apikeys.tokens import api_key_prefix, generate_api_key, key_matches

KEY_FORMAT = re.compile(r"^kbk_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")


def test_generate_api_key_format_and_hash() -> None:
    generated = generate_api_key()

    match = KEY_FORMAT.fullmatch(generated.value)
    assert match is not None
    assert generated.prefix == match.group(1)
    assert generated.hash == hashlib.sha256(generated.value.encode()).hexdigest()


def test_generate_api_key_is_random() -> None:
    assert generate_api_key().value != generate_api_key().value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "kbk_",
        "kbr_abcdefgh_" + "a" * 43,
        "kbk_ABCDEFGH_" + "a" * 43,
        "kbk_abcdefgh_" + "a" * 42,
    ],
)
def test_api_key_prefix_rejects_malformed(value: str) -> None:
    assert api_key_prefix(value) is None


def test_api_key_prefix_of_valid_key() -> None:
    generated = generate_api_key()

    assert api_key_prefix(generated.value) == generated.prefix


def test_key_matches() -> None:
    generated = generate_api_key()

    assert key_matches(generated.value, generated.hash)
    assert not key_matches(generated.value, "f" * 64)
    assert not key_matches(generated.value, None)
