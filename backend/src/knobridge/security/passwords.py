"""Password hashing (argon2id) and the password policy.

Hashes are PHC strings (``$argon2id$v=19$m=...,t=...,p=...$salt$hash``) that carry their own
parameters, so raising the cost later only needs :meth:`PasswordHasher.verify_and_update`
at login: old hashes still verify and get replaced by one with the current parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from argon2 import PasswordHasher as _Argon2Hasher
from argon2 import Type
from argon2.exceptions import InvalidHashError, VerificationError

from knobridge.core.errors import KnoBridgeError

MIN_PASSWORD_LENGTH = 12
# Upper bound so a huge input cannot be used to burn CPU in the hash; far above any passphrase.
MAX_PASSWORD_LENGTH = 1024


class WeakPasswordError(KnoBridgeError):
    code = "weak_password"
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY


def validate_password(password: str) -> None:
    """Enforce the policy: 12 to 1024 characters, nothing else (no composition rules)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must have at least {MIN_PASSWORD_LENGTH} characters.",
            details={"min_length": MIN_PASSWORD_LENGTH},
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must have at most {MAX_PASSWORD_LENGTH} characters.",
            details={"max_length": MAX_PASSWORD_LENGTH},
        )


@dataclass(frozen=True)
class Argon2Params:
    """argon2id cost. Defaults follow RFC 9106's low-memory profile (argon2-cffi defaults)."""

    time_cost: int = 3
    memory_cost: int = 65536  # KiB
    parallelism: int = 4


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    # A fresh hash with the current parameters when the stored one is outdated; else None.
    new_hash: str | None = None


class PasswordHasher:
    def __init__(self, params: Argon2Params | None = None) -> None:
        resolved = params if params is not None else Argon2Params()
        self._hasher = _Argon2Hasher(
            time_cost=resolved.time_cost,
            memory_cost=resolved.memory_cost,
            parallelism=resolved.parallelism,
            type=Type.ID,
        )

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        """``True`` when ``password`` matches; ``False`` for a mismatch or a malformed hash."""
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)

    def verify_and_update(self, password_hash: str, password: str) -> VerifyResult:
        """Verify and, on success with outdated parameters, return the replacement hash."""
        if not self.verify(password_hash, password):
            return VerifyResult(valid=False)
        if self.needs_rehash(password_hash):
            return VerifyResult(valid=True, new_hash=self.hash(password))
        return VerifyResult(valid=True)
