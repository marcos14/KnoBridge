from __future__ import annotations

import pytest

from knobridge.security.passwords import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    Argon2Params,
    PasswordHasher,
    VerifyResult,
    WeakPasswordError,
    validate_password,
)

# Cheap parameters keep the suite fast; production uses the Argon2Params defaults.
CHEAP = Argon2Params(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery staple"  # noqa: S105 - test value


def test_password_hash_and_verify() -> None:
    hasher = PasswordHasher(CHEAP)

    password_hash = hasher.hash(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash
    assert hasher.verify(password_hash, PASSWORD) is True
    assert hasher.verify(password_hash, "wrong password!!") is False


def test_password_hash_is_salted() -> None:
    hasher = PasswordHasher(CHEAP)

    assert hasher.hash(PASSWORD) != hasher.hash(PASSWORD)


def test_password_verify_rejects_malformed_hash() -> None:
    hasher = PasswordHasher(CHEAP)

    assert hasher.verify("not-a-hash", PASSWORD) is False


def test_password_rehash_when_params_change() -> None:
    old_hash = PasswordHasher(CHEAP).hash(PASSWORD)
    stronger = PasswordHasher(Argon2Params(time_cost=2, memory_cost=16, parallelism=1))

    result = stronger.verify_and_update(old_hash, PASSWORD)

    assert stronger.needs_rehash(old_hash) is True
    assert result.valid is True
    assert result.new_hash is not None
    assert stronger.needs_rehash(result.new_hash) is False
    assert stronger.verify(result.new_hash, PASSWORD) is True


def test_password_verify_and_update_keeps_current_hash() -> None:
    hasher = PasswordHasher(CHEAP)
    current = hasher.hash(PASSWORD)

    assert hasher.verify_and_update(current, PASSWORD) == VerifyResult(valid=True)


def test_password_verify_and_update_rejects_wrong_password() -> None:
    hasher = PasswordHasher(CHEAP)
    current = hasher.hash(PASSWORD)

    assert hasher.verify_and_update(current, "wrong password!!") == VerifyResult(valid=False)


def test_password_hasher_defaults_to_rfc9106_low_memory_profile() -> None:
    assert PasswordHasher().needs_rehash(PasswordHasher(CHEAP).hash(PASSWORD)) is True
    assert Argon2Params() == Argon2Params(time_cost=3, memory_cost=65536, parallelism=4)


def test_password_policy_accepts_minimum_length() -> None:
    validate_password("a" * MIN_PASSWORD_LENGTH)


def test_password_policy_rejects_short_password() -> None:
    with pytest.raises(WeakPasswordError) as raised:
        validate_password("a" * (MIN_PASSWORD_LENGTH - 1))

    assert raised.value.status_code == 422
    assert raised.value.details == {"min_length": MIN_PASSWORD_LENGTH}


def test_password_policy_rejects_huge_password() -> None:
    with pytest.raises(WeakPasswordError) as raised:
        validate_password("a" * (MAX_PASSWORD_LENGTH + 1))

    assert raised.value.details == {"max_length": MAX_PASSWORD_LENGTH}


def test_password_policy_counts_characters_not_bytes() -> None:
    validate_password("ç" * MIN_PASSWORD_LENGTH)
