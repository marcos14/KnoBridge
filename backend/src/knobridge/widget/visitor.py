"""The visitor's conversation token ``kbv_`` (``docs/specs/widget.md``, "Token de conversa").

Shown once, when the conversation is created; the server keeps only the SHA-256 (hex) of the
whole token. The conversation routes take it as ``Authorization: Bearer kbv_…``: absent or
malformed is 401 ``invalid_visitor_token``; a token that matches no conversation of the widget
reads as a missing conversation (404, ``conversations/access.py``). Never logged.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from http import HTTPStatus

from knobridge.core.errors import KnoBridgeError

VISITOR_TOKEN_PREFIX = "kbv_"  # noqa: S105 - a public prefix, not a secret
_TOKEN = re.compile(r"^kbv_[A-Za-z0-9_-]{43}$")
_BEARER = "bearer"


class InvalidVisitorTokenError(KnoBridgeError):
    code = "invalid_visitor_token"
    status_code = HTTPStatus.UNAUTHORIZED
    headers = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012 - read-only class default


def generate_visitor_token() -> str:
    return VISITOR_TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_visitor_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def visitor_token_hash(authorization: str | None) -> str:
    """The hash of the ``Bearer kbv_…`` token of the header, or 401."""
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != _BEARER or not _TOKEN.fullmatch(token):
        raise InvalidVisitorTokenError("Missing or malformed visitor token.")
    return hash_visitor_token(token)
