from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from webhook_sink import (
    Sink,
    _serve_forever,  # pyright: ignore[reportPrivateUsage]
    main,
    make_server,
    parse_signature,
    sign,
    verify_signature,
)

SECRET = "kbw_synthetic-test-secret"  # noqa: S105 - synthetic, signs test bodies only
NOW = 1_760_000_000
REQUESTER = {"name": "Ana", "email": "ana@example.test", "verified": True}
BODY = json.dumps(
    {
        "event": "ticket.requested",
        "question": "Como emito a nota?",
        "channel": "widget",
        "requester": REQUESTER,
    }
).encode()


def hook_headers(
    body: bytes = BODY, *, event: str = "ticket.requested", delivery: str = "d-1", at: int = NOW
) -> dict[str, str]:
    return {
        "knobridge-signature": f"t={at},v1={sign(SECRET, at, body)}",
        "knobridge-event": event,
        "knobridge-delivery": delivery,
    }


def ready_sink() -> Sink:
    sink = Sink(clock=lambda: float(NOW))
    sink.handle("PUT", "/secret", {}, json.dumps({"secret": SECRET}).encode())
    return sink


def test_parse_signature_reads_t_and_every_v1() -> None:
    assert parse_signature("t=12,v0=x, v1=aa,v1=bb,v1=") == (12, ["aa", "bb"])
    assert parse_signature("v1=aa,t=abc") == (None, ["aa"])


def test_verify_signature_accepts_the_spec_example_shape() -> None:
    header = f"t={NOW},v1={sign(SECRET, NOW, BODY)}"

    assert verify_signature(header, BODY, SECRET, NOW + 300)


@pytest.mark.parametrize(
    ("header", "body", "now"),
    [
        (f"t={NOW},v1={sign(SECRET, NOW, BODY)}", BODY + b" ", NOW),
        (f"t={NOW},v1={sign('kbw_other', NOW, BODY)}", BODY, NOW),
        (f"t={NOW},v1={sign(SECRET, NOW, BODY)}", BODY, NOW + 301),
        (f"v1={sign(SECRET, NOW, BODY)}", BODY, NOW),
    ],
    ids=["changed_body", "other_secret", "too_old", "no_timestamp"],
)
def test_verify_signature_rejects_tampering(header: str, body: bytes, now: int) -> None:
    assert not verify_signature(header, body, SECRET, now)


def test_sink_answers_a_signed_request_with_a_ticket() -> None:
    sink = ready_sink()

    status, payload = sink.handle("POST", "/hook", hook_headers(), BODY)

    assert status == 200
    assert payload == {"ticket_id": "KB-0001", "url": "https://chamados.example.test/KB-0001"}
    assert sink.deliveries == [
        {
            "delivery_id": "d-1",
            "event": "ticket.requested",
            "verified": True,
            "ticket_id": "KB-0001",
            "question": "Como emito a nota?",
            "channel": "widget",
            "requester": REQUESTER,
        }
    ]


def test_sink_gives_the_same_ticket_to_a_retry() -> None:
    sink = ready_sink()
    sink.handle("POST", "/hook", hook_headers(), BODY)

    _, retry = sink.handle("POST", "/hook", hook_headers(at=NOW + 10), BODY)
    _, other = sink.handle("POST", "/hook", hook_headers(delivery="d-2"), BODY)

    assert retry == {"ticket_id": "KB-0001", "url": "https://chamados.example.test/KB-0001"}
    assert other == {"ticket_id": "KB-0002", "url": "https://chamados.example.test/KB-0002"}


def test_sink_accepts_the_test_event_without_a_ticket() -> None:
    sink = ready_sink()
    body = b'{"event":"ticket.test"}'

    status, payload = sink.handle("POST", "/hook", hook_headers(body, event="ticket.test"), body)

    assert (status, payload) == (200, {})
    assert sink.deliveries[0]["ticket_id"] is None


def test_sink_refuses_a_bad_signature_and_records_it() -> None:
    sink = ready_sink()
    headers = hook_headers() | {"knobridge-signature": f"t={NOW},v1=00"}

    status, payload = sink.handle("POST", "/hook", headers, BODY)

    assert (status, payload) == (401, {"error": "invalid_signature"})
    assert sink.deliveries[0]["verified"] is False


def test_sink_refuses_everything_before_the_secret_is_set() -> None:
    sink = Sink(clock=lambda: float(NOW))

    status, _ = sink.handle("POST", "/hook", hook_headers(), BODY)

    assert status == 401


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b'{"secret": ""}', b'{"secret": 1}'])
def test_sink_rejects_a_bad_secret_body(body: bytes) -> None:
    sink = Sink()

    assert sink.handle("PUT", "/secret", {}, body) == (400, {"error": "secret_required"})
    assert sink.secret is None


def test_sink_lists_deliveries_health_and_unknown_routes() -> None:
    sink = ready_sink()
    sink.handle("POST", "/hook", hook_headers(), BODY)

    assert sink.handle("GET", "/health", {}, b"") == (200, {"ok": True})
    status, listed = sink.handle("GET", "/deliveries", {}, b"")
    assert status == 200
    assert isinstance(listed, list)
    assert len(listed) == 1
    assert sink.handle("DELETE", "/hook", {}, b"") == (404, {"error": "not_found"})


@pytest.fixture
def server() -> Iterator[ThreadingHTTPServer]:
    sink = Sink()
    running = make_server("127.0.0.1", 0, sink)
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
    assert call(server, "GET", "/health") == (200, {"ok": True})
    assert call(server, "PUT", "/secret", json.dumps({"secret": SECRET}).encode()) == (
        200,
        {"ok": True},
    )
    assert call(server, "POST", "/hook") == (401, {"error": "invalid_signature"})
    assert call(server, "GET", "/deliveries")[1] == [
        {
            "delivery_id": "",
            "event": "",
            "verified": False,
            "ticket_id": None,
            "question": None,
            "channel": None,
            "requester": None,
        }
    ]


def test_main_binds_the_given_port_and_closes() -> None:
    served: list[tuple[str, int]] = []

    def serve(running: ThreadingHTTPServer) -> None:
        host, port = running.server_address[:2]
        served.append((str(host), int(port)))

    assert main(["--host", "127.0.0.1", "--port", "0"], serve=serve) == 0
    assert served[0][0] == "127.0.0.1"
