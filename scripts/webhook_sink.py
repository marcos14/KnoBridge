"""Fake ticket system for the E2E stack: receives "Abrir chamado" and checks the signature.

It plays the destination of an assistant's ticket webhook (docs/specs/chamados.md, "Abrir
chamado"), standard library only, so the E2E compose runs it on a plain Python image:

- ``PUT /secret`` with ``{"secret": "kbw_..."}``: the secret the panel showed once (the test
  sets it after generating it);
- ``POST /hook``: verifies ``KnoBridge-Signature`` (``t`` within 300 s, HMAC-SHA256 of
  ``"<t>.<body>"`` compared in constant time) and answers 401 when it does not match; a
  ``ticket.requested`` gets ``{"ticket_id", "url"}``, the same for every retry of one delivery;
  ``ticket.test`` gets ``{}``;
- ``GET /deliveries``: what arrived, for the test to check; ``GET /health``: readiness.

Usage: ``python webhook_sink.py [--host HOST] [--port PORT]``. Development and E2E only.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

TOLERANCE_SECONDS = 300
TICKET_URL = "https://chamados.example.test/{ticket_id}"

Payload = dict[str, object] | list[dict[str, object]] | None


def parse_signature(header: str) -> tuple[int | None, list[str]]:
    """``t`` and every ``v1`` of ``t=<unix>,v1=<hex>``; other pairs are ignored."""
    timestamp: int | None = None
    signatures: list[str] = []
    for pair in header.split(","):
        name, _, value = pair.strip().partition("=")
        if name == "t" and value.isdigit():
            timestamp = int(value)
        elif name == "v1" and value:
            signatures.append(value)
    return timestamp, signatures


def sign(secret: str, timestamp: int, body: bytes) -> str:
    message = str(timestamp).encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(header: str, body: bytes, secret: str, now: float) -> bool:
    timestamp, signatures = parse_signature(header)
    if timestamp is None or abs(now - timestamp) > TOLERANCE_SECONDS:
        return False
    expected = sign(secret, timestamp, body)
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


@dataclass
class Sink:
    """The fake destination's state and routes, apart from HTTP so tests call it directly."""

    clock: Callable[[], float] = time.time
    secret: str | None = None
    deliveries: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    tickets: dict[str, str] = field(default_factory=dict[str, str])
    lock: Lock = field(default_factory=Lock)

    def handle(
        self, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, Payload]:
        with self.lock:
            if method == "GET" and path == "/health":
                return 200, {"ok": True}
            if method == "GET" and path == "/deliveries":
                return 200, list(self.deliveries)
            if method == "PUT" and path == "/secret":
                return self._set_secret(body)
            if method == "POST" and path == "/hook":
                return self._receive(headers, body)
            return 404, {"error": "not_found"}

    def _set_secret(self, body: bytes) -> tuple[int, Payload]:
        try:
            secret = json.loads(body)["secret"]
        except (ValueError, TypeError, KeyError):
            return 400, {"error": "secret_required"}
        if not isinstance(secret, str) or not secret:
            return 400, {"error": "secret_required"}
        self.secret = secret
        return 200, {"ok": True}

    def _receive(self, headers: dict[str, str], body: bytes) -> tuple[int, Payload]:
        signature = headers.get("knobridge-signature", "")
        verified = self.secret is not None and verify_signature(
            signature, body, self.secret, self.clock()
        )
        event = headers.get("knobridge-event", "")
        delivery_id = headers.get("knobridge-delivery", "")
        record: dict[str, object] = {
            "delivery_id": delivery_id,
            "event": event,
            "verified": verified,
            "ticket_id": None,
            "question": None,
        }
        self.deliveries.append(record)
        if not verified:
            return 401, {"error": "invalid_signature"}
        if event != "ticket.requested":
            return 200, {}
        ticket_id = self.tickets.setdefault(delivery_id, f"KB-{len(self.tickets) + 1:04d}")
        record["ticket_id"] = ticket_id
        record["question"] = json.loads(body).get("question")
        return 200, {"ticket_id": ticket_id, "url": TICKET_URL.format(ticket_id=ticket_id)}


def handler_for(sink: Sink) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            headers = {name.lower(): value for name, value in self.headers.items()}
            status, payload = sink.handle(self.command, self.path, headers, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = _serve  # noqa: N815 - names fixed by BaseHTTPRequestHandler
        do_POST = _serve  # noqa: N815
        do_PUT = _serve  # noqa: N815

    return Handler


def make_server(host: str, port: int, sink: Sink) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_for(sink))


def _serve_forever(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def main(
    argv: list[str] | None = None,
    *,
    serve: Callable[[ThreadingHTTPServer], None] = _serve_forever,
) -> int:
    parser = argparse.ArgumentParser(description="Fake ticket webhook destination (E2E).")
    # Inside the E2E compose network only; never published beyond the host's loopback.
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, Sink())
    try:
        serve(server)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
