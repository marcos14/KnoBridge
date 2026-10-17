from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from fake_reranker import (
    TOP_MARKER,
    _serve_forever,  # pyright: ignore[reportPrivateUsage]
    handle,
    main,
    make_server,
    rerank,
    score,
    words,
)


def test_words_lowercases_and_drops_accents() -> None:
    assert words("Relatório de FECHAMENTO, caixa!") == {"relatorio", "de", "fechamento", "caixa"}


def test_score_is_the_share_of_query_words_in_the_text() -> None:
    assert score("fechar caixa", "Como fechar o caixa do dia") == 1.0
    assert score("fechar caixa relatório", "relatorio do caixa") == pytest.approx(2 / 3)
    assert score("fechar caixa", "nota fiscal") == 0.0


def test_score_gives_the_marker_the_top_score() -> None:
    assert score("fechar caixa", f"nota fiscal {TOP_MARKER}") == 1.0


def test_score_of_an_empty_query_is_zero() -> None:
    assert score("  ?! ", "qualquer texto") == 0.0


def test_rerank_orders_by_score_with_ties_in_input_order() -> None:
    texts = ["nada a ver", "caixa", "fechar caixa", "caixa aberto", f"outro {TOP_MARKER}"]

    ranked = rerank("fechar caixa", texts)

    assert [item["index"] for item in ranked] == [2, 4, 1, 3, 0]
    assert ranked[0]["score"] == 1.0
    assert ranked[2]["score"] == 0.5
    assert ranked[-1]["score"] == 0.0


def test_handle_answers_the_tei_shape() -> None:
    body = json.dumps(
        {"query": "caixa", "texts": ["nota", "caixa"], "raw_scores": False, "truncate": True}
    ).encode()

    assert handle("POST", "/rerank", body) == (
        200,
        [{"index": 1, "score": 1.0}, {"index": 0, "score": 0.0}],
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"not json", (400, {"error": "invalid_json"})),
        (b"[1, 2]", (400, {"error": "invalid_body"})),
        (b'{"query": "x"}', (422, {"error": "query_and_texts_required"})),
        (b'{"query": 1, "texts": []}', (422, {"error": "query_and_texts_required"})),
        (b'{"query": "x", "texts": ["a", 2]}', (422, {"error": "texts_must_be_strings"})),
    ],
    ids=["not_json", "not_object", "no_texts", "query_not_text", "text_not_string"],
)
def test_handle_rejects_bad_bodies(body: bytes, expected: tuple[int, object]) -> None:
    assert handle("POST", "/rerank", body) == expected


def test_handle_health_and_unknown_routes() -> None:
    assert handle("GET", "/health", b"") == (200, {"ok": True})
    assert handle("GET", "/rerank", b"") == (404, {"error": "not_found"})


@pytest.fixture
def server() -> Iterator[ThreadingHTTPServer]:
    running = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=_serve_forever, args=(running,), daemon=True)
    thread.start()
    yield running
    running.shutdown()
    running.server_close()
    thread.join()


def call(
    server: ThreadingHTTPServer, method: str, path: str, body: bytes | None = None
) -> tuple[int, object]:
    host, port = server.server_address[:2]
    request = urllib.request.Request(f"http://{host!s}:{port}{path}", data=body, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_server_speaks_http_with_json(server: ThreadingHTTPServer) -> None:
    body = json.dumps({"query": "caixa", "texts": ["caixa", "nota"]}).encode()

    assert call(server, "GET", "/health") == (200, {"ok": True})
    assert call(server, "POST", "/rerank", body) == (
        200,
        [{"index": 0, "score": 1.0}, {"index": 1, "score": 0.0}],
    )
    assert call(server, "POST", "/rerank") == (400, {"error": "invalid_json"})


def test_main_binds_the_given_port_and_closes() -> None:
    served: list[tuple[str, int]] = []

    def serve(running: ThreadingHTTPServer) -> None:
        host, port = running.server_address[:2]
        served.append((str(host), int(port)))

    assert main(["--host", "127.0.0.1", "--port", "0"], serve=serve) == 0
    assert served[0][0] == "127.0.0.1"
