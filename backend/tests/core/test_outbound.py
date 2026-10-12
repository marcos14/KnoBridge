"""SSRF guard and outbound client: URL rules, forbidden addresses (literal and resolved by a
fake resolver), the development allowlist, the connection pinned to the checked address, and
a real request to a local HTTP server (127.0.0.1, allowlisted; no external network)."""

from __future__ import annotations

import asyncio
import ipaddress

import httpx2
import pytest

from knobridge.core.outbound import (
    MAX_RESPONSE_BYTES,
    Destination,
    DestinationValidator,
    OutboundClient,
    OutboundDestinationBlocked,
    OutboundRequestFailed,
    OutboundUrlInvalid,
    SystemResolver,
    blocked_reason,
)

PUBLIC_V4 = "93.184.216.34"
PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"


class FakeResolver:
    """Answers from a fixed table; unknown names fail like the system resolver."""

    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table
        self.asked: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> list[str]:
        self.asked.append((host, port))
        if host not in self.table:
            raise OSError("name does not resolve")
        return self.table[host]


def _validator(
    table: dict[str, list[str]] | None = None, allowed: tuple[str, ...] = ()
) -> DestinationValidator:
    return DestinationValidator(FakeResolver(table or {}), allowed)


def _check(validator: DestinationValidator, url: str) -> Destination:
    return asyncio.run(validator.check(url))


@pytest.mark.parametrize(
    ("address", "reason"),
    [
        ("127.0.0.1", "loopback"),
        ("127.255.0.9", "loopback"),
        ("::1", "loopback"),
        ("10.1.2.3", "private"),
        ("172.16.0.1", "private"),
        ("172.31.255.255", "private"),
        ("192.168.1.1", "private"),
        ("fd00::1", "private"),
        ("169.254.169.254", "link_local"),
        ("fe80::1", "link_local"),
        ("100.64.0.1", "cgnat"),
        ("0.0.0.0", "unspecified"),  # noqa: S104 - an address under test, not a bind
        ("::", "unspecified"),
        ("224.0.0.1", "multicast"),
        ("ff02::1", "multicast"),
        ("240.0.0.1", "reserved"),
        ("192.0.2.10", "reserved"),
        ("::ffff:127.0.0.1", "loopback"),
        ("::ffff:10.0.0.1", "private"),
    ],
)
def test_blocked_reason_refuses_special_addresses(address: str, reason: str) -> None:
    assert blocked_reason(ipaddress.ip_address(address)) == reason


@pytest.mark.parametrize("address", [PUBLIC_V4, PUBLIC_V6, "172.32.0.1", "::ffff:8.8.8.8"])
def test_blocked_reason_accepts_public_addresses(address: str) -> None:
    assert blocked_reason(ipaddress.ip_address(address)) is None


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("http://hooks.example.com/x", "scheme_not_https"),
        ("ftp://hooks.example.com/x", "scheme_not_https"),
        ("hooks.example.com/x", "scheme_not_https"),
        ("https:///path", "host_missing"),
        ("https://user:pass@hooks.example.com/x", "credentials_in_url"),
        ("https://user@hooks.example.com/x", "credentials_in_url"),
        ("https://hooks.example.com:99999/x", "malformed"),
        ("https://[::1/x", "malformed"),
    ],
)
def test_validator_refuses_invalid_url(url: str, reason: str) -> None:
    with pytest.raises(OutboundUrlInvalid) as raised:
        _check(_validator({"hooks.example.com": [PUBLIC_V4]}), url)

    assert raised.value.reason == reason


def test_validator_accepts_public_host_and_keeps_first_address() -> None:
    resolver = FakeResolver({"hooks.example.com": [PUBLIC_V4, PUBLIC_V6]})

    destination = _check(DestinationValidator(resolver), "https://Hooks.Example.com/in?a=1")

    assert destination == Destination(
        "https://Hooks.Example.com/in?a=1", "https", "hooks.example.com", 443, PUBLIC_V4
    )
    assert resolver.asked == [("hooks.example.com", 443)]


def test_validator_refuses_host_resolving_to_any_private_address() -> None:
    validator = _validator({"hooks.example.com": [PUBLIC_V4, "10.0.0.5"]})

    with pytest.raises(OutboundDestinationBlocked) as raised:
        _check(validator, "https://hooks.example.com/in")

    assert raised.value.reason == "private"


def test_validator_refuses_literal_private_ip_without_resolving() -> None:
    resolver = FakeResolver({})

    with pytest.raises(OutboundDestinationBlocked) as raised:
        _check(DestinationValidator(resolver), "https://169.254.169.254/latest/meta-data")

    assert raised.value.reason == "link_local"
    assert resolver.asked == []


def test_validator_refuses_literal_ipv6_loopback() -> None:
    with pytest.raises(OutboundDestinationBlocked) as raised:
        _check(_validator(), "https://[::1]:8443/in")

    assert raised.value.reason == "loopback"


def test_validator_accepts_literal_public_ip() -> None:
    destination = _check(_validator(), f"https://{PUBLIC_V4}:8443/in")

    assert (destination.port, destination.address) == (8443, PUBLIC_V4)


def test_validator_accepts_resolved_address_with_scope() -> None:
    destination = _check(
        _validator({"v6.example.com": [f"{PUBLIC_V6}%0"]}), "https://v6.example.com"
    )

    assert destination.address == PUBLIC_V6


@pytest.mark.parametrize("table", [{}, {"hooks.example.com": []}])
def test_validator_refuses_unresolvable_host(table: dict[str, list[str]]) -> None:
    with pytest.raises(OutboundUrlInvalid) as raised:
        _check(_validator(table), "https://hooks.example.com/in")

    assert raised.value.reason == "host_unresolvable"


def test_validator_allowlist_skips_checks_and_accepts_http() -> None:
    resolver = FakeResolver({})
    validator = DestinationValidator(resolver, [" Webhook-Sink ", ""])

    destination = _check(validator, "http://webhook-sink:8080/hook")

    assert destination == Destination(
        "http://webhook-sink:8080/hook", "http", "webhook-sink", 8080, None
    )
    assert resolver.asked == []


def test_validator_allowlist_is_exact_host() -> None:
    validator = _validator({"evil.webhook-sink": ["127.0.0.1"]}, ("webhook-sink",))

    with pytest.raises(OutboundUrlInvalid) as raised:
        _check(validator, "http://evil.webhook-sink/hook")

    assert raised.value.reason == "scheme_not_https"


def test_validator_allowlisted_https_uses_default_port() -> None:
    destination = _check(_validator(allowed=("localhost",)), "https://localhost/hook")

    assert (destination.port, destination.address) == (443, None)


def test_validator_allowlisted_http_uses_port_80() -> None:
    destination = _check(_validator(allowed=("localhost",)), "http://localhost/hook")

    assert destination.port == 80


def test_system_resolver_resolves_literal_without_network() -> None:
    addresses = asyncio.run(SystemResolver().resolve("127.0.0.1", 443))

    assert addresses == ["127.0.0.1"]


class Recorder:
    def __init__(self, response: httpx2.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _post(destination: Destination, recorder: Recorder) -> tuple[int, bytes]:
    client = OutboundClient(httpx2.MockTransport(recorder))
    response = asyncio.run(client.post(destination, b'{"a":1}', {"X-Test": "1"}))
    return response.status, response.body


def test_client_connects_to_checked_address_with_original_host_and_sni() -> None:
    recorder = Recorder(httpx2.Response(202, content=b"ok"))
    destination = Destination(
        "https://hooks.example.com/in?a=1", "https", "hooks.example.com", 443, PUBLIC_V4
    )

    result = _post(destination, recorder)

    request = recorder.requests[0]
    assert result == (202, b"ok")
    assert str(request.url) == f"https://{PUBLIC_V4}/in?a=1"
    assert request.headers["Host"] == "hooks.example.com"
    assert request.extensions["sni_hostname"] == "hooks.example.com"
    assert request.headers["X-Test"] == "1"
    assert request.content == b'{"a":1}'


def test_client_pins_ipv6_address_and_keeps_custom_port_in_host() -> None:
    recorder = Recorder(httpx2.Response(200))
    destination = Destination(
        "https://hooks.example.com:8443/in", "https", "hooks.example.com", 8443, PUBLIC_V6
    )

    _post(destination, recorder)

    request = recorder.requests[0]
    assert str(request.url) == f"https://[{PUBLIC_V6}]:8443/in"
    assert request.headers["Host"] == "hooks.example.com:8443"


def test_client_host_header_brackets_literal_ipv6() -> None:
    recorder = Recorder(httpx2.Response(200))
    destination = Destination(f"https://[{PUBLIC_V6}]/in", "https", PUBLIC_V6, 443, PUBLIC_V6)

    _post(destination, recorder)

    assert recorder.requests[0].headers["Host"] == f"[{PUBLIC_V6}]"


def test_client_pinned_http_sets_no_sni() -> None:
    recorder = Recorder(httpx2.Response(200))
    destination = Destination(
        "http://hooks.example.com/in", "http", "hooks.example.com", 80, PUBLIC_V4
    )

    _post(destination, recorder)

    request = recorder.requests[0]
    assert str(request.url) == f"http://{PUBLIC_V4}/in"
    assert "sni_hostname" not in request.extensions


def test_client_reaches_allowlisted_host_by_name() -> None:
    recorder = Recorder(httpx2.Response(204))
    destination = Destination("http://webhook-sink:8080/hook", "http", "webhook-sink", 8080, None)

    result = _post(destination, recorder)

    assert result == (204, b"")
    assert str(recorder.requests[0].url) == "http://webhook-sink:8080/hook"


def test_client_does_not_follow_redirects() -> None:
    recorder = Recorder(httpx2.Response(302, headers={"Location": "https://other.example/"}))
    destination = Destination("https://h.example/in", "https", "h.example", 443, PUBLIC_V4)

    result = _post(destination, recorder)

    assert result[0] == 302
    assert len(recorder.requests) == 1


def test_client_reads_at_most_the_limit() -> None:
    recorder = Recorder(httpx2.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 10)))
    destination = Destination("https://h.example/in", "https", "h.example", 443, PUBLIC_V4)

    _, body = _post(destination, recorder)

    assert len(body) == MAX_RESPONSE_BYTES


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (httpx2.ReadTimeout("slow"), "timeout"),
        (httpx2.ConnectTimeout("slow"), "timeout"),
        (httpx2.ConnectError("refused"), "network"),
    ],
)
def test_client_reports_network_failures(error: Exception, reason: str) -> None:
    destination = Destination("https://h.example/in", "https", "h.example", 443, PUBLIC_V4)

    with pytest.raises(OutboundRequestFailed) as raised:
        _post(destination, Recorder(error))

    assert raised.value.reason == reason


async def _serve_once(status: int, received: list[bytes]) -> tuple[asyncio.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await reader.readuntil(b"\r\n\r\n")
        length = next(
            int(line.split(b":", 1)[1])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        received.append(head + await reader.readexactly(length))
        writer.write(
            f"HTTP/1.1 {status} X\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok".encode()
        )
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


def test_client_posts_to_local_http_server() -> None:
    received: list[bytes] = []

    async def scenario() -> tuple[int, bytes]:
        server, port = await _serve_once(201, received)
        async with server:
            validator = DestinationValidator(SystemResolver(), ["127.0.0.1"])
            destination = await validator.check(f"http://127.0.0.1:{port}/hook")
            response = await OutboundClient().post(destination, b"{}", {"X-A": "b"})
            return response.status, response.body

    result = asyncio.run(scenario())

    assert result == (201, b"ok")
    assert received[0].startswith(b"POST /hook HTTP/1.1")
    assert b"x-a: b" in received[0].lower()
    assert received[0].endswith(b"\r\n\r\n{}")
