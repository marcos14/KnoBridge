"""Request limits of the widget's public routes: fixed windows counted in Postgres
(``docs/specs/widget.md``, "Limites de requisição").

The first hit opens a window (``window_ends_at = now + window``); each hit inside it adds one;
the first hit after it starts a new window at one. A single ``INSERT … ON CONFLICT … RETURNING``
does it atomically, so concurrent requests of every API process are all counted. Refused hits
count too, so a flood stays blocked until its window ends. Over the limit: 429 ``rate_limited``
with ``Retry-After``.

The counter key is ``HMAC-SHA256(key derived from KNOBRIDGE_SECRET_KEY, "<scope>|<widget>|<ip>")``:
a plain SHA-256 of an IPv4 address is reversed by brute force. An IPv6 client counts by its
``/64`` (whoever holds one changes address at will). At most once an hour per process, the
limiter deletes the windows that ended more than a day ago. Every call runs in the caller's
``system_session`` (the visitor is anonymous); the clock is injected.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from http import HTTPStatus

from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from knobridge.core.clock import Clock
from knobridge.core.crypto import derive_key
from knobridge.core.db import system_session
from knobridge.core.errors import KnoBridgeError
from knobridge.widget.models import RateLimitCounter

# HKDF label of the counter key; a new label (v2) means new keys, never reuse this one.
RATE_LIMIT_KEY_INFO = b"knobridge/rate-limit/v1"
CLEANUP_INTERVAL = timedelta(hours=1)
RETENTION = timedelta(hours=24)
_IPV6_PREFIX = 64


class RateLimitScope(StrEnum):
    """What a counter counts (``details.limit`` of the 429)."""

    WIDGET_REQUEST = "widget_request"
    WIDGET_CONVERSATION = "widget_conversation"
    WIDGET_MESSAGE_IP = "widget_message_ip"
    WIDGET_MESSAGE_DAY = "widget_message_day"
    WIDGET_TICKET = "widget_ticket"


@dataclass(frozen=True)
class RateLimit:
    scope: RateLimitScope
    limit: int
    window: timedelta


def widget_request_limit(per_minute: int) -> RateLimit:
    """Every public request of a widget and client (``KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE``)."""
    return RateLimit(RateLimitScope.WIDGET_REQUEST, per_minute, timedelta(minutes=1))


def widget_conversation_limit(per_hour: int) -> RateLimit:
    """New conversations of a widget and client (``KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR``)."""
    return RateLimit(RateLimitScope.WIDGET_CONVERSATION, per_hour, timedelta(hours=1))


def widget_message_ip_limit(per_hour: int) -> RateLimit:
    """Questions of a widget and client (``messages_per_ip_per_hour`` of the widget)."""
    return RateLimit(RateLimitScope.WIDGET_MESSAGE_IP, per_hour, timedelta(hours=1))


def widget_message_day_limit(per_day: int) -> RateLimit:
    """Questions of a widget from every client (``messages_per_day``; counted with ``ip=None``)."""
    return RateLimit(RateLimitScope.WIDGET_MESSAGE_DAY, per_day, timedelta(hours=24))


def widget_ticket_limit(per_hour: int) -> RateLimit:
    """Ticket requests of a widget and client (``KNOBRIDGE_WIDGET_TICKETS_PER_HOUR``)."""
    return RateLimit(RateLimitScope.WIDGET_TICKET, per_hour, timedelta(hours=1))


class RateLimitedError(KnoBridgeError):
    code = "rate_limited"
    status_code = HTTPStatus.TOO_MANY_REQUESTS

    def __init__(self, scope: RateLimitScope, retry_after: int) -> None:
        super().__init__(
            "Too many requests; try again later.",
            details={"limit": scope.value, "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


def client_bucket(ip: str | None) -> str:
    """The address a client counts by: IPv4 as is, IPv6 by its ``/64`` network, else ``""``."""
    if not ip:
        return ""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, _IPV6_PREFIX), strict=False))
    return str(address)


class RateLimiter:
    """Counts hits per scope, widget and client in fixed windows; one per API process."""

    def __init__(self, clock: Clock, *, secret_key: str) -> None:
        self._clock = clock
        self._key = derive_key(secret_key, info=RATE_LIMIT_KEY_INFO)
        self._last_cleanup: datetime | None = None

    def counter_key(self, scope: RateLimitScope, widget_id: uuid.UUID, ip: str | None) -> str:
        """The stored key of a counter; ``ip=None`` counts every client together."""
        bucket = "" if ip is None else client_bucket(ip)
        message = f"{scope.value}|{widget_id}|{bucket}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    async def hit(
        self, db: AsyncSession, rule: RateLimit, *, widget_id: uuid.UUID, ip: str | None
    ) -> None:
        """Count one hit; ``RateLimitedError`` when it passes ``rule.limit`` in the window."""
        now = self._clock.now()
        await self._cleanup(db, now)
        ends_at = now + rule.window
        expired = RateLimitCounter.window_ends_at <= now
        statement = (
            insert(RateLimitCounter)
            .values(
                key_hash=self.counter_key(rule.scope, widget_id, ip), hits=1, window_ends_at=ends_at
            )
            .on_conflict_do_update(
                index_elements=[RateLimitCounter.key_hash],
                set_={
                    "hits": case((expired, 1), else_=RateLimitCounter.hits + 1),
                    "window_ends_at": case(
                        (expired, ends_at), else_=RateLimitCounter.window_ends_at
                    ),
                },
            )
            .returning(RateLimitCounter.hits, RateLimitCounter.window_ends_at)
        )
        hits, window_ends_at = (await db.execute(statement)).one()
        if hits > rule.limit:
            seconds = math.ceil((window_ends_at - now).total_seconds())
            raise RateLimitedError(rule.scope, max(seconds, 1))

    async def check(
        self,
        factory: async_sessionmaker[AsyncSession],
        rule: RateLimit,
        *,
        widget_id: uuid.UUID,
        ip: str | None,
    ) -> None:
        """:meth:`hit` in a short transaction of its own, committed even when the hit is
        refused (refused hits count) and whatever the request does next."""
        refused: RateLimitedError | None = None
        async with system_session(factory) as db:
            try:
                await self.hit(db, rule, widget_id=widget_id, ip=ip)
            except RateLimitedError as exc:
                refused = exc
        if refused is not None:
            raise refused

    async def _cleanup(self, db: AsyncSession, now: datetime) -> None:
        if self._last_cleanup is not None and now - self._last_cleanup < CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        await db.execute(
            delete(RateLimitCounter).where(RateLimitCounter.window_ends_at < now - RETENTION)
        )
