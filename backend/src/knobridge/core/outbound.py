"""Outbound HTTP to user-configured destinations, guarded against SSRF.

Rules of docs/specs/chamados.md ("Proteção contra SSRF"), applied when a URL is saved and on
every request: ``https`` only, a host and no credentials in the URL; every address the host
resolves to (or the literal IP) must be public (not loopback, private, link-local, CGNAT,
unspecified, multicast or reserved; an IPv4-mapped IPv6 address is checked as IPv4). The
request then goes to the address that was checked, with the original name in ``Host`` and in
the TLS SNI, so a second DNS answer (rebinding) cannot change the destination; proxies from
the environment are ignored and redirects are not followed.

Hosts listed in ``allowed_hosts`` (``KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS``, development and E2E
only) skip the address checks and the pinning, and may use ``http``.

The DNS resolver and the HTTP transport are injected, so tests never touch the network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import SplitResult, urlsplit

import httpx2

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Seconds for each phase of a request (connect, write, read, pool), per the spec.
DEFAULT_TIMEOUT = 10.0
# Most of a response body that is ever read.
MAX_RESPONSE_BYTES = 64 * 1024

_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class OutboundUrlInvalid(Exception):  # noqa: N818 - a refusal reason, not an "Error" type
    """The URL itself is not acceptable (``reason``: ``malformed``, ``scheme_not_https``,
    ``host_missing``, ``credentials_in_url``, ``host_unresolvable``)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OutboundDestinationBlocked(Exception):  # noqa: N818 - a refusal reason
    """The host is, or resolves to, a forbidden address (``reason``: ``loopback``,
    ``private``, ``link_local``, ``cgnat``, ``unspecified``, ``multicast``, ``reserved``)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class OutboundRequestFailed(Exception):  # noqa: N818 - a network outcome
    """No HTTP answer: ``reason`` is ``timeout`` or ``network``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Resolver(Protocol):
    async def resolve(self, host: str, port: int) -> list[str]:
        """The addresses (A and AAAA) of ``host``; ``OSError`` when it does not resolve."""
        ...


class SystemResolver:
    """The operating system's resolver (``getaddrinfo``)."""

    async def resolve(self, host: str, port: int) -> list[str]:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return list(dict.fromkeys(str(info[4][0]) for info in infos))


def blocked_reason(address: IPAddress) -> str | None:
    """Why ``address`` may not be a destination, or ``None`` when it is public."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if address.is_unspecified:
        return "unspecified"
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link_local"
    if isinstance(address, ipaddress.IPv4Address) and address in _CGNAT:
        return "cgnat"
    if any(address in network for network in _PRIVATE_NETWORKS):
        return "private"
    if address.is_multicast:
        return "multicast"
    # Everything else that is not globally routable (documentation, benchmarking, 240/4...).
    if address.is_reserved or not address.is_global:
        return "reserved"
    return None


@dataclass(frozen=True)
class Destination:
    """A checked URL. ``address`` is where to connect; ``None`` for an allowlisted host,
    which is reached by its name."""

    url: str
    scheme: str
    host: str
    port: int
    address: str | None


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    # At most ``MAX_RESPONSE_BYTES`` of the body.
    body: bytes


def _split(url: str) -> SplitResult:
    try:
        parts = urlsplit(url)
        parts.port  # noqa: B018 - raises ValueError for an invalid port
    except ValueError as exc:
        raise OutboundUrlInvalid("malformed") from exc
    return parts


def _literal(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


class DestinationValidator:
    def __init__(self, resolver: Resolver, allowed_hosts: Iterable[str] = ()) -> None:
        self._resolver = resolver
        self._allowed = frozenset(host.strip().lower() for host in allowed_hosts if host.strip())

    def parse(self, url: str) -> SplitResult:
        """The URL rules alone (no DNS), for saving: raises ``OutboundUrlInvalid``."""
        parts = _split(url)
        host = (parts.hostname or "").lower()
        allowed_http = parts.scheme == "http" and host in self._allowed
        if parts.scheme != "https" and not allowed_http:
            raise OutboundUrlInvalid("scheme_not_https")
        if not host:
            raise OutboundUrlInvalid("host_missing")
        if parts.username is not None or parts.password is not None:
            raise OutboundUrlInvalid("credentials_in_url")
        return parts

    async def check(self, url: str) -> Destination:
        """Every rule, resolving the host; raises ``OutboundUrlInvalid`` or
        ``OutboundDestinationBlocked``."""
        parts = self.parse(url)
        host = (parts.hostname or "").lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if host in self._allowed:
            return Destination(url, parts.scheme, host, port, None)
        literal = _literal(host)
        if literal is not None:
            addresses = [literal]
        else:
            try:
                found = await self._resolver.resolve(host, port)
            except OSError as exc:
                raise OutboundUrlInvalid("host_unresolvable") from exc
            addresses = [ipaddress.ip_address(item.split("%", 1)[0]) for item in found]
            if not addresses:
                raise OutboundUrlInvalid("host_unresolvable")
        for address in addresses:
            reason = blocked_reason(address)
            if reason is not None:
                raise OutboundDestinationBlocked(reason)
        return Destination(url, parts.scheme, host, port, str(addresses[0]))


def _pinned_url(destination: Destination) -> str:
    """The URL with the checked address in place of the host name."""
    parts = urlsplit(destination.url)
    address = destination.address or destination.host
    shown = f"[{address}]" if ":" in address else address
    return parts._replace(netloc=f"{shown}:{destination.port}").geturl()


def _host_header(destination: Destination) -> str:
    default = 443 if destination.scheme == "https" else 80
    shown = f"[{destination.host}]" if ":" in destination.host else destination.host
    return shown if destination.port == default else f"{shown}:{destination.port}"


class OutboundClient:
    """POSTs to a checked ``Destination`` (no proxy from the environment, no redirects)."""

    def __init__(
        self,
        transport: httpx2.AsyncBaseTransport | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._transport = transport
        self._timeout = timeout

    async def post(
        self, destination: Destination, body: bytes, headers: Mapping[str, str]
    ) -> OutboundResponse:
        url, extensions = destination.url, {}
        sent = dict(headers)
        if destination.address is not None:
            url = _pinned_url(destination)
            sent["Host"] = _host_header(destination)
            if destination.scheme == "https":
                extensions = {"sni_hostname": destination.host}
        async with httpx2.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            trust_env=False,
            follow_redirects=False,
        ) as client:
            try:
                request = client.build_request(
                    "POST", url, content=body, headers=sent, extensions=extensions
                )
                response = await client.send(request, stream=True)
                try:
                    received = bytearray()
                    async for chunk in response.aiter_bytes():
                        received += chunk
                        if len(received) >= MAX_RESPONSE_BYTES:
                            break
                finally:
                    await response.aclose()
            except httpx2.TimeoutException as exc:
                raise OutboundRequestFailed("timeout") from exc
            except httpx2.TransportError as exc:
                raise OutboundRequestFailed("network") from exc
        return OutboundResponse(response.status_code, bytes(received[:MAX_RESPONSE_BYTES]))
