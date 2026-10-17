"""Fake reranker for the E2E stack: the ``POST /rerank`` route of the Text Embeddings Inference.

It plays the ``reranker`` service of the compose (docs/specs/indexacao.md, "Reranker") without
downloading the cross-encoder, standard library only, so the E2E layer runs it on a plain
Python image:

- ``POST /rerank`` with ``{"query", "texts", ...}``: ``[{"index", "score"}]``, highest score
  first, ties in input order. The score of a text is the share of the query's words
  (lowercase, without accents) found among its words; a text carrying the marker
  ``[[rerank-top]]`` scores 1.0, so the E2E sees the order change with the product option on;
- ``GET /health``: readiness.

Usage: ``python fake_reranker.py [--host HOST] [--port PORT]``. Development and E2E only.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

TOP_MARKER = "[[rerank-top]]"

Payload = dict[str, object] | list[dict[str, object]]

_WORD = re.compile(r"\w+")


def words(text: str) -> set[str]:
    """Lowercase words of ``text`` without accents."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return set(_WORD.findall(plain))


def score(query: str, text: str) -> float:
    if TOP_MARKER in text:
        return 1.0
    wanted = words(query)
    if not wanted:
        return 0.0
    return len(wanted & words(text)) / len(wanted)


def rerank(query: str, texts: list[str]) -> list[dict[str, object]]:
    scores = [score(query, text) for text in texts]
    order = sorted(range(len(texts)), key=lambda index: (-scores[index], index))
    return [{"index": index, "score": scores[index]} for index in order]


def handle(method: str, path: str, body: bytes) -> tuple[int, Payload]:
    if method == "GET" and path == "/health":
        return 200, {"ok": True}
    if method == "POST" and path == "/rerank":
        return _rerank(body)
    return 404, {"error": "not_found"}


def _rerank(body: bytes) -> tuple[int, Payload]:
    try:
        parsed: object = json.loads(body)
    except ValueError:
        return 400, {"error": "invalid_json"}
    if not isinstance(parsed, dict):
        return 400, {"error": "invalid_body"}
    request = cast(dict[str, object], parsed)
    query = request.get("query")
    texts = request.get("texts")
    if not isinstance(query, str) or not isinstance(texts, list):
        return 422, {"error": "query_and_texts_required"}
    items = cast(list[object], texts)
    if not all(isinstance(text, str) for text in items):
        return 422, {"error": "texts_must_be_strings"}
    return 200, rerank(query, [str(text) for text in items])


def handler_for() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            status, payload = handle(self.command, self.path, body)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = _serve  # noqa: N815 - names fixed by BaseHTTPRequestHandler
        do_POST = _serve  # noqa: N815

    return Handler


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_for())


def _serve_forever(server: ThreadingHTTPServer) -> None:
    server.serve_forever()


def main(
    argv: list[str] | None = None,
    *,
    serve: Callable[[ThreadingHTTPServer], None] = _serve_forever,
) -> int:
    parser = argparse.ArgumentParser(description="Fake TEI reranker (E2E).")
    # Inside the E2E compose network only; the service publishes no host port.
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104
    parser.add_argument("--port", type=int, default=80)
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port)
    try:
        serve(server)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
