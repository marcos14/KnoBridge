"""``KnoBridge-Signature``: HMAC-SHA256 of ``"<t>.<body>"`` keyed by the ``kbw_`` secret, and the
receiver's verification from the spec (tolerance, extra pairs, several ``v1``)."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from knobridge.tickets.signature import compute_signature, signature_header, verify_signature

SECRET = "kbw_" + "s" * 43  # synthetic
BODY = b'{"event":"ticket.test","version":1}'
T = 1_760_270_400


def test_compute_signature_is_hmac_of_timestamp_dot_body() -> None:
    expected = hmac.new(SECRET.encode(), f"{T}.".encode() + BODY, hashlib.sha256).hexdigest()

    assert compute_signature(SECRET, T, BODY) == expected


def test_signature_header_has_t_and_v1() -> None:
    assert signature_header(SECRET, T, BODY) == f"t={T},v1={compute_signature(SECRET, T, BODY)}"


def test_verify_signature_accepts_own_header() -> None:
    assert verify_signature(signature_header(SECRET, T, BODY), secret=SECRET, body=BODY, now=T)


@pytest.mark.parametrize("now", [T + 300, T - 300])
def test_verify_signature_accepts_edge_of_tolerance(now: int) -> None:
    assert verify_signature(signature_header(SECRET, T, BODY), secret=SECRET, body=BODY, now=now)


@pytest.mark.parametrize("now", [T + 301, T - 301])
def test_verify_signature_refuses_outside_tolerance(now: int) -> None:
    header = signature_header(SECRET, T, BODY)

    assert not verify_signature(header, secret=SECRET, body=BODY, now=now)


def test_verify_signature_refuses_changed_body() -> None:
    header = signature_header(SECRET, T, BODY)

    assert not verify_signature(header, secret=SECRET, body=BODY + b" ", now=T)


def test_verify_signature_refuses_other_secret() -> None:
    header = signature_header(SECRET, T, BODY)

    assert not verify_signature(header, secret="kbw_" + "o" * 43, body=BODY, now=T)


def test_verify_signature_ignores_unknown_pairs_and_accepts_any_v1() -> None:
    good = compute_signature(SECRET, T, BODY)
    header = f"v0=abc, t={T}, v1={'0' * 64}, v1={good}, x"

    assert verify_signature(header, secret=SECRET, body=BODY, now=T)


@pytest.mark.parametrize(
    "header",
    ["", "v1=abc", "t=abc,v1=abc", f"t={T}", f"t={T},v1=é"],
)
def test_verify_signature_refuses_malformed_header(header: str) -> None:
    assert not verify_signature(header, secret=SECRET, body=BODY, now=T)
