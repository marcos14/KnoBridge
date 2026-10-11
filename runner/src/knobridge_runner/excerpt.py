"""Excerpts of verified evidence and secret redaction (docs/specs/harness.md, "Excertos").

Redaction applies to every text that leaves the machine: excerpts, item texts and rejection
labels. Each occurrence becomes ``[REDACTED]``. The list is conservative on purpose: a false
positive hides a value in an excerpt; a false negative leaks a secret.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from knobridge_runner.protocol_result import MAX_EXCERPT_BYTES

REDACTED = "[REDACTED]"
ELLIPSIS = "…"
MAX_EXCERPT_LINE_CHARS = 400

_FLAGS_I = re.IGNORECASE
_ASSIGNMENT_NAMES = (
    r"(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key"
    r"|client[_-]?secret|private[_-]?key)"
)
# (pattern, group): group 0 replaces the whole match, group 1 only the captured value.
_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----(?:.*?-----END [A-Z ]*PRIVATE KEY-----|.*\Z)",
            re.DOTALL,
        ),
        0,
    ),
    (re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"), 0),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}"), 0),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), 0),
    (re.compile(r"xox[abposr]-[A-Za-z0-9-]{10,}"), 0),
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), 0),
    (re.compile(r"kbr_[a-z0-9]{8}_[A-Za-z0-9_-]{43}"), 0),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), 0),
    (re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@]+:([^@\s/]+)@", _FLAGS_I), 1),
    (re.compile(_ASSIGNMENT_NAMES + r"[\"']?\s*[:=]\s*[\"']?([^\s\"',;]{4,})", _FLAGS_I), 1),
)

_SENSITIVE_NAMES = frozenset(
    {".npmrc", ".pypirc", ".netrc", ".git-credentials", "credentials.json"}
)
_SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")
_SENSITIVE_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "secrets.")
_ENV_EXAMPLES = frozenset({".env.example", ".env.sample", ".env.template"})


def redact(text: str) -> tuple[str, int]:
    """TEXT with every secret replaced by ``[REDACTED]``, and the number of replacements."""
    count = 0
    for pattern, group in _PATTERNS:

        def replace(match: re.Match[str], group: int = group) -> str:
            nonlocal count
            if match.group(group) == REDACTED:
                return match.group(0)
            count += 1
            start, end = match.span(group)
            base = match.start(0)
            whole = match.group(0)
            return whole[: start - base] + REDACTED + whole[end - base :]

        text = pattern.sub(replace, text)
    return text, count


def cut(text: str, limit: int) -> str:
    """TEXT cut to LIMIT characters, ending in ``…`` when something was cut."""
    return text if len(text) <= limit else text[: limit - 1] + ELLIPSIS


def is_sensitive_file(path: str) -> bool:
    """Files that never get an excerpt, by name (the evidence itself stays valid)."""
    name = path.rpartition("/")[2].lower()
    if name == ".env" or (name.startswith(".env.") and name not in _ENV_EXAMPLES):
        return True
    return (
        name in _SENSITIVE_NAMES
        or name.endswith(_SENSITIVE_SUFFIXES)
        or name.startswith(_SENSITIVE_PREFIXES)
    )


@dataclass(frozen=True)
class Excerpt:
    text: str | None
    truncated: bool = False
    omitted: Literal["disabled", "sensitive_file"] | None = None
    redactions: int = 0


def _cut_bytes(text: str, limit: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= limit:
        return text
    room = limit - len(ELLIPSIS.encode("utf-8"))
    return encoded[:room].decode("utf-8", errors="ignore") + ELLIPSIS


def make_excerpt(path: str, lines: Sequence[str], start: int, end: int, max_lines: int) -> Excerpt:
    """Lines START..END (1-based, already verified) of LINES, within the excerpt limits."""
    if max_lines <= 0:
        return Excerpt(None, omitted="disabled")
    if is_sensitive_file(path):
        return Excerpt(None, omitted="sensitive_file")
    last = min(end, start + max_lines - 1)
    truncated = last < end
    text, redactions = redact("\n".join(lines[start - 1 : last]))
    shown: list[str] = []
    for line in text.split("\n"):
        short = cut(line, MAX_EXCERPT_LINE_CHARS)
        truncated = truncated or short != line
        shown.append(short)
    joined = "\n".join(shown)
    final = _cut_bytes(joined, MAX_EXCERPT_BYTES)
    return Excerpt(final, truncated or final != joined, None, redactions)
