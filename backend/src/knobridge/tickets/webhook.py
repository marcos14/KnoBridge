"""The ticket webhook of a product: its URL rules, its ``kbw_`` signing secret and the test
event (docs/specs/chamados.md, "Abrir chamado (webhook de saída)").

The secret is generated here, shown once and stored only as ciphertext
(``webhook_secret.py``); it never reaches a log or the audit trail. Every request goes through
``core/outbound.py``: the URL and its resolved addresses are checked again on each send and the
connection is pinned to the checked address. The delivery of real ticket requests (workflow
and retries) reuses ``webhook_headers`` and ``send_webhook``.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.audit.actions import AuditAction
from knobridge.audit.service import AuditService, AuditTarget
from knobridge.core.clock import Clock
from knobridge.core.crypto import SecretBox
from knobridge.core.errors import ConflictError, NotFoundError, ValidationError
from knobridge.core.logging import get_logger
from knobridge.core.outbound import (
    DestinationValidator,
    OutboundClient,
    OutboundDestinationBlocked,
    OutboundRequestFailed,
    OutboundResponse,
    OutboundUrlInvalid,
)
from knobridge.products.models import Product
from knobridge.tenancy.models import Workspace
from knobridge.tickets.signature import SIGNATURE_HEADER, signature_header
from knobridge.tickets.webhook_secret import open_webhook_secret, seal_webhook_secret

SECRET_SCHEME = "kbw"  # noqa: S105 - public marker of the format, not a secret
SECRET_BYTES = 32
USER_AGENT = "KnoBridge-Webhook/1"
TEST_EVENT = "ticket.test"
EVENT_VERSION = 1

_log = get_logger(__name__)


class WebhookUrlInvalidError(ValidationError):
    code = "webhook_url_invalid"


class WebhookDestinationBlockedError(ValidationError):
    code = "webhook_destination_blocked"


class TicketWebhookNotConfiguredError(ConflictError):
    code = "ticket_webhook_not_configured"


def generate_webhook_secret() -> str:
    """``kbw_`` + 32 random bytes in URL-safe base64 (43 characters)."""
    return f"{SECRET_SCHEME}_{secrets.token_urlsafe(SECRET_BYTES)}"


async def check_webhook_url(validator: DestinationValidator, url: str) -> None:
    """Every SSRF rule, resolving the host, as when the URL is saved: 422
    ``webhook_url_invalid`` or ``webhook_destination_blocked``, with ``details.reason``."""
    try:
        await validator.check(url)
    except OutboundUrlInvalid as exc:
        raise _url_invalid(exc.reason) from exc
    except OutboundDestinationBlocked as exc:
        raise WebhookDestinationBlockedError(
            "The webhook URL points to a forbidden address.", details={"reason": exc.reason}
        ) from exc


def _url_invalid(reason: str) -> WebhookUrlInvalidError:
    return WebhookUrlInvalidError("The webhook URL is not acceptable.", details={"reason": reason})


def webhook_headers(
    *, event: str, delivery_id: uuid.UUID, secret: str, timestamp: int, body: bytes
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "KnoBridge-Event": event,
        "KnoBridge-Delivery": str(delivery_id),
        SIGNATURE_HEADER: signature_header(secret, timestamp, body),
    }


async def send_webhook(
    validator: DestinationValidator,
    client: OutboundClient,
    *,
    url: str,
    secret: str,
    event: str,
    delivery_id: uuid.UUID,
    body: bytes,
    timestamp: int,
) -> OutboundResponse:
    """One signed attempt. Raises ``OutboundUrlInvalid``, ``OutboundDestinationBlocked`` (the
    URL is checked again) or ``OutboundRequestFailed``; any HTTP status is returned."""
    destination = await validator.check(url)
    headers = webhook_headers(
        event=event, delivery_id=delivery_id, secret=secret, timestamp=timestamp, body=body
    )
    return await client.post(destination, body, headers)


def encode_body(payload: dict[str, object]) -> bytes:
    """Compact UTF-8 JSON, the exact bytes that are signed and sent."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _instant(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class IssuedWebhookSecret:
    secret: str  # plain value: shown once to the user, never stored or logged
    created_at: datetime


@dataclass(frozen=True)
class WebhookTestResult:
    delivery_id: uuid.UUID
    ok: bool
    # HTTP status of the destination; ``None`` when no answer came.
    status: int | None
    # ``webhook_url_invalid``, ``webhook_destination_blocked``, ``webhook_unreachable`` or
    # ``webhook_rejected``; ``None`` when ``ok``.
    error_code: str | None = None
    # ``details.reason`` of the error (not for ``webhook_rejected``, which has ``status``).
    reason: str | None = None


class TicketWebhookService:
    def __init__(
        self,
        clock: Clock,
        box: SecretBox,
        validator: DestinationValidator,
        client: OutboundClient,
    ) -> None:
        self._clock = clock
        self._box = box
        self._validator = validator
        self._client = client
        self._audit = AuditService(clock)

    async def rotate_secret(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        product_id: uuid.UUID,
        ip: str | None,
    ) -> IssuedWebhookSecret:
        """Generate the signing secret, replacing the current one at once."""
        product = await _product(db, workspace_id, product_id, lock=True)
        secret = generate_webhook_secret()
        now = self._clock.now()
        product.ticket_webhook_secret_ciphertext = seal_webhook_secret(self._box, product, secret)
        product.ticket_webhook_secret_created_at = now
        await db.flush()
        await self._audit.record(
            db,
            action=AuditAction.PRODUCT_TICKET_WEBHOOK_SECRET_ROTATED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("product", str(product.id)),
            metadata={"name": product.name},
            ip=ip,
        )
        return IssuedWebhookSecret(secret=secret, created_at=now)

    async def send_test(
        self,
        db: AsyncSession,
        *,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        product_id: uuid.UUID,
        ip: str | None,
    ) -> WebhookTestResult:
        """Send one signed ``ticket.test`` event, without retries, and report the outcome
        (audited either way). 409 ``ticket_webhook_not_configured`` without URL or secret."""
        product = await _product(db, workspace_id, product_id, lock=False)
        url = product.ticket_webhook_url
        secret = open_webhook_secret(self._box, product)
        if url is None or secret is None:
            raise TicketWebhookNotConfiguredError("The product has no webhook URL or secret.")
        workspace_name = await db.scalar(select(Workspace.name).where(Workspace.id == workspace_id))
        delivery_id = uuid.uuid4()
        now = self._clock.now()
        body = encode_body(
            {
                "event": TEST_EVENT,
                "version": EVENT_VERSION,
                "id": str(delivery_id),
                "created_at": _instant(now),
                "workspace": {"id": str(workspace_id), "name": workspace_name},
                "product": {"id": str(product.id), "name": product.name},
                # Repeats ``product``; obsolete since chamados.md v0.2.
                "assistant": {"id": str(product.id), "name": product.name},
            }
        )
        result = await self._attempt(url, secret, delivery_id, body, int(now.timestamp()))
        await self._audit.record(
            db,
            action=AuditAction.PRODUCT_TICKET_WEBHOOK_TESTED,
            workspace_id=workspace_id,
            actor_user_id=actor_id,
            target=AuditTarget("product", str(product.id)),
            metadata={
                "name": product.name,
                "ok": result.ok,
                "status": result.status,
                "error_code": result.error_code,
            },
            ip=ip,
        )
        _log.info(
            "ticket_webhook_tested",
            workspace_id=str(workspace_id),
            product_id=str(product.id),
            ok=result.ok,
            status=result.status,
            error_code=result.error_code,
        )
        return result

    async def _attempt(
        self, url: str, secret: str, delivery_id: uuid.UUID, body: bytes, timestamp: int
    ) -> WebhookTestResult:
        try:
            response = await send_webhook(
                self._validator,
                self._client,
                url=url,
                secret=secret,
                event=TEST_EVENT,
                delivery_id=delivery_id,
                body=body,
                timestamp=timestamp,
            )
        except OutboundUrlInvalid as exc:
            return WebhookTestResult(delivery_id, False, None, "webhook_url_invalid", exc.reason)
        except OutboundDestinationBlocked as exc:
            return WebhookTestResult(
                delivery_id, False, None, "webhook_destination_blocked", exc.reason
            )
        except OutboundRequestFailed as exc:
            return WebhookTestResult(delivery_id, False, None, "webhook_unreachable", exc.reason)
        if 200 <= response.status < 300:
            return WebhookTestResult(delivery_id, True, response.status)
        return WebhookTestResult(delivery_id, False, response.status, "webhook_rejected")


async def _product(
    db: AsyncSession, workspace_id: uuid.UUID, product_id: uuid.UUID, *, lock: bool
) -> Product:
    query = select(Product).where(Product.workspace_id == workspace_id, Product.id == product_id)
    if lock:
        query = query.with_for_update()
    product = (await db.scalars(query)).one_or_none()
    if product is None:
        raise NotFoundError("Product not found.")
    return product
