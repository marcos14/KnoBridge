"""API key values: ``kbk_<prefix>_<secret>`` (``docs/specs/api-publica.md``, "Formato").

The prefix (8 characters of ``[a-z0-9]``) is public: stored in clear, unique in the instance,
it is how authentication finds the key before the workspace is known (system mode). The secret
is 32 random bytes in URL-safe base64 (43 characters). Only the SHA-256 (hex) of the whole key
is stored; the key itself exists once, in the value returned at creation.
"""

from __future__ import annotations

import hmac
import re
import secrets
import string
from dataclasses import dataclass

from knobridge.apikeys.models import KEY_PREFIX_LENGTH
from knobridge.security.tokens import hash_token

KEY_SCHEME = "kbk"
SECRET_BYTES = 32
_PREFIX_ALPHABET = string.ascii_lowercase + string.digits
_KEY_PATTERN = re.compile(r"^kbk_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$")
# Compared when no key has the prefix, so an unknown prefix costs the same as a wrong secret.
_DUMMY_HASH = "0" * 64


@dataclass(frozen=True)
class GeneratedKey:
    """A freshly generated key: hand ``value`` to the user once, store only ``hash``."""

    value: str
    prefix: str
    hash: str


def generate_api_key() -> GeneratedKey:
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(KEY_PREFIX_LENGTH))
    value = f"{KEY_SCHEME}_{prefix}_{secrets.token_urlsafe(SECRET_BYTES)}"
    return GeneratedKey(value=value, prefix=prefix, hash=hash_token(value))


def api_key_prefix(key: str) -> str | None:
    """The prefix of a well-formed key; ``None`` for anything else."""
    match = _KEY_PATTERN.fullmatch(key)
    return None if match is None else match.group(1)


def key_matches(key: str, stored_hash: str | None) -> bool:
    """Constant-time check of ``key`` against the stored hash (``None``: no such key)."""
    expected = _DUMMY_HASH if stored_hash is None else stored_hash
    return hmac.compare_digest(hash_token(key), expected) and stored_hash is not None
