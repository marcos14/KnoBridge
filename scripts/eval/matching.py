"""Citation matchers (``path:``, ``ticket:``, ``card:``) and text normalization
(docs/specs/avaliacao.md, "Perguntas e gabarito")."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

_SPACES = re.compile(r"\s+")
_EXTERNAL_ID = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
_GLOB_CHARS = re.compile(r"^[^\x00-\x1f\x7f\\]{1,500}$")


@dataclass(frozen=True)
class Citation:
    """The part of a ``CitationOut`` the judgement looks at."""

    index: int
    kind: str | None
    uri: str | None
    path: str | None


def normalize(text: str) -> str:
    """Lowercase, no accents (NFKD without marks), runs of whitespace as one space."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _SPACES.sub(" ", stripped).strip()


def matcher_problem(matcher: str) -> str | None:
    """Why ``matcher`` is invalid, or ``None`` when it is well formed."""
    prefix, sep, value = matcher.partition(":")
    if not sep:
        return "expected path:<glob>, ticket:<id> or card:<id>"
    if prefix == "path":
        if not _GLOB_CHARS.match(value) or value.startswith("/"):
            return "expected a relative glob"
        return None
    if prefix in ("ticket", "card"):
        if value != "*" and not _EXTERNAL_ID.match(value):
            return "expected an external_id or *"
        return None
    return f"unknown matcher prefix {prefix!r}"


@lru_cache(maxsize=256)
def _glob_regex(glob: str) -> re.Pattern[str]:
    parts: list[str] = []
    i = 0
    while i < len(glob):
        if glob.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            parts.append(".*")
            i += 2
        elif glob[i] == "*":
            parts.append("[^/]*")
            i += 1
        else:
            parts.append(re.escape(glob[i]))
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def glob_matches(glob: str, path: str) -> bool:
    """``*`` stays inside one path segment; ``**`` spans any depth."""
    return _glob_regex(glob).match(path) is not None


def matches(matcher: str, citation: Citation) -> bool:
    prefix, _, value = matcher.partition(":")
    if prefix == "path":
        return citation.path is not None and glob_matches(value, citation.path)
    if citation.kind != prefix or citation.uri is None:
        return False
    if value == "*":
        return citation.uri.startswith(f"{prefix}:")
    return citation.uri == f"{prefix}:{value}"


def any_matches(matchers: tuple[str, ...], citations: tuple[Citation, ...]) -> bool:
    return any(matches(m, c) for m in matchers for c in citations)
