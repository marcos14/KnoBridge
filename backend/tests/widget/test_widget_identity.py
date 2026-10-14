"""The signed identity of the widget visitor (``widget/identity.py``), with the reproducible
example of ``docs/specs/widget.md`` and every reason of refusal, in the order of the spec."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from knobridge.widget.identity import (
    IdentityRejection,
    VisitorIdentity,
    WidgetIdentityInvalidError,
    sign_identity,
    verify_identity,
)

SECRET = "kbs_teste-NAO-use-em-producao-0123456789abcdefg"  # noqa: S105 - spec test value
PAYLOAD = (
    "eyJzdWIiOiJjbGllbnRlLTQyIiwibmFtZSI6IkFuYSBTb3V6YSIsImVtYWlsIjoiYW5hQGV4ZW1wbG8uY29tLmJyIiwi"
    "aWF0IjoxNzkxODAwMDAwLCJleHAiOjE3OTE4MDM2MDB9"
)
SIGNATURE = "880cf2b97633c3f6e883162cbdb90e927e79642940f40d8f81f79a9e0b10bec2"
IDENTITY = f"v1.{PAYLOAD}.{SIGNATURE}"
VALID_AT = datetime(2026, 10, 12, 10, 30, tzinfo=UTC)
IAT = datetime(2026, 10, 12, 10, 13, 20, tzinfo=UTC)
EXP = datetime(2026, 10, 12, 11, 13, 20, tzinfo=UTC)


def _verify(identity: str, now: datetime = VALID_AT, *, skew: int = 60) -> VisitorIdentity:
    return verify_identity(identity, secret=SECRET, now=now, clock_skew=skew)


def _reason(identity: str, now: datetime = VALID_AT, *, secret: str | None = SECRET) -> str:
    with pytest.raises(WidgetIdentityInvalidError) as caught:
        verify_identity(identity, secret=secret, now=now, clock_skew=60)
    assert caught.value.status_code == 401
    assert caught.value.code == "widget_identity_invalid"
    assert caught.value.details == {"reason": caught.value.reason.value}
    return caught.value.reason.value


def _signed(claims: object, *, raw: bytes | None = None) -> str:
    data = raw if raw is not None else json.dumps(claims, separators=(",", ":")).encode()
    payload = base64.urlsafe_b64encode(data).rstrip(b"=").decode()
    return f"v1.{payload}.{sign_identity(SECRET, payload)}"


def _claims(**overrides: object) -> dict[str, object]:
    claims: dict[str, object] = {
        "sub": "cliente-42",
        "iat": int(IAT.timestamp()),
        "exp": int(EXP.timestamp()),
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def test_identity_of_the_spec_example_is_valid() -> None:
    assert sign_identity(SECRET, PAYLOAD) == SIGNATURE

    identity = _verify(IDENTITY)

    assert identity == VisitorIdentity(
        sub="cliente-42", name="Ana Souza", email="ana@exemplo.com.br"
    )


def test_identity_of_the_spec_example_expires_61_seconds_after_exp() -> None:
    assert _verify(IDENTITY, EXP + timedelta(seconds=60)).sub == "cliente-42"
    assert _reason(IDENTITY, datetime(2026, 10, 12, 11, 14, 21, tzinfo=UTC)) == "expired"


def test_identity_of_the_spec_example_is_not_yet_valid_61_seconds_before_iat() -> None:
    assert _verify(IDENTITY, IAT - timedelta(seconds=60)).sub == "cliente-42"
    assert _reason(IDENTITY, datetime(2026, 10, 12, 10, 12, 19, tzinfo=UTC)) == "not_yet_valid"


def test_identity_clock_skew_is_configurable() -> None:
    with pytest.raises(WidgetIdentityInvalidError) as caught:
        _verify(IDENTITY, EXP + timedelta(seconds=1), skew=0)

    assert caught.value.reason is IdentityRejection.EXPIRED


def test_identity_with_a_changed_payload_fails_the_signature() -> None:
    changed = PAYLOAD[:10] + ("A" if PAYLOAD[10] != "A" else "B") + PAYLOAD[11:]

    assert _reason(f"v1.{changed}.{SIGNATURE}") == "signature"


def test_identity_signed_with_another_secret_fails_the_signature() -> None:
    other = "kbs_" + "x" * 43

    assert _reason(IDENTITY, secret=other) == "signature"


def test_identity_without_a_secret_is_not_configured() -> None:
    assert _reason("anything", secret=None) == "not_configured"


@pytest.mark.parametrize(
    "identity",
    [
        "",
        f"v2.{PAYLOAD}.{SIGNATURE}",
        f"{PAYLOAD}.{SIGNATURE}",
        f"v1.{PAYLOAD}.{SIGNATURE}.x",
        f"v1.{PAYLOAD}=.{SIGNATURE}",
        f"v1.{PAYLOAD}.{SIGNATURE.upper()}",
        f"v1.{PAYLOAD}.{SIGNATURE[:-1]}",
        f"v1..{SIGNATURE}",
        # A base64url text of 4n+1 characters decodes to nothing.
        f"v1.AAAAA.{SIGNATURE}",
        "v1." + "A" * 4100 + f".{SIGNATURE}",
        f"v1.{'A' * 2736}.{SIGNATURE}",
    ],
    ids=[
        "empty",
        "version",
        "two-parts",
        "four-parts",
        "padding",
        "upper-hex",
        "short-signature",
        "empty-payload",
        "bad-base64",
        "too-long",
        "payload-too-big",
    ],
)
def test_identity_out_of_format_is_malformed(identity: str) -> None:
    assert _reason(identity) == "malformed"


@pytest.mark.parametrize(
    ("claims", "raw"),
    [
        (None, b"not json"),
        (None, b'"text"'),
        (None, b"[1, 2]"),
        (None, b"\xff"),
        (_claims(sub=None), None),
        (_claims(sub=""), None),
        (_claims(sub="x" * 201), None),
        (_claims(sub=42), None),
        (_claims(name=""), None),
        (_claims(name=["Ana"]), None),
        (_claims(email="not an e-mail"), None),
        (_claims(email="a" * 312 + "@exemplo.com"), None),
        (_claims(email=7), None),
        (_claims(iat=None), None),
        (_claims(exp="1791803600"), None),
        (_claims(iat=True), None),
        (_claims(exp=1.5), None),
        (_claims(exp=int(IAT.timestamp())), None),
    ],
    ids=[
        "not-json",
        "string",
        "list",
        "not-utf8",
        "no-sub",
        "empty-sub",
        "long-sub",
        "number-sub",
        "empty-name",
        "list-name",
        "bad-email",
        "long-email",
        "number-email",
        "no-iat",
        "text-exp",
        "bool-iat",
        "float-exp",
        "exp-not-after-iat",
    ],
)
def test_identity_with_invalid_claims_is_refused(claims: object, raw: bytes | None) -> None:
    identity = _signed(claims, raw=raw)

    assert _reason(identity) == "claims"


def test_identity_lifetime_above_a_day_is_refused() -> None:
    longest = _signed(_claims(exp=int((IAT + timedelta(days=1)).timestamp())))
    too_long = _signed(_claims(exp=int((IAT + timedelta(days=1, seconds=1)).timestamp())))

    assert _verify(longest).sub == "cliente-42"
    assert _reason(too_long) == "lifetime_too_long"


def test_identity_keeps_only_known_claims_and_optional_ones_may_be_missing() -> None:
    identity = _signed(_claims(role="admin", name=None, email=None))

    assert _verify(identity) == VisitorIdentity(sub="cliente-42", name=None, email=None)
