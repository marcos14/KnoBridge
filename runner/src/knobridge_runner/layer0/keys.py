"""Stable module keys derived from folder paths (docs/specs/harness.md, "Chave do módulo")."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

MAX_KEY_LENGTH = 100
_PREFIX_LENGTH = 91
_NOT_KEY_CHAR = re.compile(r"[^a-z0-9]+")


def _short_hash(origin: str) -> str:
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()[:8]


def key_base(origin: str) -> str:
    """NFKD without accents, lower case, runs of other characters as one '-', no edge hyphens.

    Above 100 characters: the first 91, '-' and 8 hex digits of the SHA-256 of ORIGIN. A path
    with no ASCII letter or digit at all (e.g. only CJK) becomes ``module-<hash>``.
    """
    decomposed = unicodedata.normalize("NFKD", origin)
    ascii_only = "".join(char for char in decomposed if not unicodedata.combining(char))
    key = _NOT_KEY_CHAR.sub("-", ascii_only.lower()).strip("-")
    if not key:
        return f"module-{_short_hash(origin)}"
    if len(key) > MAX_KEY_LENGTH:
        key = f"{key[:_PREFIX_LENGTH].rstrip('-')}-{_short_hash(origin)}"
    return key


def assign_keys(origins: Iterable[str]) -> dict[str, str]:
    """Key per origin path; on collision the first origin in sorted order keeps the key and
    the next ones get ``-2``, ``-3``..."""
    keys: dict[str, str] = {}
    taken: set[str] = set()
    for origin in sorted(set(origins)):
        base = key = key_base(origin)
        counter = 1
        while key in taken:
            counter += 1
            suffix = f"-{counter}"
            key = f"{base[: MAX_KEY_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        taken.add(key)
        keys[origin] = key
    return keys
