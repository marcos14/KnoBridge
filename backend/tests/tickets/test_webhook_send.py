"""The webhook helpers without a database: the ``kbw_`` secret, the URL check as saved (errors
with ``details.reason``), the headers, and one signed attempt to a local HTTP receiver that
verifies the signature as the spec tells integrators to (127.0.0.1, allowlisted)."""

from __future__ import annotations

import asyncio
import re
import uuid

import httpx2
import pytest

from knobridge.core.outbound import (
    DestinationValidator,
    OutboundClient,
    OutboundDestinationBlocked,
    SystemResolver,
)
from knobridge.tickets.signature import compute_signature, verify_signature
from knobridge.tickets.webhook import (
    WebhookDestinationBlockedError,
    WebhookUrlInvalidError,
    check_webhook_url,
    encode_body,
    generate_webhook_secret,
    send_webhook,
    webhook_headers,
)

SECRET = "kbw_" + "w" * 43  # synthetic
DELIVERY = uuid.UUID("00000000-0000-4000-8000-000000000001")
T = 1_760_270_400


class FakeResolver:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table

    async def resolve(self, host: str, port: int) -> list[str]:
        return self.table[host]


def test_generate_webhook_secret_format_and_uniqueness() -> None:
    first, second = generate_webhook_secret(), generate_webhook_secret()

    assert re.fullmatch(r"kbw_[A-Za-z0-9_-]{43}", first)
    assert first != second


def test_check_webhook_url_accepts_public_destination() -> None:
    validator = DestinationValidator(FakeResolver({"hooks.example.com": ["93.184.216.34"]}))

    asyncio.run(check_webhook_url(validator, "https://hooks.example.com/in"))


def test_check_webhook_url_refuses_http_with_reason() -> None:
    validator = DestinationValidator(FakeResolver({}))

    with pytest.raises(WebhookUrlInvalidError) as raised:
        asyncio.run(check_webhook_url(validator, "http://hooks.example.com/in"))

    assert (raised.value.status_code, raised.value.details) == (
        422,
        {"reason": "scheme_not_https"},
    )


def test_check_webhook_url_refuses_private_resolution_with_reason() -> None:
    validator = DestinationValidator(FakeResolver({"hooks.example.com": ["192.168.0.10"]}))

    with pytest.raises(WebhookDestinationBlockedError) as raised:
        asyncio.run(check_webhook_url(validator, "https://hooks.example.com/in"))

    assert (raised.value.code, raised.value.details) == (
        "webhook_destination_blocked",
        {"reason": "private"},
    )


def test_webhook_headers_follow_spec() -> None:
    headers = webhook_headers(
        event="ticket.requested", delivery_id=DELIVERY, secret=SECRET, timestamp=T, body=b"{}"
    )

    assert headers == {
        "Content-Type": "application/json",
        "User-Agent": "KnoBridge-Webhook/1",
        "KnoBridge-Event": "ticket.requested",
        "KnoBridge-Delivery": str(DELIVERY),
        "KnoBridge-Signature": f"t={T},v1={compute_signature(SECRET, T, b'{}')}",
    }


def test_encode_body_is_compact_utf8() -> None:
    assert encode_body({"a": "ção", "b": [1, 2]}) == '{"a":"ção","b":[1,2]}'.encode()


def test_send_webhook_checks_url_again_before_sending() -> None:
    sent: list[httpx2.Request] = []
    client = OutboundClient(httpx2.MockTransport(lambda r: sent.append(r) or httpx2.Response(200)))
    validator = DestinationValidator(FakeResolver({"hooks.example.com": ["10.0.0.1"]}))

    with pytest.raises(OutboundDestinationBlocked):
        asyncio.run(
            send_webhook(
                validator,
                client,
                url="https://hooks.example.com/in",
                secret=SECRET,
                event="ticket.test",
                delivery_id=DELIVERY,
                body=b"{}",
                timestamp=T,
            )
        )

    assert sent == []


async def _receiver(
    received: list[tuple[dict[str, str], bytes]],
) -> tuple[asyncio.Server, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        headers = {
            name.strip().lower(): value.strip()
            for name, _, value in (line.partition(":") for line in head.split("\r\n")[1:] if line)
        }
        body = await reader.readexactly(int(headers["content-length"]))
        received.append((headers, body))
        valid = verify_signature(
            headers["knobridge-signature"], secret=SECRET, body=body, now=T + 5
        )
        status = "204 No Content" if valid else "401 Unauthorized"
        writer.write(f"HTTP/1.1 {status}\r\nContent-Length: 0\r\n\r\n".encode())
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.parametrize(("secret", "status"), [(SECRET, 204), ("kbw_" + "x" * 43, 401)])
def test_send_webhook_signature_verified_by_local_receiver(secret: str, status: int) -> None:
    received: list[tuple[dict[str, str], bytes]] = []
    body = encode_body({"event": "ticket.test", "id": str(DELIVERY)})

    async def scenario() -> int:
        server, port = await _receiver(received)
        async with server:
            response = await send_webhook(
                DestinationValidator(SystemResolver(), ["127.0.0.1"]),
                OutboundClient(),
                url=f"http://127.0.0.1:{port}/hook",
                secret=secret,
                event="ticket.test",
                delivery_id=DELIVERY,
                body=body,
                timestamp=T,
            )
            return response.status

    result = asyncio.run(scenario())

    headers, got = received[0]
    assert result == status
    assert got == body
    assert headers["knobridge-event"] == "ticket.test"
    assert headers["knobridge-delivery"] == str(DELIVERY)
    assert headers["user-agent"] == "KnoBridge-Webhook/1"
