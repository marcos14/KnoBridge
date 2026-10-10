"""An in-process SMTP server (aiosmtpd) on 127.0.0.1 with an OS-chosen port, for sender tests.

Runs inside the test's own event loop, so there is no thread, no sleep and no external network.
"""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import Message

from aiosmtpd.smtp import SMTP, AuthResult, Envelope, LoginPassword, Session


@dataclass
class ReceivedMail:
    mail_from: str | None
    rcpt_tos: list[str]
    message: Message


@dataclass
class RecordingHandler:
    """Keeps every accepted message; refuses recipients listed in ``refused``."""

    refused: set[str] = field(default_factory=set[str])
    received: list[ReceivedMail] = field(default_factory=list[ReceivedMail])
    logins: list[str] = field(default_factory=list[str])

    async def handle_RCPT(  # noqa: N802 - name required by aiosmtpd
        self,
        server: SMTP,
        session: Session,
        envelope: Envelope,
        address: str,
        rcpt_options: list[str],
    ) -> str:
        if address in self.refused:
            return "550 mailbox unavailable"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(  # noqa: N802 - name required by aiosmtpd
        self, server: SMTP, session: Session, envelope: Envelope
    ) -> str:
        content = envelope.original_content or b""
        self.received.append(
            ReceivedMail(envelope.mail_from, list(envelope.rcpt_tos), message_from_bytes(content))
        )
        return "250 Message accepted"


@dataclass(frozen=True)
class SmtpServer:
    port: int
    handler: RecordingHandler


Authenticator = Callable[[SMTP, Session, Envelope, str, object], AuthResult]


def _authenticator(credentials: tuple[str, str], handler: RecordingHandler) -> Authenticator:
    def authenticate(
        server: SMTP, session: Session, envelope: Envelope, mechanism: str, auth_data: object
    ) -> AuthResult:
        ok = (
            isinstance(auth_data, LoginPassword)
            and (
                auth_data.login.decode(),
                auth_data.password.decode(),
            )
            == credentials
        )
        if ok:
            handler.logins.append(credentials[0])
        return AuthResult(success=ok)

    return authenticate


@asynccontextmanager
async def smtp_server(
    *, credentials: tuple[str, str] | None = None, refused: set[str] | None = None
) -> AsyncGenerator[SmtpServer]:
    loop = asyncio.get_running_loop()
    handler = RecordingHandler(refused=refused or set())
    authenticator = _authenticator(credentials, handler) if credentials else None

    def factory() -> SMTP:
        with warnings.catch_warnings():
            # AUTH without TLS is fine on a throwaway loopback server; aiosmtpd warns about it.
            warnings.filterwarnings("ignore", "Requiring AUTH while not requiring TLS")
            return SMTP(
                handler,
                loop=loop,
                hostname="localhost",
                authenticator=authenticator,
                auth_required=credentials is not None,
                auth_require_tls=False,
            )

    server = await loop.create_server(factory, "127.0.0.1", 0)
    try:
        port: int = server.sockets[0].getsockname()[1]
        yield SmtpServer(port=port, handler=handler)
    finally:
        server.close()
        await server.wait_closed()
