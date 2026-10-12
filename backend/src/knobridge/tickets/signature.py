"""``KnoBridge-Signature`` of the ticket webhook (docs/specs/chamados.md, "Cabeçalhos e
assinatura"). Pure: no clock, no IO.

``t=<unix seconds>,v1=<hex HMAC-SHA256>``, keyed by the whole ``kbw_`` secret (UTF-8) over
``"<t>.<body>"``. ``verify_signature`` is the receiver's side, as the spec describes it: the
reference for integrators and the check of the test receivers.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_HEADER = "KnoBridge-Signature"
# Largest accepted distance between ``t`` and the receiver's clock (replay protection).
DEFAULT_TOLERANCE_SECONDS = 300


def compute_signature(secret: str, timestamp: int, body: bytes) -> str:
    """Hex HMAC-SHA256 of ``"<timestamp>.<body>"`` with ``secret``."""
    message = str(timestamp).encode("ascii") + b"." + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def signature_header(secret: str, timestamp: int, body: bytes) -> str:
    return f"t={timestamp},v1={compute_signature(secret, timestamp, body)}"


def verify_signature(
    header: str,
    *,
    secret: str,
    body: bytes,
    now: int,
    tolerance: int = DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """Whether ``header`` signs ``body`` with ``secret`` at a time within ``tolerance`` of
    ``now`` (unknown pairs ignored; any matching ``v1`` accepted)."""
    timestamp: int | None = None
    candidates: list[str] = []
    for pair in header.split(","):
        key, _, value = pair.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1":
            candidates.append(value)
    if timestamp is None or abs(now - timestamp) > tolerance:
        return False
    expected = compute_signature(secret, timestamp, body).encode("ascii")
    # Bytes, so a non-ASCII candidate is just a mismatch; every candidate is compared, so
    # the time taken does not depend on which one matches.
    matches = [hmac.compare_digest(expected, candidate.encode()) for candidate in candidates]
    return any(matches)
