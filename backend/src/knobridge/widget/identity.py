"""The signed identity of a widget visitor (``docs/specs/widget.md``, "Identidade assinada").

``v1.<payload>.<signature>``: the payload is the JSON of the claims in base64url without
padding; the signature is ``HMAC-SHA256(kbs_ secret, "v1." + payload)`` in lowercase hex. The
message is the exact text sent, so there is no JSON canonicalization. Checked in the order of
the spec, the signature before any claim is read; the clock is the caller's (injected). The
identity only identifies: it never raises the level of the conversation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from http import HTTPStatus
from typing import cast

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from knobridge.core.errors import KnoBridgeError
from knobridge.tickets.wire import Email

VERSION = "v1"
IDENTITY_MAX_CHARS = 4096
PAYLOAD_MAX_BYTES = 2048
TEXT_MAX_CHARS = 200
EMAIL_MAX_CHARS = 320
MAX_LIFETIME_SECONDS = 86_400
_PAYLOAD = re.compile(r"^[A-Za-z0-9_-]+$")
_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = TypeAdapter[str](Email)


class IdentityRejection(StrEnum):
    """Why an identity was refused (``details.reason`` of the 401)."""

    NOT_CONFIGURED = "not_configured"
    MALFORMED = "malformed"
    SIGNATURE = "signature"
    CLAIMS = "claims"
    LIFETIME_TOO_LONG = "lifetime_too_long"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"


class WidgetIdentityInvalidError(KnoBridgeError):
    code = "widget_identity_invalid"
    status_code = HTTPStatus.UNAUTHORIZED

    def __init__(self, reason: IdentityRejection) -> None:
        super().__init__("The visitor identity was refused.", details={"reason": reason.value})
        self.reason = reason


@dataclass(frozen=True)
class VisitorIdentity:
    """The verified claims kept on the conversation."""

    sub: str
    name: str | None
    email: str | None


def sign_identity(secret: str, payload: str) -> str:
    """The lowercase hex signature of ``payload`` (already base64url) with ``secret``."""
    message = f"{VERSION}.{payload}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_identity(
    identity: str, *, secret: str | None, now: datetime, clock_skew: int
) -> VisitorIdentity:
    """The claims of ``identity``; ``WidgetIdentityInvalidError`` with the first failed step."""
    if secret is None:
        raise WidgetIdentityInvalidError(IdentityRejection.NOT_CONFIGURED)
    payload, signature, raw = _split(identity)
    if not hmac.compare_digest(sign_identity(secret, payload), signature):
        raise WidgetIdentityInvalidError(IdentityRejection.SIGNATURE)
    claims = _claims(raw)
    if claims.exp - claims.iat > MAX_LIFETIME_SECONDS:
        raise WidgetIdentityInvalidError(IdentityRejection.LIFETIME_TOO_LONG)
    moment = now.timestamp()
    if moment < claims.iat - clock_skew:
        raise WidgetIdentityInvalidError(IdentityRejection.NOT_YET_VALID)
    if moment > claims.exp + clock_skew:
        raise WidgetIdentityInvalidError(IdentityRejection.EXPIRED)
    return VisitorIdentity(sub=claims.sub, name=claims.name, email=claims.email)


def _split(identity: str) -> tuple[str, str, bytes]:
    """Payload text, signature and decoded payload, or ``malformed``."""
    parts = identity.split(".")
    if len(identity) > IDENTITY_MAX_CHARS or len(parts) != 3 or parts[0] != VERSION:
        raise WidgetIdentityInvalidError(IdentityRejection.MALFORMED)
    _, payload, signature = parts
    if not _PAYLOAD.fullmatch(payload) or not _SIGNATURE.fullmatch(signature):
        raise WidgetIdentityInvalidError(IdentityRejection.MALFORMED)
    try:
        raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    except (binascii.Error, ValueError) as exc:
        raise WidgetIdentityInvalidError(IdentityRejection.MALFORMED) from exc
    if len(raw) > PAYLOAD_MAX_BYTES:
        raise WidgetIdentityInvalidError(IdentityRejection.MALFORMED)
    return payload, signature, raw


@dataclass(frozen=True)
class _Claims:
    sub: str
    name: str | None
    email: str | None
    iat: int
    exp: int


def _claims(raw: bytes) -> _Claims:
    try:
        decoded: object = json.loads(raw)
    except ValueError as exc:  # also UnicodeDecodeError
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS) from exc
    if not isinstance(decoded, dict):
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS)
    # JSON object keys are always text.
    claims = cast(dict[str, object], decoded)
    sub = _text(claims.get("sub"))
    name = None if claims.get("name") is None else _text(claims.get("name"))
    email = _email(claims.get("email"))
    iat, exp = _seconds(claims.get("iat")), _seconds(claims.get("exp"))
    if exp <= iat:
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS)
    return _Claims(sub=sub, name=name, email=email, iat=iat, exp=exp)


def _text(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= TEXT_MAX_CHARS:
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS)
    return value


def _email(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > EMAIL_MAX_CHARS:
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS)
    try:
        return _EMAIL.validate_python(value)
    except PydanticValidationError as exc:
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS) from exc


def _seconds(value: object) -> int:
    # ``bool`` is an ``int`` in Python, never a timestamp.
    if not isinstance(value, int) or isinstance(value, bool):
        raise WidgetIdentityInvalidError(IdentityRejection.CLAIMS)
    return value
