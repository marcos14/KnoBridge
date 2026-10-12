"""The ``EmailSender`` interface and its SMTP adapter.

Callers depend on :class:`EmailSender` only; production injects :class:`SmtpEmailSender`
and tests inject the fake from ``tests/fakes/``, so no test talks to a real mail server.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from http import HTTPStatus
from typing import Protocol

import aiosmtplib

from knobridge.core.clock import Clock, SystemClock
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings

_log = get_logger(__name__)


@dataclass(frozen=True)
class OutgoingEmail:
    """A rendered e-mail ready to send: plain-text body plus its HTML alternative."""

    to: str
    subject: str
    text: str
    html: str


class EmailDeliveryError(KnoBridgeError):
    """The mail server refused or could not be reached; the message was not sent."""

    code = "email_delivery_failed"
    status_code = HTTPStatus.BAD_GATEWAY


class EmailSender(Protocol):
    async def send(self, email: OutgoingEmail) -> None:
        """Deliver ``email`` or raise :class:`EmailDeliveryError`."""
        ...


class SmtpEmailSender:
    """Sends through an SMTP server with ``aiosmtplib`` (one connection per message)."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        start_tls: bool = False,
        timeout: float = 10.0,
        clock: Clock | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._username = username
        self._password = password
        self._start_tls = start_tls
        self._timeout = timeout
        self._clock = clock or SystemClock()

    @classmethod
    def from_settings(cls, settings: Settings, *, clock: Clock | None = None) -> SmtpEmailSender:
        password = settings.smtp_password
        return cls(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.smtp_from,
            username=settings.smtp_user,
            password=password.get_secret_value() if password is not None else None,
            start_tls=settings.smtp_starttls,
            timeout=settings.smtp_timeout,
            clock=clock,
        )

    def build_message(self, email: OutgoingEmail) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = email.to
        message["Subject"] = email.subject
        message["Date"] = format_datetime(self._clock.now())
        message["Message-ID"] = make_msgid(domain=self._sender_domain())
        message.set_content(email.text)
        message.add_alternative(email.html, subtype="html")
        return message

    async def send(self, email: OutgoingEmail) -> None:
        try:
            await aiosmtplib.send(
                self.build_message(email),
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                start_tls=self._start_tls,
                timeout=self._timeout,
            )
        except aiosmtplib.SMTPException as exc:
            # The recipient address is personal data: log only the failure kind.
            _log.warning("email_delivery_failed", error=type(exc).__name__)
            raise EmailDeliveryError("Could not deliver the e-mail") from exc

    def _sender_domain(self) -> str:
        address = self._sender.rsplit("<", 1)[-1].rstrip(">")
        _, at, domain = address.rpartition("@")
        return domain if at and domain else "knobridge.local"
