from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.message import Message

import pytest
from email_support import smtp_server
from pydantic import SecretStr

from fakes.email_sender import FakeEmailSender
from knobridge.core.clock import FrozenClock
from knobridge.core.settings import Settings
from knobridge.email.sender import EmailDeliveryError, EmailSender, OutgoingEmail, SmtpEmailSender

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
EMAIL = OutgoingEmail(
    to="ana@example.com",
    subject="Assunto com acentuação",
    text="Olá, texto simples.\n",
    html="<p>Olá, <strong>HTML</strong>.</p>\n",
)


def _sender(
    port: int,
    *,
    sender: str = "KnoBridge <no-reply@kb.example>",
    username: str | None = None,
    password: str | None = None,
) -> SmtpEmailSender:
    return SmtpEmailSender(
        host="127.0.0.1",
        port=port,
        sender=sender,
        username=username,
        password=password,
        timeout=5.0,
        clock=FrozenClock(NOW),
    )


def _part(message: Message, content_type: str) -> str:
    for part in message.walk():
        if part.get_content_type() == content_type:
            payload = part.get_payload(decode=True)
            assert isinstance(payload, bytes)
            text = payload.decode(part.get_content_charset() or "utf-8")
            return "\n".join(text.splitlines()) + "\n"  # SMTP sends CRLF line ends
    raise AssertionError(f"no {content_type} part")


def test_smtp_sender_sends_message() -> None:
    async def scenario() -> None:
        async with smtp_server() as server:
            await _sender(server.port).send(EMAIL)

            [mail] = server.handler.received
            assert mail.mail_from == "no-reply@kb.example"
            assert mail.rcpt_tos == ["ana@example.com"]
            assert mail.message["Date"] == "Sat, 10 Oct 2026 12:00:00 +0000"
            assert mail.message["Message-ID"].endswith("@kb.example>")
            assert _part(mail.message, "text/plain") == EMAIL.text
            assert _part(mail.message, "text/html") == EMAIL.html

    asyncio.run(scenario())


def test_smtp_sender_logs_in_when_user_is_set() -> None:
    async def scenario() -> None:
        async with smtp_server(credentials=("mailer", "s3cret")) as server:
            await _sender(server.port, username="mailer", password="s3cret").send(EMAIL)  # noqa: S106

            assert server.handler.logins == ["mailer"]
            assert len(server.handler.received) == 1

    asyncio.run(scenario())


def test_smtp_sender_raises_delivery_error_when_server_refuses() -> None:
    async def scenario() -> None:
        async with smtp_server(refused={"ana@example.com"}) as server:
            with pytest.raises(EmailDeliveryError):
                await _sender(server.port).send(EMAIL)

            assert server.handler.received == []

    asyncio.run(scenario())


def test_smtp_sender_message_id_falls_back_when_sender_has_no_domain() -> None:
    message = _sender(25, sender="knobridge").build_message(EMAIL)

    assert message["Message-ID"].endswith("@knobridge.local>")
    assert message["From"] == "knobridge"


def test_smtp_sender_from_settings_uses_smtp_variables() -> None:
    async def scenario() -> None:
        async with smtp_server(credentials=("mailer", "s3cret")) as server:
            settings = Settings(
                smtp_host="127.0.0.1",
                smtp_port=server.port,
                smtp_user="mailer",
                smtp_password=SecretStr("s3cret"),
                smtp_from="Suporte <suporte@example.com>",
                smtp_timeout=5.0,
            )

            await SmtpEmailSender.from_settings(settings, clock=FrozenClock(NOW)).send(EMAIL)

            assert server.handler.logins == ["mailer"]
            [mail] = server.handler.received
            assert mail.mail_from == "suporte@example.com"

    asyncio.run(scenario())


def test_smtp_sender_from_settings_without_credentials_skips_login() -> None:
    async def scenario() -> None:
        async with smtp_server() as server:
            settings = Settings(smtp_host="127.0.0.1", smtp_port=server.port)

            await SmtpEmailSender.from_settings(settings).send(EMAIL)

            assert server.handler.logins == []
            assert len(server.handler.received) == 1

    asyncio.run(scenario())


def test_fake_sender_records_messages() -> None:
    fake = FakeEmailSender()
    sender: EmailSender = fake
    other = OutgoingEmail(to="bruno@example.com", subject="s", text="t", html="h")

    async def scenario() -> None:
        await sender.send(EMAIL)
        await sender.send(other)

    asyncio.run(scenario())

    assert fake.sent == [EMAIL, other]
    assert fake.sent_to("bruno@example.com") == [other]
