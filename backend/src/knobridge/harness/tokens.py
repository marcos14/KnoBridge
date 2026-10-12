"""Runner tokens: ``kbr_<prefix>_<secret>`` (docs/specs/runner.md, "Token de runner").

The prefix (8 characters of ``[a-z0-9]``) is public: it is stored in clear, unique in the
instance, and is how authentication finds the runner before the workspace is known. The secret
is 32 random bytes in URL-safe base64 without padding (43 characters). Only the SHA-256 (hex)
of the whole token is stored; the token itself exists once, in the value returned at creation.
"""

from __future__ import annotations

import hmac
import re
import secrets
import string
from dataclasses import dataclass

from knobridge.harness.models import TOKEN_PREFIX_LENGTH
from knobridge.security.tokens import hash_token

TOKEN_SCHEME = "kbr"  # noqa: S105 - public marker of the format, not a secret
SECRET_BYTES = 32
_PREFIX_ALPHABET = string.ascii_lowercase + string.digits
_TOKEN_PATTERN = re.compile(r"^kbr_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")
# Compared when no runner has the prefix, so an unknown prefix costs the same as a wrong secret.
_DUMMY_HASH = "0" * 64


@dataclass(frozen=True)
class RunnerToken:
    """A freshly generated token: hand ``value`` to the user once, store only ``hash``."""

    value: str
    prefix: str
    hash: str


def generate_runner_token() -> RunnerToken:
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(TOKEN_PREFIX_LENGTH))
    value = f"{TOKEN_SCHEME}_{prefix}_{secrets.token_urlsafe(SECRET_BYTES)}"
    return RunnerToken(value=value, prefix=prefix, hash=hash_token(value))


def token_prefix(token: str) -> str | None:
    """The prefix of a well-formed token; ``None`` for anything else."""
    match = _TOKEN_PATTERN.fullmatch(token)
    return None if match is None else match.group(1)


def token_matches(token: str, stored_hash: str | None) -> bool:
    """Constant-time check of ``token`` against the stored hash (``None``: no such runner)."""
    expected = _DUMMY_HASH if stored_hash is None else stored_hash
    return hmac.compare_digest(hash_token(token), expected) and stored_hash is not None
