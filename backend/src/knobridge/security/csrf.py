"""CSRF protection by signed double-submit.

On login the API sets a readable (not ``httpOnly``) cookie with a CSRF token; the frontend
copies it into the ``X-CSRF-Token`` header of every unsafe request. A cross-site page can
make the browser send the cookie but cannot read it, so it cannot fill the header. The
token is ``<nonce>.<HMAC-SHA256(secret_key, nonce)>``: a cookie planted by a sibling
subdomain without the key fails the signature check.

:func:`require_csrf` is the FastAPI dependency for routers that use the session cookie;
safe methods (GET, HEAD, OPTIONS, TRACE) pass untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from http import HTTPStatus

from fastapi import Request, Response

from knobridge.core.errors import KnoBridgeError
from knobridge.core.settings import Settings

CSRF_COOKIE_NAME = "knobridge_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})
_NONCE_BYTES = 32


class CsrfError(KnoBridgeError):
    code = "csrf_failed"
    status_code = HTTPStatus.FORBIDDEN


def _sign(secret_key: str, nonce: str) -> str:
    return hmac.new(secret_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_csrf_token(secret_key: str) -> str:
    nonce = secrets.token_urlsafe(_NONCE_BYTES)
    return f"{nonce}.{_sign(secret_key, nonce)}"


def is_valid_csrf_token(secret_key: str, token: str) -> bool:
    nonce, separator, signature = token.partition(".")
    if not separator or not nonce:
        return False
    return hmac.compare_digest(signature, _sign(secret_key, nonce))


def set_csrf_cookie(response: Response, token: str, settings: Settings) -> None:
    # httponly=False on purpose: the frontend must read it to echo it in the header.
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=int(settings.session_ttl.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


def check_csrf(method: str, cookie: str | None, header: str | None, secret_key: str) -> None:
    """Raise :class:`CsrfError` unless the method is safe or cookie and header match."""
    if method.upper() in SAFE_METHODS:
        return
    if not cookie or not header:
        raise CsrfError("Missing CSRF token.")
    if not hmac.compare_digest(cookie, header) or not is_valid_csrf_token(secret_key, cookie):
        raise CsrfError("Invalid CSRF token.")


def require_csrf(request: Request) -> None:
    """FastAPI dependency; reads the secret from ``app.state.settings`` (set by create_app)."""
    settings: Settings = request.app.state.settings
    check_csrf(
        request.method,
        request.cookies.get(CSRF_COOKIE_NAME),
        request.headers.get(CSRF_HEADER_NAME),
        settings.secret_key.get_secret_value(),
    )
